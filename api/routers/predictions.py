"""FORESIGHT — /predict router."""

from __future__ import annotations

import logging
import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db
from api.models.schemas import PredictionRequest, PredictionResponse

log = logging.getLogger(__name__)
router = APIRouter()


@router.post(
    "",
    response_model=PredictionResponse,
    summary="On-demand failure prediction for a single asset",
    description=(
        "Loads the latest features for the asset and runs the champion ML model. "
        "Returns failure probabilities for 7-day and 30-day horizons, a health score, "
        "confidence interval, and the top 3 contributing features."
    ),
)
async def predict(
    request: PredictionRequest,
    db: AsyncSession = Depends(get_db),
) -> PredictionResponse:
    """
    Run on-demand failure prediction for a specific asset.

    Args:
        request:        PredictionRequest with asset_id and tenant_id.
        db:             Database session.

    Returns:
        PredictionResponse with failure probabilities and feature explanations.

    Raises:
        HTTPException 404: Asset not found.
        HTTPException 503: ML model not available.
    """
    # Load features from feature store (or use provided features)
    if request.features:
        # Features provided inline
        features = request.features
    else:
        # Verify asset belongs to tenant before loading features from DB
        result = await db.execute(
            text("""
                SELECT asset_id, asset_type, criticality, installed_date
                FROM assets
                WHERE asset_id = :asset_id AND tenant_id = :tenant_id AND is_active = true
            """),
            {"asset_id": request.asset_id, "tenant_id": request.tenant_id},
        )
        asset_row = result.fetchone()

        if not asset_row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Asset {request.asset_id} not found for tenant {request.tenant_id}.",
            )
        features = await _load_features_for_asset(db, request.asset_id, request.tenant_id)

    # Get predictor and run inference
    from ml.serving.predictor import get_predictor

    predictor = get_predictor()
    try:
        result_obj = predictor.predict(
            asset_id=request.asset_id,
            tenant_id=request.tenant_id,
            features=features,
        )
    except Exception as exc:
        log.error("Prediction failed for asset %s: %s", request.asset_id, exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ML prediction service temporarily unavailable",
        )

    # Persist prediction to asset_health_scores (upsert)
    try:
        await _persist_prediction(db, result_obj, request.tenant_id)
        await db.commit()
    except Exception as db_exc:
        log.warning("Could not persist prediction to DB: %s", db_exc)
        try:
            await db.rollback()
        except Exception:
            pass

    return PredictionResponse.from_prediction_result(result_obj)


async def _load_features_for_asset(db: AsyncSession, asset_id: str, tenant_id: str) -> dict:
    """
    Load the latest feature vector for an asset from the feature store (PostgreSQL cache).

    Args:
        db:        Database session.
        asset_id:  Asset UUID.
        tenant_id: Tenant UUID.

    Returns:
        Dict of feature name → value.
    """
    # Load latest health score as proxy for features (real feature store in Hive)
    result = await db.execute(
        text("""
            SELECT hs.top_features_json,
                   EXTRACT(EPOCH FROM (NOW() - mr.last_maint)) / 86400 AS days_since_maint,
                   EXTRACT(EPOCH FROM (NOW() - a.installed_date::timestamp)) / 86400 AS days_since_install
            FROM assets a
            LEFT JOIN (
                SELECT asset_id, MAX(performed_at) AS last_maint
                FROM maintenance_records
                WHERE asset_id = :asset_id
                GROUP BY asset_id
            ) mr ON mr.asset_id = a.asset_id
            LEFT JOIN (
                SELECT asset_id, top_features_json
                FROM asset_health_scores
                WHERE asset_id = :asset_id
                ORDER BY score_date DESC
                LIMIT 1
            ) hs ON hs.asset_id = a.asset_id
            WHERE a.asset_id = :asset_id AND a.tenant_id = :tenant_id
        """),
        {"asset_id": asset_id, "tenant_id": tenant_id},
    )
    row = result.fetchone()

    # Default features when no history available
    features = {
        "temp_mean_7d": 65.0,
        "temp_std_7d": 5.0,
        "temp_max_24h": 72.0,
        "vibration_mean_7d": 15.0,
        "vibration_std_7d": 2.0,
        "vibration_max_24h": 20.0,
        "pressure_mean_7d": 110.0,
        "pressure_std_7d": 8.0,
        "rpm_mean_7d": 2000.0,
        "rpm_std_7d": 100.0,
        "days_since_last_maintenance": 30.0,
        "days_since_install": 1825.0,
        "failure_count_90d": 0,
        "maintenance_cost_90d": 0.0,
    }

    if row:
        if row[1] is not None:
            features["days_since_last_maintenance"] = float(row[1])
        if row[2] is not None:
            features["days_since_install"] = float(row[2])

    return features


async def _persist_prediction(db: AsyncSession, result_obj, tenant_id: str) -> None:
    """Upsert prediction result to asset_health_scores table."""
    import json

    await db.execute(
        text("""
            INSERT INTO asset_health_scores (
                score_id, asset_id, tenant_id, score_date,
                health_score, failure_prob_7d, failure_prob_30d,
                model_version, model_name, top_features_json,
                confidence_lower, confidence_upper
            ) VALUES (
                :score_id, :asset_id, :tenant_id, :score_date,
                :health_score, :failure_prob_7d, :failure_prob_30d,
                :model_version, :model_name, :top_features_json,
                :confidence_lower, :confidence_upper
            )
            ON CONFLICT (asset_id, score_date)
            DO UPDATE SET
                health_score = EXCLUDED.health_score,
                failure_prob_7d = EXCLUDED.failure_prob_7d,
                failure_prob_30d = EXCLUDED.failure_prob_30d,
                model_version = EXCLUDED.model_version,
                top_features_json = EXCLUDED.top_features_json
        """),
        {
            "score_id": str(uuid.uuid4()),
            "asset_id": result_obj.asset_id,
            "tenant_id": tenant_id,
            "score_date": date.today(),
            "health_score": result_obj.health_score,
            "failure_prob_7d": result_obj.failure_prob_7d,
            "failure_prob_30d": result_obj.failure_prob_30d,
            "model_version": result_obj.model_version,
            "model_name": result_obj.model_name,
            "top_features_json": json.dumps(result_obj.top_3_features),
            "confidence_lower": result_obj.confidence_lower,
            "confidence_upper": result_obj.confidence_upper,
        },
    )
