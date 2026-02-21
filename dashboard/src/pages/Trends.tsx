/**
 * Trends Page — multi-metric sensor trend charts with metric and time-range selectors
 */

import { useState } from 'react'
import { TopBar } from '@/components/layout/TopBar'
import { TrendChart } from '@/components/charts/TrendChart'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { useTrends } from '@/hooks/useTrends'
import { Activity, Thermometer, Gauge, Zap } from 'lucide-react'

const METRICS = [
  { key: 'vibration_rms',        label: 'Vibration RMS',       unit: 'mm/s',    threshold: 8.0,   icon: Activity },
  { key: 'bearing_temp_celsius', label: 'Bearing Temperature', unit: '°C',      threshold: 85.0,  icon: Thermometer },
  { key: 'oil_pressure_bar',     label: 'Oil Pressure',        unit: 'bar',     threshold: 2.5,   icon: Gauge },
  { key: 'motor_current_amp',    label: 'Motor Current',       unit: 'A',       threshold: undefined, icon: Zap },
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
        <Card>
          <CardContent className="pt-4 pb-4">
            <div className="flex items-center gap-4">
              <span className="text-sm text-muted-foreground">Time Range:</span>
              <div className="flex gap-2">
                {DAY_OPTIONS.map((d) => (
                  <button
                    key={d}
                    onClick={() => setDays(d)}
                    className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${
                      days === d
                        ? 'bg-primary text-primary-foreground shadow-lg shadow-primary/20'
                        : 'bg-muted text-muted-foreground hover:bg-muted/80'
                    }`}
                  >
                    {d} days
                  </button>
                ))}
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Chart grid */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {METRICS.map(({ key, label, unit, threshold, icon: Icon }) => (
            <TrendChartCard
              key={key}
              metric={key}
              label={label}
              unit={unit}
              threshold={threshold}
              days={days}
              icon={Icon}
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
  unit,
  threshold,
  days,
  icon: Icon,
}: {
  metric: string
  label: string
  unit: string
  threshold?: number
  days: number
  icon: React.FC<{ className?: string }>
}) {
  const { data, isLoading } = useTrends(metric, days)

  return (
    <Card className="overflow-hidden">
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm font-semibold flex items-center gap-2">
            <div className="h-8 w-8 rounded-lg bg-primary/10 flex items-center justify-center">
              <Icon className="h-4 w-4 text-primary" />
            </div>
            {label}
          </CardTitle>
          <span className="text-xs text-muted-foreground">{unit}</span>
        </div>
        {threshold !== undefined && (
          <p className="text-xs text-muted-foreground">Alert threshold: {threshold} {unit}</p>
        )}
      </CardHeader>
      <CardContent>
        <TrendChart
          data={data?.data_points ?? []}
          metric={metric}
          threshold={threshold}
          isLoading={isLoading}
          height={220}
        />
      </CardContent>
    </Card>
  )
}
