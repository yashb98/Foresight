/**
 * FORESIGHT API Endpoints
 *
 * All API calls in one place — typed request/response,
 * so components never call axios directly.
 */

import { apiClient } from './client'
import type {
  Alert,
  AlertListResponse,
  AlertRule,
  AssetDetail,
  AssetListResponse,
  CostAvoidanceReport,
  FleetSummary,
  Prediction,
  TokenResponse,
  TrendResponse,
} from '@/types'

// ─────────────────────────────────────────────────────────────────────────────
// Auth
// ─────────────────────────────────────────────────────────────────────────────

export async function login(clientId: string, clientSecret: string): Promise<TokenResponse> {
  const { data } = await apiClient.post<TokenResponse>('/auth/token', {
    client_id: clientId,
    client_secret: clientSecret,
  })
  return data
}

// ─────────────────────────────────────────────────────────────────────────────
// Assets
// ─────────────────────────────────────────────────────────────────────────────

export interface AssetFilters {
  status?: string
  asset_type?: string
  criticality?: string
  page?: number
  page_size?: number
}

export async function fetchAssets(
  tenantId: string,
  filters: AssetFilters = {}
): Promise<AssetListResponse> {
  const { data } = await apiClient.get<AssetListResponse>(`/assets/${tenantId}`, {
    params: filters,
  })
  return data
}

export async function fetchAssetDetail(tenantId: string, assetId: string): Promise<AssetDetail> {
  const { data } = await apiClient.get<AssetDetail>(`/assets/${tenantId}/${assetId}`)
  return data
}

// ─────────────────────────────────────────────────────────────────────────────
// Alerts
// ─────────────────────────────────────────────────────────────────────────────

export interface AlertFilters {
  severity?: string
  status?: string
  asset_id?: string
  days?: number
}

export async function fetchAlerts(
  tenantId: string,
  filters: AlertFilters = {}
): Promise<AlertListResponse> {
  const { data } = await apiClient.get<AlertListResponse>(`/alerts/${tenantId}`, {
    params: filters,
  })
  return data
}

export async function acknowledgeAlert(
  tenantId: string,
  alertId: string,
  notes?: string
): Promise<Alert> {
  const { data } = await apiClient.patch<Alert>(`/alerts/${tenantId}/${alertId}`, {
    status: 'acknowledged',
    notes,
  })
  return data
}

export async function resolveAlert(
  tenantId: string,
  alertId: string,
  notes?: string
): Promise<Alert> {
  const { data } = await apiClient.patch<Alert>(`/alerts/${tenantId}/${alertId}`, {
    status: 'resolved',
    notes,
  })
  return data
}

// ─────────────────────────────────────────────────────────────────────────────
// Predictions
// ─────────────────────────────────────────────────────────────────────────────

export async function predictAsset(
  tenantId: string,
  assetId: string,
  features?: Record<string, number>
): Promise<Prediction> {
  const { data } = await apiClient.post<Prediction>('/predict', {
    tenant_id: tenantId,
    asset_id: assetId,
    features,
  })
  return data
}

// ─────────────────────────────────────────────────────────────────────────────
// Alert Rules
// ─────────────────────────────────────────────────────────────────────────────

export async function fetchRules(tenantId: string): Promise<AlertRule[]> {
  const { data } = await apiClient.get<AlertRule[]>(`/rules/${tenantId}`)
  return data
}

export async function createRule(
  tenantId: string,
  payload: Omit<AlertRule, 'id' | 'tenant_id' | 'is_active' | 'created_at'>
): Promise<AlertRule> {
  const { data } = await apiClient.post<AlertRule>(`/rules/${tenantId}`, payload)
  return data
}

export async function updateRule(
  tenantId: string,
  ruleId: string,
  payload: Partial<AlertRule>
): Promise<AlertRule> {
  const { data } = await apiClient.put<AlertRule>(`/rules/${tenantId}/${ruleId}`, payload)
  return data
}

export async function deleteRule(tenantId: string, ruleId: string): Promise<void> {
  await apiClient.delete(`/rules/${tenantId}/${ruleId}`)
}

// ─────────────────────────────────────────────────────────────────────────────
// Reports
// ─────────────────────────────────────────────────────────────────────────────

export async function fetchFleetSummary(tenantId: string): Promise<FleetSummary> {
  const { data } = await apiClient.get<FleetSummary>(`/reports/${tenantId}/summary`)
  return data
}

export async function fetchTrends(
  tenantId: string,
  metric: string,
  days: number,
  assetId?: string
): Promise<TrendResponse> {
  const { data } = await apiClient.get<TrendResponse>(`/reports/${tenantId}/trends`, {
    params: { metric, days, ...(assetId && { asset_id: assetId }) },
  })
  return data
}

export async function fetchCostAvoidance(
  tenantId: string,
  year?: number
): Promise<CostAvoidanceReport> {
  const { data } = await apiClient.get<CostAvoidanceReport>(
    `/reports/${tenantId}/cost-avoidance`,
    { params: year ? { year } : {} }
  )
  return data
}

export async function fetchAssetReport(tenantId: string, assetId: string) {
  const { data } = await apiClient.get(`/reports/${tenantId}/asset/${assetId}`)
  return data
}
