#!/usr/bin/env python3
"""
FORESIGHT — Database Seed Script

Creates test tenants, assets, threshold rules, and 90 days of mock maintenance records.
Safe to re-run: uses upsert patterns (no duplicates on second run).

Usage:
    python seed.py                              # default: 2 tenants, 30 assets
    python seed.py --tenant-count 2 --asset-count 30
    python seed.py --drop-existing              # wipe and reseed (dev only)

Acceptance criteria:
    - 2 tenants created
    - 30 assets spread across 3 types
    - 5 threshold rules per tenant
    - 90 days of maintenance records per asset
"""

from __future__ import annotations

import argparse
import logging
import os
import random
import sys
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv

load_dotenv()

import sqlalchemy as sa
from passlib.context import CryptContext
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from infrastructure.db.base import (
    Alert,
    Asset,
    AssetHealthScore,
    Base,
    MaintenanceRecord,
    Tenant,
    ThresholdRule,
)

# ─────────────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("seed")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ─────────────────────────────────────────────────────────────────────────────
# Deterministic UUIDs for test data (stable across re-runs)
# ─────────────────────────────────────────────────────────────────────────────
TENANT_1_ID = "11111111-1111-1111-1111-111111111111"
TENANT_2_ID = "22222222-2222-2222-2222-222222222222"

TENANT_CONFIGS = [
    {
        "tenant_id": TENANT_1_ID,
        "name": "Meridian Power & Water",
        "client_id": "tenant1",
        "client_secret": "password123",
        "subscription_tier": "enterprise",
        "config_json": {
            "connected_systems": ["sap", "asset_suite"],
            "industry": "utilities",
            "timezone": "Europe/London",
            "currency": "GBP",
            "alert_email": "ops@meridian-power.com",
        },
    },
    {
        "tenant_id": TENANT_2_ID,
        "name": "TransRail Infrastructure Ltd",
        "client_id": "tenant2",
        "client_secret": "password456",
        "subscription_tier": "professional",
        "config_json": {
            "connected_systems": ["asset_suite"],
            "industry": "rail",
            "timezone": "Europe/London",
            "currency": "GBP",
            "alert_email": "maintenance@transrail.co.uk",
        },
    },
]

ASSET_TYPES = ["pump", "turbine", "transformer", "compressor", "motor"]
CRITICALITIES = ["low", "medium", "high", "critical"]
CRITICALITY_WEIGHTS = [0.2, 0.4, 0.3, 0.1]  # realistic distribution

LOCATIONS = [
    "Site A - Pump House 1",
    "Site A - Substation 3",
    "Site B - Turbine Hall",
    "Site B - Control Room",
    "Site C - Compressor Station",
    "Site C - Distribution Node",
    "Substation Alpha",
    "Pipeline Junction 7",
    "Cooling Tower East",
    "Generator Block 2",
]

MAINTENANCE_TYPES = [
    "preventive", "corrective", "predictive", "inspection",
    "lubrication", "calibration", "overhaul",
]
MAINTENANCE_OUTCOMES = ["success", "partial", "success", "success", "deferred"]

THRESHOLD_RULES_TEMPLATE = [
    {
        "metric_name": "temperature",
        "operator": "gt",
        "threshold_value": 85.0,
        "severity": "high",
        "description": "Temperature exceeds 85°C — risk of thermal damage",
    },
    {
        "metric_name": "temperature",
        "operator": "gt",
        "threshold_value": 95.0,
        "severity": "critical",
        "description": "Temperature exceeds 95°C — imminent failure risk",
    },
    {
        "metric_name": "vibration",
        "operator": "gt",
        "threshold_value": 35.0,
        "severity": "high",
        "description": "Vibration exceeds 35 mm/s — bearing wear likely",
    },
    {
        "metric_name": "pressure",
        "operator": "gt",
        "threshold_value": 180.0,
        "severity": "critical",
        "description": "Pressure exceeds 180 bar — safety threshold",
    },
    {
        "metric_name": "rpm",
        "operator": "lt",
        "threshold_value": 500.0,
        "severity": "medium",
        "description": "RPM below 500 — possible blockage or belt slip",
    },
]


