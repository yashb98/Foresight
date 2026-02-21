"""FORESIGHT — /alerts router."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import TenantContext, get_current_tenant, get_db, verify_tenant_access
from api.models.schemas import AlertListResponse, AlertResponse, AlertUpdateRequest

log = logging.getLogger(__name__)
router = APIRouter()


@router.get(
    "/{tenant_id}",
    response_model=AlertListResponse,
    summary="List active alerts for a tenant",
)
async def list_alerts(
    tenant_id: str,
    severity: Optional[str] = Query(None, description="Filter by severity: low|medium|high|critical"),
    alert_status: Optional[str] = Query(None, alias="status", description="Filter by status: active|acknowledged|resolved"),
    limit: int = Query(100, ge=1, le=500),
    current_tenant: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
) -> AlertListResponse:
    """
    Return alerts for a tenant, sorted by severity and time (newest first).
    Active alerts are returned by default.

    Args:
        tenant_id:    Must match JWT token tenant.
        severity:     Optional severity filter.
        alert_status: Optional status filter (default: active).
        limit:        Maximum number of alerts to return.
        current_tenant: Injected JWT context.
        db:           Database session.
    """
    verify_tenant_access(tenant_id, current_tenant)

    conditions = ["tenant_id = :tenant_id"]
    params: dict = {"tenant_id": tenant_id, "limit": limit}

    filter_status = alert_status or "active"
    if filter_status != "all":
        conditions.append("status = :status")
        params["status"] = filter_status

    if severity:
        conditions.append("severity = :severity")
        params["severity"] = severity

    where = " AND ".join(conditions)

    result = await db.execute(
        text(f"""
            SELECT alert_id, asset_id, tenant_id, rule_id, alert_type,
                   metric_name, actual_value, threshold_value, severity,
                   status, triggered_at, acknowledged_at, resolved_at,
                   acknowledged_by, notes
            FROM alerts
            WHERE {where}
            ORDER BY
                CASE severity WHEN 'critical' THEN 1 WHEN 'high' THEN 2
                              WHEN 'medium' THEN 3 ELSE 4 END,
                triggered_at DESC
            LIMIT :limit
        """),
        params,
    )
    rows = result.fetchall()

    count_result = await db.execute(
        text(f"SELECT COUNT(*) FROM alerts WHERE {where}"),
        {k: v for k, v in params.items() if k != "limit"},
    )
    total = count_result.scalar() or 0

    alerts = [
        AlertResponse(
            alert_id=str(row[0]), asset_id=str(row[1]), tenant_id=str(row[2]),
            rule_id=str(row[3]) if row[3] else None, alert_type=row[4],
            metric_name=row[5], actual_value=float(row[6]) if row[6] else None,
            threshold_value=float(row[7]) if row[7] else None,
            severity=row[8], status=row[9], triggered_at=row[10],
            acknowledged_at=row[11], resolved_at=row[12],
            acknowledged_by=row[13], notes=row[14],
        )
        for row in rows
    ]
    return AlertListResponse(tenant_id=tenant_id, total=int(total), alerts=alerts)


@router.patch(
    "/{tenant_id}/{alert_id}",
    response_model=AlertResponse,
    summary="Acknowledge or resolve an alert",
)
async def update_alert(
    tenant_id: str,
    alert_id: str,
    update: AlertUpdateRequest,
    current_tenant: TenantContext = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
) -> AlertResponse:
    """
    Update an alert's status to acknowledged or resolved.

    Args:
        tenant_id:      Tenant UUID (must match token).
        alert_id:       Alert UUID to update.
        update:         New status and optional notes.
        current_tenant: Injected JWT context.
        db:             Database session.
    """
    verify_tenant_access(tenant_id, current_tenant)
    now = datetime.now(tz=timezone.utc)

    extra_cols = ""
    extra_params: dict = {}

    if update.status == "acknowledged":
        extra_cols = ", acknowledged_at = :now, acknowledged_by = :by"
        extra_params = {"now": now, "by": current_tenant.client_id}
    elif update.status == "resolved":
        extra_cols = ", resolved_at = :now, acknowledged_by = :by"
        extra_params = {"now": now, "by": current_tenant.client_id}

    await db.execute(
        text(f"""
            UPDATE alerts
            SET status = :status, notes = :notes {extra_cols}
            WHERE alert_id = :alert_id AND tenant_id = :tenant_id
        """),
        {
            "status": update.status,
            "notes": update.notes,
            "alert_id": alert_id,
            "tenant_id": tenant_id,
            **extra_params,
        },
    )
    await db.commit()

    result = await db.execute(
        text("SELECT * FROM alerts WHERE alert_id = :alert_id AND tenant_id = :tenant_id"),
        {"alert_id": alert_id, "tenant_id": tenant_id},
    )
    row = result.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")

    return AlertResponse(
        alert_id=str(row[0]), asset_id=str(row[1]), tenant_id=str(row[2]),
        rule_id=str(row[3]) if row[3] else None, alert_type=row[4],
        metric_name=row[5], actual_value=float(row[6]) if row[6] else None,
        threshold_value=float(row[7]) if row[7] else None,
        severity=row[8], status=row[9], triggered_at=row[10],
        acknowledged_at=row[11], resolved_at=row[12],
        acknowledged_by=row[13], notes=row[14],
    )
