# =============================================================================
# FORESIGHT API — Alerts Router
# Alert management and alert rules endpoints
# =============================================================================

from typing import List, Optional
from uuid import UUID
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query

from api.dependencies import get_current_user, get_pagination, PaginationParams
from api.models.schemas import (
    AlertCreate, AlertResponse, AlertUpdate, AlertListResponse, AlertStats,
    AlertAcknowledgeRequest, AlertResolveRequest,
    AlertRuleCreate, AlertRuleResponse, AlertRuleUpdate
)
from common.logging_config import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/alerts", tags=["Alerts"])


# =============================================================================
# Helper Functions
# =============================================================================

async def get_db_conn():
    """Get database connection."""
    import asyncpg
    from common.config import settings
    return await asyncpg.connect(dsn=settings.DATABASE_URL)


# =============================================================================
# Alert Endpoints
# =============================================================================

@router.get("/{tenant_id}", response_model=AlertListResponse)
async def list_alerts(
    tenant_id: UUID,
    status: Optional[str] = None,
    severity: Optional[str] = None,
    alert_type: Optional[str] = None,
    asset_id: Optional[UUID] = None,
    days: int = 7,
    pagination: PaginationParams = Depends(get_pagination),
    current_user: dict = Depends(get_current_user)
):
    """List alerts with filtering and pagination."""
    if current_user["tenant_id"] != tenant_id:
        raise HTTPException(status_code=403, detail="Access denied for this tenant")
    
    conn = await get_db_conn()
    try:
        where_clauses = ["a.tenant_id = $1", "a.created_at >= $2"]
        params = [tenant_id, datetime.utcnow() - timedelta(days=days)]
        param_idx = 3
        
        if status:
            where_clauses.append(f"a.status = ${param_idx}")
            params.append(status)
            param_idx += 1
        
        if severity:
            where_clauses.append(f"a.severity = ${param_idx}")
            params.append(severity)
            param_idx += 1
        
        if alert_type:
            where_clauses.append(f"a.alert_type = ${param_idx}")
            params.append(alert_type)
            param_idx += 1
        
        if asset_id:
            where_clauses.append(f"a.asset_id = ${param_idx}")
            params.append(asset_id)
            param_idx += 1
        
        where_sql = " AND ".join(where_clauses)
        
        # Get total count
        count_query = f"""
            SELECT COUNT(*) FROM alerts a WHERE {where_sql}
        """
        total = await conn.fetchval(count_query, *params)
        
        # Get summary stats
        stats = await conn.fetchrow(
            f"""
            SELECT 
                COUNT(*) FILTER (WHERE status = 'open') as open_count,
                COUNT(*) FILTER (WHERE severity = 'critical') as critical_count,
                COUNT(*) FILTER (WHERE severity = 'warning') as warning_count
            FROM alerts a
            WHERE {where_sql}
            """,
            *params
        )
        
        # Get paginated results
        sort_direction = "DESC" if pagination.sort_order == "desc" else "ASC"
        query = f"""
            SELECT a.*, 
                   ast.name as asset_name,
                   s.name as sensor_name,
                   u.full_name as acknowledged_by_name
            FROM alerts a
            LEFT JOIN assets ast ON a.asset_id = ast.id
            LEFT JOIN sensors s ON a.sensor_id = s.id
            LEFT JOIN users u ON a.acknowledged_by = u.id
            WHERE {where_sql}
            ORDER BY a.created_at {sort_direction}
            LIMIT ${param_idx} OFFSET ${param_idx + 1}
        """
        params.extend([pagination.page_size, pagination.offset])
        
        rows = await conn.fetch(query, *params)
        
        return AlertListResponse(
            total=total,
            items=[AlertResponse(**dict(row)) for row in rows],
            page=pagination.page,
            page_size=pagination.page_size,
            open_count=stats["open_count"],
            critical_count=stats["critical_count"],
            warning_count=stats["warning_count"]
        )
    
    finally:
        await conn.close()


