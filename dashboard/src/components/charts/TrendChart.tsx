/**
 * TrendChart — time-series line chart for sensor metrics
 * Uses Recharts with a dark theme.
 */

import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from 'recharts'
import type { TrendDataPoint } from '@/types'
import { Skeleton } from '@/components/ui/skeleton'

interface TrendChartProps {
  data: TrendDataPoint[]
  metric: string
  threshold?: number
  isLoading?: boolean
  height?: number
}

const METRIC_LABELS: Record<string, string> = {
  vibration_rms: 'Vibration RMS (m/s²)',
  bearing_temp_celsius: 'Bearing Temperature (°C)',
  oil_pressure_bar: 'Oil Pressure (bar)',
  motor_current_amp: 'Motor Current (A)',
  rpm: 'RPM',
}

export function TrendChart({
  data,
  metric,
  threshold,
  isLoading = false,
  height = 280,
}: TrendChartProps) {
  if (isLoading) {
    return <Skeleton className="w-full" style={{ height }} />
  }

  const label = METRIC_LABELS[metric] ?? metric

  return (
    <div>
      <p className="mb-3 text-xs text-muted-foreground uppercase tracking-wider">{label}</p>
      <ResponsiveContainer width="100%" height={height}>
        <LineChart data={data} margin={{ top: 5, right: 20, left: -10, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" vertical={false} />
          <XAxis
            dataKey="date"
            tick={{ fontSize: 11, fill: 'hsl(var(--muted-foreground))' }}
            tickLine={false}
            axisLine={false}
            tickFormatter={(v: string) => v.slice(5)} // "MM-DD"
            interval="preserveStartEnd"
          />
          <YAxis
            tick={{ fontSize: 11, fill: 'hsl(var(--muted-foreground))' }}
            tickLine={false}
            axisLine={false}
            width={45}
          />
          <Tooltip
            contentStyle={{
              background: 'hsl(var(--card))',
              border: '1px solid hsl(var(--border))',
              borderRadius: 8,
              fontSize: 12,
            }}
            labelStyle={{ color: 'hsl(var(--foreground))', fontWeight: 600 }}
            itemStyle={{ color: 'hsl(var(--primary))' }}
          />
          {threshold !== undefined && (
            <ReferenceLine
              y={threshold}
              stroke="hsl(var(--destructive))"
              strokeDasharray="4 2"
              label={{
                value: `Threshold: ${threshold}`,
                fill: 'hsl(var(--destructive))',
                fontSize: 10,
                position: 'insideTopRight',
              }}
            />
          )}
          <Line
            type="monotone"
            dataKey="avg_value"
            name="Avg"
            stroke="hsl(var(--primary))"
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 4, strokeWidth: 0 }}
          />
          <Line
            type="monotone"
            dataKey="max_value"
            name="Max"
            stroke="hsl(var(--destructive))"
            strokeWidth={1}
            strokeDasharray="3 2"
            dot={false}
            opacity={0.5}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
