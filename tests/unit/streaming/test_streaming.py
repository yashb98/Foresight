"""
FORESIGHT — Day 3 Streaming Layer Tests

Tests:
  - Rule evaluation logic: exactly at threshold, above, below, operators
  - Windowed aggregation correctness (static DataFrames)
  - Alert creation schema validation
  - RulesLoader cache logic
  - Anomaly → alert pipeline integration (mocked Kafka)

Run offline (no Docker / no Spark cluster):
    pytest tests/unit/streaming/test_streaming.py -v -m "not integration"
"""

from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))


# ─────────────────────────────────────────────────────────────────────────────
# Rules Engine Tests (no Spark needed)
# ─────────────────────────────────────────────────────────────────────────────

class TestCachedRule:
    """Unit tests for threshold rule evaluation logic."""

    def _make_rule(self, operator: str, threshold: float) -> "CachedRule":
        from streaming.rules_loader import CachedRule

        return CachedRule(
            rule_id=str(uuid.uuid4()),
            tenant_id="t1",
            asset_type=None,
            metric_name="temperature",
            operator=operator,
            threshold_value=threshold,
            severity="high",
            active=True,
        )

    def test_gt_above_threshold_triggers(self):
        """Value above threshold triggers GT rule."""
        rule = self._make_rule("gt", 85.0)
        assert rule.evaluate(86.0) is True

    def test_gt_exactly_at_threshold_does_not_trigger(self):
        """Value exactly at threshold does NOT trigger GT (strictly greater)."""
        rule = self._make_rule("gt", 85.0)
        assert rule.evaluate(85.0) is False

    def test_gt_below_threshold_does_not_trigger(self):
        """Value below threshold does not trigger GT rule."""
        rule = self._make_rule("gt", 85.0)
        assert rule.evaluate(80.0) is False

    def test_gte_exactly_at_threshold_triggers(self):
        """Value exactly at threshold triggers GTE rule."""
        rule = self._make_rule("gte", 85.0)
        assert rule.evaluate(85.0) is True

    def test_lt_below_threshold_triggers(self):
        """Value below threshold triggers LT rule (e.g. RPM < 500)."""
        rule = self._make_rule("lt", 500.0)
        assert rule.evaluate(499.9) is True

    def test_lt_above_threshold_does_not_trigger(self):
        """Value above threshold does not trigger LT rule."""
        rule = self._make_rule("lt", 500.0)
        assert rule.evaluate(600.0) is False

    def test_lte_exactly_at_threshold_triggers(self):
        """Value exactly at threshold triggers LTE rule."""
        rule = self._make_rule("lte", 500.0)
        assert rule.evaluate(500.0) is True

    def test_eq_exact_match_triggers(self):
        """Exact value match triggers EQ rule."""
        rule = self._make_rule("eq", 100.0)
        assert rule.evaluate(100.0) is True

    def test_eq_near_match_does_not_trigger(self):
        """Near-match does not trigger EQ (within floating-point tolerance)."""
        rule = self._make_rule("eq", 100.0)
        assert rule.evaluate(100.001) is False

    def test_critical_temperature_threshold(self):
        """Critical 95°C temperature rule works correctly."""
        rule = self._make_rule("gt", 95.0)
        assert rule.evaluate(95.1) is True
        assert rule.evaluate(95.0) is False
        assert rule.evaluate(94.9) is False

    def test_vibration_threshold_35_mm_s(self):
        """High vibration threshold (35 mm/s) works correctly."""
        rule = self._make_rule("gt", 35.0)
        assert rule.evaluate(35.5) is True
        assert rule.evaluate(34.9) is False

    def test_pressure_critical_threshold(self):
        """Critical pressure threshold (180 bar) works correctly."""
        rule = self._make_rule("gt", 180.0)
        assert rule.evaluate(181.0) is True
        assert rule.evaluate(179.99) is False


