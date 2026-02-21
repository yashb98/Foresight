"""FORESIGHT — /assets router."""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db
from api.models.schemas import (
    AssetDetailResponse,
    AssetListResponse,
    AssetResponse,
    HealthScoreSummary,
    PredictionHistoryEntry,
)

log = logging.getLogger(__name__)
router = APIRouter()


def _risk_level(prob_30d: Optional[float]) -> Optional[str]:
    """Derive a risk level label from 30-day failure probability."""
    if prob_30d is None:
        return None
    if prob_30d > 0.70:
        return "critical"
    if prob_30d > 0.40:
        return "high"
    if prob_30d > 0.15:
        return "medium"
    return "low"


@router.get(
    "/{tenant_id}",
    response_model=AssetListResponse,
    summary="List all assets with current health scores",
)
async def list_assets(
    tenant_id: str,
    asset_type: Optional[str] = Query(None, description="Filter by asset type"),
    criticality: Optional[str] = Query(None, description="Filter by criticality level"),
    risk_level: Optional[str] = Query(
        None, description="Filter by risk level: low|medium|high|critical"
    ),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> AssetListResponse:
    """
    Return all active assets for a tenant with their latest health scores.

    Args:
        tenant_id:      Tenant UUID.
        asset_type:     Optional filter (pump, turbine, etc.)
        criticality:    Optional filter (low, medium, high, critical)
        risk_level:     Optional filter based on failure_prob_30d
        page:           Page number (1-based)
        page_size:      Results per page (max 200)
        db:             Database session.

    Returns:
        AssetListResponse with list of assets and their current health scores.
    """
    from api.feature_store import asset_list
    data = asset_list(
        tenant_id,
        page=page,
        page_size=page_size,
        asset_type_filter=asset_type,
        risk_filter=risk_level,
    )

    assets = []
    for a in data["assets"]:
        ch = a.get("current_health")
        assets.append(
            AssetResponse(
                asset_id=a["asset_id"],
                tenant_id=a["tenant_id"],
                name=a["name"],
                asset_type=a["asset_type"],
                location=a["location"],
                criticality=a["criticality"],
                installed_date=a.get("installed_date"),
                source_system=a.get("source_system"),
                is_active=a.get("is_active", True),
                current_health=(
                    HealthScoreSummary(
                        health_score=ch["health_score"],
                        failure_prob_7d=ch["failure_prob_7d"],
                        failure_prob_30d=ch["failure_prob_30d"],
                        score_date=ch["score_date"],
                        risk_level=ch["risk_level"],
                    )
                    if ch else None
                ),
            )
        )

    return AssetListResponse(tenant_id=tenant_id, total=data["total"], assets=assets)


@router.get(
    "/{tenant_id}/{asset_id}",
    response_model=AssetDetailResponse,
    summary="Get single asset detail with 30-day prediction history",
)
async def get_asset_detail(
    tenant_id: str,
    asset_id: str,
    db: AsyncSession = Depends(get_db),
) -> AssetDetailResponse:
    """
    Return full detail for a single asset including 30-day prediction history.

    Args:
        tenant_id:      Tenant UUID.
        asset_id:       Asset UUID.
        db:             Database session.

    Returns:
        AssetDetailResponse with full prediction history.

    Raises:
        HTTPException 404: Asset not found.
    """
    # Fetch asset
    asset_result = await db.execute(
        text("""
            SELECT asset_id, tenant_id, name, asset_type, location,
                   criticality, installed_date, source_system, is_active
            FROM assets
            WHERE asset_id = :asset_id AND tenant_id = :tenant_id AND is_active = true
        """),
        {"asset_id": asset_id, "tenant_id": tenant_id},
    )
    asset_row = asset_result.fetchone()
    if not asset_row:
        raise HTTPException(status_code=404, detail=f"Asset {asset_id} not found")

    # Fetch 30-day prediction history
    hist_result = await db.execute(
        text("""
            SELECT score_date, health_score, failure_prob_7d, failure_prob_30d, model_version
            FROM asset_health_scores
            WHERE asset_id = :asset_id AND tenant_id = :tenant_id
            ORDER BY score_date DESC
            LIMIT 30
        """),
        {"asset_id": asset_id, "tenant_id": tenant_id},
    )
    history = [
        PredictionHistoryEntry(
            score_date=row[0],
            health_score=float(row[1]),
            failure_prob_7d=float(row[2]),
            failure_prob_30d=float(row[3]),
            model_version=row[4],
        )
        for row in hist_result.fetchall()
    ]

    # Latest health score
    latest = history[0] if history else None
    prob_30d = latest.failure_prob_30d if latest else None

    # Maintenance summary
    maint_result = await db.execute(
        text("""
            SELECT MAX(performed_at), SUM(cost)
            FROM maintenance_records
            WHERE asset_id = :asset_id AND tenant_id = :tenant_id
              AND performed_at >= NOW() - INTERVAL '90 days'
        """),
        {"asset_id": asset_id, "tenant_id": tenant_id},
    )
    maint_row = maint_result.fetchone()

    # Active alerts count
    alert_result = await db.execute(
        text("""
            SELECT COUNT(*) FROM alerts
            WHERE asset_id = :asset_id AND tenant_id = :tenant_id AND status = 'active'
        """),
        {"asset_id": asset_id, "tenant_id": tenant_id},
    )
    alert_count = alert_result.scalar() or 0

    return AssetDetailResponse(
        asset_id=str(asset_row[0]),
        tenant_id=str(asset_row[1]),
        name=asset_row[2],
        asset_type=asset_row[3],
        location=asset_row[4],
        criticality=asset_row[5],
        installed_date=asset_row[6],
        source_system=asset_row[7],
        is_active=asset_row[8],
        current_health=(
            HealthScoreSummary(
                health_score=latest.health_score if latest else None,
                failure_prob_7d=latest.failure_prob_7d if latest else None,
                failure_prob_30d=prob_30d,
                score_date=latest.score_date if latest else None,
                risk_level=_risk_level(prob_30d),
            )
            if latest
            else None
        ),
        prediction_history=history,
        recent_alerts_count=int(alert_count),
        last_maintenance_date=maint_row[0] if maint_row else None,
        total_maintenance_cost_90d=float(maint_row[1]) if maint_row and maint_row[1] else None,
    )
