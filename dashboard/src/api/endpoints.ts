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
  TrendResponse,
} from '@/types'

// Default tenant ID for single-tenant mode
const DEFAULT_TENANT_ID = '11111111-1111-1111-1111-111111111111'

// -----------------------------------------------------------------------------
// Assets
// -----------------------------------------------------------------------------

export interface AssetFilters {
  status?: string
  asset_type?: string
  criticality?: string
  page?: number
  page_size?: number
}

export async function fetchAssets(
  filters: AssetFilters = {}
): Promise<AssetListResponse> {
  const { data } = await apiClient.get<AssetListResponse>(`/assets/${DEFAULT_TENANT_ID}`, {
    params: filters,
  })
  return data
}

export async function fetchAssetDetail(assetId: string): Promise<AssetDetail> {
  const { data } = await apiClient.get<AssetDetail>(`/assets/${DEFAULT_TENANT_ID}/${assetId}`)
  return data
}

// -----------------------------------------------------------------------------
// Alerts
// -----------------------------------------------------------------------------

export interface AlertFilters {
  severity?: string
  status?: string
  asset_id?: string
  days?: number
}

export async function fetchAlerts(
  filters: AlertFilters = {}
): Promise<AlertListResponse> {
  const { data } = await apiClient.get<AlertListResponse>(`/alerts/${DEFAULT_TENANT_ID}`, {
    params: filters,
  })
  return data
}

export async function acknowledgeAlert(
  alertId: string,
  notes?: string
): Promise<Alert> {
  const { data } = await apiClient.patch<Alert>(`/alerts/${DEFAULT_TENANT_ID}/${alertId}`, {
    status: 'acknowledged',
    notes,
  })
  return data
}

export async function resolveAlert(
  alertId: string,
  notes?: string
): Promise<Alert> {
  const { data } = await apiClient.patch<Alert>(`/alerts/${DEFAULT_TENANT_ID}/${alertId}`, {
    status: 'resolved',
    notes,
  })
  return data
}

// -----------------------------------------------------------------------------
// Predictions
// -----------------------------------------------------------------------------

export async function predictAsset(
  assetId: string,
  features?: Record<string, number>
): Promise<Prediction> {
  const { data } = await apiClient.post<Prediction>('/predict', {
    tenant_id: DEFAULT_TENANT_ID,
    asset_id: assetId,
    features,
  })
  return data
}

// -----------------------------------------------------------------------------
// Alert Rules
// -----------------------------------------------------------------------------

export async function fetchRules(): Promise<AlertRule[]> {
  const { data } = await apiClient.get<AlertRule[]>(`/rules/${DEFAULT_TENANT_ID}`)
  return data
}

export async function createRule(
  payload: Omit<AlertRule, 'id' | 'tenant_id' | 'is_active' | 'created_at'>
): Promise<AlertRule> {
  const { data } = await apiClient.post<AlertRule>(`/rules/${DEFAULT_TENANT_ID}`, payload)
  return data
}

export async function updateRule(
  ruleId: string,
  payload: Partial<AlertRule>
): Promise<AlertRule> {
  const { data } = await apiClient.put<AlertRule>(`/rules/${DEFAULT_TENANT_ID}/${ruleId}`, payload)
  return data
}

export async function deleteRule(ruleId: string): Promise<void> {
  await apiClient.delete(`/rules/${DEFAULT_TENANT_ID}/${ruleId}`)
}

// -----------------------------------------------------------------------------
// Reports
// -----------------------------------------------------------------------------

export async function fetchFleetSummary(): Promise<FleetSummary> {
  const { data } = await apiClient.get<FleetSummary>(`/reports/${DEFAULT_TENANT_ID}/summary`)
  return data
}

export async function fetchTrends(
  metric: string,
  days: number,
  assetId?: string
): Promise<TrendResponse> {
  const { data } = await apiClient.get<TrendResponse>(`/reports/${DEFAULT_TENANT_ID}/trends`, {
    params: { metric, days, ...(assetId && { asset_id: assetId }) },
  })
  return data
}

export async function fetchCostAvoidance(year?: number): Promise<CostAvoidanceReport> {
  const { data } = await apiClient.get<CostAvoidanceReport>(
    `/reports/${DEFAULT_TENANT_ID}/cost-avoidance`,
    { params: year ? { year } : {} }
  )
  return data
}

export async function fetchAssetReport(assetId: string) {
  const { data } = await apiClient.get(`/reports/${DEFAULT_TENANT_ID}/asset/${assetId}`)
  return data
}
