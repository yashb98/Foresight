#!/usr/bin/env python3
"""
FORESIGHT — Data Seeding Script
Creates sample assets, sensors, and maintenance records for testing
"""

import asyncio
import argparse
import random
from datetime import datetime, timedelta
from decimal import Decimal
from uuid import uuid4, UUID

import asyncpg
from kafka import KafkaProducer
import json
import os

# Default tenant ID
DEFAULT_TENANT_ID = UUID("550e8400-e29b-41d4-a716-446655440000")

ASSET_TYPES = [
    ("pump", "centrifugal", "critical"),
    ("pump", "positive_displacement", "high"),
    ("motor", "induction", "critical"),
    ("motor", "synchronous", "high"),
    ("turbine", "gas", "critical"),
    ("compressor", "reciprocating", "high"),
    ("compressor", "centrifugal", "critical"),
    ("generator", "diesel", "high"),
]

SENSOR_CONFIGS = {
    "temperature": {"unit": "celsius", "min": 20, "max": 100, "threshold": 85},
    "vibration": {"unit": "mm/s", "min": 1, "max": 15, "threshold": 10},
    "pressure": {"unit": "bar", "min": 1, "max": 50, "threshold": 45},
    "flow": {"unit": "m3/h", "min": 10, "max": 200, "threshold": 180},
}

LOCATIONS = ["Building A", "Building B", "Building C", "Outdoor"]
MANUFACTURERS = ["Siemens", "ABB", "GE", "Schneider", "Emerson"]


async def create_database_connection():
    """Create database connection."""
    return await asyncpg.connect(
        host=os.environ.get("POSTGRES_HOST", "localhost"),
        port=os.environ.get("POSTGRES_PORT", "5432"),
        database=os.environ.get("POSTGRES_DB", "foresight"),
        user=os.environ.get("POSTGRES_USER", "foresight"),
        password=os.environ.get("POSTGRES_PASSWORD", "foresight"),
    )


def create_kafka_producer():
    """Create Kafka producer."""
    return KafkaProducer(
        bootstrap_servers=os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:29092"),
        value_serializer=lambda v: json.dumps(v, default=str).encode('utf-8'),
    )


async def seed_assets(conn: asyncpg.Connection, count: int = 10):
    """Create sample assets."""
    print(f"Creating {count} assets...")
    asset_ids = []
    
    for i in range(count):
        asset_type, category, criticality = random.choice(ASSET_TYPES)
        asset_id = f"ASSET-{1000 + i:04d}"
        
        result = await conn.fetchval(
            """
            INSERT INTO assets (tenant_id, asset_id, name, asset_type, category,
                manufacturer, location, criticality, status, install_date, purchase_cost)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            ON CONFLICT (tenant_id, asset_id) DO UPDATE SET name = EXCLUDED.name
            RETURNING id
            """,
            DEFAULT_TENANT_ID, asset_id, f"{asset_type.title()} {i+1}",
            asset_type, category, random.choice(MANUFACTURERS), random.choice(LOCATIONS),
            criticality, "operational",
            datetime.now() - timedelta(days=random.randint(365, 1825)),
            Decimal(str(random.randint(50000, 500000)))
        )
        asset_ids.append((result, asset_id))
    
    print(f"Created {len(asset_ids)} assets")
    return asset_ids


async def seed_sensors(conn: asyncpg.Connection, assets: list):
    """Create sensors for assets."""
    print(f"Creating sensors...")
    sensor_ids = []
    
    for asset_id, asset_external_id in assets:
        num_sensors = random.randint(2, 3)
        sensor_types = random.sample(list(SENSOR_CONFIGS.keys()), num_sensors)
        
        for sensor_type in sensor_types:
            config = SENSOR_CONFIGS[sensor_type]
            sensor_id = f"SNS-{asset_external_id}-{sensor_type.upper()}"
            
            result = await conn.fetchval(
                """
                INSERT INTO sensors (tenant_id, sensor_id, asset_id, name, sensor_type,
                    unit, sampling_rate, min_threshold, max_threshold)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                ON CONFLICT (tenant_id, sensor_id) DO UPDATE SET name = EXCLUDED.name
                RETURNING id
                """,
                DEFAULT_TENANT_ID, sensor_id, asset_id, f"{sensor_type.title()} Sensor",
                sensor_type, config["unit"], 60,
                Decimal(str(config["min"])), Decimal(str(config["max"]))
            )
            sensor_ids.append((result, sensor_id, sensor_type, asset_external_id, asset_id))
    
    print(f"Created {len(sensor_ids)} sensors")
    return sensor_ids


def generate_sensor_readings(sensors: list, hours: int = 24):
    """Generate historical sensor readings."""
    print(f"Generating {hours} hours of sensor readings...")
    producer = create_kafka_producer()
    readings_count = 0
    
    end_time = datetime.utcnow()
    start_time = end_time - timedelta(hours=hours)
    current_time = start_time
    
    while current_time < end_time:
        for sensor_id, sensor_external_id, sensor_type, asset_external_id, asset_id in sensors:
            config = SENSOR_CONFIGS[sensor_type]
            base_value = (config["min"] + config["max"]) / 2
            variation = (config["max"] - config["min"]) * 0.1
            value = base_value + random.uniform(-variation, variation)
            
            reading = {
                "timestamp": current_time.isoformat(),
                "tenant_id": str(DEFAULT_TENANT_ID),
                "asset_id": asset_external_id,
                "sensor_id": sensor_external_id,
                "sensor_type": sensor_type,
                "value": round(value, 3),
                "unit": config["unit"],
                "quality": "good"
            }
            producer.send("sensor_readings", value=reading)
            readings_count += 1
        
        current_time += timedelta(minutes=1)
        if readings_count % 1000 == 0:
            print(f"  Generated {readings_count} readings...")
    
    producer.flush()
    producer.close()
    print(f"Generated {readings_count} sensor readings")


async def main():
    parser = argparse.ArgumentParser(description="Seed FORESIGHT with sample data")
    parser.add_argument("--assets", type=int, default=10)
    parser.add_argument("--readings-hours", type=int, default=24)
    parser.add_argument("--skip-readings", action="store_true")
    args = parser.parse_args()
    
    print("=" * 60)
    print("FORESIGHT Data Seeding")
    print("=" * 60)
    
    conn = await create_database_connection()
    try:
        assets = await seed_assets(conn, args.assets)
        sensors = await seed_sensors(conn, assets)
        
        if not args.skip_readings:
            generate_sensor_readings(sensors, args.readings_hours)
        
        print("=" * 60)
        print("Seeding completed!")
        print(f"  Assets: {len(assets)}")
        print(f"  Sensors: {len(sensors)}")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
