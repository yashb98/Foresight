/**
 * FORESIGHT Dashboard — Shared TypeScript Types
 *
 * Mirror of the FastAPI Pydantic schemas for type-safe API consumption.
 */

// ─────────────────────────────────────────────────────────────────────────────
// Auth
// ─────────────────────────────────────────────────────────────────────────────

export interface TokenResponse {
  access_token: string
  token_type: 'bearer'
  expires_in: number
  tenant_id: string
}

// ─────────────────────────────────────────────────────────────────────────────
// Assets
// ─────────────────────────────────────────────────────────────────────────────

export type RiskLevel = 'low' | 'medium' | 'high' | 'critical'
export type AssetStatus = 'active' | 'inactive' | 'maintenance' | 'decommissioned'
export type AlertSeverity = 'low' | 'medium' | 'high' | 'critical'
export type AlertStatus = 'open' | 'acknowledged' | 'resolved'

export interface HealthScoreSummary {
  health_score: number | null
  failure_prob_7d: number | null
  failure_prob_30d: number | null
  score_date: string | null
  risk_level: RiskLevel | null
}

export interface Asset {
  asset_id: string
  tenant_id: string
  name: string
  asset_type: string
  location: string | null
  criticality: string
  installed_date: string | null
  source_system: string | null
  current_health: HealthScoreSummary | null
  is_active: boolean
}

export interface AssetListResponse {
  tenant_id: string
  total: number
  assets: Asset[]
}

export interface PredictionHistoryEntry {
  score_date: string
  health_score: number
  failure_prob_7d: number
  failure_prob_30d: number
  model_version: string
}

export interface AssetDetail extends Asset {
  prediction_history: PredictionHistoryEntry[]
  recent_alerts_count: number
  last_maintenance_date: string | null
  total_maintenance_cost_90d: number | null
}

// ─────────────────────────────────────────────────────────────────────────────
// Alerts
// ─────────────────────────────────────────────────────────────────────────────

export interface Alert {
  alert_id: string
  asset_id: string
  tenant_id: string
  rule_id: string | null
  alert_type: string
  metric_name: string
  actual_value: number | null
  threshold_value: number | null
  severity: AlertSeverity
  status: AlertStatus
  triggered_at: string
  acknowledged_at: string | null
  resolved_at: string | null
  acknowledged_by: string | null
  notes: string | null
}

export interface AlertListResponse {
  tenant_id: string
  total: number
  alerts: Alert[]
}

// ─────────────────────────────────────────────────────────────────────────────
// Predictions
// ─────────────────────────────────────────────────────────────────────────────

export interface TopFeature {
  feature: string
  importance: number
  value: number
}

export interface Prediction {
  asset_id: string
  tenant_id: string
  predicted_at: string
  failure_prob_7d: number
  failure_prob_30d: number
  health_score: number
  confidence_lower: number
  confidence_upper: number
  risk_level: RiskLevel
  top_3_features: TopFeature[]
  model_version: string
  model_name: string
}

// ─────────────────────────────────────────────────────────────────────────────
// Alert Rules
// ─────────────────────────────────────────────────────────────────────────────

export interface AlertRule {
  id: string
  tenant_id: string
  name: string
  description: string | null
  asset_type: string | null
  metric: string
  operator: 'gt' | 'lt' | 'gte' | 'lte' | 'eq'
  threshold: number
  severity: AlertSeverity
  is_active: boolean
  created_at: string | null
}

// ─────────────────────────────────────────────────────────────────────────────
// Reports
// ─────────────────────────────────────────────────────────────────────────────

export interface FleetSummary {
  tenant_id: string
  total_assets: number
  active_assets: number
  critical_alerts: number
  high_alerts: number
  medium_alerts: number
  low_alerts: number
  assets_at_risk: number
  fleet_health_score: number
  as_of: string
}

export interface TrendDataPoint {
  date: string
  avg_value: number
  max_value: number
  min_value: number
  reading_count: number
}

export interface TrendResponse {
  tenant_id: string
  metric: string
  days: number
  data_points: TrendDataPoint[]
}

export interface CostAvoidanceReport {
  tenant_id: string
  year: number
  total_predicted_failures: number
  estimated_cost_avoided_usd: number
  actual_maintenance_cost_usd: number
  roi_percent: number
  breakdown_by_severity: Record<AlertSeverity, number>
  generated_at: string
}

// ─────────────────────────────────────────────────────────────────────────────
// UI State
// ─────────────────────────────────────────────────────────────────────────────

export interface AuthState {
  token: string | null
  tenantId: string | null
  isAuthenticated: boolean
}

export interface FilterState {
  severity?: AlertSeverity
  status?: AlertStatus
  assetType?: string
  dateFrom?: string
  dateTo?: string
}
