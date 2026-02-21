import { useQuery } from '@tanstack/react-query'
import { fetchTrends, fetchCostAvoidance } from '@/api/endpoints'

export function useTrends(metric: string, days: number) {
  return useQuery({
    queryKey: ['trends', metric, days],
    queryFn: () => fetchTrends(metric, days),
    staleTime: 5 * 60 * 1000, // 5 minutes
  })
}

export function useCostAvoidance(year?: number) {
  return useQuery({
    queryKey: ['cost-avoidance', year],
    queryFn: () => fetchCostAvoidance(year),
    staleTime: 5 * 60 * 1000,
  })
}
