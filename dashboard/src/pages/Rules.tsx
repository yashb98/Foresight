/**
 * Alert Rules Page — CRUD interface for threshold-based alert rules
 */

import { TopBar } from '@/components/layout/TopBar'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Skeleton } from '@/components/ui/skeleton'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { fetchRules, deleteRule } from '@/api/endpoints'
import { operatorLabel } from '@/lib/utils'
import { ShieldCheck, Trash2, Plus, ToggleLeft, ToggleRight, FileWarning, Settings2 } from 'lucide-react'
import type { AlertRule } from '@/types'

export function Rules() {
  const queryClient = useQueryClient()

  const { data: rules = [], isLoading } = useQuery({
    queryKey: ['rules'],
    queryFn: fetchRules,
  })

  const deleteMutation = useMutation({
    mutationFn: (ruleId: string) => deleteRule(ruleId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['rules'] }),
  })

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <TopBar
        title="Alert Rules"
        subtitle="Threshold rules evaluated by the Spark streaming pipeline"
      />
      <div className="flex-1 overflow-y-auto p-6 space-y-6">
        {/* Header stats */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <Card className="bg-gradient-to-br from-card to-muted/20">
            <CardContent className="pt-4 pb-4 flex items-center gap-3">
              <div className="h-10 w-10 rounded-lg bg-primary/10 flex items-center justify-center">
                <Settings2 className="h-5 w-5 text-primary" />
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Total Rules</p>
                <p className="text-lg font-semibold">{rules.length} configured</p>
              </div>
            </CardContent>
          </Card>
          <Card className="bg-gradient-to-br from-card to-muted/20">
            <CardContent className="pt-4 pb-4 flex items-center gap-3">
              <div className="h-10 w-10 rounded-lg bg-emerald-400/10 flex items-center justify-center">
                <ToggleRight className="h-5 w-5 text-emerald-400" />
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Active Rules</p>
                <p className="text-lg font-semibold">{rules.filter(r => r.is_active).length} active</p>
              </div>
            </CardContent>
          </Card>
          <Card className="bg-gradient-to-br from-card to-muted/20">
            <CardContent className="pt-4 pb-4 flex items-center gap-3">
              <div className="h-10 w-10 rounded-lg bg-orange-400/10 flex items-center justify-center">
                <FileWarning className="h-5 w-5 text-orange-400" />
              </div>
              <div>
                <p className="text-xs text-muted-foreground">Detection</p>
                <p className="text-lg font-semibold">Real-time evaluation</p>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Rules list */}
        <Card>
          <CardHeader className="pb-3 flex flex-row items-center justify-between">
            <CardTitle className="text-sm font-semibold">Configured Rules</CardTitle>
            <Button size="sm" className="gap-1.5">
              <Plus className="h-4 w-4" />
              New Rule
            </Button>
          </CardHeader>
          <CardContent>
            {isLoading && (
              <div className="space-y-3">
                {Array.from({ length: 4 }).map((_, i) => (
                  <Skeleton key={i} className="h-20 w-full" />
                ))}
              </div>
            )}

            <div className="grid grid-cols-1 gap-3">
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
              <div className="py-12 flex flex-col items-center text-muted-foreground border border-dashed border-border rounded-lg">
                <ShieldCheck className="h-12 w-12 mb-3 opacity-30" />
                <p className="text-sm">No alert rules configured</p>
                <p className="text-xs mt-1">Create a rule to start detecting anomalies</p>
              </div>
            )}
          </CardContent>
        </Card>
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
    <div className={`flex items-center justify-between p-4 rounded-lg border transition-all ${
      rule.is_active 
        ? 'bg-card border-border hover:border-primary/30' 
        : 'bg-muted/20 border-border/50 opacity-60'
    }`}>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="font-medium text-sm text-foreground">{rule.name}</span>
          <Badge variant={rule.severity as 'critical' | 'high' | 'medium' | 'low'} className="text-[10px]">
            {rule.severity}
          </Badge>
          {!rule.is_active && (
            <Badge variant="outline" className="text-[10px]">Inactive</Badge>
          )}
        </div>
        {rule.description && (
          <p className="text-xs text-muted-foreground mt-1">{rule.description}</p>
        )}
        <div className="mt-2 flex items-center gap-2 flex-wrap text-xs">
          <code className="bg-muted px-2 py-0.5 rounded font-mono text-primary">
            {rule.metric} {operatorLabel(rule.operator)} {rule.threshold}
          </code>
          {rule.asset_type && (
            <span className="text-muted-foreground">· {rule.asset_type}</span>
          )}
        </div>
      </div>
      <div className="flex gap-1 shrink-0 ml-4">
        <Button
          variant="ghost"
          size="icon"
          className="h-8 w-8"
          title={rule.is_active ? 'Deactivate rule' : 'Activate rule'}
        >
          {rule.is_active ? (
            <ToggleRight className="h-4 w-4 text-emerald-400" />
          ) : (
            <ToggleLeft className="h-4 w-4 text-muted-foreground" />
          )}
        </Button>
        <Button
          variant="ghost"
          size="icon"
          className="h-8 w-8 text-muted-foreground hover:text-destructive"
          title="Delete rule"
          onClick={onDelete}
          disabled={isDeleting}
        >
          <Trash2 className="h-4 w-4" />
        </Button>
      </div>
    </div>
  )
}
