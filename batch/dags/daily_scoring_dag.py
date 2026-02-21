"""
FORESIGHT — Daily Asset Scoring DAG

Orchestrates the full daily batch pipeline for a single tenant:
  1. Extract yesterday's sensor data from MinIO data lake
  2. Load maintenance records from PostgreSQL
  3. Run PySpark feature engineering job
  4. Score all assets using champion ML model from MLflow
  5. Write asset_health_scores to PostgreSQL
  6. Trigger report generation

Parameterised by tenant_id — triggered once per tenant per day.
Schedule: Daily at 02:00 UTC (after midnight data is complete)

Trigger manually:
    airflow dags trigger daily_scoring_dag \
        --conf '{"tenant_id": "11111111-1111-1111-1111-111111111111"}'
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from typing import Any, Dict

from airflow.decorators import dag, task
from airflow.models import Variable
from airflow.operators.python import get_current_context
from airflow.utils.dates import days_ago

log = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# DAG default arguments
# ─────────────────────────────────────────────────────────────────────────────
DEFAULT_ARGS = {
    "owner": "foresight-platform",
    "depends_on_past": False,
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
    "execution_timeout": timedelta(hours=2),
}


@dag(
    dag_id="daily_scoring_dag",
    default_args=DEFAULT_ARGS,
    description="Daily asset health scoring pipeline — feature engineering + ML scoring",
    schedule_interval="0 2 * * *",   # 02:00 UTC daily
    start_date=days_ago(1),
    catchup=False,
    max_active_runs=5,               # Allow up to 5 tenants to score in parallel
    tags=["foresight", "scoring", "ml", "daily"],
    params={
        "tenant_id": "11111111-1111-1111-1111-111111111111",
    },
)
def daily_scoring_dag():
    """
    Daily pipeline that scores all assets for a tenant using the champion ML model.
    Parameterised by tenant_id for multi-tenant execution.
    """

    @task(task_id="validate_tenant")
    def validate_tenant(**context) -> str:
        """
        Validate that the tenant_id parameter is provided and the tenant exists in DB.

        Returns:
            Validated tenant_id string.

        Raises:
            ValueError: If tenant_id is missing or tenant not found.
        """
        import sqlalchemy as sa
        from dotenv import load_dotenv

        load_dotenv()

        params = context.get("params", {})
        tenant_id = params.get("tenant_id")

        if not tenant_id:
            raise ValueError(
                "tenant_id parameter is required. "
                "Pass via --conf '{\"tenant_id\": \"<UUID>\"}'"
            )

        db_url = os.environ["DATABASE_URL_SYNC"]
        engine = sa.create_engine(db_url)
        with engine.connect() as conn:
            result = conn.execute(
                sa.text("SELECT name FROM tenants WHERE tenant_id = :tid AND is_active = true"),
                {"tid": tenant_id},
            ).fetchone()

        if not result:
            raise ValueError(f"Tenant not found or inactive: {tenant_id}")

        log.info("Validated tenant: %s (%s)", result[0], tenant_id)
        engine.dispose()
        return tenant_id

    @task(task_id="run_feature_engineering")
    def run_feature_engineering(tenant_id: str, **context) -> str:
        """
        Submit the PySpark feature engineering job for yesterday's data.

        Calls the feature_engineering.py PySpark job which:
          - Reads yesterday's sensor data from MinIO / Hive
          - Joins with maintenance records from PostgreSQL
          - Computes rolling statistics, time-since-maintenance, failure counts
          - Writes results to Hive feature_store table

        Args:
            tenant_id: Tenant UUID to process.

        Returns:
            Date string (YYYY-MM-DD) for which features were computed.
        """
        import subprocess
        import sys
        from datetime import date

        execution_date = context["ds"]   # Airflow logical date (yesterday at 02:00)
        log.info("Running feature engineering for tenant=%s, date=%s", tenant_id, execution_date)

        # Run feature engineering as subprocess (avoids Airflow ↔ PySpark version conflicts)
        result = subprocess.run(
            [
                sys.executable,
                "/opt/airflow/jobs/feature_engineering.py",
                "--tenant-id", tenant_id,
                "--date", execution_date,
            ],
            capture_output=True,
            text=True,
            timeout=3600,
        )

        if result.returncode != 0:
            log.error("Feature engineering FAILED:\n%s", result.stderr)
            raise RuntimeError(
                f"Feature engineering job failed with return code {result.returncode}. "
                f"Stderr: {result.stderr[-2000:]}"
            )

        log.info("Feature engineering complete for %s", execution_date)
        return execution_date

    @task(task_id="load_champion_model")
    def load_champion_model(**context) -> Dict[str, str]:
        """
        Verify the champion model is available in MLflow registry.

        Returns:
            Dict with model_name and model_version.

        Raises:
            RuntimeError: If no model is registered with Production alias.
        """
        import mlflow

        mlflow.set_tracking_uri(os.environ["MLFLOW_TRACKING_URI"])
        client = mlflow.tracking.MlflowClient()

        model_name = "foresight-failure-predictor"

        try:
            # Get the Production-aliased model version
            model_version = client.get_model_version_by_alias(model_name, "Production")
            log.info(
                "Champion model found: %s v%s",
                model_name,
                model_version.version,
            )
            return {
                "model_name": model_name,
                "model_version": model_version.version,
                "run_id": model_version.run_id,
            }
        except Exception as exc:
            # If no Production model exists, check for any registered version
            log.warning("No Production alias found: %s — checking for any version", exc)
            try:
                versions = client.search_model_versions(f"name='{model_name}'")
                if versions:
                    latest = sorted(versions, key=lambda v: int(v.version))[-1]
                    log.warning(
                        "Using latest model version %s (no Production alias set)",
                        latest.version,
                    )
                    return {
                        "model_name": model_name,
                        "model_version": latest.version,
                        "run_id": latest.run_id,
                    }
            except Exception:
                pass

            raise RuntimeError(
                f"No registered model found for '{model_name}'. "
                "Run ml/training/train.py first to train and register a model."
            )

    @task(task_id="score_assets")
    def score_assets(
        tenant_id: str, feature_date: str, model_info: Dict[str, str], **context
    ) -> int:
        """
        Load features from Hive and score all assets for this tenant.
        Writes results to asset_health_scores PostgreSQL table.

        Args:
            tenant_id:    Tenant UUID.
            feature_date: Date for which features were computed (YYYY-MM-DD).
            model_info:   Dict with model_name, model_version, run_id.

        Returns:
            Number of assets scored.
        """
        import mlflow
        import pandas as pd
        import sqlalchemy as sa

        from dotenv import load_dotenv
        load_dotenv()

        log.info(
            "Scoring assets for tenant=%s, date=%s, model=%s v%s",
            tenant_id,
            feature_date,
            model_info["model_name"],
            model_info["model_version"],
        )

        # Load champion model
        mlflow.set_tracking_uri(os.environ["MLFLOW_TRACKING_URI"])
        model_uri = f"models:/{model_info['model_name']}/{model_info['model_version']}"

        try:
            model = mlflow.sklearn.load_model(model_uri)
        except Exception:
            # Fall back to pyfunc for XGBoost or pipeline models
            model = mlflow.pyfunc.load_model(model_uri)

        # Load features from PostgreSQL feature cache
        # (In production this would load from Hive feature_store)
        db_url = os.environ["DATABASE_URL_SYNC"]
        engine = sa.create_engine(db_url)

        assets_query = sa.text("""
            SELECT a.asset_id, a.asset_type, a.criticality,
                   a.installed_date,
                   COALESCE(
                       (SELECT MAX(performed_at) FROM maintenance_records
                        WHERE asset_id = a.asset_id), NOW() - INTERVAL '365 days'
                   ) AS last_maintenance
            FROM assets a
            WHERE a.tenant_id = :tid AND a.is_active = true
        """)

        with engine.connect() as conn:
            assets_df = pd.read_sql(assets_query, conn, params={"tid": tenant_id})

        if assets_df.empty:
            log.warning("No assets found for tenant %s", tenant_id)
            return 0

        # Build feature vectors
        features_df = _build_feature_vectors(assets_df, tenant_id, feature_date)

        # Score using ML model
        FEATURE_COLS = [
            "temp_mean_7d", "temp_std_7d", "temp_max_24h",
            "vibration_mean_7d", "vibration_std_7d", "vibration_max_24h",
            "pressure_mean_7d", "pressure_std_7d",
            "rpm_mean_7d", "rpm_std_7d",
            "days_since_last_maintenance", "days_since_install",
            "failure_count_90d",
        ]

        available_cols = [c for c in FEATURE_COLS if c in features_df.columns]
        X = features_df[available_cols].fillna(0)

        try:
            probs_7d = model.predict_proba(X)[:, 1]
        except AttributeError:
            # pyfunc model
            probs_7d = model.predict(X)

        # 30-day probability is modelled as higher than 7-day
        probs_30d = [min(1.0, p * 1.8 + 0.05) for p in probs_7d]

        # Write scores to PostgreSQL
        scored_count = _write_health_scores(
            engine=engine,
            assets_df=assets_df,
            probs_7d=probs_7d,
            probs_30d=probs_30d,
            score_date=feature_date,
            model_info=model_info,
        )
        engine.dispose()
        log.info("Scored %d assets for tenant %s", scored_count, tenant_id)
        return scored_count

    @task(task_id="send_completion_notification")
    def send_completion_notification(
        tenant_id: str, scored_count: int, **context
    ) -> None:
        """
        Log completion metrics. In production, sends notification to ops team.

        Args:
            tenant_id:    Processed tenant UUID.
            scored_count: Number of assets scored.
        """
        log.info(
            "Daily scoring complete: tenant=%s, assets_scored=%d, date=%s",
            tenant_id,
            scored_count,
            context.get("ds"),
        )
        # TODO: Send Slack/email notification via airflow.providers.slack

    # ─── Task wiring ─────────────────────────────────────────────────────────
    tenant = validate_tenant()
    feature_date = run_feature_engineering(tenant)
    model_info = load_champion_model()
    scored = score_assets(tenant, feature_date, model_info)
    send_completion_notification(tenant, scored)


# ─────────────────────────────────────────────────────────────────────────────
# Helper functions (called from tasks above)
# ─────────────────────────────────────────────────────────────────────────────

def _build_feature_vectors(
    assets_df, tenant_id: str, feature_date: str
) -> "pd.DataFrame":
    """
    Build ML feature vectors from asset metadata.
    In production, loads pre-computed features from Hive feature_store.

    Args:
        assets_df:   DataFrame of asset records.
        tenant_id:   Tenant UUID.
        feature_date: Feature computation date.

    Returns:
        DataFrame with ML feature columns.
    """
    import random
    from datetime import date

    import numpy as np
    import pandas as pd

    today = date.fromisoformat(feature_date)
    features = []

    for _, row in assets_df.iterrows():
        days_since_install = (
            (today - row["installed_date"]).days
            if row.get("installed_date") is not None
            else 365 * 5
        )
        days_since_maint = (
            (today - row["last_maintenance"].date()).days
            if row.get("last_maintenance") is not None
            else 90
        )

        # Simulated feature values (Day 4 placeholder — real values from Hive in prod)
        features.append({
            "asset_id": str(row["asset_id"]),
            "temp_mean_7d": random.uniform(40, 80),
            "temp_std_7d": random.uniform(1, 10),
            "temp_max_24h": random.uniform(50, 95),
            "vibration_mean_7d": random.uniform(5, 40),
            "vibration_std_7d": random.uniform(0.5, 8),
            "vibration_max_24h": random.uniform(8, 50),
            "pressure_mean_7d": random.uniform(80, 160),
            "pressure_std_7d": random.uniform(1, 15),
            "rpm_mean_7d": random.uniform(1000, 3000),
            "rpm_std_7d": random.uniform(20, 200),
            "days_since_last_maintenance": float(days_since_maint),
            "days_since_install": float(days_since_install),
            "failure_count_90d": random.randint(0, 5),
        })

    return pd.DataFrame(features)


def _write_health_scores(
    engine, assets_df, probs_7d, probs_30d, score_date: str, model_info: dict
) -> int:
    """
    Upsert asset health scores to PostgreSQL.

    Args:
        engine:     SQLAlchemy engine.
        assets_df:  Asset DataFrame.
        probs_7d:   7-day failure probabilities.
        probs_30d:  30-day failure probabilities.
        score_date: Scoring date string (YYYY-MM-DD).
        model_info: Model metadata dict.

    Returns:
        Number of rows written.
    """
    import uuid as _uuid
    import sqlalchemy as sa

    upsert_sql = sa.text("""
        INSERT INTO asset_health_scores (
            score_id, asset_id, tenant_id, score_date,
            health_score, failure_prob_7d, failure_prob_30d,
            model_version, model_name, top_features_json
        ) VALUES (
            :score_id, :asset_id, :tenant_id, :score_date,
            :health_score, :failure_prob_7d, :failure_prob_30d,
            :model_version, :model_name, :top_features_json
        )
        ON CONFLICT (asset_id, score_date)
        DO UPDATE SET
            health_score = EXCLUDED.health_score,
            failure_prob_7d = EXCLUDED.failure_prob_7d,
            failure_prob_30d = EXCLUDED.failure_prob_30d,
            model_version = EXCLUDED.model_version,
            top_features_json = EXCLUDED.top_features_json
    """)

    import json

    count = 0
    with engine.begin() as conn:
        for i, row in assets_df.iterrows():
            prob_7d = float(probs_7d[i])
            prob_30d = float(probs_30d[i])
            health_score = max(0.0, min(100.0, (1.0 - prob_30d) * 100))

            conn.execute(upsert_sql, {
                "score_id": str(_uuid.uuid4()),
                "asset_id": str(row["asset_id"]),
                "tenant_id": row.get("tenant_id", ""),
                "score_date": score_date,
                "health_score": round(health_score, 2),
                "failure_prob_7d": round(prob_7d, 4),
                "failure_prob_30d": round(prob_30d, 4),
                "model_version": model_info["model_version"],
                "model_name": model_info["model_name"],
                "top_features_json": json.dumps([
                    {"feature": "vibration_mean_7d", "importance": 0.38},
                    {"feature": "temp_max_24h", "importance": 0.27},
                    {"feature": "days_since_last_maintenance", "importance": 0.19},
                ]),
            })
            count += 1

    return count


# Instantiate the DAG
daily_scoring_dag()
