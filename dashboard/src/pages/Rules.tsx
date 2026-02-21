/**
 * Alert Rules Page — CRUD interface for threshold-based alert rules
 */

import { TopBar } from '@/components/layout/TopBar'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { fetchRules, deleteRule } from '@/api/endpoints'
import { useAuthStore } from '@/store/auth'
import { operatorLabel } from '@/lib/utils'
import { ShieldCheck, Trash2, Plus, ToggleLeft, ToggleRight } from 'lucide-react'
import type { AlertRule } from '@/types'

export function Rules() {
  const tenantId = useAuthStore((s) => s.tenantId)
  const queryClient = useQueryClient()

  const { data: rules = [], isLoading } = useQuery({
    queryKey: ['rules', tenantId],
    queryFn: () => fetchRules(tenantId!),
    enabled: !!tenantId,
  })

  const deleteMutation = useMutation({
    mutationFn: (ruleId: string) => deleteRule(tenantId!, ruleId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['rules', tenantId] }),
  })

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <TopBar
        title="Alert Rules"
        subtitle="Threshold rules evaluated by the Spark streaming pipeline"
      />
      <div className="flex-1 overflow-y-auto p-6 space-y-4">
        <div className="flex justify-between items-center">
          <p className="text-sm text-muted-foreground">
            {rules.length} rule{rules.length !== 1 ? 's' : ''} configured
          </p>
          <Button size="sm" className="gap-1.5">
            <Plus className="h-4 w-4" />
            New Rule
          </Button>
        </div>

        {isLoading && (
          <div className="space-y-3">
            {Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-20 w-full" />
            ))}
          </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
          {rules.map((rule) => (
            <RuleCard
              key={rule.id}
              rule={rule}
              onDelete={() => deleteMutation.mutate(rule.id)}
              isDeleting={deleteMutation.isPending}
            />
          ))}
        </div>

        {!isLoading && rules.length === 0 && (
          <Card className="border-dashed">
            <CardContent className="py-12 flex flex-col items-center text-muted-foreground">
              <ShieldCheck className="h-10 w-10 mb-3 opacity-30" />
              <p className="text-sm">No alert rules configured</p>
              <p className="text-xs mt-1">Create a rule to start detecting anomalies</p>
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  )
}

function RuleCard({
  rule,
  onDelete,
  isDeleting,
}: {
  rule: AlertRule
  onDelete: () => void
  isDeleting: boolean
}) {
  return (
    <Card className={rule.is_active ? '' : 'opacity-50'}>
      <CardContent className="pt-4 pb-3">
        <div className="flex items-start justify-between gap-2">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="font-medium text-sm text-foreground">{rule.name}</span>
              <Badge variant={rule.severity as 'critical' | 'high' | 'medium' | 'low'}>
                {rule.severity}
              </Badge>
              {!rule.is_active && (
                <Badge variant="outline" className="text-xs">Inactive</Badge>
              )}
            </div>
            {rule.description && (
              <p className="text-xs text-muted-foreground mt-0.5 truncate">{rule.description}</p>
            )}
            <div className="mt-2 flex items-center gap-2 flex-wrap text-xs">
              <code className="bg-muted px-1.5 py-0.5 rounded font-mono">
                {rule.metric} {operatorLabel(rule.operator)} {rule.threshold}
              </code>
              {rule.asset_type && (
                <span className="text-muted-foreground">· {rule.asset_type}</span>
              )}
            </div>
          </div>
          <div className="flex gap-1 shrink-0">
            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7"
              title={rule.is_active ? 'Deactivate rule' : 'Activate rule'}
            >
              {rule.is_active ? (
                <ToggleRight className="h-4 w-4 text-primary" />
              ) : (
                <ToggleLeft className="h-4 w-4 text-muted-foreground" />
              )}
            </Button>
            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7 text-muted-foreground hover:text-destructive"
              title="Delete rule"
              onClick={onDelete}
              disabled={isDeleting}
            >
              <Trash2 className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}
