"""
FORESIGHT — /reports router

Generates scheduled and on-demand maintenance & reliability reports for a tenant.

Endpoints
---------
GET /reports/{tenant_id}/summary          — fleet-level health summary (KPIs)
GET /reports/{tenant_id}/asset/{asset_id} — full asset maintenance report
GET /reports/{tenant_id}/trends           — fleet-level sensor trend data (time-series)
GET /reports/{tenant_id}/cost-avoidance   — estimated maintenance cost savings
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db
from api.models.schemas import (
    AssetHealthSummary,
    CostAvoidanceReport,
    FleetSummaryResponse,
    TrendDataPoint,
    TrendResponse,
)

log = logging.getLogger(__name__)
router = APIRouter()


@router.get(
    "/{tenant_id}/summary",
    response_model=FleetSummaryResponse,
    summary="Fleet health summary KPIs",
    description=(
        "Returns high-level KPIs for the tenant's full asset fleet: "
        "asset counts by health band, active alert counts by severity, "
        "and mean time between predicted failures (MTBF estimate)."
    ),
)
async def fleet_summary(
    tenant_id: str,
    db: AsyncSession = Depends(get_db),
) -> FleetSummaryResponse:
    from api.feature_store import fleet_summary as fs_summary
    data = fs_summary(tenant_id)
    return FleetSummaryResponse(**data)


@router.get(
    "/{tenant_id}/asset/{asset_id}",
    response_model=AssetHealthSummary,
    summary="Asset maintenance report",
    description=(
        "Returns a full maintenance report for a single asset: "
        "health score, recent alerts, predicted failure probability, "
        "and recommended maintenance actions."
    ),
)
async def asset_report(
    tenant_id: str,
    asset_id: str,
    db: AsyncSession = Depends(get_db),
) -> AssetHealthSummary:
    from infrastructure.db.base import Asset, Alert

    asset_q = await db.execute(
        select(Asset).where(Asset.tenant_id == tenant_id).where(Asset.id == asset_id)
    )
    asset = asset_q.scalar_one_or_none()
    if not asset:
        raise HTTPException(status_code=404, detail=f"Asset {asset_id} not found.")

    alert_q = await db.execute(
        select(Alert)
        .where(Alert.tenant_id == tenant_id)
        .where(Alert.asset_id == asset_id)
        .where(Alert.created_at >= datetime.now(timezone.utc) - timedelta(days=30))
        .order_by(Alert.created_at.desc())
    )
    recent_alerts = alert_q.scalars().all()

    return AssetHealthSummary(
        asset_id=str(asset.id),
        asset_name=asset.name,
        asset_type=asset.asset_type,
        tenant_id=tenant_id,
        health_score=asset.health_score or 0.0,
        status=asset.status,
        failure_probability_30d=asset.failure_probability or 0.0,
        days_to_maintenance=asset.days_to_maintenance,
        open_alert_count=sum(1 for a in recent_alerts if a.status == "open"),
        alert_summary=[
            {
                "id": str(a.id),
                "severity": a.severity,
                "message": a.message,
                "created_at": a.created_at.isoformat(),
            }
            for a in recent_alerts[:5]
        ],
        last_updated=datetime.now(timezone.utc),
    )


@router.get(
    "/{tenant_id}/trends",
    response_model=TrendResponse,
    summary="Fleet-level sensor trend data",
    description=(
        "Returns aggregated time-series data for a given sensor metric "
        "across the fleet or for a specific asset. "
        "Useful for charting historical trends on the dashboard."
    ),
)
async def fleet_trends(
    tenant_id: str,
    metric: str = Query("vibration_rms", description="Sensor metric to aggregate"),
    asset_id: Optional[str] = Query(None, description="Filter to a single asset"),
    days: int = Query(30, ge=1, le=365, description="Number of historical days"),
    db: AsyncSession = Depends(get_db),
) -> TrendResponse:
    from api.feature_store import trend_data
    data = trend_data(tenant_id, metric, days, asset_id)
    points = [TrendDataPoint(**p) for p in data["data_points"]]
    return TrendResponse(tenant_id=tenant_id, metric=metric, days=days, data_points=points)


@router.get(
    "/{tenant_id}/cost-avoidance",
    response_model=CostAvoidanceReport,
    summary="Estimated maintenance cost avoidance",
    description=(
        "Calculates the estimated cost savings achieved by predicting failures "
        "before they become unplanned breakdowns. "
        "Based on industry benchmarks: unplanned maintenance costs 3–5× planned maintenance."
    ),
)
async def cost_avoidance(
    tenant_id: str,
    year: int = Query(datetime.now().year, description="Reporting year"),
    db: AsyncSession = Depends(get_db),
) -> CostAvoidanceReport:
    from api.feature_store import cost_avoidance_data
    data = cost_avoidance_data(tenant_id, year)
    return CostAvoidanceReport(**data)
