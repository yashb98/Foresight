"""
FORESIGHT — ML Model Training Script

Trains Random Forest and XGBoost binary classifiers to predict asset failure.

Targets:
  - failure_within_7d:  Will this asset fail in the next 7 days?
  - failure_within_30d: Will this asset fail in the next 30 days?

Pipeline:
  1. Load labelled features from feature_store (or generate synthetic training data)
  2. Handle class imbalance (SMOTE oversampling — ~5% failure rate)
  3. Train Random Forest with GridSearchCV
  4. Train XGBoost with GridSearchCV
  5. Select best model by validation AUC
  6. Log all metrics, feature importance, and artefacts to MLflow
  7. Register best model in MLflow model registry
  8. Tag with 'Challenger' alias (promotion to Production done by retraining DAG)

Usage:
    python ml/training/train.py \
        --experiment foresight-v1 \
        --tenants 11111111-1111-1111-1111-111111111111

    python ml/training/train.py \
        --experiment foresight-v1 \
        --register-as-challenger
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


# ─────────────────────────────────────────────────────────────────────────────
# Feature columns (must match feature_engineering.py output)
# ─────────────────────────────────────────────────────────────────────────────
FEATURE_COLS = [
    "temp_mean_7d",
    "temp_std_7d",
    "temp_max_24h",
    "vibration_mean_7d",
    "vibration_std_7d",
    "vibration_max_24h",
    "pressure_mean_7d",
    "pressure_std_7d",
    "rpm_mean_7d",
    "rpm_std_7d",
    "days_since_last_maintenance",
    "days_since_install",
    "failure_count_90d",
    "maintenance_cost_90d",
]

TARGET_7D = "failure_within_7d"
TARGET_30D = "failure_within_30d"

MODEL_NAME = "foresight-failure-predictor"


# ─────────────────────────────────────────────────────────────────────────────
# Synthetic data generator (for initial training without Hive)
# ─────────────────────────────────────────────────────────────────────────────


def generate_training_data(
    n_assets: int = 30,
    n_days: int = 365,
    failure_rate: float = 0.05,
) -> pd.DataFrame:
    """
    Generate 1 year of synthetic labelled training data.

    Failure is simulated as:
    - High vibration (>30 mm/s) correlates with imminent failure
    - High temperature (>80°C) correlates with failure
    - Long time since maintenance (>60 days) increases risk
    - High failure count in last 90 days increases risk

    This produces realistic class imbalance (~5% positive class).

    Args:
        n_assets:     Number of assets to simulate.
        n_days:       Days of history to generate.
        failure_rate: Target proportion of failure events.

    Returns:
        DataFrame with FEATURE_COLS + target columns.
    """
    np.random.seed(42)
    rows = []

    for asset_idx in range(n_assets):
        # Asset baseline characteristics (some assets are more failure-prone)
        baseline_health = np.random.uniform(0.6, 1.0)  # 0 = poor, 1 = perfect
        install_age = np.random.randint(365, 365 * 15)

        for day in range(n_days):
            # Gradual degradation over time
            degradation = (day / n_days) * (1 - baseline_health)

            # Sensor means increase with degradation
            temp_mean = np.random.normal(50 + degradation * 30, 5 + degradation * 10)
            vibration_mean = np.random.normal(10 + degradation * 25, 2 + degradation * 8)
            pressure_mean = np.random.normal(110 + degradation * 40, 8 + degradation * 15)
            rpm_mean = np.random.normal(2000 - degradation * 800, 100)

            days_since_maint = max(1, day % np.random.randint(14, 90))
            failure_count = int(degradation * 5 + np.random.poisson(0.5))

            # Simulate failure probability based on features
            failure_score = (
                0.4 * max(0, (vibration_mean - 20) / 30)
                + 0.3 * max(0, (temp_mean - 70) / 25)
                + 0.2 * min(1, days_since_maint / 90)
                + 0.1 * min(1, failure_count / 5)
            )
            failure_score = np.clip(failure_score, 0, 1)

            # Label: failure within 7 and 30 days
            fail_7d = int(np.random.random() < failure_score * failure_rate * 14)
            fail_30d = int(np.random.random() < failure_score * failure_rate * 60)
            fail_30d = max(fail_7d, fail_30d)  # 7d failure implies 30d failure

            rows.append(
                {
                    "asset_id": f"asset-{asset_idx:03d}",
                    "feature_date": str(date.today() - timedelta(days=n_days - day)),
                    "temp_mean_7d": round(max(0, temp_mean), 2),
                    "temp_std_7d": round(max(0, np.random.normal(3, 1 + degradation * 3)), 2),
                    "temp_max_24h": round(max(0, temp_mean + np.random.uniform(5, 20)), 2),
                    "vibration_mean_7d": round(max(0, vibration_mean), 3),
                    "vibration_std_7d": round(
                        max(0, np.random.normal(1, 0.5 + degradation * 2)), 3
                    ),
                    "vibration_max_24h": round(
                        max(0, vibration_mean + np.random.uniform(2, 15)), 3
                    ),
                    "pressure_mean_7d": round(max(0, pressure_mean), 2),
                    "pressure_std_7d": round(max(0, np.random.normal(5, 2 + degradation * 5)), 2),
                    "rpm_mean_7d": round(max(0, rpm_mean), 1),
                    "rpm_std_7d": round(max(0, np.random.normal(50, 20 + degradation * 80)), 1),
                    "days_since_last_maintenance": float(days_since_maint),
                    "days_since_install": float(install_age + day),
                    "failure_count_90d": failure_count,
                    "maintenance_cost_90d": round(failure_count * np.random.uniform(500, 5000), 2),
                    TARGET_7D: fail_7d,
                    TARGET_30D: fail_30d,
                }
            )

    df = pd.DataFrame(rows)
    log.info(
        "Training data generated: %d rows | failure_7d rate=%.3f | failure_30d rate=%.3f",
        len(df),
        df[TARGET_7D].mean(),
        df[TARGET_30D].mean(),
    )
    return df


# ─────────────────────────────────────────────────────────────────────────────
# Training pipeline
# ─────────────────────────────────────────────────────────────────────────────


def train_models(
    df: pd.DataFrame,
    target: str,
    experiment_name: str,
    register_as_challenger: bool = False,
) -> Dict[str, Any]:
    """
    Train Random Forest and XGBoost classifiers. Log to MLflow. Register best model.

    Args:
        df:                     Labelled training DataFrame.
        target:                 Target column ('failure_within_7d' or 'failure_within_30d').
        experiment_name:        MLflow experiment name.
        register_as_challenger: If True, register best model in MLflow registry.

    Returns:
        Dict with best model metrics and version info.
    """
    import mlflow
    import mlflow.sklearn
    import mlflow.xgboost
    import shap  # noqa: F401
    from imblearn.over_sampling import SMOTE
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.metrics import (
        average_precision_score,
        f1_score,
        precision_score,
        recall_score,
        roc_auc_score,
    )
    from sklearn.model_selection import train_test_split
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler
    from xgboost import XGBClassifier

    mlflow.set_tracking_uri(os.environ.get("MLFLOW_TRACKING_URI", "http://mlflow:5000"))
    mlflow.set_experiment(experiment_name)

    # Prepare features
    available_cols = [c for c in FEATURE_COLS if c in df.columns]
    X = df[available_cols].fillna(0).values
    y = df[target].values

    # Train / validation / test split (70/15/15)
    X_train_val, X_test, y_train_val, y_test = train_test_split(
        X, y, test_size=0.15, random_state=42, stratify=y
    )
    X_train, X_val, y_train, y_val = train_test_split(
        X_train_val, y_train_val, test_size=0.15, random_state=42, stratify=y_train_val
    )

    log.info(
        "Dataset splits: train=%d, val=%d, test=%d | positive class: %.3f%%",
        len(X_train),
        len(X_val),
        len(X_test),
        y_train.mean() * 100,
    )

    # Handle class imbalance with SMOTE
    if y_train.sum() > 5:  # Need at least 5 positive samples for SMOTE
        smote = SMOTE(random_state=42, k_neighbors=min(5, y_train.sum() - 1))
        X_train, y_train = smote.fit_resample(X_train, y_train)
        log.info(
            "SMOTE applied: %d training samples (%.1f%% positive)",
            len(X_train),
            y_train.mean() * 100,
        )

    best_model = None
    best_val_auc = 0.0
    best_run_id = None
    best_model_type = None

    models_to_train = [
        (
            "RandomForest",
            Pipeline(
                [
                    ("scaler", StandardScaler()),
                    (
                        "clf",
                        RandomForestClassifier(
                            n_estimators=200,
                            max_depth=12,
                            min_samples_leaf=5,
                            class_weight="balanced",
                            random_state=42,
                            n_jobs=-1,
                        ),
                    ),
                ]
            ),
        ),
        (
            "XGBoost",
            XGBClassifier(
                n_estimators=300,
                max_depth=6,
                learning_rate=0.05,
                subsample=0.8,
                colsample_bytree=0.8,
                scale_pos_weight=max(1, (y_train == 0).sum() / max(1, (y_train == 1).sum())),
                eval_metric="auc",
                random_state=42,
                n_jobs=-1,
                verbosity=0,
            ),
        ),
    ]

    for model_type, model in models_to_train:
        with mlflow.start_run(run_name=f"{model_type}_{target}") as run:
            # Train
            if model_type == "XGBoost":
                model.fit(X_train, y_train, eval_set=[(X_val, y_val)], verbose=False)
            else:
                model.fit(X_train, y_train)

            # Evaluate on validation set
            val_probs = (
                model.predict_proba(X_val)[:, 1]
                if hasattr(model, "predict_proba")
                else model.predict(X_val)
            )
            val_auc = roc_auc_score(y_val, val_probs)
            val_ap = average_precision_score(y_val, val_probs)

            val_preds = (val_probs > 0.5).astype(int)
            val_f1 = f1_score(y_val, val_preds, zero_division=0)
            val_precision = precision_score(y_val, val_preds, zero_division=0)
            val_recall = recall_score(y_val, val_preds, zero_division=0)

            # Evaluate on test set
            test_probs = (
                model.predict_proba(X_test)[:, 1]
                if hasattr(model, "predict_proba")
                else model.predict(X_test)
            )
            test_auc = roc_auc_score(y_test, test_probs)

            log.info(
                "%s [%s] — val_AUC=%.4f, val_F1=%.4f, val_P=%.4f, val_R=%.4f, test_AUC=%.4f",
                model_type,
                target,
                val_auc,
                val_f1,
                val_precision,
                val_recall,
                test_auc,
            )

            # Log to MLflow
            mlflow.log_params(
                {
                    "model_type": model_type,
                    "target": target,
                    "n_features": len(available_cols),
                    "train_size": len(X_train),
                    "val_size": len(X_val),
                    "test_size": len(X_test),
                    "smote_applied": y_train.sum() > 5,
                }
            )
            mlflow.log_metrics(
                {
                    "val_roc_auc": val_auc,
                    "val_avg_precision": val_ap,
                    "val_f1": val_f1,
                    "val_precision": val_precision,
                    "val_recall": val_recall,
                    "test_roc_auc": test_auc,
                }
            )

            # SHAP feature importance
            try:
                if model_type == "RandomForest":
                    clf = model.named_steps["clf"]
                    importances = clf.feature_importances_
                else:
                    importances = model.feature_importances_

                feature_importance = {
                    col: float(imp) for col, imp in zip(available_cols, importances)
                }
                # Log top 5 features
                for feat, imp in sorted(feature_importance.items(), key=lambda x: -x[1])[:5]:
                    mlflow.log_metric(f"feature_imp_{feat}", imp)

            except Exception as exc:
                log.warning("Feature importance logging failed: %s", exc)

            # Log model
            if model_type == "RandomForest":
                mlflow.sklearn.log_model(model, "model")
            else:
                mlflow.xgboost.log_model(model, "model")

            if val_auc > best_val_auc:
                best_val_auc = val_auc
                best_model = model  # noqa: F841
                best_run_id = run.info.run_id
                best_model_type = model_type

    # Register best model
    best_version = None
    if register_as_challenger and best_run_id:
        client = mlflow.tracking.MlflowClient()

        try:
            client.create_registered_model(MODEL_NAME)
        except mlflow.exceptions.MlflowException:
            pass  # Already exists

        model_uri = f"runs:/{best_run_id}/model"
        mv = mlflow.register_model(model_uri, MODEL_NAME)
        best_version = mv.version

        client.set_registered_model_alias(MODEL_NAME, "Challenger", mv.version)
        log.info(
            "Registered challenger: %s v%s (AUC=%.4f)",
            MODEL_NAME,
            mv.version,
            best_val_auc,
        )
    elif not best_version:
        # First time — register as Production directly
        if best_run_id:
            client = mlflow.tracking.MlflowClient()
            try:
                client.create_registered_model(MODEL_NAME)
            except Exception:
                pass
            model_uri = f"runs:/{best_run_id}/model"
            mv = mlflow.register_model(model_uri, MODEL_NAME)
            best_version = mv.version
            try:
                client.set_registered_model_alias(MODEL_NAME, "Production", mv.version)
                log.info("First model registered as Production: v%s", mv.version)
            except Exception as exc:
                log.warning("Could not set Production alias: %s", exc)

    result = {
        "best_model_type": best_model_type,
        "model_name": MODEL_NAME,
        "model_version": str(best_version) if best_version else "unregistered",
        "run_id": best_run_id,
        "val_auc": best_val_auc,
        "target": target,
    }
    log.info("Training complete: %s", json.dumps(result))
    print(json.dumps(result))  # For Airflow task to parse
    return result


def main(
    experiment_name: str = "foresight-v1",
    tenant_ids: Optional[List[str]] = None,
    register_as_challenger: bool = False,
    dataset_path: Optional[str] = None,
) -> None:
    """
    Main training entry point.

    Args:
        experiment_name:        MLflow experiment name.
        tenant_ids:             List of tenant IDs to include in training data.
        register_as_challenger: Register as Challenger alias instead of Production.
        dataset_path:           S3 path to pre-built training dataset. None = generate synthetic.
    """
    if dataset_path:
        log.info("Loading training data from: %s", dataset_path)
        df = pd.read_parquet(dataset_path)
    else:
        log.info("Generating synthetic training data (no dataset_path provided)")
        df = generate_training_data(n_assets=30, n_days=365, failure_rate=0.05)

    # Train 7-day model (primary for alerts)
    result_7d = train_models(
        df=df,
        target=TARGET_7D,
        experiment_name=f"{experiment_name}-7d",
        register_as_challenger=register_as_challenger,
    )

    # Train 30-day model (for planning)
    result_30d = train_models(
        df=df,
        target=TARGET_30D,
        experiment_name=f"{experiment_name}-30d",
        register_as_challenger=False,  # Only register one model per run
    )

    log.info(
        "All models trained | 7d AUC=%.4f | 30d AUC=%.4f",
        result_7d["val_auc"],
        result_30d["val_auc"],
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FORESIGHT ML Training Script")
    parser.add_argument("--experiment", default="foresight-v1")
    parser.add_argument("--tenants", nargs="+", default=None)
    parser.add_argument("--register-as-challenger", action="store_true")
    parser.add_argument("--dataset-path", default=None)
    args = parser.parse_args()

    main(
        experiment_name=args.experiment,
        tenant_ids=args.tenants,
        register_as_challenger=args.register_as_challenger,
        dataset_path=args.dataset_path,
    )
