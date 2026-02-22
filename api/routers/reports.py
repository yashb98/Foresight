# =============================================================================
# FORESIGHT API — Reports Router
# Reporting and analytics endpoints
# =============================================================================

from typing import List, Optional
from uuid import UUID
from datetime import datetime, timedelta, date

from fastapi import APIRouter, Depends, HTTPException, Query

from api.dependencies import get_current_user
from api.models.schemas import (
    ReportSummary, ReportFilters, AssetTrend, CostAvoidanceReport,
    DashboardSummary, AssetResponse, AlertResponse
)
from common.logging_config import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/reports", tags=["Reports"])


# =============================================================================
# Helper Functions
# =============================================================================

async def get_db_conn():
    """Get database connection."""
    import asyncpg
    from common.config import settings
    return await asyncpg.connect(dsn=settings.DATABASE_URL)


# =============================================================================
# Report Endpoints
# =============================================================================

@router.get("/{tenant_id}/summary", response_model=ReportSummary)
async def get_summary_report(
    tenant_id: UUID,
    current_user: dict = Depends(get_current_user)
):
    """Get high-level summary report for the tenant."""
    if current_user["tenant_id"] != tenant_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    conn = await get_db_conn()
    try:
        # Asset stats
        asset_stats = await conn.fetchrow(
            """
            SELECT 
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE status = 'operational') as operational,
                COUNT(*) FILTER (WHERE status = 'maintenance') as in_maintenance
            FROM assets
            WHERE tenant_id = $1
            """,
            tenant_id
        )
        
        # Sensor count
        sensor_count = await conn.fetchval(
            "SELECT COUNT(*) FROM sensors WHERE tenant_id = $1 AND is_active = true",
            tenant_id
        )
        
        # Alert stats
        alert_stats = await conn.fetchrow(
            """
            SELECT 
                COUNT(*) FILTER (WHERE status = 'open') as active,
                COUNT(*) FILTER (WHERE status = 'open' AND severity = 'critical') as critical
            FROM alerts
            WHERE tenant_id = $1
            """,
            tenant_id
        )
        
        # Average health score
        avg_health = await conn.fetchval(
            """
            SELECT AVG(score)
            FROM (
                SELECT DISTINCT ON (asset_id) score
                FROM health_scores
                WHERE tenant_id = $1
                ORDER BY asset_id, computed_at DESC
            ) latest_scores
            """,
            tenant_id
        )
        
        # Maintenance this month
        maint_this_month = await conn.fetchval(
            """
            SELECT COUNT(*) FROM maintenance_records
            WHERE tenant_id = $1 
              AND started_date >= DATE_TRUNC('month', NOW())
            """,
            tenant_id
        )
        
        # Upcoming maintenance
        upcoming = await conn.fetchval(
            """
            SELECT COUNT(*) FROM maintenance_records
            WHERE tenant_id = $1
              AND status = 'scheduled'
              AND scheduled_date <= NOW() + INTERVAL '30 days'
            """,
            tenant_id
        )
        
        return ReportSummary(
            total_assets=asset_stats["total"] or 0,
            operational_assets=asset_stats["operational"] or 0,
            assets_in_maintenance=asset_stats["in_maintenance"] or 0,
            total_sensors=sensor_count or 0,
            active_alerts=alert_stats["active"] or 0,
            critical_alerts=alert_stats["critical"] or 0,
            avg_health_score=round(float(avg_health), 2) if avg_health else 0.0,
            maintenance_this_month=maint_this_month or 0,
            upcoming_maintenance=upcoming or 0
        )
    
    finally:
        await conn.close()


