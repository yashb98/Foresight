"""
FORESIGHT — SQLAlchemy declarative base and ORM models.

All PostgreSQL tables are defined here. Alembic reads this module's
metadata to generate and apply migrations automatically.

Design decisions:
- UUIDs as primary keys: avoids integer sequence collisions in multi-region setups.
- JSONB columns: for flexible metadata without schema churn.
- Explicit tenant_id on every table: enforces multi-tenancy at DB level.
- Indexes on (tenant_id, ...) for every table: ensures queries never do full scans.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, relationship
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    """Declarative base — all ORM models inherit from this."""
    pass


def _uuid() -> str:
    """Generate a new UUID4 string. Used as default for primary keys."""
    return str(uuid.uuid4())


# =============================================================================
# tenants — one row per customer organisation
# =============================================================================
class Tenant(Base):
    """
    A customer organisation using the FORESIGHT platform.
    Every other table references tenant_id as a discriminator.
    """

    __tablename__ = "tenants"

    tenant_id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    name = Column(String(255), nullable=False)
    config_json = Column(JSONB, nullable=False, default=dict,
                         comment="Connected systems, custom settings, feature flags")
    subscription_tier = Column(
        Enum("starter", "professional", "enterprise", name="subscription_tier_enum"),
        nullable=False,
        default="starter",
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(),
                        onupdate=func.now(), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)

    # Auth: hashed secret for /auth/token
    client_id = Column(String(128), unique=True, nullable=False)
    client_secret_hash = Column(String(255), nullable=False)

    # Relationships
    assets = relationship("Asset", back_populates="tenant", lazy="dynamic")
    alerts = relationship("Alert", back_populates="tenant", lazy="dynamic")
    rules = relationship("ThresholdRule", back_populates="tenant", lazy="dynamic")

    __table_args__ = (
        Index("idx_tenants_client_id", "client_id"),
        Index("idx_tenants_active", "is_active"),
    )

    def __repr__(self) -> str:
        return f"<Tenant id={self.tenant_id} name={self.name}>"


# =============================================================================
# assets — physical or logical assets being monitored
# =============================================================================
class Asset(Base):
    """
    A monitored asset (pump, turbine, transformer, etc.).
    Belongs to exactly one tenant.
    """

    __tablename__ = "assets"

    asset_id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    tenant_id = Column(UUID(as_uuid=False), ForeignKey("tenants.tenant_id", ondelete="CASCADE"),
                       nullable=False)
    name = Column(String(255), nullable=False)
    asset_type = Column(
        Enum("pump", "turbine", "transformer", "compressor", "motor",
             "valve", "conveyor", "generator", name="asset_type_enum"),
        nullable=False,
    )
    location = Column(String(500), nullable=True)
    criticality = Column(
        Enum("low", "medium", "high", "critical", name="criticality_enum"),
        nullable=False,
        default="medium",
    )
    installed_date = Column(Date, nullable=True)
    metadata_json = Column(JSONB, nullable=False, default=dict,
                           comment="SAP EQUNR, serial numbers, specs, etc.")
    source_system = Column(String(50), nullable=True,
                           comment="sap | asset_suite | manual")
    source_asset_id = Column(String(255), nullable=True,
                             comment="ID in the originating system")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(),
                        onupdate=func.now(), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)

    # Relationships
    tenant = relationship("Tenant", back_populates="assets")
    health_scores = relationship("AssetHealthScore", back_populates="asset", lazy="dynamic")
    alerts = relationship("Alert", back_populates="asset", lazy="dynamic")
    maintenance_records = relationship("MaintenanceRecord", back_populates="asset", lazy="dynamic")

    __table_args__ = (
        Index("idx_assets_tenant_id", "tenant_id"),
        Index("idx_assets_tenant_type", "tenant_id", "asset_type"),
        Index("idx_assets_source", "tenant_id", "source_system", "source_asset_id"),
    )

    def __repr__(self) -> str:
        return f"<Asset id={self.asset_id} name={self.name} type={self.asset_type}>"


# =============================================================================
# asset_health_scores — daily ML model output per asset
# =============================================================================
class AssetHealthScore(Base):
    """
    ML-computed health and failure probability for an asset on a given date.
    One row per asset per day. Upserted by the daily scoring Airflow DAG.
    """

    __tablename__ = "asset_health_scores"

    score_id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    asset_id = Column(UUID(as_uuid=False), ForeignKey("assets.asset_id", ondelete="CASCADE"),
                      nullable=False)
    tenant_id = Column(UUID(as_uuid=False), nullable=False)  # denormalised for fast queries
    score_date = Column(Date, nullable=False)
    health_score = Column(Numeric(5, 2), nullable=False,
                          comment="0–100, higher is healthier")
    failure_prob_7d = Column(Numeric(6, 4), nullable=False,
                             comment="Probability of failure within 7 days")
    failure_prob_30d = Column(Numeric(6, 4), nullable=False,
                              comment="Probability of failure within 30 days")
    model_version = Column(String(50), nullable=False)
    model_name = Column(String(100), nullable=False, default="foresight-failure-predictor")
    top_features_json = Column(JSONB, nullable=False, default=list,
                               comment="[{feature, importance, value}]")
    confidence_lower = Column(Numeric(6, 4), nullable=True)
    confidence_upper = Column(Numeric(6, 4), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    asset = relationship("Asset", back_populates="health_scores")

    __table_args__ = (
        UniqueConstraint("asset_id", "score_date", name="uq_asset_score_date"),
        Index("idx_scores_tenant_date", "tenant_id", "score_date"),
        Index("idx_scores_asset_date", "asset_id", "score_date"),
        Index("idx_scores_high_risk", "tenant_id", "failure_prob_30d"),
    )

    def __repr__(self) -> str:
        return (
            f"<AssetHealthScore asset={self.asset_id} date={self.score_date} "
            f"prob_7d={self.failure_prob_7d}>"
        )


# =============================================================================
# threshold_rules — tenant-configurable alert rules
# =============================================================================
class ThresholdRule(Base):
    """
    A rule that triggers an alert when a metric crosses a threshold.
    Loaded by Spark streaming job and refreshed every 60 seconds.
    """

    __tablename__ = "threshold_rules"

    rule_id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    tenant_id = Column(UUID(as_uuid=False), ForeignKey("tenants.tenant_id", ondelete="CASCADE"),
                       nullable=False)
    asset_type = Column(String(50), nullable=True,
                        comment="Null = applies to all asset types")
    metric_name = Column(String(50), nullable=False)
    operator = Column(
        Enum("gt", "lt", "gte", "lte", "eq", name="rule_operator_enum"),
        nullable=False,
    )
    threshold_value = Column(Numeric(12, 4), nullable=False)
    severity = Column(
        Enum("low", "medium", "high", "critical", name="severity_enum"),
        nullable=False,
        default="medium",
    )
    active = Column(Boolean, nullable=False, default=True)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(),
                        onupdate=func.now(), nullable=False)

    # Relationships
    tenant = relationship("Tenant", back_populates="rules")

    __table_args__ = (
        Index("idx_rules_tenant_active", "tenant_id", "active"),
        Index("idx_rules_tenant_metric", "tenant_id", "metric_name"),
    )

    def __repr__(self) -> str:
        return (
            f"<ThresholdRule id={self.rule_id} metric={self.metric_name} "
            f"op={self.operator} threshold={self.threshold_value}>"
        )


# =============================================================================
# alerts — triggered alert events
# =============================================================================
class Alert(Base):
    """
    An alert triggered by a threshold rule breach.
    Published to Kafka and written here for the API and dashboard.
    """

    __tablename__ = "alerts"

    alert_id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    asset_id = Column(UUID(as_uuid=False), ForeignKey("assets.asset_id", ondelete="CASCADE"),
                      nullable=False)
    tenant_id = Column(UUID(as_uuid=False), ForeignKey("tenants.tenant_id", ondelete="CASCADE"),
                       nullable=False)
    rule_id = Column(UUID(as_uuid=False), ForeignKey("threshold_rules.rule_id",
                                                      ondelete="SET NULL"),
                     nullable=True)
    alert_type = Column(String(50), nullable=False, default="threshold_breach")
    metric_name = Column(String(50), nullable=False)
    actual_value = Column(Numeric(12, 4), nullable=True)
    threshold_value = Column(Numeric(12, 4), nullable=True)
    severity = Column(
        Enum("low", "medium", "high", "critical", name="severity_enum"),
        nullable=False,
    )
    status = Column(
        Enum("active", "acknowledged", "resolved", name="alert_status_enum"),
        nullable=False,
        default="active",
    )
    triggered_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    acknowledged_at = Column(DateTime(timezone=True), nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    acknowledged_by = Column(String(255), nullable=True)
    notes = Column(Text, nullable=True)

    # Relationships
    tenant = relationship("Tenant", back_populates="alerts")
    asset = relationship("Asset", back_populates="alerts")
    rule = relationship("ThresholdRule")

    __table_args__ = (
        Index("idx_alerts_tenant_status", "tenant_id", "status"),
        Index("idx_alerts_tenant_triggered", "tenant_id", "triggered_at"),
        Index("idx_alerts_asset_active", "asset_id", "status"),
    )

    def __repr__(self) -> str:
        return (
            f"<Alert id={self.alert_id} asset={self.asset_id} "
            f"severity={self.severity} status={self.status}>"
        )


# =============================================================================
# maintenance_records — historical maintenance events from all source systems
# =============================================================================
class MaintenanceRecord(Base):
    """
    A maintenance event sourced from SAP, Asset Suite 9, or manual entry.
    Used as features in the ML failure prediction model.
    """

    __tablename__ = "maintenance_records"

    record_id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    asset_id = Column(UUID(as_uuid=False), ForeignKey("assets.asset_id", ondelete="CASCADE"),
                      nullable=False)
    tenant_id = Column(UUID(as_uuid=False), nullable=False)
    maintenance_type = Column(String(100), nullable=False,
                              comment="preventive | corrective | predictive | inspection")
    performed_at = Column(DateTime(timezone=True), nullable=False)
    cost = Column(Numeric(12, 2), nullable=True)
    outcome = Column(String(255), nullable=True,
                     comment="success | partial | failure | deferred")
    source_system = Column(
        Enum("sap", "asset_suite", "manual", name="source_system_enum"),
        nullable=False,
    )
    source_record_id = Column(String(255), nullable=True,
                              comment="SAP AUFNR or Asset Suite record ID")
    description = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    asset = relationship("Asset", back_populates="maintenance_records")

    __table_args__ = (
        Index("idx_maintenance_tenant_asset", "tenant_id", "asset_id"),
        Index("idx_maintenance_asset_date", "asset_id", "performed_at"),
        Index("idx_maintenance_source", "source_system", "source_record_id"),
    )

    def __repr__(self) -> str:
        return (
            f"<MaintenanceRecord id={self.record_id} asset={self.asset_id} "
            f"type={self.maintenance_type} at={self.performed_at}>"
        )