@router.get("/{tenant_id}/stats", response_model=AlertStats)
async def get_alert_stats(
    tenant_id: UUID,
    days: int = 30,
    current_user: dict = Depends(get_current_user)
):
    """Get alert statistics."""
    if current_user["tenant_id"] != tenant_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    conn = await get_db_conn()
    try:
        stats = await conn.fetchrow(
            """
            SELECT 
                COUNT(*) as total_alerts,
                COUNT(*) FILTER (WHERE status = 'open') as open_alerts,
                COUNT(*) FILTER (WHERE status = 'acknowledged') as acknowledged_alerts,
                COUNT(*) FILTER (WHERE status = 'resolved') as resolved_alerts,
                COUNT(*) FILTER (WHERE severity = 'critical') as critical_count,
                COUNT(*) FILTER (WHERE severity = 'warning') as warning_count,
                COUNT(*) FILTER (WHERE severity = 'info') as info_count,
                AVG(EXTRACT(EPOCH FROM (resolved_at - created_at))/3600) 
                    FILTER (WHERE status = 'resolved') as avg_resolution_hours
            FROM alerts
            WHERE tenant_id = $1 AND created_at >= $2
            """,
            tenant_id, datetime.utcnow() - timedelta(days=days)
        )
        
        return AlertStats(
            total_alerts=stats["total_alerts"],
            open_alerts=stats["open_alerts"],
            acknowledged_alerts=stats["acknowledged_alerts"],
            resolved_alerts=stats["resolved_alerts"],
            critical_count=stats["critical_count"],
            warning_count=stats["warning_count"],
            info_count=stats["info_count"],
            avg_resolution_hours=float(stats["avg_resolution_hours"]) if stats["avg_resolution_hours"] else None
        )
    
    finally:
        await conn.close()


@router.get("/{tenant_id}/{alert_id}", response_model=AlertResponse)
async def get_alert(
    tenant_id: UUID,
    alert_id: UUID,
    current_user: dict = Depends(get_current_user)
):
    """Get a single alert by ID."""
    if current_user["tenant_id"] != tenant_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    conn = await get_db_conn()
    try:
        alert = await conn.fetchrow(
            """
            SELECT a.*, 
                   ast.name as asset_name,
                   s.name as sensor_name,
                   u.full_name as acknowledged_by_name
            FROM alerts a
            LEFT JOIN assets ast ON a.asset_id = ast.id
            LEFT JOIN sensors s ON a.sensor_id = s.id
            LEFT JOIN users u ON a.acknowledged_by = u.id
            WHERE a.tenant_id = $1 AND a.id = $2
            """,
            tenant_id, alert_id
        )
        
        if not alert:
            raise HTTPException(status_code=404, detail="Alert not found")
        
        return AlertResponse(**dict(alert))
    
    finally:
        await conn.close()


@router.patch("/{tenant_id}/{alert_id}/acknowledge", response_model=AlertResponse)
async def acknowledge_alert(
    tenant_id: UUID,
    alert_id: UUID,
    req: AlertAcknowledgeRequest,
    current_user: dict = Depends(get_current_user)
):
    """Acknowledge an alert."""
    if current_user["tenant_id"] != tenant_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    conn = await get_db_conn()
    try:
        # Verify alert exists and is open
        alert = await conn.fetchrow(
            "SELECT id, status FROM alerts WHERE tenant_id = $1 AND id = $2",
            tenant_id, alert_id
        )
        
        if not alert:
            raise HTTPException(status_code=404, detail="Alert not found")
        
        if alert["status"] != "open":
            raise HTTPException(status_code=400, detail="Alert is not open")
        
        await conn.execute(
            """
            UPDATE alerts 
            SET status = 'acknowledged', 
                acknowledged_at = NOW(), 
                acknowledged_by = $1,
                metadata = metadata || $2
            WHERE id = $3
            """,
            current_user["user_id"], 
            {"acknowledgment_notes": req.notes} if req.notes else {},
            alert_id
        )
        
        # Return updated alert
        updated = await conn.fetchrow(
            """
            SELECT a.*, 
                   ast.name as asset_name,
                   s.name as sensor_name,
                   u.full_name as acknowledged_by_name
            FROM alerts a
            LEFT JOIN assets ast ON a.asset_id = ast.id
            LEFT JOIN sensors s ON a.sensor_id = s.id
            LEFT JOIN users u ON a.acknowledged_by = u.id
            WHERE a.id = $1
            """,
            alert_id
        )
        
        logger.info(f"Alert {alert_id} acknowledged by {current_user['email']}")
        return AlertResponse(**dict(updated))
    
    finally:
        await conn.close()


