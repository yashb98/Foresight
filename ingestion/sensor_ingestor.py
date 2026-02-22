#!/usr/bin/env python3
# =============================================================================
# FORESIGHT — Real Sensor Data Ingestor
# Reads real sensor data and publishes to Kafka
# =============================================================================

import os
import sys
import json
import time
import argparse
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from pathlib import Path

from kafka import KafkaProducer
from kafka.errors import KafkaError
import pandas as pd

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# =============================================================================
# Configuration
# =============================================================================

KAFKA_BOOTSTRAP_SERVERS = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:29092")
KAFKA_TOPIC = os.environ.get("KAFKA_TOPIC", "sensor_readings")


# =============================================================================
# Kafka Producer
# =============================================================================

class SensorDataProducer:
    """Producer for sending sensor data to Kafka."""
    
    def __init__(self, bootstrap_servers: str = KAFKA_BOOTSTRAP_SERVERS):
        self.bootstrap_servers = bootstrap_servers
        self.producer = None
        self._connect()
    
    def _connect(self):
        """Establish connection to Kafka."""
        try:
            self.producer = KafkaProducer(
                bootstrap_servers=self.bootstrap_servers,
                value_serializer=lambda v: json.dumps(v, default=str).encode('utf-8'),
                key_serializer=lambda k: k.encode('utf-8') if k else None,
                acks='all',
                retries=3,
                retry_backoff_ms=1000,
                request_timeout_ms=30000,
            )
            logger.info(f"Connected to Kafka at {self.bootstrap_servers}")
        except Exception as e:
            logger.error(f"Failed to connect to Kafka: {e}")
            raise
    
    def send_reading(self, reading: Dict[str, Any], topic: str = KAFKA_TOPIC) -> bool:
        """Send a single sensor reading to Kafka."""
        try:
            # Use asset_id as key for partitioning
            key = reading.get("asset_id", "unknown")
            
            future = self.producer.send(topic, key=key, value=reading)
            record_metadata = future.get(timeout=10)
            
            logger.debug(
                f"Sent to {record_metadata.topic} partition {record_metadata.partition} "
                f"offset {record_metadata.offset}"
            )
            return True
            
        except KafkaError as e:
            logger.error(f"Failed to send message: {e}")
            return False
    
    def send_batch(self, readings: list, topic: str = KAFKA_TOPIC) -> int:
        """Send multiple readings to Kafka."""
        success_count = 0
        
        for reading in readings:
            if self.send_reading(reading, topic):
                success_count += 1
        
        return success_count
    
    def flush(self):
        """Flush all pending messages."""
        self.producer.flush()
    
    def close(self):
        """Close the producer."""
        if self.producer:
            self.producer.close()
            logger.info("Kafka producer closed")


# =============================================================================
# Data Sources
# =============================================================================

def read_csv_sensor_data(file_path: str) -> pd.DataFrame:
    """Read sensor data from CSV file."""
    logger.info(f"Reading sensor data from {file_path}")
    
    df = pd.read_csv(file_path)
    
    # Standardize column names
    column_mapping = {
        'timestamp': 'timestamp',
        'time': 'timestamp',
        'date': 'timestamp',
        'asset_id': 'asset_id',
        'asset': 'asset_id',
        'equipment_id': 'asset_id',
        'sensor_id': 'sensor_id',
        'sensor': 'sensor_id',
        'sensor_type': 'sensor_type',
        'type': 'sensor_type',
        'value': 'value',
        'reading': 'value',
        'unit': 'unit',
        'tenant_id': 'tenant_id',
        'tenant': 'tenant_id',
    }
    
    df = df.rename(columns={k: v for k, v in column_mapping.items() if k in df.columns})
    
    # Ensure required columns exist
    required = ['timestamp', 'asset_id', 'sensor_id', 'value']
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")
    
    return df


def read_json_sensor_data(file_path: str) -> list:
    """Read sensor data from JSON file (one record per line or array)."""
    logger.info(f"Reading sensor data from {file_path}")
    
    with open(file_path, 'r') as f:
        content = f.read().strip()
    
    # Try parsing as JSON array
    if content.startswith('['):
        data = json.loads(content)
    else:
        # Parse as NDJSON (one JSON per line)
        data = [json.loads(line) for line in content.split('\n') if line.strip()]
    
    return data


