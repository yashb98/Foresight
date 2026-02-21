"""
FORESIGHT — Shared Pydantic data models.

These models are the single source of truth for data structures crossing
service boundaries: ingestion → Kafka → streaming → DB → API.
Import from here — never redefine schemas in individual modules.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

# =============================================================================
# Enumerations
# =============================================================================


class AssetType(str, Enum):
    """Supported asset categories."""

    PUMP = "pump"
    TURBINE = "turbine"
    TRANSFORMER = "transformer"
    COMPRESSOR = "compressor"
    MOTOR = "motor"
    VALVE = "valve"
    CONVEYOR = "conveyor"
    GENERATOR = "generator"


class Criticality(str, Enum):
    """Asset criticality levels — drives alert priority and SLA."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Severity(str, Enum):
    """Alert / rule severity levels."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AlertStatus(str, Enum):
    """Lifecycle state of an alert."""

    ACTIVE = "active"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"


class RuleOperator(str, Enum):
    """Threshold comparison operators."""

    GT = "gt"
    LT = "lt"
    GTE = "gte"
    LTE = "lte"
    EQ = "eq"


class QualityFlag(str, Enum):
    """Sensor reading data quality."""

    GOOD = "good"
    DEGRADED = "degraded"
    SUSPECT = "suspect"


class MetricName(str, Enum):
    """Supported sensor metric types."""

    TEMPERATURE = "temperature"
    VIBRATION = "vibration"
    PRESSURE = "pressure"
    RPM = "rpm"
    CURRENT = "current"
    VOLTAGE = "voltage"
    FLOW_RATE = "flow_rate"


class SourceSystem(str, Enum):
    """Source system for maintenance records."""

    SAP = "sap"
    ASSET_SUITE = "asset_suite"
    MANUAL = "manual"


class SubscriptionTier(str, Enum):
    """Tenant subscription levels."""

    STARTER = "starter"
    PROFESSIONAL = "professional"
    ENTERPRISE = "enterprise"


# =============================================================================
# Core sensor / ingestion models
# =============================================================================


class SensorReading(BaseModel):
    """
    A single sensor telemetry reading from any asset.

    Published to Kafka topic 'sensor-readings' by the simulator and all
    physical connectors. Consumed by Spark Structured Streaming.
    """

    reading_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str = Field(..., description="Tenant UUID — required for multi-tenancy")
    asset_id: str = Field(..., description="Asset UUID")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    metric_name: MetricName
    value: float
    unit: str = Field(..., description="degC | mm_s | bar | rpm")
    quality_flag: QualityFlag = QualityFlag.GOOD
    source: str = Field(default="simulator", description="Data source identifier")

    @field_validator("value")
    @classmethod
    def value_must_be_finite(cls, v: float) -> float:
        """Reject NaN and infinite sensor values."""
        import math

        if not math.isfinite(v):
            raise ValueError(f"Sensor value must be finite, got: {v}")
        return round(v, 4)

    def to_kafka_dict(self) -> Dict[str, Any]:
        """Serialise to dict suitable for Kafka JSON message."""
        return self.model_dump(mode="json")


class SAPEquipmentRecord(BaseModel):
    """
    SAP Equipment Master record (EQUI table equivalent).
    Field names mirror SAP PM field naming conventions.
    """

    tenant_id: str
    equnr: str = Field(..., description="Equipment number (SAP EQUNR)")
    eqktx: str = Field(..., description="Equipment short description")
    eqart: str = Field(..., description="Type of technical object")
    anlnr: Optional[str] = Field(None, description="Asset number")
    brgew: Optional[float] = Field(None, description="Gross weight")
    gewei: Optional[str] = Field(None, description="Unit of weight")
    baujj: Optional[int] = Field(None, description="Year of manufacture")
    inbdt: Optional[datetime] = Field(None, description="Start-up date")
    swerk: Optional[str] = Field(None, description="Maintenance plant")
    iwerk: Optional[str] = Field(None, description="Planning plant")
    extracted_at: datetime = Field(default_factory=datetime.utcnow)
    raw_json: Dict[str, Any] = Field(default_factory=dict)


class SAPWorkOrder(BaseModel):
    """SAP Work Order (AUFK table equivalent)."""

    tenant_id: str
    aufnr: str = Field(..., description="Order number (SAP AUFNR)")
    auart: str = Field(..., description="Order type")
    equnr: Optional[str] = Field(None, description="Equipment number")
    ktext: Optional[str] = Field(None, description="Short description")
    erdat: Optional[datetime] = Field(None, description="Creation date")
    gstrp: Optional[datetime] = Field(None, description="Scheduled start date")
    gltrp: Optional[datetime] = Field(None, description="Scheduled end date")
    istat: Optional[str] = Field(None, description="Object status")
    kostl: Optional[str] = Field(None, description="Cost centre")
    extracted_at: datetime = Field(default_factory=datetime.utcnow)


class AssetSuiteRecord(BaseModel):
    """Asset Suite 9 asset register record."""

    tenant_id: str
    asset_id: str = Field(..., description="Asset Suite internal asset ID")
    asset_name: str
    asset_class: str
    parent_id: Optional[str] = None
    location_code: str
    criticality_rating: str
    install_date: Optional[datetime] = None
    last_maintenance: Optional[datetime] = None
    maintenance_schedule: Optional[str] = None
    failure_codes: List[str] = Field(default_factory=list)
    extracted_at: datetime = Field(default_factory=datetime.utcnow)
    raw_json: Dict[str, Any] = Field(default_factory=dict)


# =============================================================================
# Processed / alert models
# =============================================================================


class WindowedAggregate(BaseModel):
    """
    Result of a Spark windowed aggregation over sensor readings.
    Written to MongoDB aggregated_readings collection.
    """

    tenant_id: str
    asset_id: str
    metric_name: MetricName
    window_start: datetime
    window_end: datetime
    window_size: str = Field(..., description="5min | 1hour | 24hour")
    mean_value: float
    max_value: float
    min_value: float
    std_dev: float
    reading_count: int
    computed_at: datetime = Field(default_factory=datetime.utcnow)


class Alert(BaseModel):
    """
    An alert triggered when a sensor metric breaches a configured threshold rule.
    Published to Kafka 'asset-alerts' topic and stored in PostgreSQL.
    """

    alert_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    asset_id: str
    rule_id: str
    alert_type: str = Field(default="threshold_breach")
    metric_name: str
    actual_value: float
    threshold_value: float
    operator: RuleOperator
    severity: Severity
    status: AlertStatus = AlertStatus.ACTIVE
    triggered_at: datetime = Field(default_factory=datetime.utcnow)
    resolved_at: Optional[datetime] = None
    acknowledged_by: Optional[str] = None
    notes: Optional[str] = None


class ThresholdRule(BaseModel):
    """
    Tenant-configurable threshold rule for real-time alerting.
    Stored in PostgreSQL threshold_rules table. Loaded by Spark streaming job.
    """

    rule_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    asset_type: Optional[AssetType] = None  # None = applies to all types
    metric_name: MetricName
    operator: RuleOperator
    threshold_value: float
    severity: Severity
    active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)


class PredictionResult(BaseModel):
    """
    ML model prediction output for a single asset.
    Returned by FastAPI /predict endpoint and stored in asset_health_scores.
    """

    asset_id: str
    tenant_id: str
    predicted_at: datetime = Field(default_factory=datetime.utcnow)
    failure_prob_7d: float = Field(..., ge=0.0, le=1.0)
    failure_prob_30d: float = Field(..., ge=0.0, le=1.0)
    health_score: float = Field(
        ..., ge=0.0, le=100.0, description="Composite health score (100=perfect)"
    )
    confidence_lower: float = Field(..., ge=0.0, le=1.0)
    confidence_upper: float = Field(..., ge=0.0, le=1.0)
    top_3_features: List[Dict[str, Any]] = Field(
        ..., description="[{feature, importance, value}] top contributing features"
    )
    model_version: str
    model_name: str = "foresight-failure-predictor"

    @field_validator("health_score", mode="before")
    @classmethod
    def derive_health_score(cls, v: float) -> float:
        """Ensure health score is rounded to 2dp."""
        return round(float(v), 2)


class MaintenanceRecord(BaseModel):
    """A maintenance event from SAP, Asset Suite, or manual entry."""

    record_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    asset_id: str
    tenant_id: str
    maintenance_type: str
    performed_at: datetime
    cost: Optional[float] = None
    outcome: Optional[str] = None
    source_system: SourceSystem
    description: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