def get_engine() -> sa.engine.Engine:
    """Create synchronous SQLAlchemy engine from DATABASE_URL_SYNC env var."""
    url = os.environ.get("DATABASE_URL_SYNC")
    if not url:
        raise RuntimeError(
            "DATABASE_URL_SYNC is not set. Ensure .env is loaded and PostgreSQL is running."
        )
    return create_engine(url, echo=False)


def create_tenant(session: Session, config: Dict[str, Any]) -> Tenant:
    """
    Upsert a tenant record. Returns the existing tenant if already present.

    Args:
        session: Active SQLAlchemy session.
        config:  Tenant configuration dictionary.

    Returns:
        Tenant ORM object.
    """
    existing = session.get(Tenant, config["tenant_id"])
    if existing:
        log.info("Tenant already exists: %s — skipping", config["name"])
        return existing

    tenant = Tenant(
        tenant_id=config["tenant_id"],
        name=config["name"],
        client_id=config["client_id"],
        client_secret_hash=pwd_context.hash(config["client_secret"]),
        subscription_tier=config["subscription_tier"],
        config_json=config["config_json"],
        is_active=True,
    )
    session.add(tenant)
    log.info("Created tenant: %s (%s)", config["name"], config["tenant_id"])
    return tenant


def create_assets(
    session: Session, tenant_id: str, asset_count: int
) -> List[Asset]:
    """
    Create N assets for a tenant, distributed across asset types.

    Args:
        session:     Active SQLAlchemy session.
        tenant_id:   Tenant UUID string.
        asset_count: Number of assets to create.

    Returns:
        List of Asset ORM objects.
    """
    assets = []
    type_distribution = {
        "pump": 0.35,
        "turbine": 0.25,
        "transformer": 0.20,
        "compressor": 0.12,
        "motor": 0.08,
    }

    for i in range(asset_count):
        asset_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{tenant_id}-asset-{i:04d}"))

        # Check if already exists
        existing = session.get(Asset, asset_id)
        if existing:
            assets.append(existing)
            continue

        # Weighted random asset type
        asset_type = random.choices(
            list(type_distribution.keys()),
            weights=list(type_distribution.values()),
        )[0]

        criticality = random.choices(CRITICALITIES, weights=CRITICALITY_WEIGHTS)[0]
        location = random.choice(LOCATIONS)
        install_years_ago = random.randint(1, 15)
        installed_date = (
            datetime.utcnow() - timedelta(days=install_years_ago * 365)
        ).date()

        asset = Asset(
            asset_id=asset_id,
            tenant_id=tenant_id,
            name=f"{asset_type.upper()}-{i+1:03d}",
            asset_type=asset_type,
            location=location,
            criticality=criticality,
            installed_date=installed_date,
            metadata_json={
                "manufacturer": random.choice(
                    ["Siemens", "GE", "ABB", "Schneider", "Emerson"]
                ),
                "model": f"Model-{random.randint(100, 999)}",
                "serial_number": f"SN{random.randint(10000, 99999)}",
                "rated_power_kw": random.choice([55, 110, 250, 500, 1000]),
                "install_years_ago": install_years_ago,
            },
            source_system=random.choice(["sap", "asset_suite"]),
            source_asset_id=f"SRC-{random.randint(10000, 99999)}",
            is_active=True,
        )
        session.add(asset)
        assets.append(asset)

    log.info("Assets ready: %d for tenant %s", len(assets), tenant_id)
    return assets


def create_threshold_rules(session: Session, tenant_id: str) -> List[ThresholdRule]:
    """
    Create 5 threshold rules per tenant using the standard rule templates.

    Args:
        session:   Active SQLAlchemy session.
        tenant_id: Tenant UUID string.

    Returns:
        List of ThresholdRule ORM objects.
    """
    rules = []
    for tmpl in THRESHOLD_RULES_TEMPLATE:
        # Deterministic rule_id based on tenant + metric + threshold
        rule_id = str(uuid.uuid5(
            uuid.NAMESPACE_DNS,
            f"{tenant_id}-{tmpl['metric_name']}-{tmpl['threshold_value']}",
        ))

        existing = session.get(ThresholdRule, rule_id)
        if existing:
            rules.append(existing)
            continue

        rule = ThresholdRule(
            rule_id=rule_id,
            tenant_id=tenant_id,
            metric_name=tmpl["metric_name"],
            operator=tmpl["operator"],
            threshold_value=tmpl["threshold_value"],
            severity=tmpl["severity"],
            description=tmpl["description"],
            active=True,
        )
        session.add(rule)
        rules.append(rule)

    log.info("Threshold rules ready: %d for tenant %s", len(rules), tenant_id)
    return rules


