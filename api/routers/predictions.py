# =============================================================================
# FORESIGHT API — Predictions Router
# ML inference and health prediction endpoints
# =============================================================================

from typing import List
from uuid import UUID
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException

from api.dependencies import get_current_user
from api.models.schemas import (
    PredictionRequest, PredictionResponse, BatchPredictionRequest,
    BatchPredictionResponse, FleetHealthSummary, RiskLevel
)
from common.logging_config import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/predict", tags=["Predictions"])


# =============================================================================
# Helper Functions
# =============================================================================

async def get_db_conn():
    """Get database connection."""
    import asyncpg
    from common.config import settings
    return await asyncpg.connect(dsn=settings.DATABASE_URL)


def load_model():
    """Load the ML model from MLflow or local storage."""
    import joblib
    import os
    
    model_path = os.environ.get("MODEL_PATH", "/app/ml/models/champion_model.pkl")
    
    try:
        if os.path.exists(model_path):
            return joblib.load(model_path)
    except Exception as e:
        logger.warning(f"Could not load model from {model_path}: {e}")
    
    # Try loading from MLflow
    try:
        import mlflow
        mlflow.set_tracking_uri(os.environ.get("MLFLOW_TRACKING_URI", "http://mlflow:5000"))
        
        # Get latest production model
        client = mlflow.tracking.MlflowClient()
        model_versions = client.get_latest_versions("asset_health_model", stages=["Production"])
        
        if model_versions:
            model_uri = f"models:/{model_versions[0].name}/{model_versions[0].version}"
            return mlflow.pyfunc.load_model(model_uri)
    except Exception as e:
        logger.warning(f"Could not load model from MLflow: {e}")
    
    return None


def compute_health_score(features: dict, model=None) -> dict:
    """
    Compute health score from features.
    If no model available, use rule-based scoring.
    """
    if model:
        try:
            # Use ML model
            import pandas as pd
            X = pd.DataFrame([features])
            prediction = model.predict(X)[0]
            probability = model.predict_proba(X)[0] if hasattr(model, "predict_proba") else [0.5, 0.5]
            
            # Convert prediction to health score (0-100)
            failure_prob = probability[1] if len(probability) > 1 else 0.5
            health_score = int((1 - failure_prob) * 100)
            
            return {
                "health_score": health_score,
                "failure_probability": float(failure_prob),
                "model_used": "ml",
            }
        except Exception as e:
            logger.error(f"ML prediction error: {e}")
    
    # Fallback: Rule-based scoring
    score = 100
    
    # Temperature factors
    temp_avg = features.get("temp_avg_7d", 70)
    if temp_avg > 90:
        score -= 30
    elif temp_avg > 80:
        score -= 15
    
    # Vibration factors
    vib_avg = features.get("vibration_avg_7d", 5)
    if vib_avg > 10:
        score -= 30
    elif vib_avg > 7:
        score -= 15
    
    # Maintenance factors
    days_since = features.get("days_since_maintenance", 0)
    if days_since > 180:
        score -= 20
    elif days_since > 90:
        score -= 10
    
    # Failure history
    maint_count = features.get("maintenance_count_90d", 0)
    if maint_count > 3:
        score -= 20
    elif maint_count > 1:
        score -= 10
    
    score = max(0, min(100, score))
    
    return {
        "health_score": score,
        "failure_probability": (100 - score) / 100,
        "model_used": "rule_based",
    }


def get_risk_level(score: int) -> str:
    """Determine risk level from health score."""
    if score >= 80:
        return RiskLevel.LOW
    elif score >= 60:
        return RiskLevel.MEDIUM
    elif score >= 40:
        return RiskLevel.HIGH
    else:
        return RiskLevel.CRITICAL


def get_recommendation(score: int, risk_level: str) -> str:
    """Generate recommendation based on health score."""
    if score >= 90:
        return "Asset is healthy. Continue routine monitoring."
    elif score >= 80:
        return "Asset showing minor signs of wear. Schedule inspection within 30 days."
    elif score >= 60:
        return "Asset performance degrading. Schedule maintenance within 2 weeks."
    elif score >= 40:
        return "Asset at risk of failure. Schedule immediate maintenance and increase monitoring."
    else:
        return "CRITICAL: High probability of failure. Take asset offline for immediate inspection."


