import { useQuery } from '@tanstack/react-query'
import { fetchFleetSummary } from '@/api/endpoints'
import { useAuthStore } from '@/store/auth'

export function useFleetSummary() {
  const tenantId = useAuthStore((s) => s.tenantId)

  return useQuery({
    queryKey: ['fleet-summary', tenantId],
    queryFn: () => fetchFleetSummary(tenantId!),
    enabled: !!tenantId,
    refetchInterval: 60_000, // auto-refresh every 60 s
  })
}
