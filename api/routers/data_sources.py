"""
FORESIGHT — /data-sources router

CRUD endpoints for managing external data source connections.
Supports PostgreSQL, MySQL, MongoDB, CSV, APIs, Snowflake, BigQuery.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db
from api.models.data_source import (
    ConnectionStatus,
    DataSourceCreate,
    DataSourceListResponse,
    DataSourceResponse,
    DataSourceUpdate,
    ImportJobCreate,
    ImportJobResponse,
    ImportJobStatus,
    TestConnectionRequest,
    TestConnectionResponse,
)
from infrastructure.db.base import DataSource as DataSourceModel
from infrastructure.db.base import ImportJob as ImportJobModel

log = logging.getLogger(__name__)
router = APIRouter()

# Default tenant ID for single-tenant mode
DEFAULT_TENANT_ID = "11111111-1111-1111-1111-111111111111"


@router.get("", response_model=DataSourceListResponse, summary="List all data sources")
async def list_data_sources(
    db: AsyncSession = Depends(get_db),
    active_only: bool = False,
) -> DataSourceListResponse:
    """Get all data sources for the tenant."""
    stmt = select(DataSourceModel).where(DataSourceModel.tenant_id == DEFAULT_TENANT_ID)
    
    if active_only:
        stmt = stmt.where(DataSourceModel.is_active == True)
    
    stmt = stmt.order_by(DataSourceModel.created_at.desc())
    
    result = await db.execute(stmt)
    sources = result.scalars().all()
    
    return DataSourceListResponse(
        total=len(sources),
        sources=[_source_to_response(s) for s in sources],
    )


@router.post("", response_model=DataSourceResponse, status_code=status.HTTP_201_CREATED, summary="Create new data source")
async def create_data_source(
    data: DataSourceCreate,
    db: AsyncSession = Depends(get_db),
) -> DataSourceResponse:
    """Create a new data source connection."""
    source = DataSourceModel(
        id=uuid.uuid4(),
        tenant_id=DEFAULT_TENANT_ID,
        name=data.name,
        source_type=data.source_type.value,
        description=data.description,
        config=data.config,
        is_active=data.is_active,
        status=ConnectionStatus.INACTIVE.value,
        created_at=datetime.now(timezone.utc),
    )
    
    db.add(source)
    await db.commit()
    await db.refresh(source)
    
    log.info("Created data source id=%s name=%s type=%s", source.id, source.name, source.source_type)
    
    return _source_to_response(source)


@router.get("/{source_id}", response_model=DataSourceResponse, summary="Get data source details")
async def get_data_source(
    source_id: str,
    db: AsyncSession = Depends(get_db),
) -> DataSourceResponse:
    """Get a specific data source by ID."""
    source = await db.get(DataSourceModel, source_id)
    
    if not source or source.tenant_id != DEFAULT_TENANT_ID:
        raise HTTPException(status_code=404, detail=f"Data source {source_id} not found")
    
    return _source_to_response(source)


@router.put("/{source_id}", response_model=DataSourceResponse, summary="Update data source")
async def update_data_source(
    source_id: str,
    data: DataSourceUpdate,
    db: AsyncSession = Depends(get_db),
) -> DataSourceResponse:
    """Update an existing data source."""
    source = await db.get(DataSourceModel, source_id)
    
    if not source or source.tenant_id != DEFAULT_TENANT_ID:
        raise HTTPException(status_code=404, detail=f"Data source {source_id} not found")
    
    # Update fields
    if data.name is not None:
        source.name = data.name
    if data.description is not None:
        source.description = data.description
    if data.config is not None:
        source.config = data.config
    if data.is_active is not None:
        source.is_active = data.is_active
    
    source.updated_at = datetime.now(timezone.utc)
    
    await db.commit()
    await db.refresh(source)
    
    log.info("Updated data source id=%s", source_id)
    
    return _source_to_response(source)


@router.delete("/{source_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete data source")
async def delete_data_source(
    source_id: str,
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a data source (soft delete by setting inactive)."""
    source = await db.get(DataSourceModel, source_id)
    
    if not source or source.tenant_id != DEFAULT_TENANT_ID:
        raise HTTPException(status_code=404, detail=f"Data source {source_id} not found")
    
    # Soft delete
    source.is_active = False
    source.updated_at = datetime.now(timezone.utc)
    
    await db.commit()
    
    log.info("Deleted data source id=%s", source_id)


@router.post("/test", response_model=TestConnectionResponse, summary="Test connection")
async def test_connection(
    data: TestConnectionRequest,
    db: AsyncSession = Depends(get_db),
) -> TestConnectionResponse:
    """Test a data source connection without saving it."""
    try:
        result = await _test_connection_internal(data.source_type.value, data.config)
        return TestConnectionResponse(success=True, message="Connection successful", details=result)
    except Exception as e:
        log.exception("Connection test failed")
        return TestConnectionResponse(success=False, message=f"Connection failed: {str(e)}")


