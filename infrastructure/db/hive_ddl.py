"""
FORESIGHT — Hive Table DDL Script

Creates Hive-managed tables via PySpark for the feature store and raw sensor archive.
Run once at environment setup, or as part of an Airflow initialisation DAG.

Tables:
    raw_sensor_data    — partitioned by tenant_id / year / month / day
    feature_store      — partitioned by tenant_id / date

Usage:
    spark-submit infrastructure/db/hive_ddl.py
    # or from Python: python infrastructure/db/hive_ddl.py
"""

from __future__ import annotations

import logging
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

log = logging.getLogger("hive_ddl")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


def get_spark_session():
    """
    Build a SparkSession configured for Hive and MinIO (S3).

    Returns:
        Active SparkSession with Hive support enabled.
    """
    from pyspark.sql import SparkSession

    spark = (
        SparkSession.builder.appName("FORESIGHT-HiveDDL")
        .config("spark.master", os.getenv("SPARK_MASTER_URL", "local[*]"))
        .config("spark.sql.warehouse.dir", "s3a://foresight-processed/hive-warehouse")
        .config(
            "spark.hadoop.fs.s3a.endpoint",
            os.getenv("AWS_ENDPOINT_URL", "http://minio:9000"),
        )
        .config("spark.hadoop.fs.s3a.access.key", os.getenv("AWS_ACCESS_KEY_ID", "minioadmin"))
        .config(
            "spark.hadoop.fs.s3a.secret.key",
            os.getenv("AWS_SECRET_ACCESS_KEY", ""),
        )
        .config("spark.hadoop.fs.s3a.path.style.access", "true")
        .config("spark.hadoop.fs.s3a.impl", "org.apache.hadoop.fs.s3a.S3AFileSystem")
        .enableHiveSupport()
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("WARN")
    return spark


RAW_SENSOR_DDL = """
CREATE TABLE IF NOT EXISTS foresight.raw_sensor_data (
    reading_id      STRING      COMMENT 'UUID of the sensor reading',
    asset_id        STRING      COMMENT 'Asset UUID',
    timestamp       TIMESTAMP   COMMENT 'Reading timestamp (UTC)',
    metric_name     STRING      COMMENT 'temperature | vibration | pressure | rpm',
    value           DOUBLE      COMMENT 'Raw sensor measurement',
    unit            STRING      COMMENT 'degC | mm_s | bar | rpm',
    quality_flag    STRING      COMMENT 'good | degraded | suspect',
    source          STRING      COMMENT 'simulator | sap | asset_suite'
)
PARTITIONED BY (
    tenant_id STRING COMMENT 'Tenant UUID — always filter by this first',
    year      INT    COMMENT 'Year partition',
    month     INT    COMMENT 'Month partition',
    day       INT    COMMENT 'Day partition'
)
STORED AS PARQUET
LOCATION 's3a://foresight-raw/hive/raw_sensor_data'
TBLPROPERTIES (
    'parquet.compression'='SNAPPY',
    'auto.purge'='false'
)
"""

FEATURE_STORE_DDL = """
CREATE TABLE IF NOT EXISTS foresight.feature_store (
    asset_id                    STRING      COMMENT 'Asset UUID',
    asset_type                  STRING      COMMENT 'pump | turbine | transformer ...',
    criticality                 STRING      COMMENT 'low | medium | high | critical',
    -- Rolling sensor statistics
    temp_mean_7d                DOUBLE      COMMENT '7-day rolling mean temperature (°C)',
    temp_std_7d                 DOUBLE      COMMENT '7-day rolling std dev temperature',
    temp_max_24h                DOUBLE      COMMENT '24-hour max temperature',
    vibration_mean_7d           DOUBLE      COMMENT '7-day rolling mean vibration (mm/s)',
    vibration_std_7d            DOUBLE      COMMENT '7-day rolling std dev vibration',
    vibration_max_24h           DOUBLE      COMMENT '24-hour max vibration',
    pressure_mean_7d            DOUBLE      COMMENT '7-day rolling mean pressure (bar)',
    pressure_std_7d             DOUBLE      COMMENT '7-day rolling std dev pressure',
    pressure_max_24h            DOUBLE      COMMENT '24-hour max pressure',
    rpm_mean_7d                 DOUBLE      COMMENT '7-day rolling mean RPM',
    rpm_std_7d                  DOUBLE      COMMENT '7-day rolling std dev RPM',
    rpm_min_24h                 DOUBLE      COMMENT '24-hour min RPM',
    -- Time-based features
    days_since_last_maintenance DOUBLE      COMMENT 'Days since most recent maintenance event',
    days_since_install          DOUBLE      COMMENT 'Days since asset installation date',
    -- Failure history features
    failure_count_90d           INT         COMMENT 'Number of corrective maintenance events in last 90 days',
    maintenance_cost_90d        DOUBLE      COMMENT 'Total maintenance cost in last 90 days',
    -- Trend features
    temp_trend_24h              DOUBLE      COMMENT 'Linear trend slope of temperature over 24h',
    vibration_trend_24h         DOUBLE      COMMENT 'Linear trend slope of vibration over 24h',
    -- Labels (for training; NULL for inference)
    failure_within_7d           INT         COMMENT '1 if failure occurred within 7 days, 0 otherwise, NULL for inference',
    failure_within_30d          INT         COMMENT '1 if failure occurred within 30 days, 0 otherwise, NULL for inference',
    -- Metadata
    feature_date                DATE        COMMENT 'Date this feature row was computed',
    computed_at                 TIMESTAMP   COMMENT 'Timestamp of computation'
)
PARTITIONED BY (
    tenant_id STRING  COMMENT 'Tenant UUID — always filter by this first',
    dt        STRING  COMMENT 'Date partition (YYYY-MM-DD)'
)
STORED AS PARQUET
LOCATION 's3a://foresight-processed/hive/feature_store'
TBLPROPERTIES (
    'parquet.compression'='SNAPPY',
    'auto.purge'='false'
)
"""


def create_hive_tables(spark) -> None:
    """
    Create Hive database and all managed tables.
    Idempotent — uses CREATE TABLE IF NOT EXISTS throughout.

    Args:
        spark: Active SparkSession with Hive support.
    """
    log.info("Creating Hive database: foresight")
    spark.sql("CREATE DATABASE IF NOT EXISTS foresight COMMENT 'FORESIGHT platform tables'")
    spark.sql("USE foresight")

    log.info("Creating table: raw_sensor_data")
    spark.sql(RAW_SENSOR_DDL)

    log.info("Creating table: feature_store")
    spark.sql(FEATURE_STORE_DDL)

    # Verify tables were created
    tables = spark.sql("SHOW TABLES IN foresight").collect()
    table_names = [row.tableName for row in tables]
    log.info("Hive tables available: %s", table_names)

    assert "raw_sensor_data" in table_names, "raw_sensor_data table not created!"
    assert "feature_store" in table_names, "feature_store table not created!"
    log.info("Hive DDL complete — all tables verified.")


if __name__ == "__main__":
    spark = get_spark_session()
    try:
        create_hive_tables(spark)
    finally:
        spark.stop()
