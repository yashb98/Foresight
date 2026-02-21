/**
 * TrendChart — Recharts line chart wrapper for sensor trends
 */

import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
  ReferenceLine,
} from 'recharts'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'

interface DataPoint {
  date: string
  avg_value: number
  max_value?: number
  min_value?: number
}

interface TrendChartProps {
  data: DataPoint[]
  metric: string
  threshold?: number
  isLoading?: boolean
  height?: number
  className?: string
}

const metricLabels: Record<string, string> = {
  vibration_rms: 'Vibration (mm/s)',
  bearing_temp_celsius: 'Temperature (°C)',
  oil_pressure_bar: 'Pressure (bar)',
  motor_current_amp: 'Current (A)',
}

function formatDate(dateStr: string): string {
  const date = new Date(dateStr)
  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

export function TrendChart({
  data,
  metric,
  threshold,
  isLoading = false,
  height = 240,
  className,
}: TrendChartProps) {
  if (isLoading) {
    return <Skeleton className={cn('w-full', className)} style={{ height }} />
  }

  if (data.length === 0) {
    return (
      <div
        className={cn(
          'flex items-center justify-center rounded-lg border border-border bg-muted/20 text-muted-foreground',
          className
        )}
        style={{ height }}
      >
        <p className="text-sm">No data available</p>
      </div>
    )
  }

  const yAxisLabel = metricLabels[metric] || metric

  return (
    <div className={cn('w-full', className)} style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" opacity={0.5} />
          <XAxis
            dataKey="date"
            tickFormatter={formatDate}
            stroke="hsl(var(--muted-foreground))"
            fontSize={11}
            tickLine={false}
            axisLine={{ stroke: 'hsl(var(--border))' }}
          />
          <YAxis
            stroke="hsl(var(--muted-foreground))"
            fontSize={11}
            tickLine={false}
            axisLine={{ stroke: 'hsl(var(--border))' }}
            label={{
              value: yAxisLabel,
              angle: -90,
              position: 'insideLeft',
              style: { fill: 'hsl(var(--muted-foreground))', fontSize: 11 },
            }}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: 'hsl(var(--card))',
              border: '1px solid hsl(var(--border))',
              borderRadius: '6px',
              fontSize: '12px',
            }}
            labelStyle={{ color: 'hsl(var(--foreground))' }}
            itemStyle={{ color: 'hsl(var(--foreground))' }}
            labelFormatter={(label) => formatDate(label as string)}
          />
          {threshold !== undefined && (
            <ReferenceLine
              y={threshold}
              stroke="hsl(var(--destructive))"
              strokeDasharray="5 5"
              label={{
                value: `Threshold: ${threshold}`,
                fill: 'hsl(var(--destructive))',
                fontSize: 10,
                position: 'right',
              }}
            />
          )}
          <Line
            type="monotone"
            dataKey="avg_value"
            stroke="hsl(var(--primary))"
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 4, fill: 'hsl(var(--primary))' }}
          />
          {data[0]?.max_value !== undefined && (
            <Line
              type="monotone"
              dataKey="max_value"
              stroke="hsl(var(--primary) / 0.3)"
              strokeWidth={1}
              dot={false}
            />
          )}
          {data[0]?.min_value !== undefined && (
            <Line
              type="monotone"
              dataKey="min_value"
              stroke="hsl(var(--primary) / 0.3)"
              strokeWidth={1}
              dot={false}
            />
          )}
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
