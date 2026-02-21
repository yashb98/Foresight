"""
FORESIGHT — FastAPI Request/Response Pydantic Schemas

All API request and response models.
These are separate from common/models.py (which are internal domain models)
to allow API contract evolution independently of the pipeline data models.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

# =============================================================================
# Auth
# =============================================================================


class TokenRequest(BaseModel):
    """POST /auth/token request body."""

    client_id: str = Field(..., description="Tenant client ID")
    client_secret: str = Field(..., description="Tenant client secret")


class TokenResponse(BaseModel):
    """POST /auth/token response."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int = Field(..., description="Token lifetime in seconds")
    tenant_id: str


# =============================================================================
# Assets
# =============================================================================


class HealthScoreSummary(BaseModel):
    """Embedded health score for the asset list view."""

    health_score: Optional[float] = None
    failure_prob_7d: Optional[float] = None
    failure_prob_30d: Optional[float] = None
    score_date: Optional[date] = None
    risk_level: Optional[str] = None  # low | medium | high | critical


class AssetResponse(BaseModel):
    """GET /assets/{tenant_id} — single asset in list."""

    asset_id: str
    tenant_id: str
    name: str
    asset_type: str
    location: Optional[str] = None
    criticality: str
    installed_date: Optional[date] = None
    source_system: Optional[str] = None
    current_health: Optional[HealthScoreSummary] = None
    is_active: bool = True

    model_config = {"from_attributes": True}


class AssetListResponse(BaseModel):
    """GET /assets/{tenant_id} response envelope."""

    tenant_id: str
    total: int
    assets: List[AssetResponse]


class PredictionHistoryEntry(BaseModel):
    """One row of prediction history for an asset detail view."""

    score_date: date
    health_score: float
    failure_prob_7d: float
    failure_prob_30d: float
    model_version: str


class AssetDetailResponse(AssetResponse):
    """GET /assets/{tenant_id}/{asset_id} — full asset detail."""

    prediction_history: List[PredictionHistoryEntry] = Field(default_factory=list)
    recent_alerts_count: int = 0
    last_maintenance_date: Optional[datetime] = None
    total_maintenance_cost_90d: Optional[float] = None


# =============================================================================
# Predictions
# =============================================================================


class PredictionRequest(BaseModel):
    """POST /predict request body."""

    asset_id: str = Field(..., description="Asset UUID")
    tenant_id: str = Field(..., description="Tenant UUID — must match JWT token tenant")

    # Optional pre-computed features (if caller has them already)
    features: Optional[Dict[str, float]] = Field(
        None,
        description="Pre-computed feature values. If None, loaded from feature store.",
    )


class TopFeature(BaseModel):
    """A single contributing feature in a prediction."""

    feature: str
    importance: float
    value: float


class PredictionResponse(BaseModel):
    """POST /predict response."""

    asset_id: str
    tenant_id: str
    predicted_at: datetime
    failure_prob_7d: float = Field(..., description="Probability of failure within 7 days (0–1)")
    failure_prob_30d: float = Field(..., description="Probability of failure within 30 days (0–1)")
    health_score: float = Field(..., description="Composite health score (0=critical, 100=perfect)")
    confidence_lower: float
    confidence_upper: float
    risk_level: str = Field(..., description="low | medium | high | critical")
    top_3_features: List[TopFeature]
    model_version: str
    model_name: str = "foresight-failure-predictor"

    @classmethod
    def from_prediction_result(cls, result: "PredictionResult") -> "PredictionResponse":  # noqa: F821,E501
        """Convert from internal PredictionResult to API response schema."""
        prob_30d = result.failure_prob_30d
        risk = (
            "critical"
            if prob_30d > 0.70
            else "high" if prob_30d > 0.40 else "medium" if prob_30d > 0.15 else "low"
        )
        return cls(
            asset_id=result.asset_id,
            tenant_id=result.tenant_id,
            predicted_at=result.predicted_at,
            failure_prob_7d=result.failure_prob_7d,
            failure_prob_30d=result.failure_prob_30d,
            health_score=result.health_score,
            confidence_lower=result.confidence_lower,
            confidence_upper=result.confidence_upper,
            risk_level=risk,
            top_3_features=[TopFeature(**f) for f in result.top_3_features],
            model_version=result.model_version,
        )


# =============================================================================
# Alerts
# =============================================================================


class AlertResponse(BaseModel):
    """Single alert in the alert feed."""

    alert_id: str
    asset_id: str
    tenant_id: str
    rule_id: Optional[str] = None
    alert_type: str
    metric_name: str
    actual_value: Optional[float] = None
    threshold_value: Optional[float] = None
    severity: str
    status: str
    triggered_at: datetime
    acknowledged_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    acknowledged_by: Optional[str] = None
    notes: Optional[str] = None

    model_config = {"from_attributes": True}


class AlertUpdateRequest(BaseModel):
    """PATCH /alerts/{tenant_id}/{alert_id} request."""

    status: str = Field(..., pattern="^(acknowledged|resolved)$")
    notes: Optional[str] = None


class AlertListResponse(BaseModel):
    """GET /alerts/{tenant_id} response."""

    tenant_id: str
    total: int
    alerts: List[AlertResponse]


# =============================================================================
# Threshold Rules
# =============================================================================


class ThresholdRuleRequest(BaseModel):
    """POST /rules/{tenant_id} request body — create or update a rule."""

    metric_name: str = Field(..., description="temperature | vibration | pressure | rpm")
    operator: str = Field(..., pattern="^(gt|lt|gte|lte|eq)$")
    threshold_value: float
    severity: str = Field(..., pattern="^(low|medium|high|critical)$")
    asset_type: Optional[str] = Field(None, description="None = applies to all asset types")
    description: Optional[str] = None
    active: bool = True

    @field_validator("threshold_value")
    @classmethod
    def threshold_must_be_positive(cls, v: float) -> float:
        """Threshold values must be positive."""
        if v < 0:
            raise ValueError("threshold_value must be >= 0")
        return v


