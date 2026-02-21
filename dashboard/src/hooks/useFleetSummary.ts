import { useQuery } from '@tanstack/react-query'
import { fetchFleetSummary } from '@/api/endpoints'

export function useFleetSummary() {
  return useQuery({
    queryKey: ['fleet-summary'],
    queryFn: fetchFleetSummary,
    refetchInterval: 60_000, // auto-refresh every 60 s
  })
}
