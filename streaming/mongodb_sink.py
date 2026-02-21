"""
FORESIGHT — MongoDB Streaming Sink

Writes windowed aggregation results from Spark Structured Streaming to MongoDB.
Uses foreachBatch to write micro-batches as MongoDB upserts.

Collection: aggregated_readings
Partition key: (tenant_id, asset_id)
Clustering key: window_start DESC
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from pyspark.sql import DataFrame, StreamingQuery

log = logging.getLogger(__name__)


class MongoDBSink:
    """
    Writes Spark streaming DataFrames to MongoDB in foreachBatch mode.

    Args:
        mongo_uri: MongoDB connection URI. Reads from MONGO_URI env if None.
        database:  MongoDB database name.
        collection: Target collection name.
    """

    def __init__(
        self,
        mongo_uri: Optional[str] = None,
        database: Optional[str] = None,
        collection: str = "aggregated_readings",
    ) -> None:
        self._mongo_uri = mongo_uri or os.getenv("MONGO_URI")
        self._database = database or os.getenv("MONGO_DB", "foresight")
        self._collection = collection
        log.info("MongoDBSink initialised: %s.%s", self._database, self._collection)

    def write_stream(
        self,
        agg_df: DataFrame,
        window_size: str,
        trigger_interval: str = "30 seconds",
        checkpoint_suffix: str = "",
    ) -> StreamingQuery:
        """
        Start a streaming sink that writes aggregated readings to MongoDB.

        Args:
            agg_df:           Streaming aggregation DataFrame.
            window_size:      Label ('5min', '1hour', '24hour') — used in checkpoint path.
            trigger_interval: Spark micro-batch trigger interval.
            checkpoint_suffix: Optional suffix for checkpoint directory.

        Returns:
            Active StreamingQuery.
        """
        checkpoint_path = f"/tmp/spark-checkpoints/mongodb-{window_size}{checkpoint_suffix}"

        return (
            agg_df.writeStream.foreachBatch(
                lambda batch, batch_id: self._write_batch(batch, batch_id, window_size)
            )
            .outputMode("update")
            .trigger(processingTime=trigger_interval)
            .option("checkpointLocation", checkpoint_path)
            .start()
        )

    def _write_batch(self, batch_df: DataFrame, batch_id: int, window_size: str) -> None:
        """
        Write a single micro-batch to MongoDB as upserts.

        Upsert key: (tenant_id, asset_id, metric_name, window_start, window_size)
        This ensures re-processing the same window updates in place rather than
        creating duplicates.

        Args:
            batch_df:    Micro-batch DataFrame to write.
            batch_id:    Spark batch ID.
            window_size: Window label for logging.
        """
        if batch_df.isEmpty():
            return

        row_count = batch_df.count()
        log.debug(
            "Writing batch %d to MongoDB [%s]: %d rows",
            batch_id,
            window_size,
            row_count,
        )

        try:
            (
                batch_df.write.format("mongodb")
                .mode("append")
                .option("uri", self._mongo_uri)
                .option("database", self._database)
                .option("collection", self._collection)
                .option("upsertDocument", "true")
                .option(
                    "idFieldList",
                    "tenant_id,asset_id,metric_name,window_start,window_size",
                )
                .save()
            )
            log.info(
                "MongoDB batch %d [%s] written: %d rows",
                batch_id,
                window_size,
                row_count,
            )
        except Exception as exc:
            log.error(
                "MongoDB write failed for batch %d [%s]: %s",
                batch_id,
                window_size,
                exc,
            )

    def write_raw_readings(
        self,
        sensor_df: DataFrame,
        trigger_interval: str = "10 seconds",
    ) -> StreamingQuery:
        """
        Write raw sensor readings (not aggregated) to MongoDB sensor_readings collection.
        Used for real-time dashboard chart data.

        Args:
            sensor_df:        Streaming sensor DataFrame.
            trigger_interval: Trigger interval.

        Returns:
            Active StreamingQuery.
        """
        return (
            sensor_df.writeStream.foreachBatch(
                lambda batch, batch_id: self._write_raw_batch(batch, batch_id)
            )
            .outputMode("append")
            .trigger(processingTime=trigger_interval)
            .option("checkpointLocation", "/tmp/spark-checkpoints/mongodb-raw")
            .start()
        )

    def _write_raw_batch(self, batch_df: DataFrame, batch_id: int) -> None:
        """
        Write raw sensor readings to sensor_readings collection.

        Args:
            batch_df: Micro-batch DataFrame.
            batch_id: Spark batch ID.
        """
        if batch_df.isEmpty():
            return

        try:
            (
                batch_df.write.format("mongodb")
                .mode("append")
                .option("uri", self._mongo_uri)
                .option("database", self._database)
                .option("collection", "sensor_readings")
                .save()
            )
        except Exception as exc:
            log.error("Raw readings MongoDB write failed batch %d: %s", batch_id, exc)
