import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { fetchAlerts, acknowledgeAlert, resolveAlert } from '@/api/endpoints'
import type { AlertFilters } from '@/api/endpoints'

export function useAlerts(filters: AlertFilters = {}) {
  return useQuery({
    queryKey: ['alerts', filters],
    queryFn: () => fetchAlerts(filters),
    refetchInterval: 30_000,
  })
}

export function useAcknowledgeAlert() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ alertId, notes }: { alertId: string; notes?: string }) =>
      acknowledgeAlert(alertId, notes),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['alerts'] })
    },
  })
}

export function useResolveAlert() {
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: ({ alertId, notes }: { alertId: string; notes?: string }) =>
      resolveAlert(alertId, notes),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['alerts'] })
    },
  })
}
