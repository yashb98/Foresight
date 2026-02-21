"""
FORESIGHT — Day 2 Ingestion Layer Tests

Tests:
  - Sensor simulator generates valid Pydantic-validated readings
  - SAP connector generates valid SAP-format JSON with required fields
  - Asset Suite 9 connector generates valid AS9-format JSON
  - MinIO writer builds correct partition keys
  - Idempotency: running connectors twice does not create duplicates
  - Kafka message schema validation
  - Anomaly injection works (values breach thresholds)

Run offline (no Docker):
    pytest tests/unit/ingestion/test_ingestion.py -v -m "not integration"
"""

from __future__ import annotations

import math
import os
import sys
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))


# ─────────────────────────────────────────────────────────────────────────────
# Sensor Simulator Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestSensorSimulator:
    """Unit tests for the sensor simulator physics and Kafka publishing."""

    def test_simulate_temperature_returns_finite_value(self):
        """Temperature simulation must always return a finite number."""
        from ingestion.sensor_simulator import AssetState, simulate_temperature

        state = AssetState(asset_id="a1", tenant_id="t1", asset_type="pump")
        for tick in range(100):
            temp = simulate_temperature(state, tick)
            assert math.isfinite(temp), f"Non-finite temperature at tick {tick}: {temp}"

    def test_simulate_temperature_bounded(self):
        """Temperature must remain within physical bounds (10–110°C)."""
        from ingestion.sensor_simulator import AssetState, simulate_temperature

        state = AssetState(asset_id="a1", tenant_id="t1", asset_type="pump")
        for tick in range(1000):
            temp = simulate_temperature(state, tick)
            assert 10.0 <= temp <= 110.0, f"Temperature out of bounds: {temp}"

    def test_simulate_vibration_non_negative(self):
        """Vibration must always be non-negative."""
        from ingestion.sensor_simulator import AssetState, simulate_vibration

        state = AssetState(asset_id="a1", tenant_id="t1", asset_type="pump")
        for _ in range(500):
            vib = simulate_vibration(state)
            assert vib >= 0.0, f"Negative vibration: {vib}"

    def test_simulate_pressure_bounded(self):
        """Pressure must remain within [0, 220] bar."""
        from ingestion.sensor_simulator import AssetState, simulate_pressure

        state = AssetState(asset_id="a1", tenant_id="t1", asset_type="pump")
        for _ in range(500):
            pressure = simulate_pressure(state)
            assert 0.0 <= pressure <= 220.0, f"Pressure out of bounds: {pressure}"

    def test_simulate_rpm_non_negative(self):
        """RPM must always be non-negative."""
        from ingestion.sensor_simulator import AssetState, simulate_rpm

        state = AssetState(asset_id="a1", tenant_id="t1", asset_type="pump")
        for _ in range(500):
            rpm = simulate_rpm(state)
            assert rpm >= 0.0, f"Negative RPM: {rpm}"

    def test_anomaly_spikes_temperature_above_threshold(self):
        """When in_anomaly=True, temperature should exceed the 85°C high threshold."""
        from ingestion.sensor_simulator import AssetState, simulate_temperature

        state = AssetState(asset_id="a1", tenant_id="t1", asset_type="pump")
        state.temperature = 50.0
        state.in_anomaly = True

        # Sample 20 anomaly readings — at least some should breach 85°C
        spikes = [simulate_temperature(state, tick=0) for _ in range(20)]
        assert any(t > 85.0 for t in spikes), (
            f"Anomaly did not produce threshold breach. Values: {spikes}"
        )

    def test_anomaly_spikes_vibration_above_threshold(self):
        """When in_anomaly=True, vibration should exceed the 35 mm/s threshold."""
        from ingestion.sensor_simulator import AssetState, simulate_vibration

        state = AssetState(asset_id="a1", tenant_id="t1", asset_type="pump")
        state.vibration = 10.0
        state.in_anomaly = True

        spikes = [simulate_vibration(state) for _ in range(20)]
        assert any(v > 35.0 for v in spikes), (
            f"Anomaly did not produce vibration breach. Values: {spikes}"
        )

    def test_sensor_reading_pydantic_validation(self):
        """Sensor readings from simulator must pass Pydantic validation."""
        from common.models import MetricName, QualityFlag, SensorReading
        from ingestion.sensor_simulator import AssetState, simulate_temperature

        state = AssetState(
            asset_id="asset-001",
            tenant_id="11111111-1111-1111-1111-111111111111",
            asset_type="pump",
        )
        value = simulate_temperature(state, tick=0)

        reading = SensorReading(
            tenant_id=state.tenant_id,
            asset_id=state.asset_id,
            metric_name=MetricName.TEMPERATURE,
            value=value,
            unit="degC",
            quality_flag=QualityFlag.GOOD,
        )
        assert reading.tenant_id == state.tenant_id
        assert reading.asset_id == state.asset_id
        assert math.isfinite(reading.value)
        assert reading.reading_id is not None

    def test_sensor_reading_rejects_nan(self):
        """Sensor readings with NaN values must be rejected."""
        from common.models import MetricName, SensorReading

        with pytest.raises(Exception):
            SensorReading(
                tenant_id="t1",
                asset_id="a1",
                metric_name=MetricName.TEMPERATURE,
                value=float("nan"),
                unit="degC",
            )

    def test_kafka_dict_serialisable(self):
        """to_kafka_dict() must return JSON-serialisable dict."""
        import json
        from common.models import MetricName, SensorReading

        reading = SensorReading(
            tenant_id="t1",
            asset_id="a1",
            metric_name=MetricName.VIBRATION,
            value=22.5,
            unit="mm_s",
        )
        d = reading.to_kafka_dict()
        serialised = json.dumps(d, default=str)
        parsed = json.loads(serialised)
        assert parsed["tenant_id"] == "t1"
        assert parsed["value"] == 22.5

    def test_degradation_level_increases_over_time(self):
        """Degradation level must monotonically trend upward over many ticks."""
        from ingestion.sensor_simulator import (
            AssetState,
            SimulatorConfig,
            update_anomaly_state,
        )

        state = AssetState(asset_id="a1", tenant_id="t1", asset_type="pump")
        config = SimulatorConfig(
            asset_ids=["a1"],
            tenant_ids=["t1"],
            frequency_seconds=1.0,
            anomaly_probability=0.0,   # Disable anomalies for this test
        )

        initial = state.degradation_level
        for _ in range(10000):
            update_anomaly_state(state, config)

        assert state.degradation_level > initial, (
            "Degradation level should increase over time"
        )
        assert state.degradation_level <= 1.0, "Degradation level must not exceed 1.0"


