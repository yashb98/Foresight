"""
FORESIGHT — Spark Windowed Aggregations

Computes rolling statistical aggregations over sensor readings at three time scales:
  - 5-minute window (for real-time alerting — fastest detection)
  - 1-hour window (for operational awareness)
  - 24-hour window (for ML feature generation)

All windows use:
  - Watermarking: 10-minute late data tolerance (handles network jitter)
  - Sliding windows with slide = window / 2 (overlapping windows for smoother trends)
  - Aggregations: mean, max, min, stddev, count per (tenant_id, asset_id, metric_name)

Why overlapping windows?
  Non-overlapping tumbling windows can miss a spike that straddles a boundary.
  With 50% overlap, a 10-minute spike will be captured in at least one window.
"""

from __future__ import annotations

import logging
from typing import Tuple

from pyspark.sql import DataFrame
from pyspark.sql import functions as F
from pyspark.sql import types as T  # noqa: F401

log = logging.getLogger(__name__)


def apply_windowed_aggregations(
    sensor_df: DataFrame,
) -> Tuple[DataFrame, DataFrame, DataFrame]:
    """
    Apply 5-minute, 1-hour, and 24-hour sliding windowed aggregations.

    Args:
        sensor_df: Streaming DataFrame with columns:
                   tenant_id, asset_id, event_time, metric_name, value, quality_flag

    Returns:
        Tuple of (agg_5min_df, agg_1hr_df, agg_24hr_df) — all streaming DataFrames.
        Each has columns: tenant_id, asset_id, metric_name, window_start, window_end,
                          mean_value, max_value, min_value, std_dev, reading_count,
                          window_size
    """
    # Apply watermark first (late data tolerance)
    watermarked = sensor_df.withWatermark("event_time", "10 minutes")

    agg_5min = _aggregate_window(
        watermarked,
        window_duration="5 minutes",
        slide_duration="2 minutes 30 seconds",
        window_label="5min",
    )
    agg_1hr = _aggregate_window(
        watermarked, window_duration="1 hour", slide_duration="30 minutes", window_label="1hour"
    )
    agg_24hr = _aggregate_window(
        watermarked, window_duration="24 hours", slide_duration="12 hours", window_label="24hour"
    )

    log.info("Windowed aggregation streams configured: 5min, 1hour, 24hour")
    return agg_5min, agg_1hr, agg_24hr


def _aggregate_window(
    df: DataFrame,
    window_duration: str,
    slide_duration: str,
    window_label: str,
) -> DataFrame:
    """
    Compute statistical aggregations over a sliding time window.

    Args:
        df:              Watermarked streaming DataFrame.
        window_duration: Spark window duration string, e.g. '5 minutes'.
        slide_duration:  Spark slide duration string, e.g. '2 minutes 30 seconds'.
        window_label:    Human-readable label stored in 'window_size' column.

    Returns:
        Aggregated streaming DataFrame.
    """
    # Filter out suspect quality readings for aggregation accuracy
    # (keep them in raw store but don't skew averages)
    clean_df = df.filter(F.col("quality_flag") != "suspect")

    return (
        clean_df.groupBy(
            F.window(F.col("event_time"), window_duration, slide_duration),
            F.col("tenant_id"),
            F.col("asset_id"),
            F.col("metric_name"),
        )
        .agg(
            F.mean("value").alias("mean_value"),
            F.max("value").alias("max_value"),
            F.min("value").alias("min_value"),
            F.stddev("value").alias("std_dev"),
            F.count("value").alias("reading_count"),
        )
        .select(
            F.col("tenant_id"),
            F.col("asset_id"),
            F.col("metric_name"),
            F.col("window.start").alias("window_start"),
            F.col("window.end").alias("window_end"),
            F.round(F.col("mean_value"), 4).alias("mean_value"),
            F.round(F.col("max_value"), 4).alias("max_value"),
            F.round(F.col("min_value"), 4).alias("min_value"),
            F.round(F.col("std_dev"), 4).alias("std_dev"),
            F.col("reading_count"),
            F.lit(window_label).alias("window_size"),
            F.current_timestamp().alias("computed_at"),
        )
    )


def compute_batch_features(sensor_df: DataFrame, days: int = 7) -> DataFrame:
    """
    Compute rolling features over a batch (non-streaming) sensor DataFrame.
    Used by the daily batch feature engineering job (not streaming).

    Args:
        sensor_df: Batch DataFrame with columns matching the streaming schema.
        days:      Rolling window in days.

    Returns:
        DataFrame with aggregated features per (tenant_id, asset_id, metric_name).
    """
    from pyspark.sql.window import Window

    window_spec = (
        Window.partitionBy("tenant_id", "asset_id", "metric_name")
        .orderBy(F.col("event_time").cast("long"))
        .rangeBetween(-(days * 86400), 0)
    )

    return sensor_df.select(
        F.col("tenant_id"),
        F.col("asset_id"),
        F.col("metric_name"),
        F.col("event_time"),
        F.col("value"),
        F.avg("value").over(window_spec).alias(f"mean_{days}d"),
        F.stddev("value").over(window_spec).alias(f"std_{days}d"),
        F.max("value").over(window_spec).alias(f"max_{days}d"),
        F.min("value").over(window_spec).alias(f"min_{days}d"),
    )
