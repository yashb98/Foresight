/**
 * AlertFeed — Live streaming alert list with severity badges and action buttons.
 */

import { useState } from 'react'
import { Bell, CheckCircle, Eye, Filter } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { useAlerts, useAcknowledgeAlert, useResolveAlert } from '@/hooks/useAlerts'
import { relativeTime, cn } from '@/lib/utils'
import type { AlertSeverity, AlertStatus } from '@/types'

const SEVERITY_ORDER: Record<AlertSeverity, number> = {
  critical: 0, high: 1, medium: 2, low: 3,
}

interface AlertFeedProps {
  maxItems?: number
  showFilters?: boolean
}

export function AlertFeed({ maxItems = 20, showFilters = true }: AlertFeedProps) {
  const [severityFilter, setSeverityFilter] = useState<AlertSeverity | 'all'>('all')
  const [statusFilter, setStatusFilter] = useState<AlertStatus | 'all'>('open')

  const { data, isLoading, isError } = useAlerts({
    severity: severityFilter === 'all' ? undefined : severityFilter,
    status: statusFilter === 'all' ? undefined : statusFilter,
  })
  const ackMutation = useAcknowledgeAlert()
  const resolveMutation = useResolveAlert()

  const alerts = (data?.alerts ?? [])
    .sort((a, b) => SEVERITY_ORDER[a.severity] - SEVERITY_ORDER[b.severity])
    .slice(0, maxItems)

  return (
    <div className="flex flex-col h-full">
      {showFilters && (
        <div className="flex items-center gap-2 mb-3 flex-wrap">
          <Filter className="h-3.5 w-3.5 text-muted-foreground" />
          {(['all', 'critical', 'high', 'medium', 'low'] as const).map((sev) => (
            <button
              key={sev}
              onClick={() => setSeverityFilter(sev)}
              className={cn(
                'px-2 py-0.5 rounded-full text-xs font-medium transition-colors',
                severityFilter === sev
                  ? 'bg-primary text-primary-foreground'
                  : 'bg-muted text-muted-foreground hover:bg-secondary'
              )}
            >
              {sev.charAt(0).toUpperCase() + sev.slice(1)}
            </button>
          ))}
          <div className="ml-auto flex gap-1">
            {(['open', 'acknowledged', 'all'] as const).map((st) => (
              <button
                key={st}
                onClick={() => setStatusFilter(st)}
                className={cn(
                  'px-2 py-0.5 rounded-full text-xs font-medium transition-colors',
                  statusFilter === st
                    ? 'bg-secondary text-foreground'
                    : 'text-muted-foreground hover:text-foreground'
                )}
              >
                {st.charAt(0).toUpperCase() + st.slice(1)}
              </button>
            ))}
          </div>
        </div>
      )}

      {isLoading && (
        <div className="space-y-2">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-16 w-full" />
          ))}
        </div>
      )}

      {isError && (
        <div className="flex flex-col items-center justify-center py-8 text-muted-foreground">
          <Bell className="h-8 w-8 mb-2 opacity-40" />
          <p className="text-sm">Could not load alerts</p>
        </div>
      )}

      {!isLoading && !isError && alerts.length === 0 && (
        <div className="flex flex-col items-center justify-center py-8 text-muted-foreground">
          <CheckCircle className="h-8 w-8 mb-2 text-emerald-500 opacity-70" />
          <p className="text-sm">No alerts match your filters</p>
        </div>
      )}

      <div className="space-y-2 overflow-y-auto flex-1">
        {alerts.map((alert) => (
          <div
            key={alert.alert_id}
            className={cn(
              'flex items-start gap-3 rounded-lg border p-3 transition-colors',
              alert.severity === 'critical' && 'border-red-500/30 bg-red-500/5',
              alert.severity === 'high'     && 'border-orange-500/30 bg-orange-500/5',
              alert.severity === 'medium'   && 'border-yellow-500/30 bg-yellow-500/5',
              alert.severity === 'low'      && 'border-border bg-card'
            )}
          >
            {/* Severity dot */}
            <div className={cn(
              'mt-1 h-2 w-2 shrink-0 rounded-full',
              alert.severity === 'critical' && 'bg-red-400 animate-pulse-slow',
              alert.severity === 'high'     && 'bg-orange-400',
              alert.severity === 'medium'   && 'bg-yellow-400',
              alert.severity === 'low'      && 'bg-blue-400'
            )} />

            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <Badge variant={alert.severity as 'critical' | 'high' | 'medium' | 'low'}>
                  {alert.severity.toUpperCase()}
                </Badge>
                <span className="text-xs text-muted-foreground font-mono truncate">
                  {alert.asset_id.slice(0, 12)}…
                </span>
                <span className="ml-auto text-xs text-muted-foreground shrink-0">
                  {relativeTime(alert.triggered_at)}
                </span>
              </div>
              <p className="mt-1 text-sm text-foreground leading-snug">
                <span className="font-medium">{alert.metric_name}</span>
                {alert.actual_value !== null && (
                  <> = <span className="text-destructive font-mono">{alert.actual_value.toFixed(2)}</span></>
                )}
                {alert.threshold_value !== null && (
                  <span className="text-muted-foreground"> (threshold: {alert.threshold_value})</span>
                )}
              </p>
            </div>

            {/* Actions */}
            {alert.status === 'open' && (
              <div className="flex gap-1 shrink-0">
                <Button
                  size="sm"
                  variant="ghost"
                  className="h-7 px-2 text-xs"
                  title="Acknowledge"
                  onClick={() => ackMutation.mutate({ alertId: alert.alert_id })}
                  disabled={ackMutation.isPending}
                >
                  <Eye className="h-3.5 w-3.5" />
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  className="h-7 px-2 text-xs text-emerald-400 hover:text-emerald-300"
                  title="Resolve"
                  onClick={() => resolveMutation.mutate({ alertId: alert.alert_id })}
                  disabled={resolveMutation.isPending}
                >
                  <CheckCircle className="h-3.5 w-3.5" />
                </Button>
              </div>
            )}

            {alert.status !== 'open' && (
              <Badge variant="success" className="text-[10px] shrink-0">
                {alert.status}
              </Badge>
            )}
          </div>
        ))}
      </div>

      {data && data.total > maxItems && (
        <p className="mt-2 text-center text-xs text-muted-foreground">
          Showing {maxItems} of {data.total} alerts
        </p>
      )}
    </div>
  )
}