@router.patch("/{tenant_id}/{alert_id}/resolve", response_model=AlertResponse)
async def resolve_alert(
    tenant_id: UUID,
    alert_id: UUID,
    req: AlertResolveRequest,
    current_user: dict = Depends(get_current_user)
):
    """Resolve an alert."""
    if current_user["tenant_id"] != tenant_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    conn = await get_db_conn()
    try:
        # Verify alert exists
        alert = await conn.fetchrow(
            "SELECT id, status FROM alerts WHERE tenant_id = $1 AND id = $2",
            tenant_id, alert_id
        )
        
        if not alert:
            raise HTTPException(status_code=404, detail="Alert not found")
        
        if alert["status"] == "resolved":
            raise HTTPException(status_code=400, detail="Alert is already resolved")
        
        await conn.execute(
            """
            UPDATE alerts 
            SET status = 'resolved', 
                resolved_at = NOW(), 
                resolved_by = $1,
                resolution_notes = $2
            WHERE id = $3
            """,
            current_user["user_id"], req.resolution_notes, alert_id
        )
        
        # Return updated alert
        updated = await conn.fetchrow(
            """
            SELECT a.*, 
                   ast.name as asset_name,
                   s.name as sensor_name,
                   u.full_name as acknowledged_by_name
            FROM alerts a
            LEFT JOIN assets ast ON a.asset_id = ast.id
            LEFT JOIN sensors s ON a.sensor_id = s.id
            LEFT JOIN users u ON a.acknowledged_by = u.id
            WHERE a.id = $1
            """,
            alert_id
        )
        
        logger.info(f"Alert {alert_id} resolved by {current_user['email']}")
        return AlertResponse(**dict(updated))
    
    finally:
        await conn.close()


# =============================================================================
# Alert Rules Endpoints
# =============================================================================

@router.get("/{tenant_id}/rules", response_model=List[AlertRuleResponse])
async def list_alert_rules(
    tenant_id: UUID,
    active_only: bool = True,
    current_user: dict = Depends(get_current_user)
):
    """List alert rules."""
    if current_user["tenant_id"] != tenant_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    conn = await get_db_conn()
    try:
        query = "SELECT * FROM alert_rules WHERE tenant_id = $1"
        params = [tenant_id]
        
        if active_only:
            query += " AND is_active = true"
        
        query += " ORDER BY created_at DESC"
        
        rules = await conn.fetch(query, *params)
        return [AlertRuleResponse(**dict(r)) for r in rules]
    
    finally:
        await conn.close()


