"""
FORESIGHT — Feature Engineering Pipeline

Automatically generates features from imported data for ML model consumption.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import pandas as pd
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

log = logging.getLogger(__name__)


class FeaturePipeline:
    """Pipeline for engineering features from raw data."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def process_table(self, table_name: str) -> Dict[str, Any]:
        """Process a table and generate features."""
        log.info(f"Processing features for table: {table_name}")
        
        # Get table schema
        columns = await self._get_table_columns(table_name)
        
        # Detect column types
        numeric_cols = [c for c in columns if await self._is_numeric_column(table_name, c)]
        timestamp_cols = [c for c in columns if await self._is_timestamp_column(table_name, c)]
        
        # Generate features based on detected columns
        features = []
        
        if numeric_cols:
            # Calculate rolling statistics for numeric columns
            for col in numeric_cols:
                feature = await self._calculate_rolling_stats(table_name, col, timestamp_cols[0] if timestamp_cols else None)
                features.append(feature)
        
        # Update feature store
        await self._update_feature_store(table_name, features)
        
        return {
            "table": table_name,
            "features_generated": len(features),
            "columns_processed": len(columns),
        }
    
    async def _get_table_columns(self, table_name: str) -> List[str]:
        """Get column names for a table."""
        result = await self.db.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = :table
        """), {"table": table_name})
        
        return [row[0] for row in result.fetchall()]
    
    async def _is_numeric_column(self, table_name: str, column: str) -> bool:
        """Check if a column is numeric."""
        result = await self.db.execute(text("""
            SELECT data_type 
            FROM information_schema.columns 
            WHERE table_name = :table AND column_name = :column
        """), {"table": table_name, "column": column})
        
        row = result.fetchone()
        if row:
            return row[0] in ('integer', 'bigint', 'numeric', 'real', 'double precision', 'smallint')
        return False
    
    async def _is_timestamp_column(self, table_name: str, column: str) -> bool:
        """Check if a column is a timestamp."""
        result = await self.db.execute(text("""
            SELECT data_type 
            FROM information_schema.columns 
            WHERE table_name = :table AND column_name = :column
        """), {"table": table_name, "column": column})
        
        row = result.fetchone()
        if row:
            return row[0] in ('timestamp', 'timestamp with time zone', 'date')
        return False
    
    async def _calculate_rolling_stats(self, table_name: str, column: str, timestamp_col: Optional[str]) -> Dict[str, Any]:
        """Calculate rolling statistics for a numeric column."""
        
        # Query statistics
        order_by = f"ORDER BY {timestamp_col}" if timestamp_col else ""
        
        result = await self.db.execute(text(f"""
            SELECT 
                AVG({column}) as mean,
                STDDEV({column}) as std,
                MIN({column}) as min,
                MAX({column}) as max,
                COUNT(*) as count
            FROM {table_name}
            WHERE {column} IS NOT NULL
        """))
        
        row = result.fetchone()
        
        return {
            "column": column,
            "table": table_name,
            "mean": row[0],
            "std": row[1],
            "min": row[2],
            "max": row[3],
            "count": row[4],
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
    
    async def _update_feature_store(self, table_name: str, features: List[Dict]):
        """Update the feature store with generated features."""
        # Store features in the feature store table
        for feature in features:
            await self.db.execute(text("""
                INSERT INTO feature_store (
                    table_name, column_name, feature_type, 
                    mean_value, std_value, min_value, max_value, 
                    sample_count, generated_at
                ) VALUES (
                    :table, :column, 'numeric',
                    :mean, :std, :min, :max,
                    :count, :generated_at
                )
                ON CONFLICT (table_name, column_name) DO UPDATE SET
                    mean_value = EXCLUDED.mean_value,
                    std_value = EXCLUDED.std_value,
                    min_value = EXCLUDED.min_value,
                    max_value = EXCLUDED.max_value,
                    sample_count = EXCLUDED.sample_count,
                    generated_at = EXCLUDED.generated_at
            """), feature)
        
        await self.db.commit()
        log.info(f"Updated feature store with {len(features)} features for {table_name}")


async def refresh_features_for_table(table_name: str):
    """Refresh features for a specific table."""
    from api.dependencies import get_session_factory
    
    factory = get_session_factory()
    if not factory:
        log.warning("Database not configured, skipping feature refresh")
        return
    
    async with factory() as db:
        pipeline = FeaturePipeline(db)
        await pipeline.process_table(table_name)
