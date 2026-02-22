#!/usr/bin/env python3
# =============================================================================
# FORESIGHT — Spark Structured Streaming Consumer
# Consumes sensor readings from Kafka, processes, and writes to MongoDB
# =============================================================================

import os
import sys
import json
import logging
from datetime import datetime
from typing import Dict, Any

from pyspark.sql import SparkSession
from pyspark.sql.functions import (
    col, from_json, window, avg, max, min, stddev, count,
    current_timestamp, lit, to_timestamp, struct, when
)
from pyspark.sql.types import (
    StructType, StructField, StringType, DoubleType, 
    TimestampType, MapType
)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# =============================================================================
# Configuration
# =============================================================================

KAFKA_BOOTSTRAP_SERVERS = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
KAFKA_TOPIC = os.environ.get("KAFKA_TOPIC", "sensor_readings")
MONGO_URI = os.environ.get("MONGO_URI", "mongodb://mongodb:27017")
MONGO_DB = os.environ.get("MONGO_DB", "foresight")
CHECKPOINT_LOCATION = os.environ.get("CHECKPOINT_LOCATION", "/tmp/spark-checkpoints")

# =============================================================================
# Schema Definitions
# =============================================================================

# Schema for incoming sensor readings
sensor_reading_schema = StructType([
    StructField("timestamp", TimestampType(), True),
    StructField("tenant_id", StringType(), True),
    StructField("asset_id", StringType(), True),
    StructField("sensor_id", StringType(), True),
    StructField("sensor_type", StringType(), True),
    StructField("value", DoubleType(), True),
    StructField("unit", StringType(), True),
    StructField("quality", StringType(), True),
])

# =============================================================================
# Spark Session
# =============================================================================

def create_spark_session(app_name: str = "ForesightStreaming") -> SparkSession:
    """Create Spark session with required configurations."""
    return SparkSession.builder \
        .appName(app_name) \
        .config("spark.sql.streaming.checkpointLocation", CHECKPOINT_LOCATION) \
        .config("spark.mongodb.output.uri", MONGO_URI) \
        .config("spark.mongodb.output.database", MONGO_DB) \
        .config("spark.jars.packages", "org.apache.spark:spark-sql-kafka-0-10_2.12:3.4.0") \
        .getOrCreate()


# =============================================================================
# Stream Processing Functions
# =============================================================================

def create_kafka_stream(spark: SparkSession, topic: str = KAFKA_TOPIC):
    """Create Kafka stream source."""
    return spark \
        .readStream \
        .format("kafka") \
        .option("kafka.bootstrap.servers", KAFKA_BOOTSTRAP_SERVERS) \
        .option("subscribe", topic) \
        .option("startingOffsets", "latest") \
        .option("failOnDataLoss", "false") \
        .load()


def parse_sensor_data(df):
    """Parse JSON sensor data from Kafka."""
    # Parse the JSON value
    parsed = df.select(
        from_json(col("value").cast("string"), sensor_reading_schema).alias("data"),
        col("timestamp").alias("kafka_timestamp")
    ).select("data.*")
    
    return parsed


def create_5min_aggregations(df):
    """Create 5-minute windowed aggregations."""
    return df \
        .withWatermark("timestamp", "10 minutes") \
        .groupBy(
            window("timestamp", "5 minutes"),
            "tenant_id",
            "asset_id",
            "sensor_type"
        ) \
        .agg(
            count("*").alias("readings_count"),
            avg("value").alias("avg_value"),
            min("value").alias("min_value"),
            max("value").alias("max_value"),
            stddev("value").alias("std_dev")
        ) \
        .select(
            col("window.start").alias("window_start"),
            col("window.end").alias("window_end"),
            "tenant_id",
            "asset_id",
            "sensor_type",
            "readings_count",
            "avg_value",
            "min_value",
            "max_value",
            "std_dev",
            current_timestamp().alias("processed_at")
        )


def create_1hour_aggregations(df):
    """Create 1-hour windowed aggregations."""
    return df \
        .withWatermark("timestamp", "2 hours") \
        .groupBy(
            window("timestamp", "1 hour"),
            "tenant_id",
            "asset_id",
            "sensor_type"
        ) \
        .agg(
            count("*").alias("readings_count"),
            avg("value").alias("avg_value"),
            min("value").alias("min_value"),
            max("value").alias("max_value"),
            stddev("value").alias("std_dev")
        ) \
        .select(
            col("window.start").alias("window_start"),
            col("window.end").alias("window_end"),
            "tenant_id",
            "asset_id",
            "sensor_type",
            "readings_count",
            "avg_value",
            "min_value",
            "max_value",
            "std_dev",
            current_timestamp().alias("processed_at")
        )


def write_to_mongodb(df, collection: str, trigger_interval: str = "10 seconds"):
    """Write DataFrame to MongoDB collection."""
    return df \
        .writeStream \
        .format("mongodb") \
        .option("database", MONGO_DB) \
        .option("collection", collection) \
        .outputMode("append") \
        .option("checkpointLocation", f"{CHECKPOINT_LOCATION}/{collection}") \
        .trigger(processingTime=trigger_interval) \
        .start()