@router.get("/{tenant_id}/trends", response_model=List[AssetTrend])
async def get_trends_report(
    tenant_id: UUID,
    days: int = 30,
    current_user: dict = Depends(get_current_user)
):
    """Get health and alert trends over time."""
    if current_user["tenant_id"] != tenant_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    conn = await get_db_conn()
    try:
        trends = await conn.fetch(
            """
            WITH daily_stats AS (
                SELECT 
                    DATE(created_at) as date,
                    COUNT(*) FILTER (WHERE status = 'open') as alert_count
                FROM alerts
                WHERE tenant_id = $1 AND created_at >= $2
                GROUP BY DATE(created_at)
            ),
            daily_health AS (
                SELECT 
                    DATE(computed_at) as date,
                    AVG(score) as avg_score
                FROM health_scores
                WHERE tenant_id = $1 AND computed_at >= $2
                GROUP BY DATE(computed_at)
            ),
            daily_maint AS (
                SELECT 
                    DATE(started_date) as date,
                    COUNT(*) as maint_count
                FROM maintenance_records
                WHERE tenant_id = $1 AND started_date >= $2
                GROUP BY DATE(started_date)
            ),
            date_series AS (
                SELECT generate_series(
                    DATE($2),
                    CURRENT_DATE,
                    '1 day'::interval
                )::date as date
            )
            SELECT 
                ds.date,
                COALESCE(dh.avg_score, 0) as avg_health_score,
                COALESCE(ds2.alert_count, 0) as alert_count,
                COALESCE(dm.maint_count, 0) as maintenance_count
            FROM date_series ds
            LEFT JOIN daily_health dh ON ds.date = dh.date
            LEFT JOIN daily_stats ds2 ON ds.date = ds2.date
            LEFT JOIN daily_maint dm ON ds.date = dm.date
            ORDER BY ds.date
            """,
            tenant_id, datetime.utcnow() - timedelta(days=days)
        )
        
        return [
            AssetTrend(
                date=row["date"],
                avg_health_score=round(float(row["avg_health_score"]), 2) if row["avg_health_score"] else 0,
                alert_count=row["alert_count"],
                maintenance_count=row["maintenance_count"]
            )
            for row in trends
        ]
    
    finally:
        await conn.close()


@router.get("/{tenant_id}/cost-avoidance", response_model=CostAvoidanceReport)
async def get_cost_avoidance_report(
    tenant_id: UUID,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    current_user: dict = Depends(get_current_user)
):
    """Get cost avoidance analysis from predictive maintenance."""
    if current_user["tenant_id"] != tenant_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Default to last 90 days
    if not end_date:
        end_date = date.today()
    if not start_date:
        start_date = end_date - timedelta(days=90)
    
    conn = await get_db_conn()
    try:
        # Get maintenance records
        maintenance = await conn.fetch(
            """
            SELECT 
                record_type,
                COUNT(*) as count,
                SUM(cost_total) as total_cost,
                SUM(downtime_hours) as total_downtime
            FROM maintenance_records
            WHERE tenant_id = $1
              AND completed_date >= $2
              AND completed_date <= $3
            GROUP BY record_type
            """,
            tenant_id, start_date, end_date
        )
        
        # Get predictions that led to maintenance (prevented failures)
        predictions = await conn.fetchrow(
            """
            SELECT COUNT(*)
            FROM health_scores h
            JOIN maintenance_records m ON h.asset_id = m.asset_id
            WHERE h.tenant_id = $1
              AND h.score < 60
              AND m.record_type = 'preventive'
              AND m.completed_date >= $2
              AND h.computed_at <= m.completed_date
            """,
            tenant_id, start_date
        )
        
        preventive_count = sum(1 for m in maintenance if m["record_type"] == "preventive")
        corrective_count = sum(1 for m in maintenance if m["record_type"] == "corrective")
        
        # Estimate cost avoidance (preventive maintenance is typically 10x cheaper than corrective)
        total_maintenance_cost = sum(m["total_cost"] or 0 for m in maintenance)
        
        # Estimate failures prevented based on predictions
        failures_prevented = predictions["count"] if predictions else preventive_count
        
        # Assume average corrective cost is 10x preventive cost
        avg_preventive_cost = total_maintenance_cost / max(len(maintenance), 1) if maintenance else 1000
        avg_corrective_cost = avg_preventive_cost * 10
        
        estimated_cost_avoided = failures_prevented * avg_corrective_cost
        
        roi = ((estimated_cost_avoided - total_maintenance_cost) / max(total_maintenance_cost, 1)) * 100
        
        return CostAvoidanceReport(
            predicted_failures_prevented=failures_prevented,
            estimated_cost_avoided=estimated_cost_avoided,
            actual_maintenance_cost=total_maintenance_cost,
            roi_percentage=round(roi, 2),
            period_start=start_date,
            period_end=end_date
        )
    
    finally:
        await conn.close()