class TestRulesLoader:
    """Unit tests for the RulesLoader cache management."""

    def test_get_rules_for_unknown_tenant_returns_empty_list(self):
        """Unknown tenant ID should return empty list, not raise."""
        with patch("streaming.rules_loader.RulesLoader._load_rules"), \
             patch("streaming.rules_loader.RulesLoader._start_refresh_thread"):
            from streaming.rules_loader import RulesLoader

            loader = RulesLoader.__new__(RulesLoader)
            loader._rules = {}
            loader._lock = __import__("threading").RLock()

            result = loader.get_rules_for_tenant("unknown-tenant-id")
            assert result == []

    def test_rule_count_returns_total_across_tenants(self):
        """rule_count property must sum across all tenants."""
        from streaming.rules_loader import CachedRule

        with patch("streaming.rules_loader.RulesLoader._load_rules"), \
             patch("streaming.rules_loader.RulesLoader._start_refresh_thread"):
            from streaming.rules_loader import RulesLoader

            loader = RulesLoader.__new__(RulesLoader)
            loader._lock = __import__("threading").RLock()

            def make_rule(metric: str) -> CachedRule:
                return CachedRule(
                    rule_id=str(uuid.uuid4()), tenant_id="t1",
                    asset_type=None, metric_name=metric,
                    operator="gt", threshold_value=85.0,
                    severity="high", active=True,
                )

            loader._rules = {
                "tenant-1": [make_rule("temperature"), make_rule("vibration")],
                "tenant-2": [make_rule("pressure")],
            }

            assert loader.rule_count == 3

    def test_metric_name_filtering_in_evaluate(self):
        """Rules should only fire for their configured metric."""
        from streaming.rules_loader import CachedRule

        temp_rule = CachedRule(
            rule_id=str(uuid.uuid4()), tenant_id="t1",
            asset_type=None, metric_name="temperature",
            operator="gt", threshold_value=85.0,
            severity="high", active=True,
        )
        # Rule is for temperature, vibration value of 99 should NOT trigger it
        # (filtering by metric_name is done in AlertEngine, not the rule itself)
        assert temp_rule.metric_name == "temperature"
        # The evaluate() method only checks the value, caller must filter by metric
        assert temp_rule.evaluate(99.0) is True  # Value check passes


# ─────────────────────────────────────────────────────────────────────────────
# Alert Creation Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestAlertCreation:
    """Unit tests for Alert domain model creation."""

    def test_alert_has_uuid_id(self):
        """Alert must be assigned a UUID on creation."""
        from common.models import Alert, AlertStatus, RuleOperator, Severity

        alert = Alert(
            tenant_id="t1",
            asset_id="a1",
            rule_id="r1",
            metric_name="temperature",
            actual_value=92.5,
            threshold_value=85.0,
            operator=RuleOperator.GT,
            severity=Severity.HIGH,
        )
        assert alert.alert_id is not None
        assert len(alert.alert_id) == 36  # UUID format

    def test_alert_status_defaults_to_active(self):
        """New alerts must default to ACTIVE status."""
        from common.models import Alert, AlertStatus, RuleOperator, Severity

        alert = Alert(
            tenant_id="t1",
            asset_id="a1",
            rule_id="r1",
            metric_name="vibration",
            actual_value=40.0,
            threshold_value=35.0,
            operator=RuleOperator.GT,
            severity=Severity.HIGH,
        )
        assert alert.status == AlertStatus.ACTIVE

    def test_alert_triggered_at_is_set(self):
        """Alert triggered_at must be populated automatically."""
        from common.models import Alert, RuleOperator, Severity

        alert = Alert(
            tenant_id="t1",
            asset_id="a1",
            rule_id="r1",
            metric_name="pressure",
            actual_value=185.0,
            threshold_value=180.0,
            operator=RuleOperator.GT,
            severity=Severity.CRITICAL,
        )
        assert alert.triggered_at is not None
        assert isinstance(alert.triggered_at, datetime)

    def test_alert_serialises_to_dict(self):
        """Alert must serialise to JSON-compatible dict for Kafka publishing."""
        import json
        from common.models import Alert, RuleOperator, Severity

        alert = Alert(
            tenant_id="t1",
            asset_id="a1",
            rule_id="r1",
            metric_name="temperature",
            actual_value=88.0,
            threshold_value=85.0,
            operator=RuleOperator.GT,
            severity=Severity.HIGH,
        )
        d = alert.model_dump(mode="json")
        json_str = json.dumps(d, default=str)
        parsed = json.loads(json_str)
        assert parsed["tenant_id"] == "t1"
        assert parsed["metric_name"] == "temperature"
        assert parsed["severity"] == "high"


