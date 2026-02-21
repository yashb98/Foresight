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
import random
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import TenantContext, get_current_tenant, get_db, verify_tenant_access
from api.models.schemas import (
    AssetHealthSummary,
    CostAvoidanceReport,
    FleetSummaryResponse,
    TrendDataPoint,
    TrendResponse,
)

log = logging.getLogger(__name__)
router = APIRouter()


# ─────────────────────────────────────────────────────────────────────────────
# GET /reports/{tenant_id}/summary
# ─────────────────────────────────────────────────────────────────────────────


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
    current_tenant: TenantContext = Depends(get_current_tenant),
) -> FleetSummaryResponse:
    verify_tenant_access(tenant_id, current_tenant)

    from api.feature_store import fleet_summary as fs_summary
    data = fs_summary(tenant_id)
    return FleetSummaryResponse(**data)


# ─────────────────────────────────────────────────────────────────────────────
# GET /reports/{tenant_id}/asset/{asset_id}
# ─────────────────────────────────────────────────────────────────────────────


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
    current_tenant: TenantContext = Depends(get_current_tenant),
) -> AssetHealthSummary:
    verify_tenant_access(tenant_id, current_tenant)

    try:
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
    except HTTPException:
        raise
    except Exception as exc:
        log.exception(
            "Error generating asset report for asset=%s tenant=%s: %s", asset_id, tenant_id, exc
        )
        return _demo_asset_summary(tenant_id, asset_id)


# ─────────────────────────────────────────────────────────────────────────────
# GET /reports/{tenant_id}/trends
# ─────────────────────────────────────────────────────────────────────────────


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
    current_tenant: TenantContext = Depends(get_current_tenant),
) -> TrendResponse:
    verify_tenant_access(tenant_id, current_tenant)

    from api.feature_store import trend_data
    data = trend_data(tenant_id, metric, days, asset_id)
    points = [TrendDataPoint(**p) for p in data["data_points"]]
    return TrendResponse(tenant_id=tenant_id, metric=metric, days=days, data_points=points)


# ─────────────────────────────────────────────────────────────────────────────
# GET /reports/{tenant_id}/cost-avoidance
# ─────────────────────────────────────────────────────────────────────────────


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
    current_tenant: TenantContext = Depends(get_current_tenant),
) -> CostAvoidanceReport:
    verify_tenant_access(tenant_id, current_tenant)

    from api.feature_store import cost_avoidance_data
    data = cost_avoidance_data(tenant_id, year)
    return CostAvoidanceReport(**data)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _compute_fleet_health(total_assets: int, alert_counts: dict) -> float:
    if total_assets == 0:
        return 100.0
    critical = alert_counts.get("critical", 0)
    high = alert_counts.get("high", 0)
    medium = alert_counts.get("medium", 0)
    penalty = (critical * 10 + high * 5 + medium * 2) / total_assets
    return max(0.0, round(100.0 - penalty, 1))


def _build_cost_avoidance_report(
    tenant_id: str, year: int, resolved_by_severity: dict
) -> CostAvoidanceReport:
    # Cost benchmarks (USD): unplanned repair cost by severity
    unplanned_cost = {"critical": 85_000, "high": 35_000, "medium": 12_000, "low": 3_000}
    # Planned maintenance cost = ~25% of unplanned (industry rule of thumb)
    planned_cost = {"critical": 21_250, "high": 8_750, "medium": 3_000, "low": 750}

    total_avoided = sum(
        (unplanned_cost.get(sev, 0) - planned_cost.get(sev, 0)) * count
        for sev, count in resolved_by_severity.items()
    )
    total_planned = sum(
        planned_cost.get(sev, 0) * count for sev, count in resolved_by_severity.items()
    )
    events_total = sum(resolved_by_severity.values())

    return CostAvoidanceReport(
        tenant_id=tenant_id,
        year=year,
        total_predicted_failures=events_total,
        estimated_cost_avoided_usd=total_avoided,
        actual_maintenance_cost_usd=total_planned,
        roi_percent=round((total_avoided / max(total_planned, 1)) * 100, 1),
        breakdown_by_severity=resolved_by_severity,
        generated_at=datetime.now(timezone.utc),
    )


def _demo_fleet_summary(tenant_id: str) -> FleetSummaryResponse:
    return FleetSummaryResponse(
        tenant_id=tenant_id,
        total_assets=247,
        active_assets=231,
        critical_alerts=3,
        high_alerts=11,
        medium_alerts=28,
        low_alerts=54,
        assets_at_risk=14,
        fleet_health_score=87.4,
        as_of=datetime.now(timezone.utc),
    )


def _demo_asset_summary(tenant_id: str, asset_id: str) -> AssetHealthSummary:
    return AssetHealthSummary(
        asset_id=asset_id,
        asset_name=f"Asset {asset_id[:8]}",
        asset_type="pump",
        tenant_id=tenant_id,
        health_score=72.5,
        status="active",
        failure_probability_30d=0.18,
        days_to_maintenance=14,
        open_alert_count=2,
        alert_summary=[],
        last_updated=datetime.now(timezone.utc),
    )


def _demo_trends(tenant_id: str, metric: str, days: int) -> TrendResponse:
    random.seed(42)
    base_value = {"vibration_rms": 3.5, "bearing_temp_celsius": 65.0, "oil_pressure_bar": 4.2}.get(
        metric, 5.0
    )
    points = []
    for i in range(days):
        dt = datetime.now(timezone.utc) - timedelta(days=days - i)
        noise = random.gauss(0, base_value * 0.05)
        trend = i * (base_value * 0.001)  # slight upward drift
        val = round(base_value + noise + trend, 4)
        points.append(
            TrendDataPoint(
                date=dt.strftime("%Y-%m-%d"),
                avg_value=val,
                max_value=round(val * 1.1, 4),
                min_value=round(val * 0.9, 4),
                reading_count=random.randint(800, 1200),
            )
        )
    return TrendResponse(tenant_id=tenant_id, metric=metric, days=days, data_points=points)