# ─────────────────────────────────────────────────────────────────────────────
# SAP Connector Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestSAPConnector:
    """Unit tests for the SAP connector mock data generation."""

    TENANT_ID = "11111111-1111-1111-1111-111111111111"
    ASSET_ID = str(uuid.uuid4())
    INSTALL_DATE = datetime(2018, 6, 1, tzinfo=timezone.utc)

    def test_equipment_master_has_required_sap_fields(self):
        """Equipment master record must have all SAP EQUI field names."""
        from ingestion.sap_connector import generate_equipment_master

        record = generate_equipment_master(
            self.ASSET_ID, self.TENANT_ID, "pump", self.INSTALL_DATE
        )
        required_sap_fields = {"EQUNR", "EQKTX", "EQART", "ANLNR", "INBDT", "SWERK"}
        for field in required_sap_fields:
            assert field in record, f"Missing SAP field: {field}"

    def test_equipment_master_contains_tenant_id(self):
        """Every SAP record must carry tenant_id for multi-tenancy."""
        from ingestion.sap_connector import generate_equipment_master

        record = generate_equipment_master(
            self.ASSET_ID, self.TENANT_ID, "turbine", self.INSTALL_DATE
        )
        assert record["_foresight_tenant_id"] == self.TENANT_ID

    def test_equipment_master_contains_asset_id(self):
        """Equipment master must reference the FORESIGHT asset UUID."""
        from ingestion.sap_connector import generate_equipment_master

        record = generate_equipment_master(
            self.ASSET_ID, self.TENANT_ID, "transformer", self.INSTALL_DATE
        )
        assert record["_foresight_asset_id"] == self.ASSET_ID

    def test_work_orders_have_aufnr(self):
        """Work orders must have AUFNR field (SAP order number)."""
        from ingestion.sap_connector import generate_work_orders

        orders = generate_work_orders("EQ-P-12345", self.ASSET_ID, self.TENANT_ID, count=5)
        assert len(orders) == 5
        for wo in orders:
            assert "AUFNR" in wo, f"Missing AUFNR in work order: {wo}"

    def test_work_orders_maintenance_type_mapped(self):
        """Work orders must have _foresight_maintenance_type populated."""
        from ingestion.sap_connector import generate_work_orders

        orders = generate_work_orders("EQ-T-99999", self.ASSET_ID, self.TENANT_ID, count=10)
        valid_types = {"preventive", "inspection", "corrective", "predictive", "manual"}
        for wo in orders:
            assert wo["_foresight_maintenance_type"] in valid_types, (
                f"Invalid maintenance type: {wo['_foresight_maintenance_type']}"
            )

    def test_notifications_have_qmnum(self):
        """Notifications must have QMNUM field (SAP notification number)."""
        from ingestion.sap_connector import generate_notifications

        notifs = generate_notifications("EQ-C-55555", self.ASSET_ID, self.TENANT_ID, count=3)
        for notif in notifs:
            assert "QMNUM" in notif

    def test_connector_mock_extraction_all_keys(self):
        """Mock extraction must return all three data categories."""
        from ingestion.sap_connector import SAPConnector

        connector = SAPConnector(tenant_id=self.TENANT_ID, mode="mock")
        asset_ids = [str(uuid.uuid4()) for _ in range(3)]
        asset_types = {aid: "pump" for aid in asset_ids}
        install_dates = {aid: self.INSTALL_DATE for aid in asset_ids}

        data = connector.extract(asset_ids, asset_types, install_dates, days_back=30)
        assert "equipment" in data
        assert "work_orders" in data
        assert "notifications" in data
        assert len(data["equipment"]) == 3
        assert len(data["work_orders"]) > 0

    def test_connector_live_mode_raises_without_pyrfc(self):
        """Live mode without pyrfc installed must raise RuntimeError."""
        from ingestion.sap_connector import SAPConnector

        connector = SAPConnector(tenant_id=self.TENANT_ID, mode="live")
        with pytest.raises((RuntimeError, NotImplementedError)):
            connector.extract([], {}, {})