@router.post("/{tenant_id}/rules", response_model=AlertRuleResponse, status_code=201)
async def create_alert_rule(
    tenant_id: UUID,
    rule_data: AlertRuleCreate,
    current_user: dict = Depends(get_current_user)
):
    """Create a new alert rule."""
    if current_user["tenant_id"] != tenant_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    conn = await get_db_conn()
    try:
        # Validate asset_id if provided
        if rule_data.asset_id:
            asset = await conn.fetchrow(
                "SELECT id FROM assets WHERE tenant_id = $1 AND id = $2",
                tenant_id, rule_data.asset_id
            )
            if not asset:
                raise HTTPException(status_code=404, detail="Asset not found")
        
        rule_id = await conn.fetchval(
            """
            INSERT INTO alert_rules (
                tenant_id, name, description, asset_id, sensor_type, metric,
                operator, threshold_value, threshold_value_high, duration_seconds,
                severity, auto_create_work_order, notification_channels, cooldown_minutes, created_by
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15)
            RETURNING id
            """,
            tenant_id, rule_data.name, rule_data.description, rule_data.asset_id,
            rule_data.sensor_type, rule_data.metric, rule_data.operator,
            rule_data.threshold_value, rule_data.threshold_value_high, rule_data.duration_seconds,
            rule_data.severity.value, rule_data.auto_create_work_order,
            rule_data.notification_channels, rule_data.cooldown_minutes,
            current_user["user_id"]
        )
        
        rule = await conn.fetchrow("SELECT * FROM alert_rules WHERE id = $1", rule_id)
        
        logger.info(f"Alert rule '{rule_data.name}' created by {current_user['email']}")
        return AlertRuleResponse(**dict(rule))
    
    finally:
        await conn.close()


@router.patch("/{tenant_id}/rules/{rule_id}", response_model=AlertRuleResponse)
async def update_alert_rule(
    tenant_id: UUID,
    rule_id: UUID,
    rule_data: AlertRuleUpdate,
    current_user: dict = Depends(get_current_user)
):
    """Update an alert rule."""
    if current_user["tenant_id"] != tenant_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    conn = await get_db_conn()
    try:
        # Verify rule exists
        existing = await conn.fetchrow(
            "SELECT id FROM alert_rules WHERE tenant_id = $1 AND id = $2",
            tenant_id, rule_id
        )
        if not existing:
            raise HTTPException(status_code=404, detail="Alert rule not found")
        
        # Build update query
        updates = []
        params = []
        param_idx = 1
        
        fields = {
            'name': rule_data.name,
            'description': rule_data.description,
            'asset_id': rule_data.asset_id,
            'sensor_type': rule_data.sensor_type,
            'metric': rule_data.metric,
            'operator': rule_data.operator,
            'threshold_value': rule_data.threshold_value,
            'threshold_value_high': rule_data.threshold_value_high,
            'duration_seconds': rule_data.duration_seconds,
            'severity': rule_data.severity.value if rule_data.severity else None,
            'is_active': rule_data.is_active,
            'auto_create_work_order': rule_data.auto_create_work_order,
            'notification_channels': rule_data.notification_channels,
            'cooldown_minutes': rule_data.cooldown_minutes,
        }
        
        for field, value in fields.items():
            if value is not None:
                updates.append(f"{field} = ${param_idx}")
                params.append(value)
                param_idx += 1
        
        if not updates:
            raise HTTPException(status_code=400, detail="No fields to update")
        
        updates.append("updated_at = NOW()")
        params.extend([tenant_id, rule_id])
        
        await conn.execute(
            f"UPDATE alert_rules SET {', '.join(updates)} WHERE tenant_id = ${param_idx} AND id = ${param_idx + 1}",
            *params
        )
        
        rule = await conn.fetchrow("SELECT * FROM alert_rules WHERE id = $1", rule_id)
        return AlertRuleResponse(**dict(rule))
    
    finally:
        await conn.close()


@router.delete("/{tenant_id}/rules/{rule_id}", status_code=204)
async def delete_alert_rule(
    tenant_id: UUID,
    rule_id: UUID,
    current_user: dict = Depends(get_current_user)
):
    """Delete an alert rule."""
    if current_user["tenant_id"] != tenant_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    conn = await get_db_conn()
    try:
        result = await conn.execute(
            "DELETE FROM alert_rules WHERE tenant_id = $1 AND id = $2",
            tenant_id, rule_id
        )
        
        if result == "DELETE 0":
            raise HTTPException(status_code=404, detail="Alert rule not found")
        
        logger.info(f"Alert rule {rule_id} deleted by {current_user['email']}")
    
    finally:
        await conn.close()
