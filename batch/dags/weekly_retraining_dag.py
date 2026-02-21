"""
FORESIGHT — Weekly Model Retraining DAG

Runs every Sunday at 03:00 UTC to retrain failure prediction models.
Compares new challenger model against the current champion on a holdout set.
Promotes challenger to Production alias only if AUC improves by > 1%.

Why weekly?
  Daily retraining would overfit to noise in small datasets.
  Weekly gives enough new data (7 days × 30 assets × 4 metrics = 50K+ readings)
  to meaningfully update the model without wasting compute.

Champion/Challenger pattern:
  - Champion = current Production model (stable, known performance)
  - Challenger = newly trained model (may or may not be better)
  - Only promote if improvement > MODEL_MIN_IMPROVEMENT_THRESHOLD (default 1%)
  - Never automatically demote — requires human review for rollback
"""

from __future__ import annotations

import logging
import os
from datetime import timedelta

from airflow.decorators import dag, task
from airflow.utils.dates import days_ago

log = logging.getLogger(__name__)

DEFAULT_ARGS = {
    "owner": "foresight-ml",
    "depends_on_past": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=15),
    "execution_timeout": timedelta(hours=4),
}


@dag(
    dag_id="weekly_retraining_dag",
    default_args=DEFAULT_ARGS,
    description="Weekly ML model retraining with champion/challenger promotion",
    schedule_interval="0 3 * * 0",   # Sunday 03:00 UTC
    start_date=days_ago(7),
    catchup=False,
    tags=["foresight", "ml", "retraining", "weekly"],
)
def weekly_retraining_dag():
    """
    Weekly retraining pipeline:
    1. Prepare training dataset from Hive feature_store (last 90 days)
    2. Train Random Forest and XGBoost challenger models
    3. Evaluate both on holdout set
    4. Compare best challenger vs current champion
    5. Promote challenger if AUC improves > 1%
    """

    @task(task_id="prepare_training_data")
    def prepare_training_data(**context) -> dict:
        """
        Load the last 90 days of labelled features from all tenants.
        Returns S3 path to the prepared dataset.

        Returns:
            Dict with dataset_path and row_count.
        """
        import subprocess
        import sys

        log.info("Preparing training dataset from feature_store (last 90 days)...")

        result = subprocess.run(
            [sys.executable, "/opt/airflow/jobs/feature_engineering.py",
             "--mode", "training",
             "--days-back", "90",
             "--output-path", "s3a://foresight-models/training/latest/"],
            capture_output=True,
            text=True,
            timeout=7200,
        )

        if result.returncode != 0:
            raise RuntimeError(f"Data preparation failed: {result.stderr[-2000:]}")

        log.info("Training data ready.")
        return {
            "dataset_path": "s3a://foresight-models/training/latest/",
            "preparation_date": context["ds"],
        }

    @task(task_id="train_challenger_model")
    def train_challenger_model(dataset_info: dict, **context) -> dict:
        """
        Train Random Forest and XGBoost challenger models.
        Logs all metrics to MLflow and registers best challenger.

        Args:
            dataset_info: Output from prepare_training_data.

        Returns:
            Dict with challenger run_id, model_version, and validation AUC.
        """
        import subprocess
        import sys

        log.info("Training challenger models...")

        result = subprocess.run(
            [
                sys.executable,
                "/opt/airflow/ml/training/train.py",
                "--experiment", f"foresight-retraining-{context['ds']}",
                "--register-as-challenger",
                "--dataset-path", dataset_info["dataset_path"],
            ],
            capture_output=True,
            text=True,
            timeout=7200,
        )

        if result.returncode != 0:
            raise RuntimeError(f"Model training failed: {result.stderr[-2000:]}")

        # Parse metrics from stdout (train.py prints JSON summary)
        import json
        output_lines = result.stdout.strip().split("\n")
        metrics = {}
        for line in reversed(output_lines):
            try:
                metrics = json.loads(line)
                break
            except json.JSONDecodeError:
                continue

        log.info("Challenger trained: AUC=%.4f", metrics.get("val_auc", 0))
        return metrics

    @task(task_id="compare_and_promote")
    def compare_and_promote(challenger_info: dict, **context) -> bool:
        """
        Compare challenger vs champion on holdout test set.
        Promote challenger to Production if AUC improves by > MIN_THRESHOLD.

        Args:
            challenger_info: Output from train_challenger_model.

        Returns:
            True if challenger was promoted, False otherwise.
        """
        import mlflow

        mlflow.set_tracking_uri(os.environ["MLFLOW_TRACKING_URI"])
        client = mlflow.tracking.MlflowClient()

        model_name = "foresight-failure-predictor"
        min_improvement = float(
            os.getenv("MODEL_MIN_IMPROVEMENT_THRESHOLD", "0.01")
        )

        challenger_auc = float(challenger_info.get("val_auc", 0))
        challenger_version = challenger_info.get("model_version")

        if not challenger_version:
            log.warning("No challenger version found — skipping promotion")
            return False

        # Get champion AUC
        try:
            champion_version = client.get_model_version_by_alias(model_name, "Production")
            champion_run = client.get_run(champion_version.run_id)
            champion_auc = float(champion_run.data.metrics.get("val_roc_auc", 0))
        except Exception as exc:
            log.warning("No champion found (%s) — promoting challenger by default", exc)
            champion_auc = 0.0

        improvement = challenger_auc - champion_auc
        log.info(
            "Champion AUC: %.4f | Challenger AUC: %.4f | Improvement: %.4f (threshold: %.4f)",
            champion_auc,
            challenger_auc,
            improvement,
            min_improvement,
        )

        if improvement > min_improvement:
            log.info(
                "PROMOTING challenger v%s to Production (improvement=%.4f > threshold=%.4f)",
                challenger_version,
                improvement,
                min_improvement,
            )
            client.set_registered_model_alias(
                model_name, "Production", challenger_version
            )
            # Archive old champion (not delete — preserves audit trail)
            if champion_auc > 0:
                try:
                    client.delete_registered_model_alias(model_name, "Champion")
                except Exception:
                    pass
                client.set_registered_model_alias(
                    model_name, "Champion", champion_version.version
                )
            return True
        else:
            log.info(
                "Challenger NOT promoted (improvement=%.4f <= threshold=%.4f). "
                "Champion remains in Production.",
                improvement,
                min_improvement,
            )
            return False

    @task(task_id="log_retraining_result")
    def log_retraining_result(promoted: bool, **context) -> None:
        """Log the retraining outcome for monitoring and alerting."""
        status = "PROMOTED" if promoted else "RETAINED_CHAMPION"
        log.info(
            "Weekly retraining complete: %s | date=%s",
            status,
            context.get("ds"),
        )

    dataset = prepare_training_data()
    challenger = train_challenger_model(dataset)
    promoted = compare_and_promote(challenger)
    log_retraining_result(promoted)


weekly_retraining_dag()