def create_maintenance_records(
    session: Session,
    assets: List[Asset],
    days_back: int = 90,
) -> int:
    """
    Generate realistic maintenance history for each asset over the past N days.
    Assets with higher criticality get more frequent maintenance.

    Args:
        session:   Active SQLAlchemy session.
        assets:    List of Asset objects to generate records for.
        days_back: How many days of history to generate.

    Returns:
        Number of records created.
    """
    frequency_map = {"low": 60, "medium": 30, "high": 14, "critical": 7}
    created_count = 0

    for asset in assets:
        freq_days = frequency_map.get(asset.criticality, 30)
        current_date = datetime.utcnow() - timedelta(days=days_back)

        while current_date < datetime.utcnow():
            # Add random jitter ±3 days
            jitter = timedelta(days=random.randint(-3, 3))
            performed_at = current_date + jitter

            record_id = str(uuid.uuid5(
                uuid.NAMESPACE_DNS,
                f"{asset.asset_id}-maint-{performed_at.date().isoformat()}",
            ))

            existing = session.get(MaintenanceRecord, record_id)
            if not existing:
                maint_type = random.choice(MAINTENANCE_TYPES)
                record = MaintenanceRecord(
                    record_id=record_id,
                    asset_id=asset.asset_id,
                    tenant_id=asset.tenant_id,
                    maintenance_type=maint_type,
                    performed_at=performed_at,
                    cost=round(random.uniform(500, 25000), 2),
                    outcome=random.choice(MAINTENANCE_OUTCOMES),
                    source_system=asset.source_system or "manual",
                    source_record_id=f"WO-{random.randint(100000, 999999)}",
                    description=f"{maint_type.capitalize()} maintenance on {asset.name}",
                )
                session.add(record)
                created_count += 1

            current_date += timedelta(days=freq_days)

    log.info("Maintenance records created: %d", created_count)
    return created_count


def create_sample_health_scores(
    session: Session, assets: List[Asset]
) -> None:
    """
    Seed 30 days of health scores per asset so the dashboard has data to show
    before the ML pipeline runs its first real scoring pass.

    Args:
        session: Active SQLAlchemy session.
        assets:  List of Asset objects.
    """
    today = datetime.utcnow().date()
    for asset in assets:
        for days_ago in range(30, 0, -1):
            score_date = today - timedelta(days=days_ago)
            score_id = str(uuid.uuid5(
                uuid.NAMESPACE_DNS, f"{asset.asset_id}-score-{score_date.isoformat()}"
            ))
            existing = session.get(AssetHealthScore, score_id)
            if existing:
                continue

            # Simulate degrading health for some assets
            base_health = random.uniform(60, 99)
            degradation = days_ago * random.uniform(-0.1, 0.3)
            health = min(max(base_health - degradation, 10), 100)

            prob_7d = round(max(0.0, min(1.0, (100 - health) / 200 + random.uniform(0, 0.05))), 4)
            prob_30d = round(max(prob_7d, min(1.0, prob_7d + random.uniform(0.02, 0.15))), 4)

            score = AssetHealthScore(
                score_id=score_id,
                asset_id=asset.asset_id,
                tenant_id=asset.tenant_id,
                score_date=score_date,
                health_score=round(health, 2),
                failure_prob_7d=prob_7d,
                failure_prob_30d=prob_30d,
                model_version="seed-v0.0",
                model_name="foresight-failure-predictor",
                top_features_json=[
                    {"feature": "vibration_mean_7d", "importance": 0.38, "value": 22.4},
                    {"feature": "temperature_max_24h", "importance": 0.27, "value": 78.3},
                    {"feature": "days_since_maintenance", "importance": 0.19, "value": 12},
                ],
                confidence_lower=max(0.0, prob_7d - 0.05),
                confidence_upper=min(1.0, prob_7d + 0.05),
            )
            session.add(score)

    log.info("Sample health scores seeded for %d assets (30 days each)", len(assets))