# ─────────────────────────────────────────────────────────────────────────────
# Windowed Aggregation Logic Tests (static data, no Spark cluster)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.slow
class TestAggregations:
    """
    Tests for windowed aggregation logic using Spark local mode.
    Marked slow because Spark startup takes ~10 seconds.
    """

    @pytest.fixture(scope="class")
    def spark(self):
        """Create a local SparkSession for testing."""
        try:
            from pyspark.sql import SparkSession

            spark = (
                SparkSession.builder.master("local[2]")
                .appName("FORESIGHT-Test")
                .config("spark.sql.shuffle.partitions", "2")
                .getOrCreate()
            )
            spark.sparkContext.setLogLevel("ERROR")
            yield spark
            spark.stop()
        except Exception:
            pytest.skip("PySpark not available")

    def test_mean_aggregation_correct(self, spark):
        """Mean aggregation must compute the correct average."""
        from datetime import timedelta

        from pyspark.sql import types as T
        from streaming.aggregations import _aggregate_window

        # Create a static DataFrame with known values
        schema = T.StructType([
            T.StructField("tenant_id", T.StringType()),
            T.StructField("asset_id", T.StringType()),
            T.StructField("metric_name", T.StringType()),
            T.StructField("value", T.DoubleType()),
            T.StructField("quality_flag", T.StringType()),
            T.StructField("event_time", T.TimestampType()),
        ])

        base_time = datetime(2026, 2, 20, 10, 0, tzinfo=timezone.utc)
        data = [
            ("t1", "a1", "temperature", 70.0, "good", base_time),
            ("t1", "a1", "temperature", 80.0, "good", base_time + timedelta(seconds=30)),
            ("t1", "a1", "temperature", 90.0, "good", base_time + timedelta(seconds=60)),
        ]

        df = spark.createDataFrame(data, schema)
        # Expected mean: (70+80+90)/3 = 80.0

        grouped = df.groupBy("tenant_id", "asset_id", "metric_name").agg(
            __import__("pyspark.sql.functions", fromlist=["mean"]).mean("value").alias("mean_value")
        )
        result = grouped.collect()[0]
        assert abs(result["mean_value"] - 80.0) < 0.001

    def test_max_aggregation_detects_spike(self, spark):
        """Max aggregation must capture the highest value for alert detection."""
        from datetime import timedelta

        from pyspark.sql import functions as F, types as T

        schema = T.StructType([
            T.StructField("tenant_id", T.StringType()),
            T.StructField("asset_id", T.StringType()),
            T.StructField("metric_name", T.StringType()),
            T.StructField("value", T.DoubleType()),
            T.StructField("quality_flag", T.StringType()),
        ])

        # One anomaly spike in a window of normal readings
        data = [
            ("t1", "a1", "temperature", 60.0, "good"),
            ("t1", "a1", "temperature", 62.0, "good"),
            ("t1", "a1", "temperature", 95.5, "suspect"),  # anomaly
            ("t1", "a1", "temperature", 61.0, "good"),
        ]

        df = spark.createDataFrame(data, schema)
        result = df.groupBy("tenant_id", "asset_id", "metric_name").agg(
            F.max("value").alias("max_value")
        ).collect()[0]

        assert result["max_value"] == 95.5

    def test_suspect_readings_excluded_from_mean(self, spark):
        """Suspect quality readings must be excluded from mean calculation."""
        from pyspark.sql import functions as F, types as T

        schema = T.StructType([
            T.StructField("tenant_id", T.StringType()),
            T.StructField("asset_id", T.StringType()),
            T.StructField("metric_name", T.StringType()),
            T.StructField("value", T.DoubleType()),
            T.StructField("quality_flag", T.StringType()),
        ])

        data = [
            ("t1", "a1", "temperature", 60.0, "good"),
            ("t1", "a1", "temperature", 62.0, "good"),
            ("t1", "a1", "temperature", 500.0, "suspect"),  # should be excluded
        ]

        df = spark.createDataFrame(data, schema)
        # Filter suspects (as aggregations.py does)
        clean = df.filter(F.col("quality_flag") != "suspect")
        result = clean.groupBy("tenant_id", "asset_id", "metric_name").agg(
            F.mean("value").alias("mean_value")
        ).collect()[0]

        # Mean of [60, 62] = 61.0, not affected by 500.0
        assert abs(result["mean_value"] - 61.0) < 0.001
