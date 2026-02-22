# =============================================================================
# FORESIGHT API — Assets Router
# Asset management endpoints
# =============================================================================

from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from api.dependencies import get_current_user, get_pagination, PaginationParams
from api.models.schemas import (
    AssetCreate, AssetResponse, AssetUpdate, AssetListResponse,
    SensorCreate, SensorResponse, SensorUpdate, MaintenanceRecordCreate,
    MaintenanceRecordResponse, MaintenanceRecordUpdate, HealthScoreResponse,
    DashboardSummary
)
from common.logging_config import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/assets", tags=["Assets"])


# =============================================================================
# Helper Functions
# =============================================================================

async def get_db_conn():
    """Get database connection."""
    import asyncpg
    from common.config import settings
    return await asyncpg.connect(dsn=settings.DATABASE_URL)


# =============================================================================
# Asset Endpoints
# =============================================================================

@router.post("/{tenant_id}", response_model=AssetResponse, status_code=201)
async def create_asset(
    tenant_id: UUID,
    asset_data: AssetCreate,
    current_user: dict = Depends(get_current_user)
):
    """Create a new asset."""
    if current_user["tenant_id"] != tenant_id:
        raise HTTPException(status_code=403, detail="Access denied for this tenant")
    
    conn = await get_db_conn()
    try:
        # Check if asset_id already exists
        existing = await conn.fetchrow(
            "SELECT id FROM assets WHERE tenant_id = $1 AND asset_id = $2",
            tenant_id, asset_data.asset_id
        )
        if existing:
            raise HTTPException(status_code=409, detail="Asset with this ID already exists")
        
        asset_id = await conn.fetchval(
            """
            INSERT INTO assets (
                tenant_id, asset_id, name, description, asset_type, category,
                manufacturer, model, serial_number, location, department,
                criticality, install_date, purchase_cost, status, parent_asset_id,
                sap_equipment_number, asset_suite_id, metadata
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19)
            RETURNING id
            """,
            tenant_id, asset_data.asset_id, asset_data.name, asset_data.description,
            asset_data.asset_type, asset_data.category, asset_data.manufacturer,
            asset_data.model, asset_data.serial_number, asset_data.location,
            asset_data.department, asset_data.criticality.value, asset_data.install_date,
            asset_data.purchase_cost, asset_data.status.value, asset_data.parent_asset_id,
            asset_data.sap_equipment_number, asset_data.asset_suite_id,
            asset_data.metadata or {}
        )
        
        asset = await conn.fetchrow(
            """
            SELECT a.*, 
                   (SELECT COUNT(*) FROM sensors WHERE asset_id = a.id) as sensor_count,
                   (SELECT score FROM health_scores WHERE asset_id = a.id ORDER BY computed_at DESC LIMIT 1) as health_score,
                   (SELECT COUNT(*) FROM alerts WHERE asset_id = a.id AND status = 'open') as open_alerts
            FROM assets a WHERE a.id = $1
            """,
            asset_id
        )
        
        logger.info(f"Asset {asset_data.asset_id} created by {current_user['email']}")
        return AssetResponse(**dict(asset))
    
    finally:
        await conn.close()


@router.get("/{tenant_id}", response_model=AssetListResponse)
async def list_assets(
    tenant_id: UUID,
    asset_type: Optional[str] = None,
    status: Optional[str] = None,
    criticality: Optional[str] = None,
    location: Optional[str] = None,
    search: Optional[str] = None,
    pagination: PaginationParams = Depends(get_pagination),
    current_user: dict = Depends(get_current_user)
):
    """List assets with filtering and pagination."""
    if current_user["tenant_id"] != tenant_id:
        raise HTTPException(status_code=403, detail="Access denied for this tenant")
    
    conn = await get_db_conn()
    try:
        # Build query dynamically
        where_clauses = ["a.tenant_id = $1"]
        params = [tenant_id]
        param_idx = 2
        
        if asset_type:
            where_clauses.append(f"a.asset_type = ${param_idx}")
            params.append(asset_type)
            param_idx += 1
        
        if status:
            where_clauses.append(f"a.status = ${param_idx}")
            params.append(status)
            param_idx += 1
        
        if criticality:
            where_clauses.append(f"a.criticality = ${param_idx}")
            params.append(criticality)
            param_idx += 1
        
        if location:
            where_clauses.append(f"a.location ILIKE ${param_idx}")
            params.append(f"%{location}%")
            param_idx += 1
        
        if search:
            where_clauses.append(f"(a.name ILIKE ${param_idx} OR a.asset_id ILIKE ${param_idx})")
            params.append(f"%{search}%")
            param_idx += 1
        
        where_sql = " AND ".join(where_clauses)
        
        # Get total count
        count_query = f"SELECT COUNT(*) FROM assets a WHERE {where_sql}"
        total = await conn.fetchval(count_query, *params)
        
        # Get paginated results
        sort_direction = "DESC" if pagination.sort_order == "desc" else "ASC"
        sort_column = pagination.sort_by if pagination.sort_by else "created_at"
        
        query = f"""
            SELECT a.*, 
                   (SELECT COUNT(*) FROM sensors WHERE asset_id = a.id) as sensor_count,
                   (SELECT score FROM health_scores WHERE asset_id = a.id ORDER BY computed_at DESC LIMIT 1) as health_score,
                   (SELECT COUNT(*) FROM alerts WHERE asset_id = a.id AND status = 'open') as open_alerts
            FROM assets a
            WHERE {where_sql}
            ORDER BY a.{sort_column} {sort_direction}
            LIMIT ${param_idx} OFFSET ${param_idx + 1}
        """
        params.extend([pagination.page_size, pagination.offset])
        
        rows = await conn.fetch(query, *params)
        
        return AssetListResponse(
            total=total,
            items=[AssetResponse(**dict(row)) for row in rows],
            page=pagination.page,
            page_size=pagination.page_size
        )
    
    finally:
        await conn.close()


