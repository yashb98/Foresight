# =============================================================================
# FORESIGHT API — Pydantic Schemas
# Request/Response models for all endpoints
# =============================================================================

from datetime import datetime, date
from decimal import Decimal
from enum import Enum
from typing import Optional, List, Dict, Any, Union
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict, field_validator


# =============================================================================
# Enums
# =============================================================================

class UserRole(str, Enum):
    ADMIN = "admin"
    ANALYST = "analyst"
    OPERATOR = "operator"
    VIEWER = "viewer"


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


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# =============================================================================
# Base Models
# =============================================================================

class TimestampedModel(BaseModel):
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class TenantAwareModel(BaseModel):
    tenant_id: UUID


# =============================================================================
# Auth Schemas
# =============================================================================

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = 3600
    tenant_id: UUID
    user_role: str


class TokenData(BaseModel):
    user_id: Optional[UUID] = None
    tenant_id: Optional[UUID] = None
    email: Optional[str] = None
    role: Optional[str] = None


class UserLogin(BaseModel):
    email: str
    password: str


class UserCreate(BaseModel):
    email: str
    password: str = Field(..., min_length=8)
    full_name: str
    role: UserRole = UserRole.ANALYST


class UserResponse(BaseModel, TimestampedModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    tenant_id: UUID
    email: str
    full_name: str
    role: str
    is_active: bool
    last_login: Optional[datetime] = None


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None


# =============================================================================
# Tenant Schemas
# =============================================================================

class TenantCreate(BaseModel):
    name: str
    slug: str = Field(..., pattern=r"^[a-z0-9-]+$")
    description: Optional[str] = None
    contact_email: Optional[str] = None
    settings: Optional[Dict[str, Any]] = None


class TenantResponse(BaseModel, TimestampedModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    name: str
    slug: str
    description: Optional[str] = None
    contact_email: Optional[str] = None
    settings: Dict[str, Any] = {}
    is_active: bool


# =============================================================================
# Asset Schemas
# =============================================================================

class AssetCreate(BaseModel):
    asset_id: str = Field(..., description="External asset ID from SAP/Asset Suite")
    name: str
    description: Optional[str] = None
    asset_type: str = Field(..., description="pump, motor, turbine, compressor, etc.")
    category: Optional[str] = None
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    serial_number: Optional[str] = None
    location: Optional[str] = None
    department: Optional[str] = None
    criticality: CriticalityLevel = CriticalityLevel.MEDIUM
    install_date: Optional[date] = None
    purchase_cost: Optional[Decimal] = None
    status: AssetStatus = AssetStatus.OPERATIONAL
    parent_asset_id: Optional[UUID] = None
    sap_equipment_number: Optional[str] = None
    asset_suite_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class AssetResponse(BaseModel, TimestampedModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    tenant_id: UUID
    asset_id: str
    name: str
    description: Optional[str] = None
    asset_type: str
    category: Optional[str] = None
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    serial_number: Optional[str] = None
    location: Optional[str] = None
    department: Optional[str] = None
    criticality: str
    install_date: Optional[date] = None
    purchase_cost: Optional[Decimal] = None
    status: str
    parent_asset_id: Optional[UUID] = None
    sap_equipment_number: Optional[str] = None
    asset_suite_id: Optional[str] = None
    metadata: Dict[str, Any] = {}
    
    # Enriched fields
    sensor_count: Optional[int] = None
    health_score: Optional[Decimal] = None
    open_alerts: Optional[int] = None


class AssetUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    asset_type: Optional[str] = None
    category: Optional[str] = None
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    serial_number: Optional[str] = None
    location: Optional[str] = None
    department: Optional[str] = None
    criticality: Optional[CriticalityLevel] = None
    install_date: Optional[date] = None
    purchase_cost: Optional[Decimal] = None
    status: Optional[AssetStatus] = None
    parent_asset_id: Optional[UUID] = None
    sap_equipment_number: Optional[str] = None
    asset_suite_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class AssetListResponse(BaseModel):
    total: int
    items: List[AssetResponse]
    page: int
    page_size: int


# =============================================================================
# Sensor Schemas
# =============================================================================

class SensorCreate(BaseModel):
    sensor_id: str
    asset_id: UUID
    name: str
    sensor_type: str = Field(..., description="vibration, temperature, pressure, flow, etc.")
    unit: Optional[str] = None
    sampling_rate: int = 60
    min_threshold: Optional[Decimal] = None
    max_threshold: Optional[Decimal] = None
    calibration_date: Optional[date] = None
    location_on_asset: Optional[str] = None
    kafka_topic: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class SensorResponse(BaseModel, TimestampedModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    tenant_id: UUID
    sensor_id: str
    asset_id: UUID
    name: str
    sensor_type: str
    unit: Optional[str] = None
    sampling_rate: int
    min_threshold: Optional[Decimal] = None
    max_threshold: Optional[Decimal] = None
    calibration_date: Optional[date] = None
    location_on_asset: Optional[str] = None
    is_active: bool
    kafka_topic: Optional[str] = None
    metadata: Dict[str, Any] = {}
    
    # Enriched
    latest_reading: Optional[Decimal] = None
    latest_reading_at: Optional[datetime] = None


class SensorUpdate(BaseModel):
    name: Optional[str] = None
    asset_id: Optional[UUID] = None
    sensor_type: Optional[str] = None
    unit: Optional[str] = None
    sampling_rate: Optional[int] = None
    min_threshold: Optional[Decimal] = None
    max_threshold: Optional[Decimal] = None
    calibration_date: Optional[date] = None
    location_on_asset: Optional[str] = None
    is_active: Optional[bool] = None
    kafka_topic: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


# =============================================================================
# Alert Rule Schemas
# =============================================================================

class AlertRuleCreate(BaseModel):
    name: str
    description: Optional[str] = None
    asset_id: Optional[UUID] = None  # NULL = all assets
    sensor_type: Optional[str] = None  # NULL = all sensor types
    metric: str = Field(..., description="temperature, vibration_x, pressure, etc.")
    operator: str = Field(..., pattern=r"^(>|>=|<|<=|==|between)$")
    threshold_value: Decimal
    threshold_value_high: Optional[Decimal] = None  # For 'between' operator
    duration_seconds: int = 0
    severity: AlertSeverity = AlertSeverity.WARNING
    auto_create_work_order: bool = False
    notification_channels: List[str] = []
    cooldown_minutes: int = 30


class AlertRuleResponse(BaseModel, TimestampedModel):
    model_config = ConfigDict(from_attributes=True)
    
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
    duration_seconds: int
    severity: str
    is_active: bool
    auto_create_work_order: bool
    notification_channels: List[str] = []
    cooldown_minutes: int
    created_by: Optional[UUID] = None


class AlertRuleUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    asset_id: Optional[UUID] = None
    sensor_type: Optional[str] = None
    metric: Optional[str] = None
    operator: Optional[str] = Field(None, pattern=r"^(>|>=|<|<=|==|between)$")
    threshold_value: Optional[Decimal] = None
    threshold_value_high: Optional[Decimal] = None
    duration_seconds: Optional[int] = None
    severity: Optional[AlertSeverity] = None
    is_active: Optional[bool] = None
    auto_create_work_order: Optional[bool] = None
    notification_channels: Optional[List[str]] = None
    cooldown_minutes: Optional[int] = None


# =============================================================================
# Alert Schemas
# =============================================================================

class AlertCreate(BaseModel):
    rule_id: Optional[UUID] = None
    asset_id: UUID
    sensor_id: Optional[UUID] = None
    alert_type: str = Field(..., pattern=r"^(threshold|anomaly|prediction)$")
    severity: AlertSeverity
    title: str
    description: Optional[str] = None
    metric_name: Optional[str] = None
    metric_value: Optional[Decimal] = None
    threshold_value: Optional[Decimal] = None
    metadata: Optional[Dict[str, Any]] = None


class AlertResponse(BaseModel, TimestampedModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    tenant_id: UUID
    rule_id: Optional[UUID] = None
    asset_id: UUID
    sensor_id: Optional[UUID] = None
    alert_type: str
    severity: str
    status: str
    title: str
    description: Optional[str] = None
    metric_name: Optional[str] = None
    metric_value: Optional[Decimal] = None
    threshold_value: Optional[Decimal] = None
    started_at: datetime
    acknowledged_at: Optional[datetime] = None
    acknowledged_by: Optional[UUID] = None
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[UUID] = None
    resolution_notes: Optional[str] = None
    metadata: Dict[str, Any] = {}
    
    # Enriched
    asset_name: Optional[str] = None
    sensor_name: Optional[str] = None
    acknowledged_by_name: Optional[str] = None


class AlertUpdate(BaseModel):
    status: Optional[AlertStatus] = None
    resolution_notes: Optional[str] = None


class AlertAcknowledgeRequest(BaseModel):
    notes: Optional[str] = None


class AlertResolveRequest(BaseModel):
    resolution_notes: Optional[str] = None


class AlertListResponse(BaseModel):
    total: int
    items: List[AlertResponse]
    page: int
    page_size: int
    
    # Summary stats
    open_count: int = 0
    critical_count: int = 0
    warning_count: int = 0


class AlertStats(BaseModel):
    total_alerts: int
    open_alerts: int
    acknowledged_alerts: int
    resolved_alerts: int
    critical_count: int
    warning_count: int
    info_count: int
    avg_resolution_hours: Optional[float] = None


# =============================================================================
# Maintenance Schemas
# =============================================================================

class MaintenanceRecordCreate(BaseModel):
    asset_id: UUID
    work_order_number: Optional[str] = None
    record_type: MaintenanceType
    title: str
    description: Optional[str] = None
    status: str = "scheduled"
    priority: str = "medium"
    scheduled_date: Optional[datetime] = None
    started_date: Optional[datetime] = None
    completed_date: Optional[datetime] = None
    technician_name: Optional[str] = None
    technician_id: Optional[str] = None
    cost_parts: Optional[Decimal] = None
    cost_labor: Optional[Decimal] = None
    cost_total: Optional[Decimal] = None
    downtime_hours: Optional[Decimal] = None
    parts_replaced: List[Dict[str, Any]] = []
    findings: Optional[str] = None
    recommendations: Optional[str] = None
    sap_notification_number: Optional[str] = None
    asset_suite_work_order_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class MaintenanceRecordResponse(BaseModel, TimestampedModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    tenant_id: UUID
    asset_id: UUID
    work_order_number: Optional[str] = None
    record_type: str
    title: str
    description: Optional[str] = None
    status: str
    priority: str
    scheduled_date: Optional[datetime] = None
    started_date: Optional[datetime] = None
    completed_date: Optional[datetime] = None
    technician_name: Optional[str] = None
    technician_id: Optional[str] = None
    cost_parts: Optional[Decimal] = None
    cost_labor: Optional[Decimal] = None
    cost_total: Optional[Decimal] = None
    downtime_hours: Optional[Decimal] = None
    parts_replaced: List[Dict[str, Any]] = []
    findings: Optional[str] = None
    recommendations: Optional[str] = None
    sap_notification_number: Optional[str] = None
    asset_suite_work_order_id: Optional[str] = None
    metadata: Dict[str, Any] = {}
    
    # Enriched
    asset_name: Optional[str] = None


class MaintenanceRecordUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    scheduled_date: Optional[datetime] = None
    started_date: Optional[datetime] = None
    completed_date: Optional[datetime] = None
    technician_name: Optional[str] = None
    cost_parts: Optional[Decimal] = None
    cost_labor: Optional[Decimal] = None
    cost_total: Optional[Decimal] = None
    downtime_hours: Optional[Decimal] = None
    findings: Optional[str] = None
    recommendations: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


# =============================================================================
# Health Score Schemas
# =============================================================================

class HealthScoreResponse(BaseModel, TimestampedModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: UUID
    tenant_id: UUID
    asset_id: UUID
    score: Decimal = Field(..., ge=0, le=100)
    predicted_failure_probability: Optional[Decimal] = None
    predicted_failure_date: Optional[date] = None
    risk_level: Optional[str] = None
    model_version: Optional[str] = None
    features_used: Optional[Dict[str, Any]] = None
    top_contributing_features: Optional[List[Dict[str, Any]]] = None
    recommendation: Optional[str] = None
    computed_at: datetime
    valid_until: Optional[datetime] = None
    
    # Enriched
    asset_name: Optional[str] = None
    asset_type: Optional[str] = None


class HealthScoreHistory(BaseModel):
    asset_id: UUID
    asset_name: str
    scores: List[Dict[str, Any]]  # {date, score, risk_level}


class FleetHealthSummary(BaseModel):
    total_assets: int
    healthy_count: int  # score >= 80
    at_risk_count: int  # 50 <= score < 80
    critical_count: int  # score < 50
    average_score: float
    assets_needing_attention: List[HealthScoreResponse] = []


# =============================================================================
# Prediction Schemas
# =============================================================================

class PredictionRequest(BaseModel):
    asset_id: UUID
    features: Optional[Dict[str, float]] = None  # If None, fetch from feature store


class PredictionResponse(BaseModel):
    asset_id: UUID
    health_score: Decimal
    failure_probability: Decimal
    risk_level: RiskLevel
    confidence: Decimal
    predicted_failure_date: Optional[date] = None
    recommendation: str
    model_version: str
    feature_contributions: Optional[List[Dict[str, Any]]] = None
    computed_at: datetime


class BatchPredictionRequest(BaseModel):
    asset_ids: List[UUID]


class BatchPredictionResponse(BaseModel):
    predictions: List[PredictionResponse]
    failed_assets: List[Dict[str, str]] = []  # asset_id, error


# =============================================================================
# Sensor Reading Schemas (MongoDB)
-- =============================================================================

class SensorReading(BaseModel):
    timestamp: datetime
    tenant_id: UUID
    asset_id: str
    sensor_id: str
    sensor_type: str
    value: Decimal
    unit: Optional[str] = None
    quality: str = "good"
    

class SensorReadingQuery(BaseModel):
    asset_id: Optional[str] = None
    sensor_id: Optional[str] = None
    sensor_type: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    limit: int = Field(default=1000, le=10000)


class SensorAggregation(BaseModel):
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


# =============================================================================
# Report Schemas
# =============================================================================

class ReportSummary(BaseModel):
    total_assets: int
    operational_assets: int
    assets_in_maintenance: int
    total_sensors: int
    active_alerts: int
    critical_alerts: int
    avg_health_score: float
    maintenance_this_month: int
    upcoming_maintenance: int


class AssetTrend(BaseModel):
    date: date
    avg_health_score: float
    alert_count: int
    maintenance_count: int


class CostAvoidanceReport(BaseModel):
    predicted_failures_prevented: int
    estimated_cost_avoided: Decimal
    actual_maintenance_cost: Decimal
    roi_percentage: float
    period_start: date
    period_end: date


class ReportFilters(BaseModel):
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    asset_types: Optional[List[str]] = None
    departments: Optional[List[str]] = None


# =============================================================================
# Dashboard Schemas
# =============================================================================

class DashboardSummary(BaseModel):
    # Asset overview
    total_assets: int
    assets_by_status: Dict[str, int]
    assets_by_criticality: Dict[str, int]
    
    # Alerts
    total_open_alerts: int
    alerts_by_severity: Dict[str, int]
    recent_alerts: List[AlertResponse] = []
    
    # Health
    fleet_health_score: float
    health_distribution: Dict[str, int]  # healthy, at_risk, critical
    
    # Maintenance
    maintenance_due_count: int
    maintenance_overdue_count: int
    
    # Trends
    health_trend: List[Dict[str, Any]] = []  # Last 30 days
    alert_trend: List[Dict[str, Any]] = []


class RealtimeMetrics(BaseModel):
    timestamp: datetime
    readings_per_second: float
    active_assets: int
    current_alerts: int
    system_health: str  # healthy, degraded, critical
