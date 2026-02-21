"""
FORESIGHT — ML Prediction Service

Loads the champion model from MLflow registry and returns failure predictions
for individual assets. Called by the FastAPI /predict endpoint.

Design:
  - Model is loaded once at startup and cached in memory
  - Cache is invalidated when MLflow registry version changes (checked every 5 min)
  - Returns PredictionResult with probabilities, health score, and top features via SHAP
  - Graceful fallback: if model unavailable, returns rule-based heuristic score
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone
from threading import Lock
from typing import Any, Dict, List, Optional

from common.models import PredictionResult

log = logging.getLogger(__name__)

MODEL_NAME = "foresight-failure-predictor"
CACHE_TTL_SECONDS = 300  # Refresh model version check every 5 minutes

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


class ModelPredictor:
    """
    Singleton predictor that holds the champion ML model in memory.

    Thread-safe via a lock around model loading.
    Auto-refreshes when MLflow registry version changes.

    Args:
        mlflow_uri:    MLflow tracking server URI.
        model_name:    Registered model name in MLflow.
        cache_ttl:     Seconds between version checks.
    """

    def __init__(
        self,
        mlflow_uri: Optional[str] = None,
        model_name: str = MODEL_NAME,
        cache_ttl: int = CACHE_TTL_SECONDS,
    ) -> None:
        self._mlflow_uri = mlflow_uri or os.getenv("MLFLOW_TRACKING_URI", "http://mlflow:5000")
        self._model_name = model_name
        self._cache_ttl = cache_ttl
        self._model = None
        self._model_version: Optional[str] = None
        self._last_check: float = 0.0
        self._lock = Lock()

        # Try to load at construction time
        self._refresh_model()

    def _get_production_version(self) -> Optional[str]:
        """
        Query MLflow for the current Production model version.

        Returns:
            Version string, or None if unavailable.
        """
        try:
            import mlflow

            mlflow.set_tracking_uri(self._mlflow_uri)
            client = mlflow.tracking.MlflowClient()
            mv = client.get_model_version_by_alias(self._model_name, "Production")
            return mv.version
        except Exception as exc:
            log.warning("Cannot query MLflow production version: %s", exc)
            return None

    def _refresh_model(self) -> None:
        """Load (or reload) the champion model from MLflow registry."""
        try:
            import mlflow

            mlflow.set_tracking_uri(self._mlflow_uri)
            production_version = self._get_production_version()

            if production_version is None:
                log.warning(
                    "No Production model found in MLflow registry '%s'. "
                    "Run ml/training/train.py first.",
                    self._model_name,
                )
                return

            if production_version == self._model_version:
                return  # No change — keep cached model

            log.info(
                "Loading model: %s v%s from MLflow",
                self._model_name,
                production_version,
            )
            model_uri = f"models:/{self._model_name}/{production_version}"

            try:
                model = mlflow.sklearn.load_model(model_uri)
            except Exception:
                model = mlflow.pyfunc.load_model(model_uri)

            with self._lock:
                self._model = model
                self._model_version = production_version
                self._last_check = time.monotonic()

            log.info("Model loaded: %s v%s", self._model_name, production_version)

        except Exception as exc:
            log.error("Model refresh failed: %s", exc)

    def _maybe_refresh(self) -> None:
        """Check if model version cache has expired and refresh if needed."""
        if time.monotonic() - self._last_check > self._cache_ttl:
            self._refresh_model()

    def predict(
        self,
        asset_id: str,
        tenant_id: str,
        features: Dict[str, float],
    ) -> PredictionResult:
        """
        Generate failure probability prediction for a single asset.

        Args:
            asset_id:  Asset UUID.
            tenant_id: Tenant UUID.
            features:  Dict mapping feature name → value. Missing features set to 0.

        Returns:
            PredictionResult with probabilities, health score, and top features.
        """
        self._maybe_refresh()

        if self._model is None:
            log.warning("No model loaded — returning heuristic fallback prediction")
            return self._heuristic_prediction(asset_id, tenant_id, features)

        import numpy as np

        # Build feature vector
        X = np.array([[features.get(col, 0.0) for col in FEATURE_COLS]])

        with self._lock:
            model = self._model
            model_version = self._model_version

        # Get probability
        try:
            if hasattr(model, "predict_proba"):
                prob_7d = float(model.predict_proba(X)[0, 1])
            else:
                prob_7d = float(model.predict(X)[0])
        except Exception as exc:
            log.error("Model prediction failed: %s — using heuristic", exc)
            return self._heuristic_prediction(asset_id, tenant_id, features)

        prob_7d = max(0.0, min(1.0, prob_7d))
        prob_30d = max(prob_7d, min(1.0, prob_7d * 1.8 + 0.05))
        health_score = max(0.0, min(100.0, (1.0 - prob_30d) * 100))

        # SHAP top features
        top_features = self._compute_top_features(model, X, features)

        # Bootstrap confidence interval (simple ±3% for now — Day 6 adds proper CI)
        ci_margin = max(0.03, prob_7d * 0.1)

        return PredictionResult(
            asset_id=asset_id,
            tenant_id=tenant_id,
            predicted_at=datetime.now(tz=timezone.utc),
            failure_prob_7d=round(prob_7d, 4),
            failure_prob_30d=round(prob_30d, 4),
            health_score=round(health_score, 2),
            confidence_lower=max(0.0, round(prob_7d - ci_margin, 4)),
            confidence_upper=min(1.0, round(prob_7d + ci_margin, 4)),
            top_3_features=top_features[:3],
            model_version=str(model_version),
        )

    def _compute_top_features(
        self,
        model: Any,
        X: "np.ndarray",  # noqa: F821
        features: Dict[str, float],
    ) -> List[Dict[str, Any]]:
        """
        Compute feature importance for this prediction using SHAP or model importances.

        Args:
            model:    Trained model.
            X:        Feature array (1 × n_features).
            features: Original feature dict.

        Returns:
            List of {feature, importance, value} dicts sorted by importance.
        """
        try:
            import shap

            if hasattr(model, "named_steps"):
                clf = model.named_steps.get("clf", model)
            else:
                clf = model

            explainer = shap.TreeExplainer(clf)
            shap_values = explainer.shap_values(X)

            if isinstance(shap_values, list):
                # Binary classifier returns [class0, class1]
                importance_array = abs(shap_values[1][0])
            else:
                importance_array = abs(shap_values[0])

            return [
                {
                    "feature": FEATURE_COLS[i],
                    "importance": round(float(importance_array[i]), 4),
                    "value": round(float(features.get(FEATURE_COLS[i], 0)), 4),
                }
                for i in sorted(
                    range(len(FEATURE_COLS)),
                    key=lambda x: -importance_array[x],
                )
            ]
        except Exception as exc:
            log.debug("SHAP computation failed (%s) — using model importance", exc)

        # Fallback: use model-level feature importances
        try:
            if hasattr(model, "named_steps"):
                clf = model.named_steps.get("clf", model)
                importances = clf.feature_importances_
            elif hasattr(model, "feature_importances_"):
                importances = model.feature_importances_
            else:
                importances = [1.0 / len(FEATURE_COLS)] * len(FEATURE_COLS)

            return [
                {
                    "feature": FEATURE_COLS[i],
                    "importance": round(float(importances[i]), 4),
                    "value": round(float(features.get(FEATURE_COLS[i], 0)), 4),
                }
                for i in sorted(range(len(FEATURE_COLS)), key=lambda x: -importances[x])
            ]
        except Exception:
            return [
                {"feature": col, "importance": 0.0, "value": round(float(features.get(col, 0)), 4)}
                for col in FEATURE_COLS[:3]
            ]

    def _heuristic_prediction(
        self,
        asset_id: str,
        tenant_id: str,
        features: Dict[str, float],
    ) -> PredictionResult:
        """
        Rule-based fallback prediction when the ML model is unavailable.
        Uses simple threshold rules to estimate failure probability.

        Args:
            asset_id:  Asset UUID.
            tenant_id: Tenant UUID.
            features:  Feature dictionary.

        Returns:
            PredictionResult with heuristic estimates.
        """
        vib = features.get("vibration_mean_7d", 0)
        temp = features.get("temp_mean_7d", 0)
        days_maint = features.get("days_since_last_maintenance", 30)
        fail_count = features.get("failure_count_90d", 0)

        score = (
            0.4 * max(0, (vib - 15) / 35)
            + 0.3 * max(0, (temp - 60) / 30)
            + 0.2 * min(1, days_maint / 90)
            + 0.1 * min(1, fail_count / 5)
        )
        prob_7d = min(0.95, max(0.01, score))
        prob_30d = min(0.98, prob_7d * 1.5)
        health = max(5, (1 - prob_30d) * 100)

        return PredictionResult(
            asset_id=asset_id,
            tenant_id=tenant_id,
            predicted_at=datetime.now(tz=timezone.utc),
            failure_prob_7d=round(prob_7d, 4),
            failure_prob_30d=round(prob_30d, 4),
            health_score=round(health, 2),
            confidence_lower=max(0, round(prob_7d - 0.1, 4)),
            confidence_upper=min(1, round(prob_7d + 0.1, 4)),
            top_3_features=[
                {"feature": "vibration_mean_7d", "importance": 0.40, "value": round(vib, 3)},
                {"feature": "temp_mean_7d", "importance": 0.30, "value": round(temp, 2)},
                {"feature": "days_since_last_maintenance", "importance": 0.20, "value": days_maint},
            ],
            model_version="heuristic-fallback",
        )

    @property
    def is_ready(self) -> bool:
        """True if a model is loaded and ready to serve predictions."""
        return self._model is not None

    @property
    def model_version(self) -> Optional[str]:
        """Return the currently loaded model version string."""
        return self._model_version


# Module-level singleton — imported by FastAPI app
_predictor: Optional[ModelPredictor] = None


def get_predictor() -> ModelPredictor:
    """
    Return the module-level ModelPredictor singleton.
    Creates it on first call (lazy initialisation).

    Returns:
        ModelPredictor instance.
    """
    global _predictor
    if _predictor is None:
        _predictor = ModelPredictor()
    return _predictor
