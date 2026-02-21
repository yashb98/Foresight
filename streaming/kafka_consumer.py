"""
FORESIGHT — Spark Structured Streaming: Kafka Consumer

Entry point for the streaming pipeline. Reads from Kafka sensor-readings topic,
parses JSON into a typed Spark schema, applies windowed aggregations, evaluates
threshold rules, publishes alerts, and writes results to MongoDB.

Pipeline stages:
  1. Read raw Kafka events (binary JSON)
  2. Parse + validate against SensorReading schema
  3. Dead-letter malformed records to MinIO
  4. Apply 5-min / 1-hour / 24-hour windowed aggregations
  5. Load threshold rules from PostgreSQL (refreshed every 60s)
  6. Evaluate rules → publish alerts to Kafka
  7. Write aggregated data to MongoDB

Usage (from Spark master):
    spark-submit \
      --packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0,\
                 org.mongodb.spark:mongo-spark-connector_2.12:10.2.1 \
      streaming/kafka_consumer.py

Or via Python directly (uses Spark local mode):
    python streaming/kafka_consumer.py
"""

from __future__ import annotations

import logging
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from dotenv import load_dotenv

load_dotenv()

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F
from pyspark.sql import types as T

from common.logging_config import configure_logging
from streaming.aggregations import apply_windowed_aggregations
from streaming.alert_engine import AlertEngine
from streaming.mongodb_sink import MongoDBSink
from streaming.rules_loader import RulesLoader

log = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Spark schema for sensor readings (mirrors common.models.SensorReading)
# ─────────────────────────────────────────────────────────────────────────────

SENSOR_READING_SCHEMA = T.StructType(
    [
        T.StructField("reading_id", T.StringType(), True),
        T.StructField("tenant_id", T.StringType(), False),
        T.StructField("asset_id", T.StringType(), False),
        T.StructField("timestamp", T.StringType(), True),  # parsed to TimestampType below
        T.StructField("metric_name", T.StringType(), False),
        T.StructField("value", T.DoubleType(), False),
        T.StructField("unit", T.StringType(), True),
        T.StructField("quality_flag", T.StringType(), True),
        T.StructField("source", T.StringType(), True),
    ]
)