@router.get("/{tenant_id}/dashboard", response_model=DashboardSummary)
async def get_dashboard_summary(
    tenant_id: UUID,
    current_user: dict = Depends(get_current_user)
):
    """Get comprehensive dashboard summary."""
    if current_user["tenant_id"] != tenant_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    conn = await get_db_conn()
    try:
        # Asset overview
        asset_rows = await conn.fetch(
            """
            SELECT status, criticality, COUNT(*) as count
            FROM assets
            WHERE tenant_id = $1
            GROUP BY status, criticality
            """,
            tenant_id
        )
        
        assets_by_status = {}
        assets_by_criticality = {}
        total_assets = 0
        
        for row in asset_rows:
            total_assets += row["count"]
            assets_by_status[row["status"]] = assets_by_status.get(row["status"], 0) + row["count"]
            assets_by_criticality[row["criticality"]] = assets_by_criticality.get(row["criticality"], 0) + row["count"]
        
        # Alert stats
        alert_rows = await conn.fetch(
            """
            SELECT severity, COUNT(*) as count
            FROM alerts
            WHERE tenant_id = $1 AND status = 'open'
            GROUP BY severity
            """,
            tenant_id
        )
        
        alerts_by_severity = {row["severity"]: row["count"] for row in alert_rows}
        total_open_alerts = sum(alerts_by_severity.values())
        
        # Recent alerts
        recent_alerts = await conn.fetch(
            """
            SELECT a.*, ast.name as asset_name
            FROM alerts a
            JOIN assets ast ON a.asset_id = ast.id
            WHERE a.tenant_id = $1
            ORDER BY a.created_at DESC
            LIMIT 5
            """,
            tenant_id
        )
        
        # Health distribution
        health_rows = await conn.fetch(
            """
            SELECT 
                CASE 
                    WHEN score >= 80 THEN 'healthy'
                    WHEN score >= 50 THEN 'at_risk'
                    ELSE 'critical'
                END as category,
                COUNT(*) as count
            FROM (
                SELECT DISTINCT ON (asset_id) score
                FROM health_scores
                WHERE tenant_id = $1
                ORDER BY asset_id, computed_at DESC
            ) latest
            GROUP BY category
            """,
            tenant_id
        )
        
        health_distribution = {row["category"]: row["count"] for row in health_rows}
        
        # Average fleet health
        avg_health = await conn.fetchval(
            """
            SELECT AVG(score)
            FROM (
                SELECT DISTINCT ON (asset_id) score
                FROM health_scores
                WHERE tenant_id = $1
                ORDER BY asset_id, computed_at DESC
            ) latest
            """,
            tenant_id
        )
        
        # Maintenance counts
        maint_due = await conn.fetchval(
            """
            SELECT COUNT(*) FROM maintenance_records
            WHERE tenant_id = $1
              AND status = 'scheduled'
              AND scheduled_date <= NOW() + INTERVAL '7 days'
            """,
            tenant_id
        )
        
        maint_overdue = await conn.fetchval(
            """
            SELECT COUNT(*) FROM maintenance_records
            WHERE tenant_id = $1
              AND status = 'scheduled'
              AND scheduled_date < NOW()
            """,
            tenant_id
        )
        
        # Health trend (last 30 days)
        health_trend = await conn.fetch(
            """
            SELECT DATE(computed_at) as date, AVG(score) as score
            FROM health_scores
            WHERE tenant_id = $1 AND computed_at >= NOW() - INTERVAL '30 days'
            GROUP BY DATE(computed_at)
            ORDER BY date
            """,
            tenant_id
        )
        
        # Alert trend
        alert_trend = await conn.fetch(
            """
            SELECT DATE(created_at) as date, COUNT(*) as count
            FROM alerts
            WHERE tenant_id = $1 AND created_at >= NOW() - INTERVAL '30 days'
            GROUP BY DATE(created_at)
            ORDER BY date
            """,
            tenant_id
        )
        
        return DashboardSummary(
            total_assets=total_assets,
            assets_by_status=assets_by_status,
            assets_by_criticality=assets_by_criticality,
            total_open_alerts=total_open_alerts,
            alerts_by_severity=alerts_by_severity,
            recent_alerts=[AlertResponse(**dict(a)) for a in recent_alerts],
            fleet_health_score=round(float(avg_health), 2) if avg_health else 0,
            health_distribution=health_distribution,
            maintenance_due_count=maint_due or 0,
            maintenance_overdue_count=maint_overdue or 0,
            health_trend=[{"date": h["date"], "score": round(float(h["score"]), 2)} for h in health_trend],
            alert_trend=[{"date": a["date"], "count": a["count"]} for a in alert_trend]
        )
    
    finally:
        await conn.close()


