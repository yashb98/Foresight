/**
 * Cost Avoidance Page — ROI report showing maintenance savings
 */

import { TopBar } from '@/components/layout/TopBar'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { useCostAvoidance } from '@/hooks/useTrends'
import { formatCurrency, formatPercent } from '@/lib/utils'
import { DollarSign, TrendingUp, Zap, ShieldCheck, PiggyBank, Info } from 'lucide-react'

export function CostAvoidance() {
  const { data, isLoading } = useCostAvoidance()

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <TopBar
        title="Cost Avoidance"
        subtitle="Estimated maintenance savings from predictive failure detection"
      />
      <div className="flex-1 overflow-y-auto p-6 space-y-6">
        {/* KPI Cards */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <CostKpi
            title="Cost Avoided"
            value={data ? formatCurrency(data.estimated_cost_avoided_usd) : '…'}
            icon={DollarSign}
            colour="text-emerald-400"
            bgColour="bg-emerald-400/10"
            isLoading={isLoading}
          />
          <CostKpi
            title="Actual Maintenance Cost"
            value={data ? formatCurrency(data.actual_maintenance_cost_usd) : '…'}
            icon={Zap}
            colour="text-blue-400"
            bgColour="bg-blue-400/10"
            isLoading={isLoading}
          />
          <CostKpi
            title="ROI"
            value={data ? formatPercent(data.roi_percent) : '…'}
            icon={TrendingUp}
            colour="text-primary"
            bgColour="bg-primary/10"
            isLoading={isLoading}
          />
          <CostKpi
            title="Predicted Failures"
            value={data?.total_predicted_failures ?? 0}
            icon={ShieldCheck}
            colour="text-orange-400"
            bgColour="bg-orange-400/10"
            isLoading={isLoading}
          />
        </div>

        {/* Main content */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Breakdown by severity */}
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-semibold flex items-center gap-2">
                <PiggyBank className="h-4 w-4 text-primary" />
                Breakdown by Alert Severity
              </CardTitle>
            </CardHeader>
            <CardContent>
              {isLoading ? (
                <div className="space-y-3">
                  {Array.from({ length: 4 }).map((_, i) => (
                    <Skeleton key={i} className="h-10 w-full" />
                  ))}
                </div>
              ) : data ? (
                <div className="space-y-4">
                  {Object.entries(data.breakdown_by_severity).map(([sev, count]) => {
                    const unitSavings: Record<string, number> = {
                      critical: 63_750, high: 26_250, medium: 9_000, low: 2_250,
                    }
                    const saved = (unitSavings[sev] ?? 0) * count
                    const percentage = Math.min(100, (count / data.total_predicted_failures) * 100)
                    return (
                      <div key={sev} className="space-y-2">
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-2">
                            <div className={`w-3 h-3 rounded-full ${
                              sev === 'critical' ? 'bg-red-400' :
                              sev === 'high' ? 'bg-orange-400' :
                              sev === 'medium' ? 'bg-yellow-400' : 'bg-blue-400'
                            }`} />
                            <span className="capitalize font-medium text-foreground">{sev}</span>
                          </div>
                          <div className="text-right">
                            <span className="text-sm font-medium">{count} events</span>
                            <span className="text-xs text-muted-foreground ml-2">{formatCurrency(saved)} saved</span>
                          </div>
                        </div>
                        <div className="h-2 bg-muted rounded-full overflow-hidden">
                          <div
                            className={`h-full rounded-full transition-all duration-500 ${
                              sev === 'critical' ? 'bg-red-400' :
                              sev === 'high' ? 'bg-orange-400' :
                              sev === 'medium' ? 'bg-yellow-400' : 'bg-blue-400'
                            }`}
                            style={{ width: `${percentage}%` }}
                          />
                        </div>
                      </div>
                    )
                  })}
                </div>
              ) : null}
            </CardContent>
          </Card>

          {/* Summary card */}
          <Card className="bg-gradient-to-br from-card to-muted/20">
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-semibold flex items-center gap-2">
                <Info className="h-4 w-4 text-primary" />
                Summary
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="p-4 rounded-lg bg-muted/30">
                <p className="text-sm text-foreground leading-relaxed">
                  Cost avoidance is calculated using industry benchmarks where unplanned 
                  maintenance costs <strong>3–5×</strong> more than planned maintenance.
                </p>
              </div>
              <div className="space-y-2">
                <div className="flex justify-between text-sm">
                  <span className="text-muted-foreground">Per-event savings:</span>
                </div>
                <div className="grid grid-cols-2 gap-2 text-xs">
                  <div className="p-2 rounded bg-red-400/10 text-red-400">Critical: $63,750</div>
                  <div className="p-2 rounded bg-orange-400/10 text-orange-400">High: $26,250</div>
                  <div className="p-2 rounded bg-yellow-400/10 text-yellow-400">Medium: $9,000</div>
                  <div className="p-2 rounded bg-blue-400/10 text-blue-400">Low: $2,250</div>
                </div>
              </div>
              {data && (
                <div className="pt-4 border-t border-border/50">
                  <div className="flex justify-between items-center">
                    <span className="text-sm text-muted-foreground">Report generated</span>
                    <span className="text-xs text-muted-foreground">
                      {new Date(data.generated_at).toLocaleString()}
                    </span>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  )
}

function CostKpi({
  title,
  value,
  icon: Icon,
  colour,
  bgColour,
  isLoading,
}: {
  title: string
  value: string | number
  icon: React.FC<{ className?: string }>
  colour: string
  bgColour: string
  isLoading: boolean
}) {
  return (
    <Card className="relative overflow-hidden">
      <CardContent className="relative pt-5 pb-4">
        <div className="flex items-start justify-between">
          <div>
            <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">{title}</p>
            {isLoading ? (
              <Skeleton className="mt-2 h-8 w-28" />
            ) : (
              <p className="mt-1 text-2xl font-bold text-foreground">{value}</p>
            )}
          </div>
          <div className={`rounded-xl ${bgColour} p-2.5 ${colour}`}>
            <Icon className="h-5 w-5" />
          </div>
        </div>
      </CardContent>
    </Card>
  )
}
