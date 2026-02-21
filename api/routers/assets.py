"""FORESIGHT — /assets router."""
from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import TenantContext, get_current_tenant, get_db, verify_tenant_access
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
    risk_level: Optional[str] = Query(None, description="Filter by risk level: low|medium|high|critical"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    current_tenant: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
) -> AssetListResponse:
    """
    Return all active assets for a tenant with their latest health scores.

    Args:
        tenant_id:      Must match authenticated token's tenant_id.
        asset_type:     Optional filter (pump, turbine, etc.)
        criticality:    Optional filter (low, medium, high, critical)
        risk_level:     Optional filter based on failure_prob_30d
        page:           Page number (1-based)
        page_size:      Results per page (max 200)
        current_tenant: Injected JWT tenant context.
        db:             Database session.

    Returns:
        AssetListResponse with list of assets and their current health scores.
    """
    verify_tenant_access(tenant_id, current_tenant)

    offset = (page - 1) * page_size

    # Build dynamic WHERE clauses
    conditions = ["a.tenant_id = :tenant_id", "a.is_active = true"]
    params: dict = {"tenant_id": tenant_id, "limit": page_size, "offset": offset}

    if asset_type:
        conditions.append("a.asset_type = :asset_type")
        params["asset_type"] = asset_type

    if criticality:
        conditions.append("a.criticality = :criticality")
        params["criticality"] = criticality

    where_clause = " AND ".join(conditions)

    rows = await db.execute(
        text(f"""
            SELECT
                a.asset_id, a.tenant_id, a.name, a.asset_type,
                a.location, a.criticality, a.installed_date, a.source_system,
                a.is_active,
                hs.health_score, hs.failure_prob_7d, hs.failure_prob_30d, hs.score_date
            FROM assets a
            LEFT JOIN LATERAL (
                SELECT health_score, failure_prob_7d, failure_prob_30d, score_date
                FROM asset_health_scores
                WHERE asset_id = a.asset_id
                ORDER BY score_date DESC
                LIMIT 1
            ) hs ON true
            WHERE {where_clause}
            ORDER BY hs.failure_prob_30d DESC NULLS LAST, a.criticality DESC
            LIMIT :limit OFFSET :offset
        """),
        params,
    )
    asset_rows = rows.fetchall()

    count_result = await db.execute(
        text(f"SELECT COUNT(*) FROM assets a WHERE {where_clause}"),
        {k: v for k, v in params.items() if k not in ("limit", "offset")},
    )
    total = count_result.scalar() or 0

    assets = []
    for row in asset_rows:
        prob_30d = float(row[11]) if row[11] is not None else None
        rl = _risk_level(prob_30d)

        # Apply risk_level filter in Python (avoids complex SQL for computed field)
        if risk_level and rl != risk_level:
            continue

        assets.append(
            AssetResponse(
                asset_id=str(row[0]),
                tenant_id=str(row[1]),
                name=row[2],
                asset_type=row[3],
                location=row[4],
                criticality=row[5],
                installed_date=row[6],
                source_system=row[7],
                is_active=row[8],
                current_health=HealthScoreSummary(
                    health_score=float(row[9]) if row[9] is not None else None,
                    failure_prob_7d=float(row[10]) if row[10] is not None else None,
                    failure_prob_30d=prob_30d,
                    score_date=row[12],
                    risk_level=rl,
                ) if row[9] is not None else None,
            )
        )

    return AssetListResponse(tenant_id=tenant_id, total=int(total), assets=assets)


@router.get(
    "/{tenant_id}/{asset_id}",
    response_model=AssetDetailResponse,
    summary="Get single asset detail with 30-day prediction history",
)
async def get_asset_detail(
    tenant_id: str,
    asset_id: str,
    current_tenant: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
) -> AssetDetailResponse:
    """
    Return full detail for a single asset including 30-day prediction history.

    Args:
        tenant_id:      Tenant UUID (must match token).
        asset_id:       Asset UUID.
        current_tenant: Injected JWT context.
        db:             Database session.

    Returns:
        AssetDetailResponse with full prediction history.

    Raises:
        HTTPException 403: Cross-tenant access attempt.
        HTTPException 404: Asset not found.
    """
    verify_tenant_access(tenant_id, current_tenant)

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
        current_health=HealthScoreSummary(
            health_score=latest.health_score if latest else None,
            failure_prob_7d=latest.failure_prob_7d if latest else None,
            failure_prob_30d=prob_30d,
            score_date=latest.score_date if latest else None,
            risk_level=_risk_level(prob_30d),
        ) if latest else None,
        prediction_history=history,
        recent_alerts_count=int(alert_count),
        last_maintenance_date=maint_row[0] if maint_row else None,
        total_maintenance_cost_90d=float(maint_row[1]) if maint_row and maint_row[1] else None,
    )