class ThresholdRuleResponse(BaseModel):
    """GET /rules/{tenant_id} — single rule in list."""

    rule_id: str
    tenant_id: str
    metric_name: str
    operator: str
    threshold_value: float
    severity: str
    asset_type: Optional[str] = None
    description: Optional[str] = None
    active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class RuleListResponse(BaseModel):
    """GET /rules/{tenant_id} response."""

    tenant_id: str
    total: int
    rules: List[ThresholdRuleResponse]


# =============================================================================
# Alert Rules (new detailed schemas for /rules router)
# =============================================================================


class AlertRuleCreate(BaseModel):
    """POST /rules/{tenant_id} — create a new alert rule."""

    name: str = Field(..., description="Human-readable rule name")
    description: Optional[str] = None
    asset_type: Optional[str] = Field(None, description="Filter to asset type, or None for all")
    metric: str = Field(..., description="Sensor metric (e.g. vibration_rms, bearing_temp_celsius)")
    operator: str = Field(..., pattern="^(gt|lt|gte|lte|eq)$", description="Comparison operator")
    threshold: float = Field(..., ge=0, description="Threshold value for the metric")
    severity: str = Field(..., pattern="^(low|medium|high|critical)$")

    @field_validator("threshold")
    @classmethod
    def threshold_must_be_non_negative(cls, v: float) -> float:
        if v < 0:
            raise ValueError("threshold must be >= 0")
        return v


class AlertRuleUpdate(BaseModel):
    """PUT /rules/{tenant_id}/{rule_id} — partial update (all fields optional)."""

    name: Optional[str] = None
    description: Optional[str] = None
    asset_type: Optional[str] = None
    metric: Optional[str] = None
    operator: Optional[str] = Field(None, pattern="^(gt|lt|gte|lte|eq)$")
    threshold: Optional[float] = Field(None, ge=0)
    severity: Optional[str] = Field(None, pattern="^(low|medium|high|critical)$")
    is_active: Optional[bool] = None


class AlertRuleResponse(BaseModel):
    """Response schema for a single alert rule."""

    id: str
    tenant_id: str
    name: str
    description: Optional[str] = None
    asset_type: Optional[str] = None
    metric: str
    operator: str
    threshold: float
    severity: str
    is_active: bool
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


# =============================================================================
# Report Schemas (new detailed schemas for /reports router)
# =============================================================================


class FleetSummaryResponse(BaseModel):
    """GET /reports/{tenant_id}/summary — fleet KPI dashboard."""

    tenant_id: str
    total_assets: int
    active_assets: int
    critical_alerts: int
    high_alerts: int
    medium_alerts: int
    low_alerts: int
    assets_at_risk: int
    fleet_health_score: float = Field(..., description="Fleet health 0–100")
    as_of: datetime


class AssetHealthSummary(BaseModel):
    """GET /reports/{tenant_id}/asset/{asset_id} — single asset maintenance report."""

    asset_id: str
    asset_name: str
    asset_type: str
    tenant_id: str
    health_score: float
    status: str
    failure_probability_30d: float
    days_to_maintenance: Optional[int] = None
    open_alert_count: int
    alert_summary: List[Dict[str, Any]] = Field(default_factory=list)
    last_updated: datetime


class TrendDataPoint(BaseModel):
    """One data point in a time-series trend response."""

    date: str  # YYYY-MM-DD
    avg_value: float
    max_value: float
    min_value: float
    reading_count: int


class TrendResponse(BaseModel):
    """GET /reports/{tenant_id}/trends response."""

    tenant_id: str
    metric: str
    days: int
    data_points: List[TrendDataPoint]


class CostAvoidanceReport(BaseModel):
    """GET /reports/{tenant_id}/cost-avoidance response."""

    tenant_id: str
    year: int
    total_predicted_failures: int
    estimated_cost_avoided_usd: float
    actual_maintenance_cost_usd: float
    roi_percent: float
    breakdown_by_severity: Dict[str, int]
    generated_at: datetime


# =============================================================================
# Reports (legacy metadata schemas)
# =============================================================================


class ReportMetadata(BaseModel):
    """Metadata about a generated report."""

    report_id: str
    tenant_id: str
    report_type: str
    format: str
    generated_at: datetime
    file_size_bytes: Optional[int] = None
    download_url: Optional[str] = None
    status: str = "ready"


class ReportListResponse(BaseModel):
    """GET /reports/{tenant_id} response."""

    tenant_id: str
    total: int
    reports: List[ReportMetadata]


class GenerateReportRequest(BaseModel):
    """POST /reports/{tenant_id}/generate request."""

    report_type: str = Field(
        "asset_health",
        description="asset_health | alerts_summary | maintenance_forecast | executive",
    )
    format: str = Field("excel", pattern="^(excel|pdf)$")
    date_from: Optional[date] = None
    date_to: Optional[date] = None


# =============================================================================
# System Health
# =============================================================================


class ServiceStatus(BaseModel):
    """Status of a single downstream service."""

    name: str
    status: str  # healthy | degraded | unhealthy
    latency_ms: Optional[float] = None
    message: Optional[str] = None


class HealthResponse(BaseModel):
    """GET /health response."""

    status: str
    version: str
    environment: str
    services: List[ServiceStatus]
    timestamp: datetime = Field(default_factory=datetime.utcnow)