def create_spark_session() -> SparkSession:
    """
    Build and return a SparkSession configured for Kafka, MongoDB, and MinIO.

    Returns:
        Active SparkSession.
    """
    kafka_bootstrap = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")  # noqa: F841
    mongo_uri = os.getenv("MONGO_URI", "mongodb://root:password@mongodb:27017/foresight")
    minio_endpoint = os.getenv("AWS_ENDPOINT_URL", "http://minio:9000")
    spark_master = os.getenv("SPARK_MASTER_URL", "local[*]")

    spark = (
        SparkSession.builder.appName("FORESIGHT-StreamProcessor")
        .master(spark_master)
        # Kafka connector
        .config(
            "spark.jars.packages",
            ",".join(
                [
                    "org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0",
                    "org.mongodb.spark:mongo-spark-connector_2.12:10.2.1",
                    "org.apache.hadoop:hadoop-aws:3.3.4",
                ]
            ),
        )
        # MongoDB connection
        .config("spark.mongodb.write.connection.uri", mongo_uri)
        .config("spark.mongodb.read.connection.uri", mongo_uri)
        # MinIO (S3) for dead-letter queue
        .config("spark.hadoop.fs.s3a.endpoint", minio_endpoint)
        .config("spark.hadoop.fs.s3a.access.key", os.getenv("AWS_ACCESS_KEY_ID", "minioadmin"))
        .config("spark.hadoop.fs.s3a.secret.key", os.getenv("AWS_SECRET_ACCESS_KEY", ""))
        .config("spark.hadoop.fs.s3a.path.style.access", "true")
        .config("spark.hadoop.fs.s3a.impl", "org.apache.hadoop.fs.s3a.S3AFileSystem")
        # Streaming configuration
        .config("spark.sql.streaming.checkpointLocation", "/tmp/spark-checkpoints/foresight")
        .config("spark.sql.shuffle.partitions", "6")
        .config("spark.streaming.backpressure.enabled", "true")
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("WARN")
    log.info("SparkSession created: master=%s", spark_master)
    return spark


def read_kafka_stream(spark: SparkSession) -> DataFrame:
    """
    Read raw JSON sensor readings from Kafka as a Spark Structured Streaming DataFrame.

    The topic pattern 'sensor-readings' matches all tenant topic messages
    (tenant_id is embedded in the message body, not the topic name).

    Args:
        spark: Active SparkSession.

    Returns:
        Streaming DataFrame with Kafka metadata columns + raw 'value' bytes.
    """
    bootstrap = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
    topic = os.getenv("KAFKA_TOPIC_SENSOR_DATA", "sensor-readings")

    return (
        spark.readStream.format("kafka")
        .option("kafka.bootstrap.servers", bootstrap)
        .option("subscribe", topic)
        .option("startingOffsets", "latest")
        .option("failOnDataLoss", "false")
        .option("maxOffsetsPerTrigger", 10000)  # backpressure cap
        .load()
    )


def parse_sensor_readings(raw_df: DataFrame) -> tuple[DataFrame, DataFrame]:
    """
    Parse raw Kafka JSON bytes into typed sensor readings.
    Splits into valid records and dead-letter records (malformed JSON).

    Args:
        raw_df: Kafka streaming DataFrame with binary 'value' column.

    Returns:
        Tuple of (valid_df, dead_letter_df).
    """
    # Decode binary Kafka value to string, parse JSON
    parsed = raw_df.select(
        F.col("offset"),
        F.col("timestamp").alias("kafka_timestamp"),
        F.col("partition"),
        F.from_json(
            F.col("value").cast("string"),
            SENSOR_READING_SCHEMA,
        ).alias("data"),
    )

    # Cast string timestamp to proper TimestampType
    valid_df = (
        parsed.filter(F.col("data").isNotNull())
        .filter(F.col("data.tenant_id").isNotNull())
        .filter(F.col("data.asset_id").isNotNull())
        .select(
            F.col("data.reading_id"),
            F.col("data.tenant_id"),
            F.col("data.asset_id"),
            F.to_timestamp(F.col("data.timestamp")).alias("event_time"),
            F.col("data.metric_name"),
            F.col("data.value"),
            F.col("data.unit"),
            F.col("data.quality_flag"),
            F.col("data.source"),
        )
        .filter(F.col("event_time").isNotNull())
        .filter(F.col("value").isNotNull())
    )

    # Dead-letter: records that failed parsing
    dead_letter_df = parsed.filter(F.col("data").isNull()).select(
        F.col("offset"),
        F.col("kafka_timestamp"),
        F.col("partition"),
    )

    return valid_df, dead_letter_df


def write_dead_letters(dead_letter_df: DataFrame) -> None:
    """
    Write malformed records to MinIO dead-letter queue for inspection.

    Args:
        dead_letter_df: DataFrame of failed parse records.
    """
    (
        dead_letter_df.writeStream.format("json")
        .option("path", "s3a://foresight-raw/dead-letter/sensor-readings/")
        .option("checkpointLocation", "/tmp/spark-checkpoints/dead-letter")
        .outputMode("append")
        .trigger(processingTime="60 seconds")
        .start()
    )
    log.info("Dead-letter stream writer started → s3a://foresight-raw/dead-letter/")


def run_streaming_pipeline() -> None:
    """
    Build and start the complete FORESIGHT streaming pipeline.

    Pipeline:
        Kafka → parse → [valid] → aggregate → rule eval → alerts + MongoDB
                      → [invalid] → dead-letter (MinIO)
    """
    configure_logging(
        level=os.getenv("LOG_LEVEL", "INFO"),
        fmt=os.getenv("LOG_FORMAT", "text"),
        service_name="spark-streaming",
    )

    spark = create_spark_session()
    rules_loader = RulesLoader()
    alert_engine = AlertEngine(rules_loader=rules_loader)
    mongo_sink = MongoDBSink()

    log.info("Reading from Kafka...")
    raw_df = read_kafka_stream(spark)
    valid_df, dead_letter_df = parse_sensor_readings(raw_df)

    # Dead-letter sink
    write_dead_letters(dead_letter_df)

    # Windowed aggregations
    agg_5min, agg_1hr, agg_24hr = apply_windowed_aggregations(valid_df)

    # Write 5-minute aggregations to MongoDB (primary time-series store)
    mongo_query_5min = mongo_sink.write_stream(agg_5min, window_size="5min")  # noqa: F841
    mongo_query_1hr = mongo_sink.write_stream(agg_1hr, window_size="1hour")  # noqa: F841

    # Alert evaluation on 5-minute window (fastest detection)
    alert_query = alert_engine.evaluate_stream(agg_5min)  # noqa: F841

    log.info("All streaming queries started. Waiting for termination...")
    spark.streams.awaitAnyTermination()


if __name__ == "__main__":
    run_streaming_pipeline()
