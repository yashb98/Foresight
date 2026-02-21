#!/usr/bin/env python3
"""
FORESIGHT — Asset Suite 9 Connector

Extracts (or mocks) Hexagon Asset Suite 9 data across:
  1. Asset Register — asset hierarchy, specifications, location
  2. Work Management — work orders, failure history, outcomes
  3. Maintenance Schedules — upcoming planned maintenance calendar

Asset Suite 9 has a fundamentally different data model from SAP:
  - Asset IDs use a hierarchical path (e.g. 'SITE-A/BUILDING-3/PUMP-007')
  - Failure codes use an internal taxonomy (not SAP QMCOD)
  - Cost centres are called 'cost accounts'
  - Schedules are calendar-based (not floating)

Deliberate discrepancies from SAP data are injected to test reconciliation logic:
  - Different asset names for the same physical asset
  - Different cost figures (partial capture vs full)
  - Date mismatches on maintenance events (±2 days)

Usage:
    python ingestion/asset_suite_connector.py --tenant-id <UUID> --assets 30 --days-back 90
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import random
import sys
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from dotenv import load_dotenv

load_dotenv()

from kafka import KafkaProducer

from common.logging_config import configure_logging
from common.models import AssetSuiteRecord, SourceSystem
from ingestion.minio_writer import MinIOWriter

log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Asset Suite 9 data model constants
# ─────────────────────────────────────────────────────────────────────────────

AS9_ASSET_CLASSES = {
    "pump": "ROTATING/PUMP",
    "turbine": "ROTATING/TURBINE",
    "transformer": "ELECTRICAL/TRANSFORMER",
    "compressor": "ROTATING/COMPRESSOR",
    "motor": "ELECTRICAL/MOTOR",
}

AS9_SITE_CODES = ["SITE-A", "SITE-B", "SITE-C", "DEPOT-1", "SUBST-2"]
AS9_FAILURE_CODES = [
    "MECH-001",  # Mechanical failure
    "ELEC-002",  # Electrical fault
    "WEAR-003",  # Wear and tear
    "CORRO-004", # Corrosion
    "LEAK-005",  # Fluid leak
    "VIBE-006",  # Excessive vibration
    "TEMP-007",  # Thermal overload
    "ALIGN-008", # Misalignment
    "BLOCK-009", # Blockage
    "CAVI-010",  # Cavitation
]
AS9_WORK_TYPES = ["CORRECTIVE", "PREVENTIVE", "PREDICTIVE", "INSPECTION", "SHUTDOWN"]
AS9_PRIORITIES = ["1-EMERGENCY", "2-URGENT", "3-ROUTINE", "4-PLANNED"]
AS9_STATUSES = ["CLOSED", "CLOSED", "CLOSED", "IN-PROGRESS", "PLANNED"]


def generate_asset_register_record(
    asset_id: str,
    tenant_id: str,
    asset_type: str,
    asset_index: int,
    install_date: datetime,
) -> Dict[str, Any]:
    """
    Generate an Asset Suite 9 Asset Register record.

    Field names follow Asset Suite 9 REST API conventions.
    Deliberately uses different names/codes than SAP for reconciliation testing.

    Args:
        asset_id:     FORESIGHT internal UUID.
        tenant_id:    Tenant UUID.
        asset_type:   Asset category.
        asset_index:  Sequential asset number (used in hierarchical path).
        install_date: Installation date.

    Returns:
        Asset Suite 9 asset register dict.
    """
    site = random.choice(AS9_SITE_CODES)
    asset_class = AS9_ASSET_CLASSES.get(asset_type, "GENERAL/EQUIPMENT")
    # Different naming convention than SAP (deliberate discrepancy)
    as9_asset_id = f"{site}/BLDG-{random.randint(1,5)}/{asset_type.upper()}-{asset_index:03d}"

    return {
        # Asset Suite 9 fields
        "assetId": as9_asset_id,          # AS9 hierarchical path ID
        "assetNumber": f"AS9-{random.randint(10000, 99999)}",
        "assetName": f"{asset_type.capitalize()} {asset_index:03d} — {site}",
        "assetClass": asset_class,
        "parentId": f"{site}/BLDG-{random.randint(1,5)}",
        "locationCode": f"{site}-LOC-{random.randint(100, 999)}",
        "criticalityRating": random.choice(["A", "B", "C", "D"]),  # AS9 uses letters, not words
        "installDate": install_date.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "warrantyExpiry": (install_date + timedelta(days=365 * 5)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "manufacturer": random.choice(["Siemens", "GE Power", "ABB Ltd", "Flowserve", "Sulzer"]),
        "modelNumber": f"AS-MDL-{random.randint(1000, 9999)}",
        "serialNumber": f"AS9SN{random.randint(100000, 999999)}",
        "maintenanceStrategy": random.choice(["TBM", "CBM", "RCM"]),  # Time/Condition/Reliability-based
        "operatingHours": random.randint(5000, 80000),
        "costAccount": f"CA-{random.randint(1000, 9999)}",
        "lastInspectionDate": (datetime.now(tz=timezone.utc) - timedelta(
            days=random.randint(10, 120)
        )).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "nextScheduledMaintenance": (datetime.now(tz=timezone.utc) + timedelta(
            days=random.randint(7, 90)
        )).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "riskScore": round(random.uniform(1.0, 10.0), 1),
        "failureCodes": random.sample(AS9_FAILURE_CODES, k=random.randint(0, 3)),
        # FORESIGHT metadata
        "_foresight_asset_id": asset_id,
        "_foresight_tenant_id": tenant_id,
        "_foresight_extracted_at": datetime.now(tz=timezone.utc).isoformat(),
    }


def generate_work_management_records(
    as9_asset_id: str,
    foresight_asset_id: str,
    tenant_id: str,
    count: int = 8,
    days_back: int = 365,
) -> List[Dict[str, Any]]:
    """
    Generate Asset Suite 9 Work Management records.

    Deliberately has slight date mismatches vs SAP (±2 days) to test reconciliation.

    Args:
        as9_asset_id:         Asset Suite 9 hierarchical asset ID.
        foresight_asset_id:   FORESIGHT internal UUID.
        tenant_id:            Tenant UUID.
        count:                Number of work records to generate.
        days_back:            Historical range in days.

    Returns:
        List of work management record dicts.
    """
    records = []
    for i in range(count):
        days_ago = random.randint(0, days_back)
        # ±2 day jitter vs what SAP would show (deliberate discrepancy)
        jitter = timedelta(days=random.randint(-2, 2))
        work_date = datetime.now(tz=timezone.utc) - timedelta(days=days_ago) + jitter
        work_type = random.choice(AS9_WORK_TYPES)
        priority = random.choice(AS9_PRIORITIES)

        records.append({
            "workOrderId": f"AS9-WO-{random.randint(100000, 999999)}",
            "assetId": as9_asset_id,
            "workType": work_type,
            "priority": priority,
            "description": _work_description(work_type),
            "reportedDate": work_date.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "plannedStartDate": work_date.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "completionDate": (work_date + timedelta(hours=random.randint(1, 48))).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            ),
            "status": random.choice(AS9_STATUSES),
            "technicianCode": f"TECH-{random.randint(100, 999)}",
            "laborHours": round(random.uniform(0.5, 24.0), 1),
            # AS9 records costs slightly differently (e.g. excludes overhead)
            "materialCost": round(random.uniform(50, 5000), 2),
            "laborCost": round(random.uniform(100, 3000), 2),
            "totalCost": round(random.uniform(200, 8000), 2),  # may not match SAP exactly
            "failureCode": random.choice(AS9_FAILURE_CODES) if work_type == "CORRECTIVE" else None,
            "rootCause": _root_cause_text() if work_type == "CORRECTIVE" else None,
            "outcome": random.choice(["COMPLETED", "DEFERRED", "PARTIAL", "COMPLETED"]),
            "remarks": f"AS9 work record {i+1} for {work_type.lower()} maintenance",
            # FORESIGHT metadata
            "_foresight_asset_id": foresight_asset_id,
            "_foresight_tenant_id": tenant_id,
            "_foresight_extracted_at": datetime.now(tz=timezone.utc).isoformat(),
        })
    return records


def generate_maintenance_schedule(
    as9_asset_id: str,
    foresight_asset_id: str,
    tenant_id: str,
    months_ahead: int = 6,
) -> List[Dict[str, Any]]:
    """
    Generate upcoming maintenance schedule from Asset Suite 9.

    Args:
        as9_asset_id:         AS9 asset path.
        foresight_asset_id:   FORESIGHT UUID.
        tenant_id:            Tenant UUID.
        months_ahead:         How many months of schedule to generate.

    Returns:
        List of planned maintenance schedule entries.
    """
    schedule = []
    now = datetime.now(tz=timezone.utc)

    # Generate 2–5 upcoming maintenance events
    event_count = random.randint(2, 5)
    for i in range(event_count):
        days_ahead = random.randint(7, months_ahead * 30)
        planned_date = now + timedelta(days=days_ahead)

        schedule.append({
            "scheduleId": f"SCH-{random.randint(10000, 99999)}",
            "assetId": as9_asset_id,
            "workType": random.choice(["PREVENTIVE", "INSPECTION"]),
            "plannedDate": planned_date.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "estimatedDuration": f"{random.randint(2, 12)}h",
            "estimatedCost": round(random.uniform(500, 5000), 2),
            "maintenanceStrategy": random.choice(["TBM", "CBM"]),
            "taskDescription": random.choice([
                "Quarterly preventive maintenance",
                "Annual overhaul inspection",
                "6-monthly lubrication service",
                "Bi-annual calibration check",
                "Monthly condition monitoring",
            ]),
            "requiredParts": [
                f"PART-{random.randint(1000, 9999)}"
                for _ in range(random.randint(0, 3))
            ],
            # FORESIGHT metadata
            "_foresight_asset_id": foresight_asset_id,
            "_foresight_tenant_id": tenant_id,
            "_foresight_extracted_at": now.isoformat(),
        })
    return schedule


def _work_description(work_type: str) -> str:
    """Generate work description text for a given work type."""
    descriptions = {
        "CORRECTIVE": random.choice([
            "Emergency repair — bearing failure", "Corrective action — seal leak",
            "Unplanned replacement — impeller damage",
        ]),
        "PREVENTIVE": random.choice([
            "Scheduled PM service", "Quarterly preventive check",
            "Annual overhaul as per maintenance strategy",
        ]),
        "PREDICTIVE": "Predictive maintenance follow-up based on CBM data",
        "INSPECTION": random.choice(["Visual inspection", "NDE inspection", "Condition assessment"]),
        "SHUTDOWN": "Major planned shutdown maintenance",
    }
    return descriptions.get(work_type, "General maintenance task")


def _root_cause_text() -> str:
    """Generate a root cause analysis text."""
    return random.choice([
        "Normal wear and tear — end of design life",
        "Lack of lubrication — maintenance interval exceeded",
        "Process upset — cavitation induced damage",
        "Corrosive environment — material incompatibility",
        "Operator error — incorrect parameter settings",
        "Voltage transient — electrical surge damage",
        "Contamination ingress — filter bypass",
    ])


# ─────────────────────────────────────────────────────────────────────────────
# Asset Suite 9 Connector class
# ─────────────────────────────────────────────────────────────────────────────

class AssetSuiteConnector:
    """
    Extracts Asset Suite 9 data (mock or live via REST) and publishes to Kafka + MinIO.

    Args:
        tenant_id:  Tenant UUID.
        mode:       'mock' | 'live'
        kafka_bootstrap: Kafka bootstrap servers.
    """

    def __init__(
        self,
        tenant_id: str,
        mode: str = "mock",
        kafka_bootstrap: Optional[str] = None,
    ) -> None:
        self.tenant_id = tenant_id
        self.mode = mode
        self._bootstrap = kafka_bootstrap or os.getenv(
            "KAFKA_BOOTSTRAP_SERVERS", "kafka:9092"
        )
        self._topic = os.getenv("KAFKA_TOPIC_MAINTENANCE", "maintenance-events")
        self._producer: Optional[KafkaProducer] = None
        self._minio: Optional[MinIOWriter] = None

        log.info(
            "AssetSuiteConnector initialised [mode=%s, tenant=%s]", mode, tenant_id
        )

    def _get_producer(self) -> KafkaProducer:
        """Lazily initialise Kafka producer."""
        if not self._producer:
            self._producer = KafkaProducer(
                bootstrap_servers=self._bootstrap,
                value_serializer=lambda v: json.dumps(v, default=str).encode("utf-8"),
                key_serializer=lambda k: k.encode("utf-8") if k else None,
                acks="all",
                retries=3,
            )
        return self._producer

    def _get_minio(self) -> Optional[MinIOWriter]:
        """Lazily initialise MinIO writer."""
        if not self._minio:
            try:
                self._minio = MinIOWriter()
            except Exception as e:
                log.warning("MinIO not available: %s", e)
        return self._minio

    def extract(
        self,
        asset_ids: List[str],
        asset_types: Dict[str, str],
        install_dates: Dict[str, datetime],
        days_back: int = 90,
    ) -> Dict[str, Any]:
        """
        Extract Asset Suite 9 data for a list of assets.

        Args:
            asset_ids:    FORESIGHT asset UUIDs.
            asset_types:  asset_id → type mapping.
            install_dates: asset_id → install datetime mapping.
            days_back:    Days of history to extract.

        Returns:
            Dict with 'assets', 'work_records', 'schedules'.
        """
        if self.mode == "live":
            raise NotImplementedError("Live AS9 REST extraction not yet implemented.")

        return self._extract_mock(asset_ids, asset_types, install_dates, days_back)

    def _extract_mock(
        self,
        asset_ids: List[str],
        asset_types: Dict[str, str],
        install_dates: Dict[str, datetime],
        days_back: int,
    ) -> Dict[str, Any]:
        """Generate realistic Asset Suite 9 mock data."""
        asset_records = []
        work_records = []
        schedules = []

        for idx, asset_id in enumerate(asset_ids):
            asset_type = asset_types.get(asset_id, "pump")
            install_date = install_dates.get(
                asset_id, datetime.now(tz=timezone.utc) - timedelta(days=365 * 5)
            )

            asset_rec = generate_asset_register_record(
                asset_id, self.tenant_id, asset_type, idx + 1, install_date
            )
            asset_records.append(asset_rec)
            as9_id = asset_rec["assetId"]

            wo_count = max(1, int(days_back / 45))
            asset_work = generate_work_management_records(
                as9_id, asset_id, self.tenant_id, count=wo_count, days_back=days_back
            )
            work_records.extend(asset_work)

            asset_schedule = generate_maintenance_schedule(
                as9_id, asset_id, self.tenant_id, months_ahead=6
            )
            schedules.extend(asset_schedule)

        log.info(
            "AS9 mock extraction complete: %d assets, %d work records, %d schedule items",
            len(asset_records),
            len(work_records),
            len(schedules),
        )
        return {
            "assets": asset_records,
            "work_records": work_records,
            "schedules": schedules,
        }

    def publish_and_store(self, data: Dict[str, Any]) -> None:
        """
        Publish maintenance events to Kafka and write raw dump to MinIO.

        Args:
            data: Extracted AS9 data with 'assets', 'work_records', 'schedules'.
        """
        producer = self._get_producer()
        now = datetime.now(tz=timezone.utc)

        for record in data.get("work_records", []):
            event = {
                "event_type": "asset_suite_work_record",
                "tenant_id": self.tenant_id,
                "source": "asset_suite",
                "asset_id": record.get("_foresight_asset_id"),
                "source_record_id": record.get("workOrderId"),
                "maintenance_type": record.get("workType", "").lower(),
                "cost": record.get("totalCost"),
                "outcome": record.get("outcome"),
                "timestamp": now.isoformat(),
            }
            producer.send(
                self._topic,
                key=self.tenant_id,
                value=event,
                headers=[
                    ("tenant_id", self.tenant_id.encode()),
                    ("source", b"asset_suite"),
                    ("event_type", b"work_record"),
                ],
            )

        producer.flush()
        log.info(
            "Published %d AS9 work events to Kafka topic '%s'",
            len(data.get("work_records", [])),
            self._topic,
        )

        minio = self._get_minio()
        if minio:
            for source_key, records in data.items():
                if records:
                    minio.write_records(
                        records=records,
                        tenant_id=self.tenant_id,
                        source=f"asset_suite/{source_key}",
                        dt=now,
                    )

    def close(self) -> None:
        """Close Kafka producer."""
        if self._producer:
            self._producer.close()
            self._producer = None


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FORESIGHT Asset Suite 9 Connector")
    parser.add_argument("--tenant-id", default="11111111-1111-1111-1111-111111111111")
    parser.add_argument("--assets", type=int, default=30)
    parser.add_argument("--days-back", type=int, default=90)
    parser.add_argument("--mode", choices=["mock", "live"], default="mock")
    args = parser.parse_args()

    configure_logging(
        level=os.getenv("LOG_LEVEL", "INFO"),
        fmt=os.getenv("LOG_FORMAT", "text"),
        service_name="asset-suite-connector",
    )

    connector = AssetSuiteConnector(tenant_id=args.tenant_id, mode=args.mode)

    asset_ids = [
        str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{args.tenant_id}-asset-{i:04d}"))
        for i in range(args.assets)
    ]
    asset_types_map = {
        aid: ["pump", "turbine", "transformer", "compressor", "motor"][i % 5]
        for i, aid in enumerate(asset_ids)
    }
    install_dates_map = {
        aid: datetime.now(tz=timezone.utc) - timedelta(days=365 * random.randint(1, 15))
        for aid in asset_ids
    }

    try:
        data = connector.extract(asset_ids, asset_types_map, install_dates_map, args.days_back)
        connector.publish_and_store(data)
        log.info("Asset Suite 9 connector run complete.")
    finally:
        connector.close()