def create_sample_alerts(
    session: Session, assets: List[Asset], rules: List[ThresholdRule]
) -> None:
    """
    Seed a handful of active and resolved alerts for dashboard demonstration.

    Args:
        session: Active SQLAlchemy session.
        assets:  List of Asset objects.
        rules:   List of ThresholdRule objects for this tenant.
    """
    if not assets or not rules:
        return

    statuses = ["active", "active", "acknowledged", "resolved"]
    severities = ["high", "critical", "medium", "high"]

    for i in range(min(8, len(assets))):
        asset = assets[i % len(assets)]
        rule = random.choice(rules)
        alert_id = str(uuid.uuid5(
            uuid.NAMESPACE_DNS, f"{asset.asset_id}-alert-seed-{i}"
        ))
        existing = session.get(Alert, alert_id)
        if existing:
            continue

        status = statuses[i % len(statuses)]
        severity = severities[i % len(severities)]
        triggered_at = datetime.utcnow() - timedelta(hours=random.randint(1, 72))

        alert = Alert(
            alert_id=alert_id,
            asset_id=asset.asset_id,
            tenant_id=asset.tenant_id,
            rule_id=rule.rule_id,
            metric_name=rule.metric_name,
            actual_value=float(rule.threshold_value) + random.uniform(1, 15),
            threshold_value=float(rule.threshold_value),
            severity=severity,
            status=status,
            triggered_at=triggered_at,
            resolved_at=(
                triggered_at + timedelta(hours=random.randint(1, 24))
                if status == "resolved"
                else None
            ),
            acknowledged_by="ops_manager" if status in ("acknowledged", "resolved") else None,
            notes="Seeded test alert" if status == "resolved" else None,
        )
        session.add(alert)

    log.info("Sample alerts seeded for tenant assets")


def main(tenant_count: int = 2, asset_count: int = 30) -> None:
    """
    Main seed entry point.

    Args:
        tenant_count: Number of tenants to create (max 2 with current config).
        asset_count:  Total assets per tenant.
    """
    log.info("=" * 60)
    log.info("FORESIGHT Seed Script")
    log.info("Tenants: %d | Assets per tenant: %d", tenant_count, asset_count)
    log.info("=" * 60)

    engine = get_engine()

    # Create all tables (idempotent — won't overwrite existing)
    Base.metadata.create_all(engine, checkfirst=True)

    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    configs_to_use = TENANT_CONFIGS[:tenant_count]

    with SessionLocal() as session:
        try:
            for cfg in configs_to_use:
                log.info("Processing tenant: %s", cfg["name"])

                tenant = create_tenant(session, cfg)
                session.flush()

                assets = create_assets(session, tenant.tenant_id, asset_count)
                session.flush()

                rules = create_threshold_rules(session, tenant.tenant_id)
                session.flush()

                create_maintenance_records(session, assets, days_back=90)
                session.flush()

                create_sample_health_scores(session, assets)
                session.flush()

                create_sample_alerts(session, assets, rules)
                session.flush()

            session.commit()
            log.info("=" * 60)
            log.info("Seed complete. Summary:")
            log.info("  Tenants:              %d", len(configs_to_use))
            log.info("  Assets per tenant:    %d", asset_count)
            log.info("  Rules per tenant:     %d", len(THRESHOLD_RULES_TEMPLATE))
            log.info("  History:              90 days maintenance records")
            log.info("  Health scores:        30 days per asset (sample)")
            log.info("=" * 60)

        except Exception as exc:
            session.rollback()
            log.error("Seed failed: %s", exc, exc_info=True)
            raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FORESIGHT database seed script")
    parser.add_argument("--tenant-count", type=int, default=2, choices=[1, 2])
    parser.add_argument("--asset-count", type=int, default=30)
    parser.add_argument(
        "--drop-existing",
        action="store_true",
        help="DANGER: Drop all tables and reseed. Development only.",
    )
    args = parser.parse_args()

    if args.drop_existing:
        log.warning("DROP EXISTING tables requested — this is destructive!")
        confirm = input("Type 'yes' to confirm: ")
        if confirm.strip().lower() != "yes":
            log.info("Aborted.")
            sys.exit(0)
        engine = get_engine()
        Base.metadata.drop_all(engine)
        log.info("All tables dropped.")

    main(tenant_count=args.tenant_count, asset_count=args.asset_count)