@router.get("/{tenant_id}/asset/{asset_id}/details")
async def get_asset_detailed_report(
    tenant_id: UUID,
    asset_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Get detailed report for a specific asset."""
    if current_user["tenant_id"] != tenant_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    conn = await get_db_conn()
    try:
        # Get asset details
        asset = await conn.fetchrow(
            """
            SELECT a.*,
                   (SELECT COUNT(*) FROM sensors WHERE asset_id = a.id) as sensor_count,
                   (SELECT score FROM health_scores WHERE asset_id = a.id ORDER BY computed_at DESC LIMIT 1) as health_score
            FROM assets a
            WHERE a.tenant_id = $1 AND a.asset_id = $2
            """,
            tenant_id, asset_id
        )
        
        if not asset:
            raise HTTPException(status_code=404, detail="Asset not found")
        
        # Get recent alerts
        alerts = await conn.fetch(
            """
            SELECT * FROM alerts
            WHERE tenant_id = $1 AND asset_id = (SELECT id FROM assets WHERE asset_id = $2)
            ORDER BY created_at DESC
            LIMIT 10
            """,
            tenant_id, asset_id
        )
        
        # Get maintenance history
        maintenance = await conn.fetch(
            """
            SELECT * FROM maintenance_records
            WHERE tenant_id = $1 AND asset_id = (SELECT id FROM assets WHERE asset_id = $2)
            ORDER BY started_date DESC NULLS LAST
            LIMIT 10
            """,
            tenant_id, asset_id
        )
        
        # Get health history
        health_history = await conn.fetch(
            """
            SELECT * FROM health_scores
            WHERE tenant_id = $1 AND asset_id = (SELECT id FROM assets WHERE asset_id = $2)
            ORDER BY computed_at DESC
            LIMIT 30
            """,
            tenant_id, asset_id
        )
        
        # Get sensor readings summary (from MongoDB)
        from motor.motor_asyncio import AsyncIOMotorClient
        from common.config import settings
        
        mongo_client = AsyncIOMotorClient(settings.MONGO_URI)
        mongo_db = mongo_client[settings.MONGO_DB]
        
        # Get latest readings per sensor
        pipeline = [
            {"$match": {"metadata.asset_id": asset_id}},
            {"$sort": {"timestamp": -1}},
            {"$group": {
                "_id": "$metadata.sensor_id",
                "latest_value": {"$first": "$value"},
                "latest_timestamp": {"$first": "$timestamp"},
                "sensor_type": {"$first": "$metadata.sensor_type"}
            }},
            {"$limit": 10}
        ]
        
        sensor_readings = []
        try:
            cursor = mongo_db.sensor_readings.aggregate(pipeline)
            async for doc in cursor:
                sensor_readings.append({
                    "sensor_id": doc["_id"],
                    "sensor_type": doc["sensor_type"],
                    "latest_value": doc["latest_value"],
                    "timestamp": doc["latest_timestamp"]
                })
        except Exception as e:
            logger.warning(f"Could not fetch sensor readings: {e}")
        finally:
            mongo_client.close()
        
        return {
            "asset": AssetResponse(**dict(asset)),
            "recent_alerts": [AlertResponse(**dict(a)) for a in alerts],
            "maintenance_history": [dict(m) for m in maintenance],
            "health_history": [dict(h) for h in health_history],
            "latest_sensor_readings": sensor_readings
        }
    
    finally:
        await conn.close()