# ─────────────────────────────────────────────────────────────────────────────
# Asset Suite 9 Connector Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestAssetSuiteConnector:
    """Unit tests for the Asset Suite 9 connector mock data generation."""

    TENANT_ID = "22222222-2222-2222-2222-222222222222"
    ASSET_ID = str(uuid.uuid4())
    INSTALL_DATE = datetime(2019, 3, 15, tzinfo=timezone.utc)

    def test_asset_register_has_required_as9_fields(self):
        """Asset register record must have Asset Suite 9 field names."""
        from ingestion.asset_suite_connector import generate_asset_register_record

        record = generate_asset_register_record(
            self.ASSET_ID, self.TENANT_ID, "pump", 1, self.INSTALL_DATE
        )
        required = {"assetId", "assetNumber", "assetName", "assetClass",
                    "locationCode", "criticalityRating", "installDate"}
        for field in required:
            assert field in record, f"Missing AS9 field: {field}"

    def test_asset_register_criticality_uses_letter_codes(self):
        """Asset Suite 9 uses A/B/C/D criticality, not low/medium/high/critical."""
        from ingestion.asset_suite_connector import generate_asset_register_record

        record = generate_asset_register_record(
            self.ASSET_ID, self.TENANT_ID, "turbine", 1, self.INSTALL_DATE
        )
        assert record["criticalityRating"] in {"A", "B", "C", "D"}, (
            f"Expected A/B/C/D criticality rating, got: {record['criticalityRating']}"
        )

    def test_work_records_have_workOrderId(self):
        """Work management records must have workOrderId."""
        from ingestion.asset_suite_connector import generate_work_management_records

        records = generate_work_management_records(
            "SITE-A/BLDG-1/PUMP-001", self.ASSET_ID, self.TENANT_ID, count=5
        )
        for rec in records:
            assert "workOrderId" in rec
            assert rec["workOrderId"].startswith("AS9-WO-")

    def test_work_records_have_cost_fields(self):
        """Work records must include cost breakdown."""
        from ingestion.asset_suite_connector import generate_work_management_records

        records = generate_work_management_records(
            "SITE-B/BLDG-2/MOTOR-005", self.ASSET_ID, self.TENANT_ID, count=3
        )
        for rec in records:
            assert "materialCost" in rec
            assert "laborCost" in rec
            assert "totalCost" in rec

    def test_maintenance_schedule_has_future_dates(self):
        """Scheduled maintenance events must be in the future."""
        from ingestion.asset_suite_connector import generate_maintenance_schedule

        schedule = generate_maintenance_schedule(
            "SITE-C/BLDG-3/TRANSFORMER-010", self.ASSET_ID, self.TENANT_ID, months_ahead=6
        )
        now = datetime.now(tz=timezone.utc)
        for item in schedule:
            planned = datetime.fromisoformat(item["plannedDate"].replace("Z", "+00:00"))
            assert planned > now, f"Schedule date is in the past: {planned}"

    def test_connector_mock_extraction_all_categories(self):
        """Mock extraction must return assets, work_records, schedules."""
        from ingestion.asset_suite_connector import AssetSuiteConnector

        connector = AssetSuiteConnector(tenant_id=self.TENANT_ID, mode="mock")
        asset_ids = [str(uuid.uuid4()) for _ in range(5)]
        asset_types = {aid: "compressor" for aid in asset_ids}
        install_dates = {aid: self.INSTALL_DATE for aid in asset_ids}

        data = connector.extract(asset_ids, asset_types, install_dates, days_back=60)
        assert "assets" in data
        assert "work_records" in data
        assert "schedules" in data
        assert len(data["assets"]) == 5
        assert len(data["schedules"]) > 0

    def test_as9_sap_data_have_deliberate_discrepancies(self):
        """
        Asset Suite 9 and SAP data for the same asset must differ slightly
        (different naming conventions, cost figures) for reconciliation testing.
        """
        from ingestion.asset_suite_connector import generate_asset_register_record
        from ingestion.sap_connector import generate_equipment_master

        asset_id = str(uuid.uuid4())
        tenant_id = self.TENANT_ID
        install_date = self.INSTALL_DATE

        sap_record = generate_equipment_master(asset_id, tenant_id, "pump", install_date)
        as9_record = generate_asset_register_record(asset_id, tenant_id, "pump", 1, install_date)

        # Same asset, different field names (by design)
        assert "EQUNR" in sap_record        # SAP uses EQUNR
        assert "assetId" in as9_record      # AS9 uses assetId
        assert "EQUNR" not in as9_record    # AS9 must NOT use SAP field names


