"""
FORESIGHT — Threshold Rules Loader

Loads threshold rules from PostgreSQL into a local cache that the streaming
alert engine uses for rule evaluation. Refreshes every 60 seconds so new rules
created via the API take effect without restarting the Spark job.

Design:
  - Thread-safe: uses a lock around cache updates
  - Graceful degradation: if PostgreSQL is unreachable, keeps the last known rules
  - Background thread: refresh runs independently of the Spark streaming micro-batch
"""

from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional

log = logging.getLogger(__name__)


@dataclass
class CachedRule:
    """A threshold rule loaded from PostgreSQL into memory."""

    rule_id: str
    tenant_id: str
    asset_type: Optional[str]  # None = applies to all asset types
    metric_name: str
    operator: str  # gt | lt | gte | lte | eq
    threshold_value: float
    severity: str
    active: bool

    def evaluate(self, value: float) -> bool:
        """
        Check whether a sensor value breaches this rule.

        Args:
            value: Sensor metric value to evaluate.

        Returns:
            True if the value breaches the threshold, False otherwise.
        """
        ops = {
            "gt": value > self.threshold_value,
            "lt": value < self.threshold_value,
            "gte": value >= self.threshold_value,
            "lte": value <= self.threshold_value,
            "eq": abs(value - self.threshold_value) < 1e-9,
        }
        return ops.get(self.operator, False)


class RulesLoader:
    """
    Manages a refreshing cache of threshold rules loaded from PostgreSQL.

    Args:
        refresh_interval_seconds: How often to reload rules from the DB.
        db_url:                   PostgreSQL connection URL. Reads from env if None.
    """

    def __init__(
        self,
        refresh_interval_seconds: int = 60,
        db_url: Optional[str] = None,
    ) -> None:
        self._db_url = db_url or os.getenv("DATABASE_URL_SYNC")
        self._refresh_interval = refresh_interval_seconds
        self._rules: Dict[str, List[CachedRule]] = {}  # tenant_id → rules
        self._lock = threading.RLock()
        self._last_loaded: Optional[datetime] = None
        self._load_error_count: int = 0

        # Load rules immediately at startup
        self._load_rules()

        # Start background refresh thread
        self._start_refresh_thread()

    def get_rules_for_tenant(self, tenant_id: str) -> List[CachedRule]:
        """
        Return all active threshold rules for a given tenant.

        Args:
            tenant_id: Tenant UUID string.

        Returns:
            List of CachedRule objects. Empty list if tenant has no rules.
        """
        with self._lock:
            return self._rules.get(tenant_id, [])

    def get_all_rules(self) -> Dict[str, List[CachedRule]]:
        """
        Return all cached rules (all tenants).

        Returns:
            Dict mapping tenant_id → list of rules.
        """
        with self._lock:
            return dict(self._rules)

    def _load_rules(self) -> None:
        """
        Query PostgreSQL for all active threshold rules and update the cache.
        Silently keeps old rules if the DB query fails.
        """
        if not self._db_url:
            log.warning("DATABASE_URL_SYNC not set — rules cache will be empty")
            return

        try:
            import sqlalchemy as sa

            engine = sa.create_engine(self._db_url, pool_pre_ping=True)
            query = sa.text("""
                SELECT rule_id, tenant_id, asset_type, metric_name,
                       operator, threshold_value, severity, active
                FROM threshold_rules
                WHERE active = true
            """)

            with engine.connect() as conn:
                rows = conn.execute(query).fetchall()

            new_rules: Dict[str, List[CachedRule]] = {}
            for row in rows:
                rule = CachedRule(
                    rule_id=str(row[0]),
                    tenant_id=str(row[1]),
                    asset_type=row[2],
                    metric_name=str(row[3]),
                    operator=str(row[4]),
                    threshold_value=float(row[5]),
                    severity=str(row[6]),
                    active=bool(row[7]),
                )
                if rule.tenant_id not in new_rules:
                    new_rules[rule.tenant_id] = []
                new_rules[rule.tenant_id].append(rule)

            with self._lock:
                self._rules = new_rules
                self._last_loaded = datetime.utcnow()
                self._load_error_count = 0

            total_rules = sum(len(v) for v in new_rules.values())
            log.info(
                "Rules cache refreshed: %d tenants, %d total active rules",
                len(new_rules),
                total_rules,
            )
            engine.dispose()

        except Exception as exc:
            self._load_error_count += 1
            log.error(
                "Failed to load rules from PostgreSQL (error #%d): %s — " "keeping previous cache",
                self._load_error_count,
                exc,
            )

    def _start_refresh_thread(self) -> None:
        """Start a daemon background thread that refreshes rules periodically."""

        def _refresh_loop() -> None:
            while True:
                time.sleep(self._refresh_interval)
                log.debug("Refreshing threshold rules from PostgreSQL...")
                self._load_rules()

        thread = threading.Thread(target=_refresh_loop, daemon=True, name="rules-refresher")
        thread.start()
        log.info("Rules refresh thread started: interval=%ds", self._refresh_interval)

    @property
    def last_loaded(self) -> Optional[datetime]:
        """Return the datetime of the last successful rules load."""
        return self._last_loaded

    @property
    def rule_count(self) -> int:
        """Return total number of cached active rules across all tenants."""
        with self._lock:
            return sum(len(v) for v in self._rules.values())
