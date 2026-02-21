"""
FORESIGHT — Alert Engine

Evaluates windowed sensor aggregations against loaded threshold rules.
For each breach, creates an Alert and publishes it to the Kafka 'asset-alerts' topic
and writes to PostgreSQL for the API to serve.

Architecture note:
  Spark Structured Streaming uses foreachBatch to call Python code per micro-batch.
  This avoids the driver-executor serialisation overhead of map/filter UDFs and
  gives us full control over the rule evaluation logic with Python data structures.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

from pyspark.sql import DataFrame, StreamingQuery

from common.models import Alert, AlertStatus, RuleOperator, Severity
from streaming.rules_loader import CachedRule, RulesLoader

log = logging.getLogger(__name__)


class AlertEngine:
    """
    Evaluates windowed aggregation DataFrames against threshold rules.
    Publishes breaches to Kafka and PostgreSQL.

    Args:
        rules_loader: RulesLoader instance with cached threshold rules.
        kafka_bootstrap: Kafka bootstrap servers.
        pg_url: PostgreSQL synchronous connection URL.
    """

    def __init__(
        self,
        rules_loader: RulesLoader,
        kafka_bootstrap: Optional[str] = None,
        pg_url: Optional[str] = None,
    ) -> None:
        self._rules = rules_loader
        self._kafka_bootstrap = kafka_bootstrap or os.getenv(
            "KAFKA_BOOTSTRAP_SERVERS", "kafka:9092"
        )
        self._alert_topic = os.getenv("KAFKA_TOPIC_ALERTS", "asset-alerts")
        self._pg_url = pg_url or os.getenv("DATABASE_URL_SYNC")
        log.info("AlertEngine initialised — topic: %s", self._alert_topic)

    def evaluate_stream(
        self, agg_df: DataFrame, trigger_interval: str = "30 seconds"
    ) -> StreamingQuery:
        """
        Start a streaming query that evaluates each micro-batch for threshold breaches.

        Args:
            agg_df:           Streaming DataFrame of windowed aggregations.
            trigger_interval: How often Spark processes a micro-batch.

        Returns:
            Active StreamingQuery handle.
        """
        return (
            agg_df.writeStream.foreachBatch(self._evaluate_batch)
            .outputMode("update")
            .trigger(processingTime=trigger_interval)
            .option(
                "checkpointLocation",
                "/tmp/spark-checkpoints/alert-engine",
            )
            .start()
        )

    def _evaluate_batch(self, batch_df: DataFrame, batch_id: int) -> None:
        """
        Evaluate a single micro-batch against all active threshold rules.
        Called by Spark's foreachBatch for each trigger interval.

        Args:
            batch_df: Micro-batch DataFrame with windowed aggregation rows.
            batch_id: Spark micro-batch ID (for idempotency logging).
        """
        if batch_df.isEmpty():
            return

        log.debug("Evaluating batch %d for threshold breaches", batch_id)
        rows = batch_df.collect()
        alerts_created = 0

        for row in rows:
            tenant_id = row["tenant_id"]
            asset_id = row["asset_id"]
            metric_name = row["metric_name"]
            max_value = row["max_value"]  # use max_value for breach detection (worst reading)

            tenant_rules = self._rules.get_rules_for_tenant(tenant_id)

            for rule in tenant_rules:
                # Skip rules for specific asset types if they don't match
                # (asset_type=None means rule applies to all types)
                if rule.metric_name != metric_name:
                    continue

                if rule.evaluate(max_value):
                    alert = self._create_alert(
                        tenant_id=tenant_id,
                        asset_id=asset_id,
                        rule=rule,
                        actual_value=max_value,
                        window_start=row["window_start"],
                    )
                    self._publish_alert_to_kafka(alert)
                    self._write_alert_to_postgres(alert)
                    alerts_created += 1

        if alerts_created > 0:
            log.info(
                "Batch %d: %d alerts triggered across %d rows",
                batch_id,
                alerts_created,
                len(rows),
            )

    def _create_alert(
        self,
        tenant_id: str,
        asset_id: str,
        rule: CachedRule,
        actual_value: float,
        window_start,
    ) -> Alert:
        """
        Create an Alert domain object from a rule breach.

        Args:
            tenant_id:    Tenant UUID.
            asset_id:     Asset UUID.
            rule:         The breached threshold rule.
            actual_value: Actual sensor value that caused the breach.
            window_start: Start of the aggregation window.

        Returns:
            Alert Pydantic model instance.
        """
        return Alert(
            alert_id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            asset_id=asset_id,
            rule_id=rule.rule_id,
            alert_type="threshold_breach",
            metric_name=rule.metric_name,
            actual_value=round(actual_value, 4),
            threshold_value=rule.threshold_value,
            operator=RuleOperator(rule.operator),
            severity=Severity(rule.severity),
            status=AlertStatus.ACTIVE,
            triggered_at=datetime.now(tz=timezone.utc),
        )

    def _publish_alert_to_kafka(self, alert: Alert) -> None:
        """
        Publish an alert to the Kafka 'asset-alerts' topic.

        Uses a simple producer per-batch (not persistent) to avoid serialisation
        issues with Spark executors. In production, consider a batched Kafka sink.

        Args:
            alert: Alert domain object to publish.
        """
        try:
            from kafka import KafkaProducer

            producer = KafkaProducer(
                bootstrap_servers=self._kafka_bootstrap,
                value_serializer=lambda v: json.dumps(v, default=str).encode("utf-8"),
                key_serializer=lambda k: k.encode("utf-8") if k else None,
                acks=1,
                retries=2,
            )
            producer.send(
                self._alert_topic,
                key=alert.tenant_id,
                value=alert.model_dump(mode="json"),
                headers=[
                    ("tenant_id", alert.tenant_id.encode()),
                    ("severity", alert.severity.encode()),
                    ("metric_name", alert.metric_name.encode()),
                ],
            )
            producer.flush()
            producer.close()
            log.info(
                "Alert published: asset=%s metric=%s value=%.2f (threshold=%.2f %s) severity=%s",
                alert.asset_id,
                alert.metric_name,
                alert.actual_value,
                alert.threshold_value,
                alert.operator,
                alert.severity,
            )
        except Exception as exc:
            log.error("Failed to publish alert to Kafka: %s", exc)

    def _write_alert_to_postgres(self, alert: Alert) -> None:
        """
        Persist an alert to PostgreSQL for the API to serve.
        Uses a short-lived synchronous connection (foreachBatch context).

        Args:
            alert: Alert domain object to persist.
        """
        if not self._pg_url:
            log.warning("No PostgreSQL URL — alert will not be persisted")
            return

        try:
            import sqlalchemy as sa

            engine = sa.create_engine(self._pg_url, pool_pre_ping=True)
            insert_sql = sa.text("""
                INSERT INTO alerts (
                    alert_id, asset_id, tenant_id, rule_id, alert_type,
                    metric_name, actual_value, threshold_value,
                    severity, status, triggered_at
                ) VALUES (
                    :alert_id, :asset_id, :tenant_id, :rule_id, :alert_type,
                    :metric_name, :actual_value, :threshold_value,
                    :severity, :status, :triggered_at
                )
                ON CONFLICT (alert_id) DO NOTHING
            """)

            with engine.begin() as conn:
                conn.execute(
                    insert_sql,
                    {
                        "alert_id": alert.alert_id,
                        "asset_id": alert.asset_id,
                        "tenant_id": alert.tenant_id,
                        "rule_id": alert.rule_id,
                        "alert_type": alert.alert_type,
                        "metric_name": alert.metric_name,
                        "actual_value": float(alert.actual_value),
                        "threshold_value": float(alert.threshold_value),
                        "severity": alert.severity.value,
                        "status": alert.status.value,
                        "triggered_at": alert.triggered_at,
                    },
                )
            engine.dispose()
        except Exception as exc:
            log.error("Failed to write alert to PostgreSQL: %s", exc)