@router.get("/{tenant_id}/{asset_id}", response_model=AssetResponse)
async def get_asset(
    tenant_id: UUID,
    asset_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Get a single asset by ID."""
    if current_user["tenant_id"] != tenant_id:
        raise HTTPException(status_code=403, detail="Access denied for this tenant")
    
    conn = await get_db_conn()
    try:
        asset = await conn.fetchrow(
            """
            SELECT a.*, 
                   (SELECT COUNT(*) FROM sensors WHERE asset_id = a.id) as sensor_count,
                   (SELECT score FROM health_scores WHERE asset_id = a.id ORDER BY computed_at DESC LIMIT 1) as health_score,
                   (SELECT COUNT(*) FROM alerts WHERE asset_id = a.id AND status = 'open') as open_alerts
            FROM assets a
            WHERE a.tenant_id = $1 AND a.asset_id = $2
            """,
            tenant_id, asset_id
        )
        
        if not asset:
            raise HTTPException(status_code=404, detail="Asset not found")
        
        return AssetResponse(**dict(asset))
    
    finally:
        await conn.close()


@router.patch("/{tenant_id}/{asset_id}", response_model=AssetResponse)
async def update_asset(
    tenant_id: UUID,
    asset_id: str,
    asset_data: AssetUpdate,
    current_user: dict = Depends(get_current_user)
):
    """Update an asset."""
    if current_user["tenant_id"] != tenant_id:
        raise HTTPException(status_code=403, detail="Access denied for this tenant")
    
    conn = await get_db_conn()
    try:
        # Get existing asset
        existing = await conn.fetchrow(
            "SELECT id FROM assets WHERE tenant_id = $1 AND asset_id = $2",
            tenant_id, asset_id
        )
        
        if not existing:
            raise HTTPException(status_code=404, detail="Asset not found")
        
        # Build update query
        updates = []
        params = []
        param_idx = 1
        
        fields = {
            'name': asset_data.name,
            'description': asset_data.description,
            'asset_type': asset_data.asset_type,
            'category': asset_data.category,
            'manufacturer': asset_data.manufacturer,
            'model': asset_data.model,
            'serial_number': asset_data.serial_number,
            'location': asset_data.location,
            'department': asset_data.department,
            'criticality': asset_data.criticality.value if asset_data.criticality else None,
            'install_date': asset_data.install_date,
            'purchase_cost': asset_data.purchase_cost,
            'status': asset_data.status.value if asset_data.status else None,
            'parent_asset_id': asset_data.parent_asset_id,
            'sap_equipment_number': asset_data.sap_equipment_number,
            'asset_suite_id': asset_data.asset_suite_id,
            'metadata': asset_data.metadata,
        }
        
        for field, value in fields.items():
            if value is not None:
                updates.append(f"{field} = ${param_idx}")
                params.append(value)
                param_idx += 1
        
        if not updates:
            raise HTTPException(status_code=400, detail="No fields to update")
        
        updates.append("updated_at = NOW()")
        params.extend([tenant_id, asset_id])
        
        await conn.execute(
            f"UPDATE assets SET {', '.join(updates)} WHERE tenant_id = ${param_idx} AND asset_id = ${param_idx + 1}",
            *params
        )
        
        # Return updated asset
        asset = await conn.fetchrow(
            """
            SELECT a.*, 
                   (SELECT COUNT(*) FROM sensors WHERE asset_id = a.id) as sensor_count,
                   (SELECT score FROM health_scores WHERE asset_id = a.id ORDER BY computed_at DESC LIMIT 1) as health_score,
                   (SELECT COUNT(*) FROM alerts WHERE asset_id = a.id AND status = 'open') as open_alerts
            FROM assets a
            WHERE a.tenant_id = $1 AND a.asset_id = $2
            """,
            tenant_id, asset_id
        )
        
        logger.info(f"Asset {asset_id} updated by {current_user['email']}")
        return AssetResponse(**dict(asset))
    
    finally:
        await conn.close()


@router.delete("/{tenant_id}/{asset_id}", status_code=204)
async def delete_asset(
    tenant_id: UUID,
    asset_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Delete an asset."""
    if current_user["tenant_id"] != tenant_id:
        raise HTTPException(status_code=403, detail="Access denied for this tenant")
    
    conn = await get_db_conn()
    try:
        result = await conn.execute(
            "DELETE FROM assets WHERE tenant_id = $1 AND asset_id = $2",
            tenant_id, asset_id
        )
        
        if result == "DELETE 0":
            raise HTTPException(status_code=404, detail="Asset not found")
        
        logger.info(f"Asset {asset_id} deleted by {current_user['email']}")
    
    finally:
        await conn.close()


# =============================================================================
# Sensor Endpoints (Nested under Assets)
# =============================================================================

@router.post("/{tenant_id}/{asset_id}/sensors", response_model=SensorResponse, status_code=201)
async def create_sensor(
    tenant_id: UUID,
    asset_id: str,
    sensor_data: SensorCreate,
    current_user: dict = Depends(get_current_user)
):
    """Add a sensor to an asset."""
    if current_user["tenant_id"] != tenant_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    conn = await get_db_conn()
    try:
        # Verify asset exists
        asset = await conn.fetchrow(
            "SELECT id FROM assets WHERE tenant_id = $1 AND asset_id = $2",
            tenant_id, asset_id
        )
        if not asset:
            raise HTTPException(status_code=404, detail="Asset not found")
        
        # Check if sensor_id exists
        existing = await conn.fetchrow(
            "SELECT id FROM sensors WHERE tenant_id = $1 AND sensor_id = $2",
            tenant_id, sensor_data.sensor_id
        )
        if existing:
            raise HTTPException(status_code=409, detail="Sensor with this ID already exists")
        
        sensor_uuid = await conn.fetchval(
            """
            INSERT INTO sensors (
                tenant_id, sensor_id, asset_id, name, sensor_type, unit,
                sampling_rate, min_threshold, max_threshold, calibration_date,
                location_on_asset, kafka_topic, metadata
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
            RETURNING id
            """,
            tenant_id, sensor_data.sensor_id, asset["id"], sensor_data.name,
            sensor_data.sensor_type, sensor_data.unit, sensor_data.sampling_rate,
            sensor_data.min_threshold, sensor_data.max_threshold, sensor_data.calibration_date,
            sensor_data.location_on_asset, sensor_data.kafka_topic, sensor_data.metadata or {}
        )
        
        sensor = await conn.fetchrow("SELECT * FROM sensors WHERE id = $1", sensor_uuid)
        return SensorResponse(**dict(sensor))
    
    finally:
        await conn.close()


@router.get("/{tenant_id}/{asset_id}/sensors", response_model=List[SensorResponse])
async def list_asset_sensors(
    tenant_id: UUID,
    asset_id: str,
    current_user: dict = Depends(get_current_user)
):
    """List all sensors for an asset."""
    if current_user["tenant_id"] != tenant_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    conn = await get_db_conn()
    try:
        # Verify asset exists
        asset = await conn.fetchrow(
            "SELECT id FROM assets WHERE tenant_id = $1 AND asset_id = $2",
            tenant_id, asset_id
        )
        if not asset:
            raise HTTPException(status_code=404, detail="Asset not found")
        
        sensors = await conn.fetch(
            "SELECT * FROM sensors WHERE tenant_id = $1 AND asset_id = $2",
            tenant_id, asset["id"]
        )
        
        return [SensorResponse(**dict(s)) for s in sensors]
    
    finally:
        await conn.close()


# =============================================================================
# Maintenance Records Endpoints
# =============================================================================

@router.post("/{tenant_id}/{asset_id}/maintenance", response_model=MaintenanceRecordResponse, status_code=201)
async def create_maintenance_record(
    tenant_id: UUID,
    asset_id: str,
    record_data: MaintenanceRecordCreate,
    current_user: dict = Depends(get_current_user)
):
    """Create a maintenance record for an asset."""
    if current_user["tenant_id"] != tenant_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    conn = await get_db_conn()
    try:
        # Verify asset exists
        asset = await conn.fetchrow(
            "SELECT id, name FROM assets WHERE tenant_id = $1 AND asset_id = $2",
            tenant_id, asset_id
        )
        if not asset:
            raise HTTPException(status_code=404, detail="Asset not found")
        
        record_uuid = await conn.fetchval(
            """
            INSERT INTO maintenance_records (
                tenant_id, asset_id, work_order_number, record_type, title, description,
                status, priority, scheduled_date, started_date, completed_date,
                technician_name, technician_id, cost_parts, cost_labor, cost_total,
                downtime_hours, parts_replaced, findings, recommendations,
                sap_notification_number, asset_suite_work_order_id, metadata
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20, $21, $22, $23)
            RETURNING id
            """,
            tenant_id, asset["id"], record_data.work_order_number, record_data.record_type.value,
            record_data.title, record_data.description, record_data.status, record_data.priority,
            record_data.scheduled_date, record_data.started_date, record_data.completed_date,
            record_data.technician_name, record_data.technician_id, record_data.cost_parts,
            record_data.cost_labor, record_data.cost_total, record_data.downtime_hours,
            record_data.parts_replaced, record_data.findings, record_data.recommendations,
            record_data.sap_notification_number, record_data.asset_suite_work_order_id,
            record_data.metadata or {}
        )
        
        record = await conn.fetchrow(
            """
            SELECT m.*, a.name as asset_name
            FROM maintenance_records m
            JOIN assets a ON m.asset_id = a.id
            WHERE m.id = $1
            """,
            record_uuid
        )
        
        return MaintenanceRecordResponse(**dict(record))
    
    finally:
        await conn.close()


@router.get("/{tenant_id}/{asset_id}/maintenance", response_model=List[MaintenanceRecordResponse])
async def list_maintenance_records(
    tenant_id: UUID,
    asset_id: str,
    current_user: dict = Depends(get_current_user)
):
    """List maintenance records for an asset."""
    if current_user["tenant_id"] != tenant_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    conn = await get_db_conn()
    try:
        # Verify asset exists
        asset = await conn.fetchrow(
            "SELECT id FROM assets WHERE tenant_id = $1 AND asset_id = $2",
            tenant_id, asset_id
        )
        if not asset:
            raise HTTPException(status_code=404, detail="Asset not found")
        
        records = await conn.fetch(
            """
            SELECT m.*, a.name as asset_name
            FROM maintenance_records m
            JOIN assets a ON m.asset_id = a.id
            WHERE m.tenant_id = $1 AND m.asset_id = $2
            ORDER BY m.created_at DESC
            """,
            tenant_id, asset["id"]
        )
        
        return [MaintenanceRecordResponse(**dict(r)) for r in records]
    
    finally:
        await conn.close()


# =============================================================================
# Health Score Endpoints
# =============================================================================

@router.get("/{tenant_id}/{asset_id}/health", response_model=HealthScoreResponse)
async def get_asset_health(
    tenant_id: UUID,
    asset_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Get the latest health score for an asset."""
    if current_user["tenant_id"] != tenant_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    conn = await get_db_conn()
    try:
        health = await conn.fetchrow(
            """
            SELECT h.*, a.name as asset_name, a.asset_type
            FROM health_scores h
            JOIN assets a ON h.asset_id = a.id
            WHERE h.tenant_id = $1 AND a.asset_id = $2
            ORDER BY h.computed_at DESC
            LIMIT 1
            """,
            tenant_id, asset_id
        )
        
        if not health:
            raise HTTPException(status_code=404, detail="No health score found for this asset")
        
        return HealthScoreResponse(**dict(health))
    
    finally:
        await conn.close()


@router.get("/{tenant_id}/{asset_id}/health/history", response_model=List[HealthScoreResponse])
async def get_health_history(
    tenant_id: UUID,
    asset_id: str,
    days: int = 30,
    current_user: dict = Depends(get_current_user)
):
    """Get historical health scores for an asset."""
    if current_user["tenant_id"] != tenant_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    conn = await get_db_conn()
    try:
        from datetime import datetime, timedelta
        
        health_scores = await conn.fetch(
            """
            SELECT h.*, a.name as asset_name, a.asset_type
            FROM health_scores h
            JOIN assets a ON h.asset_id = a.id
            WHERE h.tenant_id = $1 AND a.asset_id = $2
              AND h.computed_at >= $3
            ORDER BY h.computed_at DESC
            """,
            tenant_id, asset_id, datetime.utcnow() - timedelta(days=days)
        )
        
        return [HealthScoreResponse(**dict(h)) for h in health_scores]
    
    finally:
        await conn.close()
