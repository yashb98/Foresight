#!/usr/bin/env python3
"""
FORESIGHT — Sensor Data Simulator

Generates realistic time-series sensor telemetry for N assets across M tenants
and publishes each reading to Kafka topic 'sensor-readings'.

Sensor physics:
  - Temperature: sinusoidal daily cycle (15–95°C) with random walk drift
  - Vibration:   log-normal baseline with bearing wear simulation (0–50 mm/s)
  - Pressure:    mean-reverting Ornstein-Uhlenbeck process (0–200 bar)
  - RPM:         setpoint tracking with load variation (0–3500 RPM)

Anomaly injection:
  - Each asset has a configurable failure probability (default 5%)
  - When an anomaly spike is injected, values breach configured thresholds
    so the streaming alert engine can fire within the 30-second SLA

Usage:
    python ingestion/sensor_simulator.py \
        --assets 30 \
        --tenants 2 \
        --frequency-seconds 1 \
        --duration-seconds 300    # run for 5 minutes then exit

    # Run indefinitely:
    python ingestion/sensor_simulator.py --assets 30 --frequency-seconds 2

Acceptance criteria:
    ☑ Visible Kafka messages in kafka-ui at localhost:8090
    ☑ MinIO receives partitioned JSON files
    ☑ 1,000+ messages in 5 minutes at --frequency-seconds 1 and --assets 30
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
import random
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from dotenv import load_dotenv

load_dotenv()

from kafka import KafkaProducer
from kafka.errors import KafkaError

from common.logging_config import configure_logging
from common.models import MetricName, QualityFlag, SensorReading
from ingestion.minio_writer import MinIOWriter

log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Asset state machine — one per simulated asset
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class AssetState:
    """
    Stateful sensor state for a single asset.
    Tracks current sensor values and drift parameters across timesteps.
    """

    asset_id: str
    tenant_id: str
    asset_type: str

    # Current sensor values
    temperature: float = field(default_factory=lambda: random.uniform(25, 55))
    vibration: float = field(default_factory=lambda: random.uniform(5, 20))
    pressure: float = field(default_factory=lambda: random.uniform(80, 130))
    rpm: float = field(default_factory=lambda: random.uniform(1500, 2500))

    # Degradation state
    degradation_level: float = 0.0   # 0.0 = healthy, 1.0 = about to fail
    in_anomaly: bool = False
    anomaly_ticks_remaining: int = 0

    # OU process parameters for pressure
    pressure_mean: float = field(default_factory=lambda: random.uniform(90, 130))
    pressure_theta: float = 0.15     # mean reversion speed
    pressure_sigma: float = 2.5      # volatility

    def __post_init__(self) -> None:
        self.pressure_mean = self.pressure  # initialise mean to starting value


@dataclass
class SimulatorConfig:
    """Runtime configuration for the simulator."""

    asset_ids: List[str]
    tenant_ids: List[str]
    frequency_seconds: float
    anomaly_probability: float = 0.005   # probability per tick of starting anomaly
    minio_flush_every: int = 100         # write to MinIO every N readings
    kafka_topic: str = "sensor-readings"
    kafka_bootstrap_servers: str = "kafka:9092"


# ─────────────────────────────────────────────────────────────────────────────
# Sensor physics functions
# ─────────────────────────────────────────────────────────────────────────────

def simulate_temperature(state: AssetState, tick: int) -> float:
    """
    Simulate temperature with:
    - Sinusoidal daily cycle (±10°C amplitude)
    - Random walk noise
    - Degradation drift (increasing baseline as asset wears)
    - Anomaly spike when in_anomaly=True

    Args:
        state: Current asset state (modified in place).
        tick:  Simulation tick counter (used for phase in sine wave).

    Returns:
        New temperature reading in °C.
    """
    daily_cycle = 10.0 * math.sin(2 * math.pi * tick / (3600 / 1))  # 1-hour period at 1Hz
    noise = random.gauss(0, 0.3)
    drift = state.degradation_level * 20.0  # up to +20°C when fully degraded

    base = state.temperature + noise + drift * 0.01
    base = base + daily_cycle * 0.01   # gradual daily variation

    if state.in_anomaly:
        base += random.uniform(20, 40)  # spike above threshold (85°C threshold)

    state.temperature = max(10.0, min(110.0, base))
    return round(state.temperature, 2)


def simulate_vibration(state: AssetState) -> float:
    """
    Simulate vibration using a log-normal process.
    Bearing wear increases baseline progressively.

    Args:
        state: Current asset state.

    Returns:
        New vibration reading in mm/s.
    """
    bearing_wear_factor = 1.0 + state.degradation_level * 3.0
    base = state.vibration * bearing_wear_factor
    noise = random.gauss(0, 0.5)
    new_val = abs(base + noise)

    if state.in_anomaly:
        new_val += random.uniform(15, 30)  # spike above 35 mm/s threshold

    state.vibration = max(0.0, min(60.0, new_val * 0.95 + state.vibration * 0.05))
    return round(state.vibration, 3)


def simulate_pressure(state: AssetState) -> float:
    """
    Simulate pressure using Ornstein-Uhlenbeck mean-reverting process.
    More realistic than random walk for fluid/gas systems.

    Args:
        state: Current asset state.

    Returns:
        New pressure reading in bar.
    """
    dt = 1.0
    # OU process: dP = θ(μ - P)dt + σ√dt * N(0,1)
    drift = state.pressure_theta * (state.pressure_mean - state.pressure) * dt
    diffusion = state.pressure_sigma * math.sqrt(dt) * random.gauss(0, 1)
    state.pressure = state.pressure + drift + diffusion

    if state.in_anomaly:
        state.pressure += random.uniform(40, 60)  # spike above 180 bar threshold

    state.pressure = max(0.0, min(220.0, state.pressure))
    return round(state.pressure, 2)


def simulate_rpm(state: AssetState) -> float:
    """
    Simulate RPM with setpoint tracking and load variation.
    Slowdown occurs with degradation; stalls with anomaly.

    Args:
        state: Current asset state.

    Returns:
        New RPM reading.
    """
    setpoint = 2000.0 * (1.0 - state.degradation_level * 0.3)
    noise = random.gauss(0, 20)
    state.rpm = state.rpm + 0.1 * (setpoint - state.rpm) + noise

    if state.in_anomaly:
        state.rpm *= 0.4   # significant RPM drop — triggers low RPM alert (<500)

    state.rpm = max(0.0, min(3600.0, state.rpm))
    return round(state.rpm, 1)


def update_anomaly_state(state: AssetState, config: SimulatorConfig) -> None:
    """
    Update the anomaly state machine for an asset.
    Anomalies last 5–30 ticks, then reset.

    Args:
        state:  Asset state (modified in place).
        config: Simulator configuration.
    """
    if state.in_anomaly:
        state.anomaly_ticks_remaining -= 1
        if state.anomaly_ticks_remaining <= 0:
            state.in_anomaly = False
            log.debug("Anomaly ended for asset %s", state.asset_id)
    elif random.random() < config.anomaly_probability:
        state.in_anomaly = True
        state.anomaly_ticks_remaining = random.randint(5, 30)
        log.info(
            "ANOMALY injected for asset %s (tenant %s) — %d ticks",
            state.asset_id,
            state.tenant_id,
            state.anomaly_ticks_remaining,
        )

    # Gradual degradation drift
    state.degradation_level = min(
        1.0, state.degradation_level + random.uniform(0, 0.0001)
    )


# ─────────────────────────────────────────────────────────────────────────────
# Kafka producer
# ─────────────────────────────────────────────────────────────────────────────

def create_kafka_producer(bootstrap_servers: str) -> KafkaProducer:
    """
    Create and return a configured KafkaProducer.

    Args:
        bootstrap_servers: Comma-separated Kafka broker addresses.

    Returns:
        Connected KafkaProducer instance.

    Raises:
        RuntimeError: If Kafka is not reachable after retries.
    """
    for attempt in range(10):
        try:
            producer = KafkaProducer(
                bootstrap_servers=bootstrap_servers,
                value_serializer=lambda v: json.dumps(v, default=str).encode("utf-8"),
                key_serializer=lambda k: k.encode("utf-8") if k else None,
                acks="all",
                retries=3,
                max_in_flight_requests_per_connection=5,
                compression_type="gzip",
                batch_size=16384,
                linger_ms=10,            # 10ms batching window
                buffer_memory=33554432,  # 32MB buffer
            )
            log.info("Kafka producer connected: %s", bootstrap_servers)
            return producer
        except KafkaError as e:
            log.warning(
                "Kafka not ready (attempt %d/10): %s — retrying in 5s", attempt + 1, e
            )
            time.sleep(5)

    raise RuntimeError(f"Cannot connect to Kafka at {bootstrap_servers} after 10 attempts")


def publish_reading(
    producer: KafkaProducer, reading: SensorReading, topic: str
) -> None:
    """
    Publish a single SensorReading to Kafka.
    Key = tenant_id:asset_id for partition affinity (same asset → same partition).

    Args:
        producer: Active KafkaProducer.
        reading:  SensorReading Pydantic model to publish.
        topic:    Kafka topic name.
    """
    key = f"{reading.tenant_id}:{reading.asset_id}"
    value = reading.to_kafka_dict()

    producer.send(
        topic,
        key=key,
        value=value,
        headers=[
            ("tenant_id", reading.tenant_id.encode()),
            ("metric_name", reading.metric_name.encode()),
            ("source", reading.source.encode()),
        ],
    )


# ─────────────────────────────────────────────────────────────────────────────
# Main simulator loop
# ─────────────────────────────────────────────────────────────────────────────

METRIC_CONFIG = {
    MetricName.TEMPERATURE: {"unit": "degC", "fn": simulate_temperature},
    MetricName.VIBRATION: {"unit": "mm_s", "fn": simulate_vibration},
    MetricName.PRESSURE: {"unit": "bar", "fn": simulate_pressure},
    MetricName.RPM: {"unit": "rpm", "fn": simulate_rpm},
}


def run_simulator(
    asset_count: int,
    tenant_count: int = 2,
    frequency_seconds: float = 1.0,
    duration_seconds: Optional[int] = None,
    kafka_bootstrap: Optional[str] = None,
    enable_minio: bool = True,
) -> None:
    """
    Main simulator entry point. Generates and publishes sensor data.

    Args:
        asset_count:        Number of assets per tenant to simulate.
        tenant_count:       Number of tenants (max 2 for seed data compatibility).
        frequency_seconds:  Seconds between readings per asset.
        duration_seconds:   Total runtime in seconds. None = run indefinitely.
        kafka_bootstrap:    Kafka bootstrap servers. Reads from env if None.
        enable_minio:       Whether to write batches to MinIO.
    """
    configure_logging(
        level=os.getenv("LOG_LEVEL", "INFO"),
        fmt=os.getenv("LOG_FORMAT", "text"),
        service_name="sensor-simulator",
    )

    bootstrap = kafka_bootstrap or os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
    topic = os.getenv("KAFKA_TOPIC_SENSOR_DATA", "sensor-readings")

    # Test tenant IDs matching seed.py
    tenant_ids = [
        "11111111-1111-1111-1111-111111111111",
        "22222222-2222-2222-2222-222222222222",
    ][:tenant_count]

    asset_types = ["pump", "turbine", "transformer", "compressor", "motor"]

    # Build asset states
    states: List[AssetState] = []
    for t_id in tenant_ids:
        for i in range(asset_count):
            asset_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{t_id}-asset-{i:04d}"))
            states.append(
                AssetState(
                    asset_id=asset_id,
                    tenant_id=t_id,
                    asset_type=asset_types[i % len(asset_types)],
                )
            )

    config = SimulatorConfig(
        asset_ids=[s.asset_id for s in states],
        tenant_ids=tenant_ids,
        frequency_seconds=frequency_seconds,
        kafka_topic=topic,
        kafka_bootstrap_servers=bootstrap,
    )

    producer = create_kafka_producer(bootstrap)

    minio: Optional[MinIOWriter] = None
    if enable_minio:
        try:
            minio = MinIOWriter()
            if not minio.check_bucket_exists():
                log.warning("MinIO bucket not accessible — MinIO writes disabled")
                minio = None
        except Exception as e:
            log.warning("MinIO init failed (%s) — continuing without MinIO", e)
            minio = None

    tick = 0
    start_time = time.monotonic()
    total_published = 0
    minio_buffer: Dict[str, List[dict]] = {t: [] for t in tenant_ids}

    log.info(
        "Simulator started: %d assets × %d tenants = %d total assets | %.1fs interval",
        asset_count,
        tenant_count,
        len(states),
        frequency_seconds,
    )

    try:
        while True:
            loop_start = time.monotonic()

            for state in states:
                update_anomaly_state(state, config)

                for metric, meta in METRIC_CONFIG.items():
                    # Call the physics function
                    if metric == MetricName.TEMPERATURE:
                        value = meta["fn"](state, tick)
                    else:
                        value = meta["fn"](state)

                    quality = (
                        QualityFlag.SUSPECT
                        if state.in_anomaly
                        else (
                            QualityFlag.DEGRADED
                            if state.degradation_level > 0.5
                            else QualityFlag.GOOD
                        )
                    )

                    reading = SensorReading(
                        tenant_id=state.tenant_id,
                        asset_id=state.asset_id,
                        timestamp=datetime.now(tz=timezone.utc),
                        metric_name=metric,
                        value=value,
                        unit=meta["unit"],
                        quality_flag=quality,
                        source="simulator",
                    )

                    publish_reading(producer, reading, topic)
                    total_published += 1

                    if minio:
                        minio_buffer[state.tenant_id].append(reading.to_kafka_dict())

            # Flush Kafka buffer periodically
            if tick % 10 == 0:
                producer.flush()

            # Flush to MinIO every N readings per tenant
            if minio and tick % config.minio_flush_every == 0 and tick > 0:
                for t_id, records in minio_buffer.items():
                    if records:
                        try:
                            minio.write_records(records, t_id, "sensors")
                        except Exception as e:
                            log.error("MinIO write failed: %s", e)
                        minio_buffer[t_id] = []

            tick += 1

            if tick % 100 == 0:
                elapsed = time.monotonic() - start_time
                rate = total_published / elapsed if elapsed > 0 else 0
                log.info(
                    "Tick %d | Published: %d | Rate: %.1f msg/s | Anomalies: %d",
                    tick,
                    total_published,
                    rate,
                    sum(1 for s in states if s.in_anomaly),
                )

            # Check duration limit
            if duration_seconds and (time.monotonic() - start_time) >= duration_seconds:
                log.info(
                    "Duration limit reached (%ds). Total published: %d",
                    duration_seconds,
                    total_published,
                )
                break

            # Sleep for the remaining interval
            elapsed_loop = time.monotonic() - loop_start
            sleep_time = max(0, frequency_seconds - elapsed_loop)
            if sleep_time > 0:
                time.sleep(sleep_time)

    except KeyboardInterrupt:
        log.info("Simulator stopped by user. Total published: %d", total_published)
    finally:
        producer.flush()
        producer.close()
        log.info("Kafka producer closed.")


# ─────────────────────────────────────────────────────────────────────────────
# CLI entry point
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="FORESIGHT Sensor Simulator — publishes sensor telemetry to Kafka"
    )
    parser.add_argument(
        "--assets",
        type=int,
        default=30,
        help="Number of assets per tenant to simulate (default: 30)",
    )
    parser.add_argument(
        "--tenants",
        type=int,
        default=2,
        choices=[1, 2],
        help="Number of tenants to simulate (default: 2)",
    )
    parser.add_argument(
        "--frequency-seconds",
        type=float,
        default=1.0,
        help="Seconds between readings per asset (default: 1.0)",
    )
    parser.add_argument(
        "--duration-seconds",
        type=int,
        default=None,
        help="Total run duration in seconds. Omit to run indefinitely.",
    )
    parser.add_argument(
        "--no-minio",
        action="store_true",
        help="Disable MinIO writes (Kafka only)",
    )
    parser.add_argument(
        "--kafka-bootstrap",
        type=str,
        default=None,
        help="Kafka bootstrap servers (overrides KAFKA_BOOTSTRAP_SERVERS env var)",
    )

    args = parser.parse_args()

    run_simulator(
        asset_count=args.assets,
        tenant_count=args.tenants,
        frequency_seconds=args.frequency_seconds,
        duration_seconds=args.duration_seconds,
        kafka_bootstrap=args.kafka_bootstrap,
        enable_minio=not args.no_minio,
    )