def write_raw_to_mongodb(df):
    """Write raw sensor readings to MongoDB."""
    return df \
        .writeStream \
        .format("mongodb") \
        .option("database", MONGO_DB) \
        .option("collection", "sensor_readings") \
        .outputMode("append") \
        .option("checkpointLocation", f"{CHECKPOINT_LOCATION}/raw_readings") \
        .trigger(processingTime="5 seconds") \
        .start()


# =============================================================================
# Main Processing Pipeline
# =============================================================================

def run_streaming_pipeline():
    """Run the main streaming pipeline."""
    logger.info("Starting FORESIGHT streaming pipeline...")
    logger.info(f"Kafka: {KAFKA_BOOTSTRAP_SERVERS}, Topic: {KAFKA_TOPIC}")
    logger.info(f"MongoDB: {MONGO_URI}/{MONGO_DB}")
    
    # Create Spark session
    spark = create_spark_session()
    spark.sparkContext.setLogLevel("WARN")
    
    try:
        # Create Kafka stream
        kafka_df = create_kafka_stream(spark)
        
        # Parse sensor data
        sensor_df = parse_sensor_data(kafka_df)
        
        # Filter out bad quality readings
        clean_df = sensor_df.filter(col("quality") != "bad")
        
        # Write raw readings to MongoDB
        raw_query = write_raw_to_mongodb(clean_df)
        logger.info("Raw readings stream started")
        
        # Create and write 5-minute aggregations
        agg_5min_df = create_5min_aggregations(clean_df)
        agg_5min_query = write_to_mongodb(agg_5min_df, "sensor_aggregations_5min", "1 minute")
        logger.info("5-minute aggregations stream started")
        
        # Create and write 1-hour aggregations
        agg_1h_df = create_1hour_aggregations(clean_df)
        agg_1h_query = write_to_mongodb(agg_1h_df, "sensor_aggregations_1h", "5 minutes")
        logger.info("1-hour aggregations stream started")
        
        # Wait for all streams
        logger.info("Streaming pipeline is running. Press Ctrl+C to stop.")
        spark.streams.awaitAnyTermination()
        
    except Exception as e:
        logger.exception(f"Streaming error: {e}")
        raise
    finally:
        spark.stop()


# =============================================================================
# Alert Detection Stream
# =============================================================================

def run_alert_detection_stream():
    """
    Separate stream for real-time alert detection.
    This monitors sensor values against thresholds and generates alerts.
    """
    logger.info("Starting alert detection stream...")
    
    spark = create_spark_session("ForesightAlertDetection")
    
    try:
        # Read from Kafka
        kafka_df = create_kafka_stream(spark)
        sensor_df = parse_sensor_data(kafka_df)
        
        # Simple threshold detection (can be extended with rules from PostgreSQL)
        # This is a basic example - in production, fetch rules from DB
        alerts_df = sensor_df \
            .filter(
                ((col("sensor_type") == "temperature") & (col("value") > 90)) |
                ((col("sensor_type") == "vibration") & (col("value") > 10))
            ) \
            .select(
                col("tenant_id"),
                col("asset_id"),
                col("sensor_id"),
                lit("threshold").alias("alert_type"),
                when(col("value") > 100, lit("critical")).otherwise(lit("warning")).alias("severity"),
                col("timestamp").alias("started_at"),
                struct(
                    col("sensor_type").alias("metric_name"),
                    col("value").alias("metric_value")
                ).alias("metadata")
            )
        
        # Write alerts to MongoDB for processing
        alert_query = alerts_df \
            .writeStream \
            .format("mongodb") \
            .option("database", MONGO_DB) \
            .option("collection", "detected_alerts") \
            .outputMode("append") \
            .option("checkpointLocation", f"{CHECKPOINT_LOCATION}/alerts") \
            .trigger(processingTime="5 seconds") \
            .start()
        
        logger.info("Alert detection stream started")
        spark.streams.awaitAnyTermination()
        
    except Exception as e:
        logger.exception(f"Alert detection error: {e}")
        raise
    finally:
        spark.stop()


# =============================================================================
# Entry Point
# =============================================================================

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="FORESIGHT Streaming Pipeline")
    parser.add_argument(
        "--mode",
        choices=["processing", "alerts", "both"],
        default="processing",
        help="Streaming mode to run"
    )
    
    args = parser.parse_args()
    
    if args.mode == "processing":
        run_streaming_pipeline()
    elif args.mode == "alerts":
        run_alert_detection_stream()
    else:
        # Run both in separate threads
        from threading import Thread
        
        processing_thread = Thread(target=run_streaming_pipeline)
        alert_thread = Thread(target=run_alert_detection_stream)
        
        processing_thread.start()
        alert_thread.start()
        
        processing_thread.join()
        alert_thread.join()
