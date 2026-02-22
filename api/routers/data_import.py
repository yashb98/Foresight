"""
FORESIGHT — /data-import router

Endpoints for running and monitoring data import jobs.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from api.data_import.engine import DataImportEngine
from api.dependencies import get_db
from infrastructure.db.base import ImportJob

log = logging.getLogger(__name__)
router = APIRouter()


@router.post("/jobs/{job_id}/run", response_model=Dict[str, Any], summary="Run import job")
async def run_import_job(
    job_id: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    Execute a data import job.
    Can run in background for large imports.
    """
    job = await db.get(ImportJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Import job {job_id} not found")
    
    engine = DataImportEngine(db)
    
    # Run the import
    result = await engine.run_import_job(job_id)
    
    return result


@router.get("/jobs/{job_id}/status", response_model=Dict[str, Any], summary="Get job status")
async def get_job_status(
    job_id: str,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Get the current status of an import job."""
    job = await db.get(ImportJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Import job {job_id} not found")
    
    return {
        "job_id": str(job.id),
        "status": job.status,
        "records_imported": job.records_imported,
        "records_failed": job.records_failed,
        "error_message": job.error_message,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }


@router.post("/jobs/{job_id}/cancel", response_model=Dict[str, Any], summary="Cancel import job")
async def cancel_import_job(
    job_id: str,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Cancel a running import job."""
    job = await db.get(ImportJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Import job {job_id} not found")
    
    if job.status != "running":
        return {"success": False, "message": f"Job is not running (status: {job.status})"}
    
    from api.models.data_source import ImportJobStatus
    job.status = ImportJobStatus.CANCELLED.value
    await db.commit()
    
    return {"success": True, "message": "Job cancelled"}


@router.get("/pipeline/status", response_model=Dict[str, Any], summary="Get pipeline status")
async def get_pipeline_status(
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Get overall data pipeline status including recent jobs."""
    from sqlalchemy import select, func
    
    # Count jobs by status
    stmt = select(
        ImportJob.status,
        func.count().label("count")
    ).group_by(ImportJob.status)
    
    result = await db.execute(stmt)
    status_counts = {row[0]: row[1] for row in result.fetchall()}
    
    # Get recent jobs
    recent_stmt = select(ImportJob).order_by(ImportJob.created_at.desc()).limit(10)
    recent_result = await db.execute(recent_stmt)
    recent_jobs = [
        {
            "id": str(job.id),
            "target_table": job.target_table,
            "status": job.status,
            "records_imported": job.records_imported,
            "created_at": job.created_at.isoformat(),
        }
        for job in recent_result.scalars().all()
    ]
    
    return {
        "job_counts": status_counts,
        "recent_jobs": recent_jobs,
        "total_jobs": sum(status_counts.values()),
    }