# =============================================================================
# Prediction Endpoints
# =============================================================================

@router.post("/{tenant_id}", response_model=PredictionResponse)
async def predict_single(
    tenant_id: UUID,
    request: PredictionRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Get health prediction for a single asset.
    
    - If features are provided, uses those for prediction
    - Otherwise fetches latest features from feature store
    """
    if current_user["tenant_id"] != tenant_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    conn = await get_db_conn()
    try:
        # Verify asset exists
        asset = await conn.fetchrow(
            "SELECT id, name FROM assets WHERE tenant_id = $1 AND id = $2",
            tenant_id, request.asset_id
        )
        
        if not asset:
            raise HTTPException(status_code=404, detail="Asset not found")
        
        # Get features
        features = request.features
        if features is None:
            # Fetch from feature store
            feature_row = await conn.fetchrow(
                """
                SELECT * FROM feature_store 
                WHERE tenant_id = $1 AND asset_id = $2
                ORDER BY feature_date DESC
                LIMIT 1
                """,
                tenant_id, request.asset_id
            )
            
            if not feature_row:
                raise HTTPException(status_code=404, detail="No features found for this asset")
            
            features = {
                "temp_avg_7d": float(feature_row["temp_avg_7d"] or 70),
                "temp_max_7d": float(feature_row["temp_max_7d"] or 80),
                "temp_std_7d": float(feature_row["temp_std_7d"] or 5),
                "vibration_avg_7d": float(feature_row["vibration_avg_7d"] or 5),
                "vibration_max_7d": float(feature_row["vibration_max_7d"] or 8),
                "vibration_std_7d": float(feature_row["vibration_std_7d"] or 2),
                "days_since_maintenance": feature_row["days_since_maintenance"] or 30,
                "maintenance_count_90d": feature_row["maintenance_count_90d"] or 0,
            }
        
        # Load model
        model = load_model()
        
        # Compute prediction
        result = compute_health_score(features, model)
        health_score = result["health_score"]
        failure_prob = result["failure_probability"]
        risk_level = get_risk_level(health_score)
        recommendation = get_recommendation(health_score, risk_level)
        
        # Store prediction in database
        model_version = "rule_based_v1" if result["model_used"] == "rule_based" else "ml_champion_v1"
        
        await conn.execute(
            """
            INSERT INTO health_scores (
                tenant_id, asset_id, score, predicted_failure_probability,
                risk_level, model_version, features_used, recommendation
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            """,
            tenant_id, request.asset_id, health_score, failure_prob,
            risk_level, model_version, features, recommendation
        )
        
        return PredictionResponse(
            asset_id=request.asset_id,
            health_score=health_score,
            failure_probability=failure_prob,
            risk_level=risk_level,
            confidence=0.85 if result["model_used"] == "ml" else 0.65,
            recommendation=recommendation,
            model_version=model_version,
            feature_contributions=[
                {"feature": k, "importance": 0.1} for k in features.keys()
            ],
            computed_at=datetime.utcnow()
        )
    
    finally:
        await conn.close()


@router.post("/{tenant_id}/batch", response_model=BatchPredictionResponse)
async def predict_batch(
    tenant_id: UUID,
    request: BatchPredictionRequest,
    current_user: dict = Depends(get_current_user)
):
    """Get health predictions for multiple assets."""
    if current_user["tenant_id"] != tenant_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    conn = await get_db_conn()
    try:
        predictions = []
        failed_assets = []
        
        # Load model once for batch
        model = load_model()
        
        for asset_id in request.asset_ids:
            try:
                # Verify asset exists
                asset = await conn.fetchrow(
                    "SELECT id FROM assets WHERE tenant_id = $1 AND id = $2",
                    tenant_id, asset_id
                )
                
                if not asset:
                    failed_assets.append({"asset_id": str(asset_id), "error": "Asset not found"})
                    continue
                
                # Fetch features
                feature_row = await conn.fetchrow(
                    """
                    SELECT * FROM feature_store 
                    WHERE tenant_id = $1 AND asset_id = $2
                    ORDER BY feature_date DESC
                    LIMIT 1
                    """,
                    tenant_id, asset_id
                )
                
                if not feature_row:
                    failed_assets.append({"asset_id": str(asset_id), "error": "No features found"})
                    continue
                
                features = {
                    "temp_avg_7d": float(feature_row["temp_avg_7d"] or 70),
                    "temp_max_7d": float(feature_row["temp_max_7d"] or 80),
                    "vibration_avg_7d": float(feature_row["vibration_avg_7d"] or 5),
                    "vibration_max_7d": float(feature_row["vibration_max_7d"] or 8),
                    "days_since_maintenance": feature_row["days_since_maintenance"] or 30,
                    "maintenance_count_90d": feature_row["maintenance_count_90d"] or 0,
                }
                
                # Compute prediction
                result = compute_health_score(features, model)
                health_score = result["health_score"]
                risk_level = get_risk_level(health_score)
                
                model_version = "rule_based_v1" if result["model_used"] == "rule_based" else "ml_champion_v1"
                
                # Store prediction
                await conn.execute(
                    """
                    INSERT INTO health_scores (
                        tenant_id, asset_id, score, predicted_failure_probability,
                        risk_level, model_version, features_used, recommendation
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                    """,
                    tenant_id, asset_id, health_score, result["failure_probability"],
                    risk_level, model_version, features, get_recommendation(health_score, risk_level)
                )
                
                predictions.append(PredictionResponse(
                    asset_id=asset_id,
                    health_score=health_score,
                    failure_probability=result["failure_probability"],
                    risk_level=risk_level,
                    confidence=0.85 if result["model_used"] == "ml" else 0.65,
                    recommendation=get_recommendation(health_score, risk_level),
                    model_version=model_version,
                    computed_at=datetime.utcnow()
                ))
                
            except Exception as e:
                logger.error(f"Error predicting for asset {asset_id}: {e}")
                failed_assets.append({"asset_id": str(asset_id), "error": str(e)})
        
        return BatchPredictionResponse(
            predictions=predictions,
            failed_assets=failed_assets
        )
    
    finally:
        await conn.close()


@router.get("/{tenant_id}/fleet-health", response_model=FleetHealthSummary)
async def get_fleet_health_summary(
    tenant_id: UUID,
    current_user: dict = Depends(get_current_user)
):
    """Get fleet-wide health summary."""
    if current_user["tenant_id"] != tenant_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    conn = await get_db_conn()
    try:
        # Get latest health score per asset
        rows = await conn.fetch(
            """
            SELECT DISTINCT ON (asset_id)
                h.*, a.name as asset_name, a.asset_type
            FROM health_scores h
            JOIN assets a ON h.asset_id = a.id
            WHERE h.tenant_id = $1
            ORDER BY asset_id, h.computed_at DESC
            """,
            tenant_id
        )
        
        if not rows:
            return FleetHealthSummary(
                total_assets=0,
                healthy_count=0,
                at_risk_count=0,
                critical_count=0,
                average_score=0.0,
                assets_needing_attention=[]
            )
        
        total = len(rows)
        healthy = sum(1 for r in rows if float(r["score"]) >= 80)
        at_risk = sum(1 for r in rows if 50 <= float(r["score"]) < 80)
        critical = sum(1 for r in rows if float(r["score"]) < 50)
        avg_score = sum(float(r["score"]) for r in rows) / total
        
        # Assets needing attention (score < 60)
        need_attention = [
            HealthScoreResponse(**dict(r)) for r in rows 
            if float(r["score"]) < 60
        ]
        need_attention.sort(key=lambda x: x.score)
        
        return FleetHealthSummary(
            total_assets=total,
            healthy_count=healthy,
            at_risk_count=at_risk,
            critical_count=critical,
            average_score=round(avg_score, 2),
            assets_needing_attention=need_attention[:10]  # Top 10
        )
    
    finally:
        await conn.close()
