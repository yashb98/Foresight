/**
 * Trends Page — multi-metric sensor trend charts with metric and time-range selectors
 */

import { useState } from 'react'
import { TopBar } from '@/components/layout/TopBar'
import { TrendChart } from '@/components/charts/TrendChart'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { useTrends } from '@/hooks/useTrends'

const METRICS = [
  { key: 'vibration_rms',        label: 'Vibration RMS',       threshold: 8.0 },
  { key: 'bearing_temp_celsius', label: 'Bearing Temperature',  threshold: 85.0 },
  { key: 'oil_pressure_bar',     label: 'Oil Pressure',         threshold: 2.5 },
  { key: 'motor_current_amp',    label: 'Motor Current',        threshold: undefined },
]

const DAY_OPTIONS = [7, 14, 30, 90]

export function Trends() {
  const [days, setDays] = useState(30)

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <TopBar
        title="Sensor Trends"
        subtitle="Aggregated time-series data across the asset fleet"
      />
      <div className="flex-1 overflow-y-auto p-6 space-y-6">
        {/* Time range selector */}
        <div className="flex gap-2">
          {DAY_OPTIONS.map((d) => (
            <button
              key={d}
              onClick={() => setDays(d)}
              className={`px-4 py-1.5 rounded-md text-sm font-medium transition-colors ${
                days === d
                  ? 'bg-primary text-primary-foreground'
                  : 'bg-muted text-muted-foreground hover:bg-secondary'
              }`}
            >
              {d}d
            </button>
          ))}
        </div>

        {/* Chart grid */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {METRICS.map(({ key, label, threshold }) => (
            <TrendChartCard
              key={key}
              metric={key}
              label={label}
              threshold={threshold}
              days={days}
            />
          ))}
        </div>
      </div>
    </div>
  )
}

function TrendChartCard({
  metric,
  label,
  threshold,
  days,
}: {
  metric: string
  label: string
  threshold?: number
  days: number
}) {
  const { data, isLoading } = useTrends(metric, days)

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-semibold">{label}</CardTitle>
        {threshold !== undefined && (
          <p className="text-xs text-muted-foreground">Alert threshold: {threshold}</p>
        )}
      </CardHeader>
      <CardContent>
        <TrendChart
          data={data?.data_points ?? []}
          metric={metric}
          threshold={threshold}
          isLoading={isLoading}
          height={200}
        />
      </CardContent>
    </Card>
  )
}
