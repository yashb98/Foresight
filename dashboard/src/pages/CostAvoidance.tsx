/**
 * Cost Avoidance Page — ROI report showing maintenance savings
 */

import { TopBar } from '@/components/layout/TopBar'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { useCostAvoidance } from '@/hooks/useTrends'
import { formatCurrency, formatPercent } from '@/lib/utils'
import { DollarSign, TrendingUp, Zap, ShieldCheck } from 'lucide-react'

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
            isLoading={isLoading}
          />
          <CostKpi
            title="Actual Maintenance Cost"
            value={data ? formatCurrency(data.actual_maintenance_cost_usd) : '…'}
            icon={Zap}
            colour="text-blue-400"
            isLoading={isLoading}
          />
          <CostKpi
            title="ROI"
            value={data ? formatPercent(data.roi_percent) : '…'}
            icon={TrendingUp}
            colour="text-primary"
            isLoading={isLoading}
          />
          <CostKpi
            title="Predicted Failures"
            value={data?.total_predicted_failures ?? 0}
            icon={ShieldCheck}
            colour="text-orange-400"
            isLoading={isLoading}
          />
        </div>

        {/* Breakdown by severity */}
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-semibold">Breakdown by Alert Severity</CardTitle>
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <div className="space-y-3">
                {Array.from({ length: 4 }).map((_, i) => (
                  <Skeleton key={i} className="h-10 w-full" />
                ))}
              </div>
            ) : data ? (
              <div className="space-y-3">
                {Object.entries(data.breakdown_by_severity).map(([sev, count]) => {
                  const unitSavings: Record<string, number> = {
                    critical: 63_750, high: 26_250, medium: 9_000, low: 2_250,
                  }
                  const saved = (unitSavings[sev] ?? 0) * count
                  return (
                    <div key={sev} className="flex items-center gap-4">
                      <div className={`w-2 h-2 rounded-full shrink-0 ${
                        sev === 'critical' ? 'bg-red-400' :
                        sev === 'high' ? 'bg-orange-400' :
                        sev === 'medium' ? 'bg-yellow-400' : 'bg-blue-400'
                      }`} />
                      <div className="flex-1">
                        <div className="flex justify-between text-sm mb-1">
                          <span className="capitalize font-medium text-foreground">{sev}</span>
                          <span className="text-muted-foreground">{count} events · {formatCurrency(saved)} avoided</span>
                        </div>
                        <div className="h-2 bg-muted rounded-full overflow-hidden">
                          <div
                            className={`h-full rounded-full ${
                              sev === 'critical' ? 'bg-red-400' :
                              sev === 'high' ? 'bg-orange-400' :
                              sev === 'medium' ? 'bg-yellow-400' : 'bg-blue-400'
                            }`}
                            style={{
                              width: `${Math.min(100, (count / data.total_predicted_failures) * 100)}%`,
                            }}
                          />
                        </div>
                      </div>
                    </div>
                  )
                })}
              </div>
            ) : null}
          </CardContent>
        </Card>

        {/* Methodology note */}
        <Card className="border-dashed">
          <CardContent className="pt-4 pb-3">
            <p className="text-xs text-muted-foreground leading-relaxed">
              <strong>Methodology:</strong> Cost avoidance is calculated using industry benchmarks where
              unplanned maintenance costs 3–5× planned maintenance (Luber, 2022). Resolved alerts are
              categorised by severity, with per-event savings of: Critical $63,750 · High $26,250 ·
              Medium $9,000 · Low $2,250. Actual savings will vary by industry and maintenance strategy.
            </p>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}

function CostKpi({
  title,
  value,
  icon: Icon,
  colour,
  isLoading,
}: {
  title: string
  value: string | number
  icon: React.FC<{ className?: string }>
  colour: string
  isLoading: boolean
}) {
  return (
    <Card>
      <CardContent className="pt-5 pb-4">
        <div className="flex items-start justify-between">
          <div>
            <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">{title}</p>
            {isLoading ? (
              <Skeleton className="mt-2 h-8 w-28" />
            ) : (
              <p className="mt-1 text-2xl font-bold text-foreground">{value}</p>
            )}
          </div>
          <div className={`rounded-lg bg-muted/50 p-2.5 ${colour}`}>
            <Icon className="h-5 w-5" />
          </div>
        </div>
      </CardContent>
    </Card>
  )
}
