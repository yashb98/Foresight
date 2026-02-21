import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { fetchAlerts, acknowledgeAlert, resolveAlert } from '@/api/endpoints'
import { useAuthStore } from '@/store/auth'
import type { AlertFilters } from '@/api/endpoints'

export function useAlerts(filters: AlertFilters = {}) {
  const tenantId = useAuthStore((s) => s.tenantId)

  return useQuery({
    queryKey: ['alerts', tenantId, filters],
    queryFn: () => fetchAlerts(tenantId!, filters),
    enabled: !!tenantId,
    refetchInterval: 30_000,
  })
}

export function useAcknowledgeAlert() {
  const queryClient = useQueryClient()
  const tenantId = useAuthStore((s) => s.tenantId)

  return useMutation({
    mutationFn: ({ alertId, notes }: { alertId: string; notes?: string }) =>
      acknowledgeAlert(tenantId!, alertId, notes),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['alerts', tenantId] })
    },
  })
}

export function useResolveAlert() {
  const queryClient = useQueryClient()
  const tenantId = useAuthStore((s) => s.tenantId)

  return useMutation({
    mutationFn: ({ alertId, notes }: { alertId: string; notes?: string }) =>
      resolveAlert(tenantId!, alertId, notes),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['alerts', tenantId] })
    },
  })
}
