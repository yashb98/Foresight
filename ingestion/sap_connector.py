#!/usr/bin/env python3
"""
FORESIGHT — SAP Plant Maintenance Connector

Extracts (or mocks) SAP PM data across three functional areas:
  1. Equipment Master (EQUI table) — physical asset attributes
  2. Work Orders (AUFK + AFKO tables) — maintenance job history
  3. Maintenance Notifications (QMEL + QMFE tables) — failure reports

In production, this connects via pyrfc (RFC connector for SAP).
In dev/test, it generates realistic SAP-format JSON using the same field names
(EQUNR, AUFNR, QMNUM) so downstream parsers work identically against live or mock data.

The connector:
  - Attaches tenant_id to every record
  - Publishes summary events to Kafka topic 'maintenance-events'
  - Writes full raw dumps to MinIO with correct partitioning
  - Is idempotent: same run on same day produces same MinIO object (overwrite)

Usage:
    # Mock mode (no live SAP)
    python ingestion/sap_connector.py --tenant-id <UUID> --assets 30 --days-back 90

    # Production mode (requires pyrfc + SAP RFC credentials in .env)
    python ingestion/sap_connector.py --tenant-id <UUID> --mode live
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

import kafka  # noqa: F401
from kafka import KafkaProducer

from common.logging_config import configure_logging
from common.models import (  # noqa: F401
    MaintenanceRecord,
    SAPEquipmentRecord,
    SAPWorkOrder,
    SourceSystem,
)
from ingestion.minio_writer import MinIOWriter

log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Mock data generators — SAP-format field names
# ─────────────────────────────────────────────────────────────────────────────

SAP_EQUIPMENT_TYPES = {
    "pump": ("P", "Centrifugal pump"),
    "turbine": ("T", "Steam turbine"),
    "transformer": ("TR", "Power transformer"),
    "compressor": ("C", "Reciprocating compressor"),
    "motor": ("M", "Electric motor"),
}

SAP_PLANTS = ["1000", "1001", "1002", "2000", "2001"]
SAP_COST_CENTRES = ["CC-OPS-001", "CC-MAINT-002", "CC-PROD-003", "CC-UTIL-004"]
SAP_ORDER_TYPES = ["PM01", "PM02", "PM03", "PM04"]  # PM01=Preventive, PM03=Corrective
SAP_ISTAT_CODES = ["I0001", "I0002", "I0045", "NOCO", "TECO"]  # status codes
SAP_NOTIFICATION_TYPES = ["M1", "M2", "S3"]  # M1=Malfunction, M2=Maintenance, S3=Activity


def generate_equipment_master(
    asset_id: str, tenant_id: str, asset_type: str, install_date: datetime
) -> Dict[str, Any]:
    """
    Generate a SAP Equipment Master record in EQUI table format.

    Args:
        asset_id:     Internal FORESIGHT asset UUID.
        tenant_id:    Tenant UUID.
        asset_type:   'pump', 'turbine', 'transformer', 'compressor', 'motor'
        install_date: Asset installation date.

    Returns:
        Dict with SAP EQUI field names.
    """
    type_code, type_desc = SAP_EQUIPMENT_TYPES.get(asset_type, ("X", "General equipment"))
    equnr = f"EQ-{type_code}-{random.randint(10000, 99999)}"

    return {
        # Core EQUI fields
        "EQUNR": equnr,  # Equipment number
        "EQKTX": f"{type_desc} Unit {random.randint(1, 99):02d}",  # Short description
        "EQART": asset_type.upper()[:4],  # Type of technical object
        "ANLNR": f"AN{random.randint(100000, 999999)}",  # Asset number (FI-AA)
        "BRGEW": round(random.uniform(50, 5000), 1),  # Gross weight (kg)
        "GEWEI": "KG",  # Unit of weight
        "BAUJJ": random.randint(2005, 2022),  # Year of manufacture
        "INBDT": install_date.strftime("%Y%m%d"),  # Start-up date (SAP date format)
        "SWERK": random.choice(SAP_PLANTS),  # Maintenance plant
        "IWERK": random.choice(SAP_PLANTS),  # Planning plant
        "EQFNR": f"FN{random.randint(1000, 9999)}",  # Functional location
        "TIDNR": f"TI{random.randint(10000, 99999)}",  # Technical identification
        "HERLD": random.choice(["DE", "US", "JP", "GB"]),  # Country of manufacture
        "HERST": random.choice(["Siemens", "GE", "ABB", "Emerson", "Schneider"]),  # Manufacturer
        "TYPBZ": f"Model-{random.randint(100, 999)}",  # Model number
        "SERGE": f"SN{random.randint(10000, 99999)}",  # Serial number
        "ZZWARTY": "W24",  # Custom: warranty type
        # FORESIGHT metadata (non-SAP)
        "_foresight_asset_id": asset_id,
        "_foresight_tenant_id": tenant_id,
        "_foresight_extracted_at": datetime.now(tz=timezone.utc).isoformat(),
    }


def generate_work_orders(
    equnr: str,
    asset_id: str,
    tenant_id: str,
    count: int = 10,
    days_back: int = 365,
) -> List[Dict[str, Any]]:
    """
    Generate SAP Work Order records in AUFK format.

    Args:
        equnr:      SAP equipment number (EQUNR).
        asset_id:   FORESIGHT asset UUID.
        tenant_id:  Tenant UUID.
        count:      Number of work orders to generate.
        days_back:  How far back in time to generate orders.

    Returns:
        List of dicts with SAP AUFK field names.
    """
    orders = []
    for _ in range(count):
        days_ago = random.randint(0, days_back)
        start_date = datetime.now(tz=timezone.utc) - timedelta(days=days_ago)
        duration_hours = random.randint(2, 72)
        end_date = start_date + timedelta(hours=duration_hours)
        order_type = random.choice(SAP_ORDER_TYPES)

        aufnr = f"WO-{random.randint(1000000, 9999999)}"

        orders.append(
            {
                # Core AUFK fields
                "AUFNR": aufnr,  # Order number
                "AUART": order_type,  # Order type
                "EQUNR": equnr,  # Equipment number
                "KTEXT": _work_order_description(order_type),  # Short description
                "ERDAT": start_date.strftime("%Y%m%d"),  # Creation date
                "AEDAT": start_date.strftime("%Y%m%d"),  # Last change date
                "GSTRP": start_date.strftime("%Y%m%d"),  # Scheduled start date
                "GLTRP": end_date.strftime("%Y%m%d"),  # Scheduled finish date
                "IDAT2": end_date.strftime("%Y%m%d"),  # Actual completion date
                "ISTAT": random.choice(SAP_ISTAT_CODES),  # Object status
                "KOSTL": random.choice(SAP_COST_CENTRES),  # Cost centre
                "WAERS": "GBP",  # Currency
                "GKOST": round(random.uniform(200, 15000), 2),  # Actual costs
                "IPHAS": "4",  # Processing phase (4=closed)
                # FORESIGHT metadata
                "_foresight_asset_id": asset_id,
                "_foresight_tenant_id": tenant_id,
                "_foresight_maintenance_type": _order_type_to_maintenance_type(order_type),
                "_foresight_extracted_at": datetime.now(tz=timezone.utc).isoformat(),
            }
        )
    return orders


def generate_notifications(
    equnr: str,
    asset_id: str,
    tenant_id: str,
    count: int = 5,
    days_back: int = 365,
) -> List[Dict[str, Any]]:
    """
    Generate SAP Maintenance Notification records in QMEL format.

    Args:
        equnr:     SAP equipment number.
        asset_id:  FORESIGHT asset UUID.
        tenant_id: Tenant UUID.
        count:     Number of notifications to generate.
        days_back: Historical range.

    Returns:
        List of dicts with SAP QMEL field names.
    """
    notifications = []
    for _ in range(count):
        days_ago = random.randint(0, days_back)
        notif_date = datetime.now(tz=timezone.utc) - timedelta(days=days_ago)
        notif_type = random.choice(SAP_NOTIFICATION_TYPES)

        qmnum = f"QM-{random.randint(10000000, 99999999)}"

        notifications.append(
            {
                "QMNUM": qmnum,  # Notification number
                "QMART": notif_type,  # Notification type
                "EQUNR": equnr,  # Equipment
                "QMTXT": _notification_description(notif_type),  # Short text
                "QMDAT": notif_date.strftime("%Y%m%d"),  # Notification date
                "MZEIT": notif_date.strftime("%H%M%S"),  # Time of notification
                "PRIOK": str(random.randint(1, 4)),  # Priority (1=highest)
                "QMCOD": f"C{random.randint(100, 999)}",  # Coding (failure code)
                "MAKNX": _failure_code_text(),  # Failure mode text
                "OTEIL": f"COMP-{random.randint(1, 50):02d}",  # Object part
                "AUFNR": f"WO-{random.randint(1000000, 9999999)}",  # Linked work order
                "STAT": random.choice(["NOCO", "OSNO", "NOPR"]),  # System status
                # FORESIGHT metadata
                "_foresight_asset_id": asset_id,
                "_foresight_tenant_id": tenant_id,
                "_foresight_extracted_at": datetime.now(tz=timezone.utc).isoformat(),
            }
        )
    return notifications


def _work_order_description(order_type: str) -> str:
    """Map SAP order type to a human-readable description."""
    descriptions = {
        "PM01": random.choice(
            [
                "Scheduled preventive maintenance",
                "Lubrication and inspection",
                "Filter replacement",
                "Annual overhaul",
            ]
        ),
        "PM02": random.choice(["Calibration check", "Instrument testing"]),
        "PM03": random.choice(
            [
                "Emergency corrective repair",
                "Breakdown maintenance",
                "Bearing replacement",
                "Seal failure repair",
            ]
        ),
        "PM04": "Predictive maintenance follow-up",
    }
    return descriptions.get(order_type, "General maintenance")


def _order_type_to_maintenance_type(order_type: str) -> str:
    """Map SAP order type to FORESIGHT maintenance type."""
    mapping = {
        "PM01": "preventive",
        "PM02": "inspection",
        "PM03": "corrective",
        "PM04": "predictive",
    }
    return mapping.get(order_type, "manual")


def _notification_description(notif_type: str) -> str:
    """Map notification type to description text."""
    descriptions = {
        "M1": random.choice(
            [
                "Malfunction report — abnormal noise detected",
                "Equipment vibration exceeding limits",
                "Oil leak observed",
                "Temperature spike — investigation required",
            ]
        ),
        "M2": "Scheduled maintenance notification",
        "S3": "Activity report — inspection completed",
    }
    return descriptions.get(notif_type, "General notification")


def _failure_code_text() -> str:
    """Generate a realistic failure mode description."""
    return random.choice(
        [
            "Bearing wear",
            "Seal degradation",
            "Impeller erosion",
            "Coupling misalignment",
            "Winding insulation breakdown",
            "Cavitation damage",
            "Corrosion",
            "Fatigue crack",
            "Thermal overload",
            "Blockage",
        ]
    )


# ─────────────────────────────────────────────────────────────────────────────
# SAP Connector class
# ─────────────────────────────────────────────────────────────────────────────


class SAPConnector:
    """
    Extracts SAP PM data (mock or live) and publishes to Kafka + MinIO.

    In mock mode: generates realistic SAP-format data.
    In live mode: uses pyrfc to connect to SAP via RFC.

    Args:
        tenant_id:  Tenant UUID this connector is operating for.
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
        self._bootstrap = kafka_bootstrap or os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092")
        self._topic = os.getenv("KAFKA_TOPIC_MAINTENANCE", "maintenance-events")
        self._producer: Optional[KafkaProducer] = None
        self._minio: Optional[MinIOWriter] = None

        log.info("SAPConnector initialised [mode=%s, tenant=%s]", mode, tenant_id)

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
        Extract SAP data for a list of assets.

        Args:
            asset_ids:    List of FORESIGHT asset UUIDs to extract for.
            asset_types:  Mapping of asset_id → asset_type string.
            install_dates: Mapping of asset_id → installation datetime.
            days_back:    How many days of history to extract.

        Returns:
            Dict with keys 'equipment', 'work_orders', 'notifications'.
        """
        if self.mode == "live":
            return self._extract_live(asset_ids, asset_types, install_dates, days_back)
        return self._extract_mock(asset_ids, asset_types, install_dates, days_back)

    def _extract_mock(
        self,
        asset_ids: List[str],
        asset_types: Dict[str, str],
        install_dates: Dict[str, datetime],
        days_back: int,
    ) -> Dict[str, Any]:
        """Generate realistic SAP mock data."""
        equipment_records = []
        work_orders = []
        notifications = []

        for asset_id in asset_ids:
            asset_type = asset_types.get(asset_id, "pump")
            install_date = install_dates.get(
                asset_id, datetime.now(tz=timezone.utc) - timedelta(days=365 * 5)
            )

            eq_record = generate_equipment_master(
                asset_id, self.tenant_id, asset_type, install_date
            )
            equipment_records.append(eq_record)
            equnr = eq_record["EQUNR"]

            wo_count = max(1, int(days_back / 30))  # ~1 WO per month
            asset_wos = generate_work_orders(
                equnr, asset_id, self.tenant_id, count=wo_count, days_back=days_back
            )
            work_orders.extend(asset_wos)

            notif_count = max(1, int(days_back / 60))  # ~1 notification per 2 months
            asset_notifs = generate_notifications(
                equnr, asset_id, self.tenant_id, count=notif_count, days_back=days_back
            )
            notifications.extend(asset_notifs)

        log.info(
            "SAP mock extraction complete: %d equipment, %d WOs, %d notifications",
            len(equipment_records),
            len(work_orders),
            len(notifications),
        )
        return {
            "equipment": equipment_records,
            "work_orders": work_orders,
            "notifications": notifications,
        }

    def _extract_live(self, *args, **kwargs) -> Dict[str, Any]:
        """
        Live SAP extraction via pyrfc RFC.

        Raises:
            RuntimeError: pyrfc is not installed or SAP RFC credentials not configured.
        """
        try:
            import pyrfc  # noqa: F401
        except ImportError:
            raise RuntimeError(
                "pyrfc not installed. Install it for live SAP connectivity, "
                "or use --mode mock for development."
            )
        raise NotImplementedError("Live SAP RFC extraction not yet implemented. Use --mode mock.")

    def publish_and_store(self, data: Dict[str, Any]) -> None:
        """
        Publish work order summary events to Kafka and write full dump to MinIO.

        Args:
            data: Extracted SAP data dict with 'equipment', 'work_orders', 'notifications'.
        """
        producer = self._get_producer()
        now = datetime.now(tz=timezone.utc)

        # Publish each work order as a Kafka event (summary)
        for wo in data.get("work_orders", []):
            event = {
                "event_type": "sap_work_order",
                "tenant_id": self.tenant_id,
                "source": "sap",
                "asset_id": wo.get("_foresight_asset_id"),
                "source_record_id": wo.get("AUFNR"),
                "maintenance_type": wo.get("_foresight_maintenance_type"),
                "cost": wo.get("GKOST"),
                "status": wo.get("ISTAT"),
                "timestamp": now.isoformat(),
            }
            producer.send(
                self._topic,
                key=self.tenant_id,
                value=event,
                headers=[
                    ("tenant_id", self.tenant_id.encode()),
                    ("source", b"sap"),
                    ("event_type", b"work_order"),
                ],
            )

        producer.flush()
        log.info(
            "Published %d SAP work order events to Kafka topic '%s'",
            len(data.get("work_orders", [])),
            self._topic,
        )

        # Write full raw dump to MinIO
        minio = self._get_minio()
        if minio:
            for source_key, records in data.items():
                if records:
                    minio.write_records(
                        records=records,
                        tenant_id=self.tenant_id,
                        source=f"sap/{source_key}",
                        dt=now,
                    )

    def close(self) -> None:
        """Close Kafka producer connection."""
        if self._producer:
            self._producer.close()
            self._producer = None


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="FORESIGHT SAP Connector")
    parser.add_argument("--tenant-id", default="11111111-1111-1111-1111-111111111111")
    parser.add_argument("--assets", type=int, default=30)
    parser.add_argument("--days-back", type=int, default=90)
    parser.add_argument("--mode", choices=["mock", "live"], default="mock")
    args = parser.parse_args()

    configure_logging(
        level=os.getenv("LOG_LEVEL", "INFO"),
        fmt=os.getenv("LOG_FORMAT", "text"),
        service_name="sap-connector",
    )

    connector = SAPConnector(tenant_id=args.tenant_id, mode=args.mode)

    # Generate asset metadata matching seed.py IDs
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
        log.info("SAP connector run complete.")
    finally:
        connector.close()