@router.post("/{source_id}/test", response_model=TestConnectionResponse, summary="Test saved connection")
async def test_saved_connection(
    source_id: str,
    db: AsyncSession = Depends(get_db),
) -> TestConnectionResponse:
    """Test an existing saved data source connection."""
    source = await db.get(DataSourceModel, source_id)
    
    if not source or source.tenant_id != DEFAULT_TENANT_ID:
        raise HTTPException(status_code=404, detail=f"Data source {source_id} not found")
    
    # Update status to testing
    source.status = ConnectionStatus.TESTING.value
    source.last_tested_at = datetime.now(timezone.utc)
    await db.commit()
    
    try:
        result = await _test_connection_internal(source.source_type, source.config)
        
        # Update status to active
        source.status = ConnectionStatus.ACTIVE.value
        source.last_error = None
        await db.commit()
        
        return TestConnectionResponse(
            success=True,
            message=f"Connected successfully to {source.name}",
            details=result,
        )
    except Exception as e:
        error_msg = str(e)
        source.status = ConnectionStatus.ERROR.value
        source.last_error = error_msg
        await db.commit()
        
        return TestConnectionResponse(success=False, message=f"Connection failed: {error_msg}")


@router.post("/{source_id}/import", response_model=ImportJobResponse, status_code=status.HTTP_201_CREATED, summary="Create import job")
async def create_import_job(
    source_id: str,
    data: ImportJobCreate,
    db: AsyncSession = Depends(get_db),
) -> ImportJobResponse:
    """Create a new data import job from a data source."""
    # Verify source exists
    source = await db.get(DataSourceModel, source_id)
    if not source or source.tenant_id != DEFAULT_TENANT_ID:
        raise HTTPException(status_code=404, detail=f"Data source {source_id} not found")
    
    job = ImportJobModel(
        id=uuid.uuid4(),
        tenant_id=DEFAULT_TENANT_ID,
        source_id=source_id,
        target_table=data.target_table,
        query=data.query,
        mapping=data.mapping,
        schedule=data.schedule,
        status=ImportJobStatus.PENDING.value,
        created_at=datetime.now(timezone.utc),
    )
    
    db.add(job)
    await db.commit()
    await db.refresh(job)
    
    log.info("Created import job id=%s source=%s target=%s", job.id, source_id, data.target_table)
    
    return _job_to_response(job)


@router.get("/{source_id}/imports", response_model=list[ImportJobResponse], summary="List import jobs")
async def list_import_jobs(
    source_id: str,
    db: AsyncSession = Depends(get_db),
) -> list[ImportJobResponse]:
    """List all import jobs for a data source."""
    stmt = select(ImportJobModel).where(
        ImportJobModel.source_id == source_id,
        ImportJobModel.tenant_id == DEFAULT_TENANT_ID,
    ).order_by(ImportJobModel.created_at.desc())
    
    result = await db.execute(stmt)
    jobs = result.scalars().all()
    
    return [_job_to_response(j) for j in jobs]


# Helper functions

def _source_to_response(source: DataSourceModel) -> DataSourceResponse:
    """Convert DB model to response model."""
    return DataSourceResponse(
        id=str(source.id),
        tenant_id=str(source.tenant_id),
        name=source.name,
        source_type=source.source_type,
        description=source.description,
        config=source.config,
        is_active=source.is_active,
        status=ConnectionStatus(source.status) if source.status else ConnectionStatus.INACTIVE,
        last_tested_at=source.last_tested_at,
        last_error=source.last_error,
        created_at=source.created_at,
        updated_at=source.updated_at,
    )


def _job_to_response(job: ImportJobModel) -> ImportJobResponse:
    """Convert DB model to response model."""
    return ImportJobResponse(
        id=str(job.id),
        source_id=str(job.source_id),
        tenant_id=str(job.tenant_id),
        target_table=job.target_table,
        status=ImportJobStatus(job.status),
        query=job.query,
        mapping=job.mapping or {},
        schedule=job.schedule,
        records_imported=job.records_imported or 0,
        records_failed=job.records_failed or 0,
        error_message=job.error_message,
        started_at=job.started_at,
        completed_at=job.completed_at,
        created_at=job.created_at,
    )


async def _test_connection_internal(source_type: str, config: Dict[str, Any]) -> Dict[str, Any]:
    """Internal function to test a connection."""
    from api.connections.testers import test_connection as test_conn
    return await test_conn(source_type, config)
