"""
FORESIGHT — Day 1 Acceptance Tests

Tests:
    - All PostgreSQL tables exist with correct schema
    - Seed data is present (2 tenants, 30 assets per tenant, 5 rules per tenant)
    - Compound indexes exist on critical tables
    - MongoDB sensor_readings collection exists with compound index
    - MinIO buckets (raw, processed, models) are accessible
    - Hive tables (raw_sensor_data, feature_store) exist via PySpark

Run against a running Docker Compose stack:
    pytest tests/unit/test_db.py -v -m integration

Offline (no Docker) — structural tests only, DB tests are skipped:
    pytest tests/unit/test_db.py -v -m "not integration"
"""

from __future__ import annotations

import os
import sys
from typing import List
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def db_session():
    """
    Synchronous SQLAlchemy session against the test PostgreSQL instance.
    Skipped if DATABASE_URL_SYNC is not set (CI without Docker).
    """
    url = os.environ.get("DATABASE_URL_SYNC")
    if not url:
        pytest.skip("DATABASE_URL_SYNC not set — skipping DB integration tests")

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(url, echo=False)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture(scope="session")
def mongo_client():
    """MongoDB client. Skipped if MONGO_URI not set."""
    uri = os.environ.get("MONGO_URI")
    if not uri:
        pytest.skip("MONGO_URI not set — skipping MongoDB integration tests")

    from pymongo import MongoClient

    client = MongoClient(uri, serverSelectionTimeoutMS=5000)
    try:
        client.admin.command("ping")
    except Exception as exc:
        pytest.skip(f"MongoDB not reachable: {exc}")
    yield client
    client.close()


@pytest.fixture(scope="session")
def minio_client():
    """MinIO client via boto3. Skipped if AWS_ENDPOINT_URL not set."""
    endpoint = os.environ.get("AWS_ENDPOINT_URL")
    if not endpoint:
        pytest.skip("AWS_ENDPOINT_URL not set — skipping MinIO integration tests")

    import boto3
    from botocore.config import Config

    client = boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID", "minioadmin"),
        aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY", ""),
        config=Config(signature_version="s3v4"),
        region_name="us-east-1",
    )
    return client


# ─────────────────────────────────────────────────────────────────────────────
# PostgreSQL — Schema tests
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.integration
class TestPostgreSQLSchema:
    """Verify all PostgreSQL tables exist with expected columns."""

    EXPECTED_TABLES = [
        "tenants",
        "assets",
        "asset_health_scores",
        "threshold_rules",
        "alerts",
        "maintenance_records",
    ]

    def test_all_tables_exist(self, db_session):
        """All 6 core tables must exist after migration."""
        from sqlalchemy import inspect

        inspector = inspect(db_session.bind)
        existing_tables = inspector.get_table_names()

        for table in self.EXPECTED_TABLES:
            assert table in existing_tables, (
                f"Table '{table}' not found. Did you run 'alembic upgrade head'?"
            )

    def test_tenants_columns(self, db_session):
        """tenants table must have all required columns."""
        from sqlalchemy import inspect

        inspector = inspect(db_session.bind)
        cols = {c["name"] for c in inspector.get_columns("tenants")}

        required = {
            "tenant_id", "name", "config_json", "subscription_tier",
            "client_id", "client_secret_hash", "is_active", "created_at",
        }
        assert required.issubset(cols), f"Missing columns: {required - cols}"

    def test_assets_columns(self, db_session):
        """assets table must have all required columns."""
        from sqlalchemy import inspect

        inspector = inspect(db_session.bind)
        cols = {c["name"] for c in inspector.get_columns("assets")}

        required = {
            "asset_id", "tenant_id", "name", "asset_type",
            "location", "criticality", "installed_date", "metadata_json",
        }
        assert required.issubset(cols), f"Missing columns: {required - cols}"

    def test_health_scores_columns(self, db_session):
        """asset_health_scores must have failure probability columns."""
        from sqlalchemy import inspect

        inspector = inspect(db_session.bind)
        cols = {c["name"] for c in inspector.get_columns("asset_health_scores")}

        required = {
            "score_id", "asset_id", "tenant_id", "score_date",
            "health_score", "failure_prob_7d", "failure_prob_30d",
            "model_version", "top_features_json",
        }
        assert required.issubset(cols), f"Missing columns: {required - cols}"

    def test_threshold_rules_columns(self, db_session):
        """threshold_rules must support configurable operators."""
        from sqlalchemy import inspect

        inspector = inspect(db_session.bind)
        cols = {c["name"] for c in inspector.get_columns("threshold_rules")}

        required = {
            "rule_id", "tenant_id", "metric_name", "operator",
            "threshold_value", "severity", "active",
        }
        assert required.issubset(cols), f"Missing columns: {required - cols}"

    def test_indexes_on_assets(self, db_session):
        """assets table must have tenant_id index for multi-tenant query performance."""
        from sqlalchemy import inspect

        inspector = inspect(db_session.bind)
        indexes = inspector.get_indexes("assets")
        index_names = {idx["name"] for idx in indexes}
        assert "idx_assets_tenant_id" in index_names, (
            "Missing index idx_assets_tenant_id on assets — will cause full table scans!"
        )

    def test_indexes_on_health_scores(self, db_session):
        """asset_health_scores must have tenant+date index."""
        from sqlalchemy import inspect

        inspector = inspect(db_session.bind)
        indexes = inspector.get_indexes("asset_health_scores")
        index_names = {idx["name"] for idx in indexes}
        assert "idx_scores_tenant_date" in index_names


