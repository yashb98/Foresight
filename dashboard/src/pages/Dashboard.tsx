/**
 * Dashboard Overview Page
 *
 * Displays:
 *  - Fleet health KPI cards (total assets, assets at risk, alert counts)
 *  - Fleet health gauge
 *  - Live alert feed (top 8 open alerts)
 *  - 30-day vibration trend chart
 */

import { TopBar } from '@/components/layout/TopBar'
import { AlertFeed } from '@/components/alerts/AlertFeed'
import { TrendChart } from '@/components/charts/TrendChart'
import { HealthGauge } from '@/components/charts/HealthGauge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { useFleetSummary } from '@/hooks/useFleetSummary'
import { useTrends } from '@/hooks/useTrends'
import { formatDate } from '@/lib/utils'
import {
  Cpu, ShieldAlert, AlertTriangle, Activity, TrendingUp, DollarSign,
} from 'lucide-react'

function KpiCard({
  title,
  value,
  subtitle,
  icon: Icon,
  iconColour = 'text-primary',
  isLoading = false,
}: {
  title: string
  value: string | number
  subtitle?: string
  icon: React.FC<{ className?: string }>
  iconColour?: string
  isLoading?: boolean
}) {
  return (
    <Card>
      <CardContent className="pt-5 pb-4">
        <div className="flex items-start justify-between">
          <div>
            <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">{title}</p>
            {isLoading ? (
              <Skeleton className="mt-2 h-8 w-20" />
            ) : (
              <p className="mt-1 text-3xl font-bold text-foreground">{value}</p>
            )}
            {subtitle && <p className="mt-1 text-xs text-muted-foreground">{subtitle}</p>}
          </div>
          <div className={`rounded-lg bg-muted/50 p-2.5 ${iconColour}`}>
            <Icon className="h-5 w-5" />
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

export function Dashboard() {
  const { data: fleet, isLoading: fleetLoading } = useFleetSummary()
  const { data: trends, isLoading: trendsLoading } = useTrends('vibration_rms', 30)

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <TopBar
        title="Fleet Overview"
        subtitle={fleet ? `Last updated ${formatDate(fleet.as_of)}` : undefined}
      />

      <div className="flex-1 overflow-y-auto p-6 space-y-6">
        {/* KPI Row */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <KpiCard
            title="Total Assets"
            value={fleet?.total_assets ?? 0}
            subtitle={`${fleet?.active_assets ?? 0} active`}
            icon={Cpu}
            iconColour="text-blue-400"
            isLoading={fleetLoading}
          />
          <KpiCard
            title="Assets at Risk"
            value={fleet?.assets_at_risk ?? 0}
            subtitle="Critical + High"
            icon={ShieldAlert}
            iconColour="text-red-400"
            isLoading={fleetLoading}
          />
          <KpiCard
            title="Open Alerts"
            value={(fleet?.critical_alerts ?? 0) + (fleet?.high_alerts ?? 0) + (fleet?.medium_alerts ?? 0)}
            subtitle={fleet ? `${fleet.critical_alerts} critical` : undefined}
            icon={AlertTriangle}
            iconColour="text-orange-400"
            isLoading={fleetLoading}
          />
          <KpiCard
            title="Fleet Health"
            value={fleet ? `${fleet.fleet_health_score.toFixed(1)}` : 0}
            subtitle="0–100 composite score"
            icon={Activity}
            iconColour="text-emerald-400"
            isLoading={fleetLoading}
          />
        </div>

        {/* Main content grid */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Trend chart — 2/3 width */}
          <Card className="lg:col-span-2">
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <CardTitle className="text-sm font-semibold flex items-center gap-2">
                  <TrendingUp className="h-4 w-4 text-primary" />
                  Fleet Vibration Trend (30 days)
                </CardTitle>
              </div>
            </CardHeader>
            <CardContent>
              <TrendChart
                data={trends?.data_points ?? []}
                metric="vibration_rms"
                threshold={8.0}
                isLoading={trendsLoading}
                height={240}
              />
            </CardContent>
          </Card>

          {/* Health gauge — 1/3 width */}
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-semibold flex items-center gap-2">
                <Activity className="h-4 w-4 text-emerald-400" />
                Fleet Health Score
              </CardTitle>
            </CardHeader>
            <CardContent className="flex flex-col items-center py-4">
              {fleetLoading ? (
                <Skeleton className="h-24 w-24 rounded-full" />
              ) : (
                <HealthGauge
                  score={fleet?.fleet_health_score ?? 0}
                  size={160}
                  strokeWidth={12}
                  label="Fleet Health"
                />
              )}
              {!fleetLoading && fleet && (
                <div className="mt-4 w-full space-y-2">
                  {[
                    { label: 'Critical Alerts', count: fleet.critical_alerts, colour: 'bg-red-400' },
                    { label: 'High Alerts',     count: fleet.high_alerts,     colour: 'bg-orange-400' },
                    { label: 'Medium Alerts',   count: fleet.medium_alerts,   colour: 'bg-yellow-400' },
                    { label: 'Low Alerts',      count: fleet.low_alerts,      colour: 'bg-blue-400' },
                  ].map(({ label, count, colour }) => (
                    <div key={label} className="flex items-center justify-between text-xs">
                      <div className="flex items-center gap-1.5">
                        <div className={`h-2 w-2 rounded-full ${colour}`} />
                        <span className="text-muted-foreground">{label}</span>
                      </div>
                      <span className="font-medium text-foreground">{count}</span>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Alert Feed */}
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-semibold flex items-center gap-2">
              <AlertTriangle className="h-4 w-4 text-orange-400" />
              Live Alert Feed
            </CardTitle>
          </CardHeader>
          <CardContent>
            <AlertFeed maxItems={8} showFilters={true} />
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
