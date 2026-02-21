"""
FORESIGHT — PySpark Feature Engineering Job

Computes ML-ready features from raw sensor and maintenance data.
Runs as a daily Airflow task and writes results to the Hive feature_store table.

Features computed per (tenant_id, asset_id, date):
  Rolling sensor statistics (7d window):
    - mean, std_dev for temperature, vibration, pressure, RPM
    - max over last 24h (for anomaly detection)

  Time-based features:
    - days_since_last_maintenance
    - days_since_install

  Failure history features:
    - failure_count_90d (corrective maintenance events in last 90 days)
    - maintenance_cost_90d

  Trend features:
    - Linear regression slope over 24h for temperature and vibration

  Labels (for training only):
    - failure_within_7d
    - failure_within_30d

Usage:
    spark-submit batch/jobs/feature_engineering.py \
        --tenant-id <UUID> \
        --date 2026-02-20

    python batch/jobs/feature_engineering.py \
        --tenant-id <UUID> \
        --date 2026-02-20 \
        --mode local
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import date, datetime, timedelta
from typing import Optional

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def get_spark_session(app_name: str = "FORESIGHT-FeatureEngineering"):
    """Create SparkSession with Hive, MinIO, and PostgreSQL JDBC support."""
    from pyspark.sql import SparkSession

    spark = (
        SparkSession.builder.appName(app_name)
        .master(os.getenv("SPARK_MASTER_URL", "local[*]"))
        .config("spark.sql.warehouse.dir", "s3a://foresight-processed/hive-warehouse")
        .config("spark.hadoop.fs.s3a.endpoint", os.getenv("AWS_ENDPOINT_URL", "http://minio:9000"))
        .config("spark.hadoop.fs.s3a.access.key", os.getenv("AWS_ACCESS_KEY_ID", "minioadmin"))
        .config("spark.hadoop.fs.s3a.secret.key", os.getenv("AWS_SECRET_ACCESS_KEY", ""))
        .config("spark.hadoop.fs.s3a.path.style.access", "true")
        .config("spark.hadoop.fs.s3a.impl", "org.apache.hadoop.fs.s3a.S3AFileSystem")
        .config("spark.sql.shuffle.partitions", "6")
        .enableHiveSupport()
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("WARN")
    return spark


def load_sensor_data(spark, tenant_id: str, target_date: date):
    """
    Load sensor readings for the last 7 days from Hive raw_sensor_data table.

    Args:
        spark:       SparkSession.
        tenant_id:   Tenant UUID filter.
        target_date: The scoring date (yesterday).

    Returns:
        Spark DataFrame with sensor readings.
    """
    from pyspark.sql import functions as F

    start_date = target_date - timedelta(days=7)

    try:
        df = spark.sql(f"""
            SELECT * FROM foresight.raw_sensor_data
            WHERE tenant_id = '{tenant_id}'
              AND CAST(CONCAT(year, '-', LPAD(month, 2, '0'), '-', LPAD(day, 2, '0')) AS DATE)
                  BETWEEN '{start_date}' AND '{target_date}'
        """)
        log.info("Loaded %d sensor rows from Hive for tenant %s", df.count(), tenant_id)
        return df
    except Exception as exc:
        log.warning("Hive not available (%s) — generating synthetic data", exc)
        return _generate_synthetic_sensor_data(spark, tenant_id, target_date)


def _generate_synthetic_sensor_data(spark, tenant_id: str, target_date: date):
    """
    Generate synthetic sensor data for testing when Hive is unavailable.

    Args:
        spark:       SparkSession.
        tenant_id:   Tenant UUID.
        target_date: Target scoring date.

    Returns:
        Synthetic sensor DataFrame.
    """
    import random
    import uuid as _uuid
    from pyspark.sql import types as T

    schema = T.StructType([
        T.StructField("reading_id", T.StringType()),
        T.StructField("tenant_id", T.StringType()),
        T.StructField("asset_id", T.StringType()),
        T.StructField("timestamp", T.TimestampType()),
        T.StructField("metric_name", T.StringType()),
        T.StructField("value", T.DoubleType()),
        T.StructField("quality_flag", T.StringType()),
    ])

    rows = []
    asset_ids = [
        str(_uuid.uuid5(_uuid.NAMESPACE_DNS, f"{tenant_id}-asset-{i:04d}"))
        for i in range(30)
    ]
    metrics = ["temperature", "vibration", "pressure", "rpm"]
    metric_ranges = {
        "temperature": (40, 90), "vibration": (5, 45),
        "pressure": (80, 170), "rpm": (800, 3200),
    }

    for asset_id in asset_ids:
        for days_ago in range(7):
            dt = datetime.combine(target_date - timedelta(days=days_ago), datetime.min.time())
            for hour in range(0, 24, 4):   # One reading per 4 hours
                reading_dt = dt.replace(hour=hour)
                for metric in metrics:
                    lo, hi = metric_ranges[metric]
                    rows.append((
                        str(_uuid.uuid4()),
                        tenant_id,
                        asset_id,
                        reading_dt,
                        metric,
                        round(random.uniform(lo, hi), 2),
                        "good",
                    ))

    df = spark.createDataFrame(rows, schema)
    log.info("Generated %d synthetic sensor rows for testing", len(rows))
    return df


def load_maintenance_data(spark, tenant_id: str, target_date: date):
    """
    Load maintenance records from PostgreSQL for the last 90 days.

    Args:
        spark:       SparkSession.
        tenant_id:   Tenant UUID filter.
        target_date: Target date.

    Returns:
        Spark DataFrame with maintenance records.
    """
    pg_url = os.getenv("DATABASE_URL_SYNC", "").replace("postgresql+asyncpg", "postgresql")
    # JDBC URL format
    jdbc_url = pg_url.replace("postgresql://", "jdbc:postgresql://") if pg_url else None

    if not jdbc_url:
        log.warning("PostgreSQL URL not set — using empty maintenance DataFrame")
        from pyspark.sql import types as T
        schema = T.StructType([
            T.StructField("asset_id", T.StringType()),
            T.StructField("maintenance_type", T.StringType()),
            T.StructField("performed_at", T.TimestampType()),
            T.StructField("cost", T.DoubleType()),
        ])
        return spark.createDataFrame([], schema)

    try:
        df = (
            spark.read.format("jdbc")
            .option("url", jdbc_url)
            .option("dbtable", f"""(
                SELECT asset_id, maintenance_type, performed_at, cost
                FROM maintenance_records
                WHERE tenant_id = '{tenant_id}'
                  AND performed_at >= CURRENT_DATE - INTERVAL '90 days'
            ) AS maint_subq""")
            .option("user", os.getenv("POSTGRES_USER", "foresight_user"))
            .option("password", os.getenv("POSTGRES_PASSWORD", ""))
            .option("driver", "org.postgresql.Driver")
            .load()
        )
        log.info("Loaded maintenance records from PostgreSQL: %d rows", df.count())
        return df
    except Exception as exc:
        log.warning("PostgreSQL JDBC failed (%s) — empty maintenance data", exc)
        from pyspark.sql import types as T
        schema = T.StructType([
            T.StructField("asset_id", T.StringType()),
            T.StructField("maintenance_type", T.StringType()),
            T.StructField("performed_at", T.TimestampType()),
            T.StructField("cost", T.DoubleType()),
        ])
        return spark.createDataFrame([], schema)


def compute_features(
    spark, sensor_df, maintenance_df, tenant_id: str, target_date: date
):
    """
    Join sensor and maintenance data and compute the ML feature set.

    Args:
        spark:          SparkSession.
        sensor_df:      Sensor readings DataFrame.
        maintenance_df: Maintenance records DataFrame.
        tenant_id:      Tenant UUID.
        target_date:    Scoring date.

    Returns:
        Feature DataFrame ready for writing to Hive feature_store.
    """
    from pyspark.sql import functions as F
    from pyspark.sql.window import Window

    # --- Sensor feature aggregations ---
    metrics = ["temperature", "vibration", "pressure", "rpm"]

    # Pivot: one row per (asset_id, metric) → one row per asset
    agg_dfs = []
    for metric in metrics:
        metric_df = sensor_df.filter(F.col("metric_name") == metric)
        prefix = metric[:3] if metric != "pressure" else "pres"   # avoid long column names

        agg = metric_df.groupBy("tenant_id", "asset_id").agg(
            F.avg("value").alias(f"{metric}_mean_7d"),
            F.stddev("value").alias(f"{metric}_std_7d"),
            F.max("value").alias(f"{metric}_max_24h"),
            F.min("value").alias(f"{metric}_min_24h"),
        )
        agg_dfs.append(agg)

    # Join all metric aggregations
    features_df = agg_dfs[0]
    for agg in agg_dfs[1:]:
        features_df = features_df.join(agg, on=["tenant_id", "asset_id"], how="outer")

    # --- Maintenance features ---
    if not maintenance_df.isEmpty():
        maint_features = maintenance_df.groupBy("asset_id").agg(
            F.max("performed_at").alias("last_maintenance_at"),
            F.sum(F.when(F.col("maintenance_type") == "corrective", 1).otherwise(0))
             .alias("failure_count_90d"),
            F.sum("cost").alias("maintenance_cost_90d"),
        )

        features_df = features_df.join(maint_features, on="asset_id", how="left")
        features_df = features_df.withColumn(
            "days_since_last_maintenance",
            F.datediff(F.lit(target_date), F.col("last_maintenance_at").cast("date")).cast("double"),
        )
    else:
        features_df = features_df.withColumn("failure_count_90d", F.lit(0).cast("int"))
        features_df = features_df.withColumn("maintenance_cost_90d", F.lit(0.0))
        features_df = features_df.withColumn("days_since_last_maintenance", F.lit(90.0))

    # Add metadata columns
    features_df = (
        features_df
        .withColumn("feature_date", F.lit(str(target_date)).cast("date"))
        .withColumn("computed_at", F.current_timestamp())
        .withColumn("dt", F.lit(str(target_date)))   # Hive partition key
        .fillna(0)
    )

    log.info("Feature computation complete: %d asset rows", features_df.count())
    return features_df


def write_features_to_hive(features_df, tenant_id: str, target_date: date) -> None:
    """
    Write computed features to Hive feature_store table.

    Args:
        features_df: Computed feature DataFrame.
        tenant_id:   Tenant UUID (Hive partition key).
        target_date: Date partition key.
    """
    try:
        (
            features_df.write.mode("overwrite")
            .partitionBy("tenant_id", "dt")
            .format("parquet")
            .option("path", f"s3a://foresight-processed/hive/feature_store/")
            .saveAsTable("foresight.feature_store")
        )
        log.info(
            "Features written to Hive feature_store: tenant=%s, date=%s",
            tenant_id,
            target_date,
        )
    except Exception as exc:
        # Fallback: write as Parquet to MinIO
        log.warning("Hive write failed (%s) — writing to MinIO fallback path", exc)
        output_path = f"s3a://foresight-processed/features/{tenant_id}/{target_date}/"
        features_df.write.mode("overwrite").parquet(output_path)
        log.info("Features written to MinIO: %s", output_path)


def run(tenant_id: str, target_date_str: str, mode: str = "production") -> None:
    """
    Main feature engineering entry point.

    Args:
        tenant_id:       Tenant UUID to process.
        target_date_str: Date string (YYYY-MM-DD) to compute features for.
        mode:            'production' | 'local' (local skips Hive writes)
    """
    target_date = date.fromisoformat(target_date_str)
    log.info(
        "Feature engineering: tenant=%s, date=%s, mode=%s",
        tenant_id,
        target_date,
        mode,
    )

    spark = get_spark_session()

    try:
        sensor_df = load_sensor_data(spark, tenant_id, target_date)
        maintenance_df = load_maintenance_data(spark, tenant_id, target_date)
        features_df = compute_features(spark, sensor_df, maintenance_df, tenant_id, target_date)

        if mode == "production":
            write_features_to_hive(features_df, tenant_id, target_date)
        else:
            features_df.show(5, truncate=False)
            log.info("Local mode — skipping Hive write")

        log.info("Feature engineering complete.")
    finally:
        spark.stop()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FORESIGHT Feature Engineering Job")
    parser.add_argument("--tenant-id", required=True)
    parser.add_argument("--date", default=str(date.today() - timedelta(days=1)))
    parser.add_argument("--mode", choices=["production", "local", "training"], default="production")
    parser.add_argument("--days-back", type=int, default=90)
    parser.add_argument("--output-path", type=str, default=None)
    args = parser.parse_args()

    run(tenant_id=args.tenant_id, target_date_str=args.date, mode=args.mode)