# ─────────────────────────────────────────────────────────────────────────────
# MinIO Writer Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestMinIOWriter:
    """Unit tests for the MinIO writer — path generation and serialisation."""

    def test_build_key_correct_partition_structure(self):
        """MinIO key must follow /raw/{tenant_id}/{source}/{YYYY}/{MM}/{DD}/ pattern."""
        from ingestion.minio_writer import MinIOWriter

        dt = datetime(2026, 2, 20, 10, 30, tzinfo=timezone.utc)
        key = MinIOWriter.build_key(
            tenant_id="11111111-1111-1111-1111-111111111111",
            source="sensors",
            dt=dt,
        )
        assert key.startswith("raw/11111111-1111-1111-1111-111111111111/sensors/2026/02/20/"), (
            f"Unexpected key structure: {key}"
        )

    def test_build_key_deterministic(self):
        """Same inputs must produce the same key (idempotency)."""
        from ingestion.minio_writer import MinIOWriter

        dt = datetime(2026, 2, 20, 12, 0, tzinfo=timezone.utc)
        key1 = MinIOWriter.build_key("t1", "sap", dt, "sap_data.json.gz")
        key2 = MinIOWriter.build_key("t1", "sap", dt, "sap_data.json.gz")
        assert key1 == key2

    def test_build_key_different_tenants_different_keys(self):
        """Different tenant IDs must produce different partition paths."""
        from ingestion.minio_writer import MinIOWriter

        dt = datetime(2026, 2, 20, tzinfo=timezone.utc)
        key1 = MinIOWriter.build_key("tenant-aaa", "sensors", dt, "file.json.gz")
        key2 = MinIOWriter.build_key("tenant-bbb", "sensors", dt, "file.json.gz")
        assert key1 != key2

    def test_build_key_includes_source(self):
        """Key must include the source system in the path."""
        from ingestion.minio_writer import MinIOWriter

        key = MinIOWriter.build_key("t1", "asset_suite", filename="test.json.gz")
        assert "asset_suite" in key

    @patch("ingestion.minio_writer.boto3.client")
    def test_write_records_calls_put_object(self, mock_boto):
        """write_records must call S3 put_object with correct bucket and key."""
        os.environ.setdefault("MINIO_BUCKET_RAW", "foresight-raw")
        os.environ.setdefault("AWS_ENDPOINT_URL", "http://localhost:9000")
        os.environ.setdefault("AWS_ACCESS_KEY_ID", "test")
        os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test")

        from ingestion.minio_writer import MinIOWriter

        mock_client = MagicMock()
        mock_boto.return_value = mock_client

        writer = MinIOWriter()
        records = [{"tenant_id": "t1", "value": 42.0}]
        writer.write_records(records, "t1", "sensors")

        mock_client.put_object.assert_called_once()
        call_kwargs = mock_client.put_object.call_args[1]
        assert call_kwargs["Bucket"] == "foresight-raw"
        assert "raw/t1/sensors/" in call_kwargs["Key"]