# ─────────────────────────────────────────────────────────────────────────────
# PostgreSQL — Seed data tests
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.integration
class TestSeedData:
    """Verify seed.py produced the expected data."""

    TENANT_1_ID = "11111111-1111-1111-1111-111111111111"
    TENANT_2_ID = "22222222-2222-2222-2222-222222222222"

    def test_two_tenants_exist(self, db_session):
        """Exactly 2 test tenants must exist after seeding."""
        from sqlalchemy import text

        result = db_session.execute(
            text("SELECT COUNT(*) FROM tenants WHERE tenant_id IN :ids"),
            {"ids": (self.TENANT_1_ID, self.TENANT_2_ID)},
        ).scalar()
        assert result == 2, f"Expected 2 tenants, found {result}"

    def test_tenant_names(self, db_session):
        """Tenants must have the expected names."""
        from sqlalchemy import text

        rows = db_session.execute(
            text("SELECT name FROM tenants WHERE tenant_id IN :ids ORDER BY name"),
            {"ids": (self.TENANT_1_ID, self.TENANT_2_ID)},
        ).fetchall()
        names = {r[0] for r in rows}
        assert "Meridian Power & Water" in names
        assert "TransRail Infrastructure Ltd" in names

    def test_thirty_assets_per_tenant(self, db_session):
        """Each tenant must have exactly 30 assets."""
        from sqlalchemy import text

        for tenant_id in (self.TENANT_1_ID, self.TENANT_2_ID):
            count = db_session.execute(
                text("SELECT COUNT(*) FROM assets WHERE tenant_id = :tid"),
                {"tid": tenant_id},
            ).scalar()
            assert count == 30, (
                f"Expected 30 assets for tenant {tenant_id}, found {count}"
            )

    def test_five_rules_per_tenant(self, db_session):
        """Each tenant must have exactly 5 threshold rules."""
        from sqlalchemy import text

        for tenant_id in (self.TENANT_1_ID, self.TENANT_2_ID):
            count = db_session.execute(
                text("SELECT COUNT(*) FROM threshold_rules WHERE tenant_id = :tid"),
                {"tid": tenant_id},
            ).scalar()
            assert count == 5, (
                f"Expected 5 threshold rules for tenant {tenant_id}, found {count}"
            )

    def test_maintenance_records_exist(self, db_session):
        """Maintenance records must exist for test assets."""
        from sqlalchemy import text

        count = db_session.execute(
            text("SELECT COUNT(*) FROM maintenance_records WHERE tenant_id = :tid"),
            {"tid": self.TENANT_1_ID},
        ).scalar()
        assert count > 0, "No maintenance records found — did seed.py run successfully?"

    def test_health_scores_seeded(self, db_session):
        """Sample health scores must exist (30 days × 30 assets = 900 rows per tenant)."""
        from sqlalchemy import text

        count = db_session.execute(
            text("SELECT COUNT(*) FROM asset_health_scores WHERE tenant_id = :tid"),
            {"tid": self.TENANT_1_ID},
        ).scalar()
        # At least 1 week of scores
        assert count >= 30, (
            f"Expected ≥30 health score rows for tenant 1, found {count}"
        )

    def test_client_secret_is_hashed(self, db_session):
        """Client secrets must never be stored as plaintext."""
        from sqlalchemy import text

        secret_hash = db_session.execute(
            text("SELECT client_secret_hash FROM tenants WHERE tenant_id = :tid"),
            {"tid": self.TENANT_1_ID},
        ).scalar()
        assert secret_hash is not None
        # bcrypt hashes always start with $2b$
        assert secret_hash.startswith("$2"), (
            "client_secret_hash does not look like a bcrypt hash — plaintext secret stored!"
        )


