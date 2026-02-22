"""
FORESIGHT — Data Import Engine

Handles importing data from external sources into the platform.
Supports incremental imports, data transformation, and schema mapping.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.data_source import ImportJobStatus
from infrastructure.db.base import ImportJob, DataSource

log = logging.getLogger(__name__)


class DataImportEngine:
    """Engine for importing data from external sources."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def run_import_job(self, job_id: str) -> Dict[str, Any]:
        """Execute an import job."""
        job = await self.db.get(ImportJob, job_id)
        if not job:
            raise ValueError(f"Import job {job_id} not found")
        
        source = await self.db.get(DataSource, job.source_id)
        if not source:
            raise ValueError(f"Data source {job.source_id} not found")
        
        # Update job status
        job.status = ImportJobStatus.RUNNING.value
        job.started_at = datetime.now(timezone.utc)
        await self.db.commit()
        
        try:
            # Import based on source type
            importer = self._get_importer(source.source_type)
            result = await importer.import_data(self.db, source, job)
            
            # Update job with success
            job.status = ImportJobStatus.COMPLETED.value
            job.records_imported = result.get("records_imported", 0)
            job.records_failed = result.get("records_failed", 0)
            job.completed_at = datetime.now(timezone.utc)
            await self.db.commit()
            
            # Trigger feature engineering pipeline
            await self._trigger_feature_pipeline(job.target_table)
            
            return {
                "success": True,
                "job_id": job_id,
                "records_imported": job.records_imported,
                "records_failed": job.records_failed,
            }
            
        except Exception as e:
            log.exception("Import job failed")
            job.status = ImportJobStatus.FAILED.value
            job.error_message = str(e)
            job.completed_at = datetime.now(timezone.utc)
            await self.db.commit()
            
            return {
                "success": False,
                "job_id": job_id,
                "error": str(e),
            }
    
    def _get_importer(self, source_type: str):
        """Get the appropriate importer for the source type."""
        from api.data_import.importers import (
            PostgreSQLImporter, MySQLImporter, MongoDBImporter,
            CSVImporter, APIImporter, SnowflakeImporter, BigQueryImporter
        )
        
        importers = {
            "postgresql": PostgreSQLImporter(),
            "mysql": MySQLImporter(),
            "mongodb": MongoDBImporter(),
            "csv": CSVImporter(),
            "api": APIImporter(),
            "snowflake": SnowflakeImporter(),
            "bigquery": BigQueryImporter(),
        }
        
        importer = importers.get(source_type)
        if not importer:
            raise ValueError(f"No importer available for type: {source_type}")
        
        return importer
    
    async def _trigger_feature_pipeline(self, target_table: str):
        """Trigger feature engineering pipeline after import."""
        from api.pipeline.feature_engineering import FeaturePipeline
        pipeline = FeaturePipeline(self.db)
        await pipeline.process_table(target_table)


async def save_records(db: AsyncSession, records: List[Dict], target_table: str, mapping: Dict[str, str] = None):
    """Save records to target table with optional column mapping."""
    if not records:
        return 0
    
    # Apply column mapping
    if mapping:
        mapped_records = []
        for record in records:
            mapped = {}
            for source_col, target_col in mapping.items():
                if source_col in record:
                    mapped[target_col] = record[source_col]
            if mapped:
                mapped_records.append(mapped)
        records = mapped_records
    
    if not records:
        return 0
    
    # Get columns from first record
    columns = list(records[0].keys())
    placeholders = ", ".join([f":{col}" for col in columns])
    column_names = ", ".join([f'"{col}"' for col in columns])
    
    query = f"""
        INSERT INTO {target_table} ({column_names})
        VALUES ({placeholders})
        ON CONFLICT DO NOTHING
    """
    
    # Insert in batches
    batch_size = 500
    imported = 0
    
    for i in range(0, len(records), batch_size):
        batch = records[i:i + batch_size]
        for record in batch:
            try:
                await db.execute(text(query), record)
                imported += 1
            except Exception as e:
                log.warning(f"Failed to insert record: {e}")
        
        await db.commit()
    
    return imported
