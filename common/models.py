# =============================================================================
# FORESIGHT — Internal Domain Models
# Shared data models used across the platform
# =============================================================================

from dataclasses import dataclass, field
from datetime import datetime, date
from decimal import Decimal
from typing import Optional, Dict, Any, List
from enum import Enum
from uuid import UUID


# =============================================================================
# Enums
# =============================================================================

class AssetStatus(str, Enum):
    OPERATIONAL = "operational"
    MAINTENANCE = "maintenance"
    DECOMMISSIONED = "decommissioned"
    STANDBY = "standby"


class CriticalityLevel(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class AlertSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
    EMERGENCY = "emergency"


class AlertStatus(str, Enum):
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"
    IGNORED = "ignored"


class MaintenanceType(str, Enum):
    PREVENTIVE = "preventive"
    CORRECTIVE = "corrective"
    PREDICTIVE = "predictive"
    INSPECTION = "inspection"


# =============================================================================
# Domain Models
# =============================================================================

@dataclass
class Tenant:
    """Represents a tenant/organization in the system."""
    id: UUID
    name: str
    slug: str
    description: Optional[str] = None
    contact_email: Optional[str] = None
    settings: Dict[str, Any] = field(default_factory=dict)
    is_active: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass
class User:
    """Represents a user in the system."""
    id: UUID
    tenant_id: UUID
    email: str
    hashed_password: str
    full_name: str
    role: str = "analyst"  # admin, analyst, operator, viewer
    is_active: bool = True
    last_login: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass
class Asset:
    """Represents a piece of equipment or machinery."""
    id: UUID
    tenant_id: UUID
    asset_id: str  # External ID
    name: str
    asset_type: str
    status: AssetStatus = AssetStatus.OPERATIONAL
    criticality: CriticalityLevel = CriticalityLevel.MEDIUM
    description: Optional[str] = None
    category: Optional[str] = None
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    serial_number: Optional[str] = None
    location: Optional[str] = None
    department: Optional[str] = None
    install_date: Optional[date] = None
    purchase_cost: Optional[Decimal] = None
    parent_asset_id: Optional[UUID] = None
    sap_equipment_number: Optional[str] = None
    asset_suite_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass
class Sensor:
    """Represents a sensor attached to an asset."""
    id: UUID
    tenant_id: UUID
    sensor_id: str
    asset_id: UUID
    name: str
    sensor_type: str
    unit: Optional[str] = None
    sampling_rate: int = 60
    min_threshold: Optional[Decimal] = None
    max_threshold: Optional[Decimal] = None
    calibration_date: Optional[date] = None
    location_on_asset: Optional[str] = None
    kafka_topic: Optional[str] = None
    is_active: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass
class SensorReading:
    """Represents a single sensor reading."""
    timestamp: datetime
    tenant_id: UUID
    asset_id: str
    sensor_id: str
    sensor_type: str
    value: float
    unit: Optional[str] = None
    quality: str = "good"
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SensorAggregation:
    """Represents aggregated sensor data over a time window."""
    window_start: datetime
    window_end: datetime
    tenant_id: UUID
    asset_id: str
    sensor_type: str
    readings_count: int
    avg_value: float
    min_value: float
    max_value: float
    std_dev: Optional[float] = None
    processed_at: Optional[datetime] = None


@dataclass
class AlertRule:
    """Represents a rule for generating alerts."""
    id: UUID
    tenant_id: UUID
    name: str
    description: Optional[str] = None
    asset_id: Optional[UUID] = None
    sensor_type: Optional[str] = None
    metric: str
    operator: str
    threshold_value: Decimal
    threshold_value_high: Optional[Decimal] = None
    duration_seconds: int = 0
    severity: AlertSeverity = AlertSeverity.WARNING
    is_active: bool = True
    auto_create_work_order: bool = False
    notification_channels: List[str] = field(default_factory=list)
    cooldown_minutes: int = 30
    created_by: Optional[UUID] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass
class Alert:
    """Represents an alert triggered by a rule or ML model."""
    id: UUID
    tenant_id: UUID
    asset_id: UUID
    alert_type: str  # threshold, anomaly, prediction
    severity: AlertSeverity
    status: AlertStatus = AlertStatus.OPEN
    title: str = ""
    description: Optional[str] = None
    rule_id: Optional[UUID] = None
    sensor_id: Optional[UUID] = None
    metric_name: Optional[str] = None
    metric_value: Optional[Decimal] = None
    threshold_value: Optional[Decimal] = None
    started_at: Optional[datetime] = None
    acknowledged_at: Optional[datetime] = None
    acknowledged_by: Optional[UUID] = None
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[UUID] = None
    resolution_notes: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: Optional[datetime] = None


@dataclass
class MaintenanceRecord:
    """Represents a maintenance work order or record."""
    id: UUID
    tenant_id: UUID
    asset_id: UUID
    record_type: MaintenanceType
    title: str
    description: Optional[str] = None
    status: str = "scheduled"
    priority: str = "medium"
    work_order_number: Optional[str] = None
    scheduled_date: Optional[datetime] = None
    started_date: Optional[datetime] = None
    completed_date: Optional[datetime] = None
    technician_name: Optional[str] = None
    technician_id: Optional[str] = None
    cost_parts: Optional[Decimal] = None
    cost_labor: Optional[Decimal] = None
    cost_total: Optional[Decimal] = None
    downtime_hours: Optional[Decimal] = None
    parts_replaced: List[Dict[str, Any]] = field(default_factory=list)
    findings: Optional[str] = None
    recommendations: Optional[str] = None
    sap_notification_number: Optional[str] = None
    asset_suite_work_order_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass
class HealthScore:
    """Represents a health score prediction for an asset."""
    id: UUID
    tenant_id: UUID
    asset_id: UUID
    score: Decimal
    predicted_failure_probability: Optional[Decimal] = None
    predicted_failure_date: Optional[date] = None
    risk_level: Optional[str] = None
    model_version: Optional[str] = None
    features_used: Optional[Dict[str, Any]] = None
    top_contributing_features: Optional[List[Dict[str, Any]]] = None
    recommendation: Optional[str] = None
    computed_at: Optional[datetime] = None
    valid_until: Optional[datetime] = None
    created_at: Optional[datetime] = None


@dataclass
class FeatureVector:
    """Represents a feature vector for ML training/inference."""
    tenant_id: UUID
    asset_id: UUID
    feature_date: date
    
    # Temperature features
    temp_avg_7d: Optional[float] = None
    temp_max_7d: Optional[float] = None
    temp_std_7d: Optional[float] = None
    temp_avg_30d: Optional[float] = None
    temp_max_30d: Optional[float] = None
    
    # Vibration features
    vibration_avg_7d: Optional[float] = None
    vibration_max_7d: Optional[float] = None
    vibration_std_7d: Optional[float] = None
    vibration_avg_30d: Optional[float] = None
    vibration_max_30d: Optional[float] = None
    
    # Maintenance features
    days_since_maintenance: Optional[int] = None
    maintenance_count_90d: Optional[int] = None
    total_downtime_hours_90d: Optional[float] = None
    
    # Derived features
    days_in_operation: Optional[int] = None
    age_days: Optional[int] = None
    criticality_score: Optional[int] = None
    
    # Target variable
    failed_within_30d: Optional[bool] = None
    
    created_at: Optional[datetime] = None


@dataclass
class ModelInfo:
    """Represents a registered ML model."""
    id: UUID
    tenant_id: UUID
    model_name: str
    model_version: str
    model_type: str
    mlflow_run_id: Optional[str] = None
    mlflow_model_uri: Optional[str] = None
    parameters: Dict[str, Any] = field(default_factory=dict)
    metrics: Dict[str, float] = field(default_factory=dict)
    feature_importance: Dict[str, float] = field(default_factory=dict)
    training_data_start: Optional[date] = None
    training_data_end: Optional[date] = None
    is_champion: bool = False
    is_active: bool = True
    deployed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None


# =============================================================================
# Event Models (for Kafka/Event Sourcing)
# =============================================================================

@dataclass
class SensorReadingEvent:
    """Event emitted when a new sensor reading is ingested."""
    event_type: str = "sensor_reading"
    timestamp: datetime = field(default_factory=datetime.utcnow)
    reading: SensorReading = field(default_factory=lambda: SensorReading(
        timestamp=datetime.utcnow(),
        tenant_id=UUID(int=0),
        asset_id="",
        sensor_id="",
        sensor_type="",
        value=0.0
    ))


@dataclass
class AlertTriggeredEvent:
    """Event emitted when an alert is triggered."""
    event_type: str = "alert_triggered"
    timestamp: datetime = field(default_factory=datetime.utcnow)
    alert: Alert = field(default_factory=lambda: Alert(
        id=UUID(int=0),
        tenant_id=UUID(int=0),
        asset_id=UUID(int=0),
        alert_type="threshold",
        severity=AlertSeverity.WARNING
    ))


@dataclass
class HealthScoreComputedEvent:
    """Event emitted when a health score is computed."""
    event_type: str = "health_score_computed"
    timestamp: datetime = field(default_factory=datetime.utcnow)
    health_score: HealthScore = field(default_factory=lambda: HealthScore(
        id=UUID(int=0),
        tenant_id=UUID(int=0),
        asset_id=UUID(int=0),
        score=Decimal("100.00")
    ))