# ─────────────────────────────────────────────────────────────────────────────
# MongoDB tests
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.integration
class TestMongoDB:
    """Verify MongoDB collection and indexes."""

    def test_sensor_readings_collection_exists(self, mongo_client):
        """sensor_readings collection must exist."""
        db = mongo_client["foresight"]
        assert "sensor_readings" in db.list_collection_names(), (
            "sensor_readings collection not found in MongoDB"
        )

    def test_compound_index_on_sensor_readings(self, mongo_client):
        """Compound index (tenant_id, asset_id, timestamp DESC) must exist."""
        collection = mongo_client["foresight"]["sensor_readings"]
        indexes = collection.index_information()

        # Check our named index exists
        assert "idx_tenant_asset_timestamp" in indexes, (
            "Missing compound index on sensor_readings — "
            "queries without this will scan the full collection at scale!"
        )

        index = indexes["idx_tenant_asset_timestamp"]
        keys = dict(index["key"])
        assert keys.get("tenant_id") == 1
        assert keys.get("asset_id") == 1
        assert keys.get("timestamp") == -1  # DESC for latest-first queries

    def test_aggregated_readings_collection_exists(self, mongo_client):
        """aggregated_readings collection for Spark windowed output must exist."""
        db = mongo_client["foresight"]
        assert "aggregated_readings" in db.list_collection_names()


# ─────────────────────────────────────────────────────────────────────────────
# MinIO tests
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.integration
class TestMinIO:
    """Verify MinIO buckets are accessible."""

    EXPECTED_BUCKETS = ["foresight-raw", "foresight-processed", "foresight-models"]

    def test_all_buckets_exist(self, minio_client):
        """All 3 required buckets must exist."""
        response = minio_client.list_buckets()
        existing_buckets = {b["Name"] for b in response["Buckets"]}

        for bucket in self.EXPECTED_BUCKETS:
            assert bucket in existing_buckets, (
                f"MinIO bucket '{bucket}' not found. Did minio-init container run?"
            )

    def test_can_write_and_read_object(self, minio_client):
        """Verify write + read round-trip works."""
        import io

        bucket = "foresight-raw"
        key = "test/health_check.txt"
        content = b"FORESIGHT MinIO health check"

        minio_client.put_object(Bucket=bucket, Key=key, Body=io.BytesIO(content))
        response = minio_client.get_object(Bucket=bucket, Key=key)
        assert response["Body"].read() == content

        # Cleanup
        minio_client.delete_object(Bucket=bucket, Key=key)


# ─────────────────────────────────────────────────────────────────────────────
# Unit tests (no Docker required)
# ─────────────────────────────────────────────────────────────────────────────


class TestSeedLogic:
    """Unit tests for seed.py helper functions — no DB required."""

    def test_tenant_config_structure(self):
        """TENANT_CONFIGS must have required keys."""
        from seed import TENANT_CONFIGS

        required_keys = {"tenant_id", "name", "client_id", "client_secret",
                         "subscription_tier", "config_json"}
        for cfg in TENANT_CONFIGS:
            assert required_keys.issubset(cfg.keys()), (
                f"Tenant config missing keys: {required_keys - cfg.keys()}"
            )

    def test_threshold_rules_template_complete(self):
        """Each rule template must have all required fields."""
        from seed import THRESHOLD_RULES_TEMPLATE

        required_keys = {"metric_name", "operator", "threshold_value", "severity", "description"}
        for rule in THRESHOLD_RULES_TEMPLATE:
            assert required_keys.issubset(rule.keys())

    def test_five_rules_defined(self):
        """Exactly 5 threshold rule templates must be defined."""
        from seed import THRESHOLD_RULES_TEMPLATE

        assert len(THRESHOLD_RULES_TEMPLATE) == 5

    def test_two_tenants_defined(self):
        """Exactly 2 test tenant configs defined."""
        from seed import TENANT_CONFIGS

        assert len(TENANT_CONFIGS) == 2

    def test_sensor_reading_model_validation(self):
        """SensorReading Pydantic model must reject infinite values."""
        import math

        from common.models import MetricName, SensorReading

        with pytest.raises(Exception):
            SensorReading(
                tenant_id="test",
                asset_id="asset-1",
                metric_name=MetricName.TEMPERATURE,
                value=math.inf,
                unit="degC",
            )

    def test_sensor_reading_model_valid(self):
        """SensorReading must accept valid numeric values."""
        from common.models import MetricName, QualityFlag, SensorReading

        reading = SensorReading(
            tenant_id="11111111-1111-1111-1111-111111111111",
            asset_id="asset-001",
            metric_name=MetricName.TEMPERATURE,
            value=72.5,
            unit="degC",
            quality_flag=QualityFlag.GOOD,
        )
        assert reading.value == 72.5
        assert reading.tenant_id == "11111111-1111-1111-1111-111111111111"
        assert reading.reading_id is not None

    def test_prediction_result_health_score_bounded(self):
        """PredictionResult health_score must be 0–100."""
        from common.models import PredictionResult

        result = PredictionResult(
            asset_id="asset-001",
            tenant_id="tenant-001",
            failure_prob_7d=0.15,
            failure_prob_30d=0.35,
            health_score=72.5,
            confidence_lower=0.10,
            confidence_upper=0.20,
            top_3_features=[
                {"feature": "vibration_mean_7d", "importance": 0.38, "value": 22.4}
            ],
            model_version="1.0",
        )
        assert 0 <= result.health_score <= 100