def validate_reading(reading: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Validate and normalize a sensor reading."""
    # Required fields
    if 'asset_id' not in reading or 'sensor_id' not in reading:
        return None
    
    if 'value' not in reading:
        return None
    
    # Normalize timestamp
    if 'timestamp' not in reading:
        reading['timestamp'] = datetime.now(timezone.utc).isoformat()
    
    # Add default tenant if not present
    if 'tenant_id' not in reading:
        reading['tenant_id'] = '550e8400-e29b-41d4-a716-446655440000'
    
    # Ensure value is numeric
    try:
        reading['value'] = float(reading['value'])
    except (ValueError, TypeError):
        return None
    
    # Add quality flag
    if 'quality' not in reading:
        reading['quality'] = 'good'
    
    return reading


# =============================================================================
# Main Ingestion Functions
# =============================================================================

def ingest_from_csv(file_path: str, producer: SensorDataProducer, realtime: bool = False, speed_factor: float = 1.0):
    """Ingest sensor data from CSV file."""
    df = read_csv_sensor_data(file_path)
    
    logger.info(f"Read {len(df)} records from CSV")
    
    # Convert DataFrame to list of dicts
    records = df.to_dict('records')
    
    if realtime and 'timestamp' in df.columns:
        # Replay data in real-time based on timestamps
        ingest_realtime(records, producer, speed_factor)
    else:
        # Send all at once
        for record in records:
            validated = validate_reading(record)
            if validated:
                producer.send_reading(validated)
        
        producer.flush()
        logger.info(f"Sent {len(records)} records to Kafka")


def ingest_from_json(file_path: str, producer: SensorDataProducer):
    """Ingest sensor data from JSON file."""
    records = read_json_sensor_data(file_path)
    
    logger.info(f"Read {len(records)} records from JSON")
    
    valid_count = 0
    for record in records:
        validated = validate_reading(record)
        if validated:
            producer.send_reading(validated)
            valid_count += 1
    
    producer.flush()
    logger.info(f"Sent {valid_count} valid records to Kafka")


def ingest_realtime(records: list, producer: SensorDataProducer, speed_factor: float = 1.0):
    """
    Replay sensor data in real-time based on timestamps.
    
    Args:
        records: List of sensor readings with timestamps
        producer: Kafka producer
        speed_factor: Multiplier for replay speed (1.0 = real-time, 10.0 = 10x faster)
    """
    # Parse timestamps
    timestamps = []
    for r in records:
        try:
            ts = pd.to_datetime(r['timestamp'])
            timestamps.append(ts)
        except:
            timestamps.append(None)
    
    # Filter out records with invalid timestamps
    valid_records = [(r, ts) for r, ts in zip(records, timestamps) if ts is not None]
    valid_records.sort(key=lambda x: x[1])  # Sort by timestamp
    
    if not valid_records:
        logger.warning("No valid timestamps found for realtime playback")
        return
    
    logger.info(f"Replaying {len(valid_records)} records in realtime (speed: {speed_factor}x)")
    
    start_time = time.time()
    first_record_time = valid_records[0][1]
    
    for record, record_time in valid_records:
        # Calculate when this record should be sent
        elapsed_simulated = (record_time - first_record_time).total_seconds() / speed_factor
        elapsed_real = time.time() - start_time
        
        wait_time = elapsed_simulated - elapsed_real
        if wait_time > 0:
            time.sleep(wait_time)
        
        # Update timestamp to current time
        record['timestamp'] = datetime.now(timezone.utc).isoformat()
        record['original_timestamp'] = record_time.isoformat()
        
        validated = validate_reading(record)
        if validated:
            producer.send_reading(validated)
        
        # Log progress
        if valid_records.index((record, record_time)) % 1000 == 0:
            logger.info(f"Replayed {valid_records.index((record, record_time))} records...")
    
    producer.flush()
    logger.info("Realtime replay completed")


def ingest_live_sensors(producer: SensorDataProducer, interval: float = 1.0):
    """
    Ingest data from live sensors (placeholder for actual sensor integration).
    
    In production, this would connect to:
    - MQTT broker
    - OPC-UA server
    - Modbus TCP
    - REST API polling
    - etc.
    """
    logger.info(f"Starting live sensor ingestion (interval: {interval}s)")
    
    try:
        while True:
            # This is where you'd read from actual sensors
            # For now, just log that we're waiting
            logger.debug("Waiting for live sensor data...")
            time.sleep(interval)
            
    except KeyboardInterrupt:
        logger.info("Live ingestion stopped")


# =============================================================================
# CLI Entry Point
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="FORESIGHT Sensor Data Ingestor - Send real sensor data to Kafka"
    )
    parser.add_argument(
        "source",
        help="Path to sensor data file (CSV or JSON) or 'live' for live ingestion"
    )
    parser.add_argument(
        "--bootstrap-servers",
        default=KAFKA_BOOTSTRAP_SERVERS,
        help="Kafka bootstrap servers"
    )
    parser.add_argument(
        "--topic",
        default=KAFKA_TOPIC,
        help="Kafka topic to publish to"
    )
    parser.add_argument(
        "--realtime",
        action="store_true",
        help="Replay CSV data in real-time based on timestamps"
    )
    parser.add_argument(
        "--speed",
        type=float,
        default=1.0,
        help="Speed factor for realtime replay (default: 1.0)"
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=1.0,
        help="Polling interval for live ingestion (seconds)"
    )
    
    args = parser.parse_args()
    
    # Create producer
    producer = SensorDataProducer(args.bootstrap_servers)
    
    try:
        if args.source.lower() == 'live':
            ingest_live_sensors(producer, args.interval)
        elif args.source.endswith('.csv'):
            ingest_from_csv(args.source, producer, args.realtime, args.speed)
        elif args.source.endswith('.json') or args.source.endswith('.jsonl'):
            ingest_from_json(args.source, producer)
        else:
            logger.error(f"Unsupported file format: {args.source}")
            sys.exit(1)
    
    except KeyboardInterrupt:
        logger.info("Ingestion interrupted by user")
    finally:
        producer.close()


if __name__ == "__main__":
    main()
