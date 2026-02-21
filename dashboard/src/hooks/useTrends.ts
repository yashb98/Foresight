import { useQuery } from '@tanstack/react-query'
import { fetchTrends, fetchCostAvoidance } from '@/api/endpoints'
import { useAuthStore } from '@/store/auth'

export function useTrends(metric: string, days: number, assetId?: string) {
  const tenantId = useAuthStore((s) => s.tenantId)

  return useQuery({
    queryKey: ['trends', tenantId, metric, days, assetId],
    queryFn: () => fetchTrends(tenantId!, metric, days, assetId),
    enabled: !!tenantId,
    staleTime: 5 * 60_000,
  })
}

export function useCostAvoidance(year?: number) {
  const tenantId = useAuthStore((s) => s.tenantId)

  return useQuery({
    queryKey: ['cost-avoidance', tenantId, year],
    queryFn: () => fetchCostAvoidance(tenantId!, year),
    enabled: !!tenantId,
    staleTime: 10 * 60_000,
  })
}
