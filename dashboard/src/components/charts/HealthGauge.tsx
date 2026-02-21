/**
 * HealthGauge — circular arc gauge for fleet health score (0–100)
 */

import { cn } from '@/lib/utils'

interface HealthGaugeProps {
  score: number
  size?: number
  strokeWidth?: number
  label?: string
  className?: string
}

export function HealthGauge({
  score,
  size = 120,
  strokeWidth = 10,
  label = 'Fleet Health',
  className,
}: HealthGaugeProps) {
  const radius = (size - strokeWidth) / 2
  const circumference = Math.PI * radius // half-circle arc
  const progress = (score / 100) * circumference
  const cx = size / 2
  const cy = size / 2

  // Colour stops for the arc
  const colour =
    score >= 85 ? '#10b981' :
    score >= 70 ? '#22c55e' :
    score >= 50 ? '#eab308' :
    score >= 30 ? '#f97316' :
    '#ef4444'

  return (
    <div className={cn('flex flex-col items-center', className)}>
      <svg width={size} height={size / 2 + strokeWidth} viewBox={`0 0 ${size} ${size / 2 + strokeWidth}`}>
        {/* Background track */}
        <path
          d={`M ${strokeWidth / 2} ${cy} A ${radius} ${radius} 0 0 1 ${size - strokeWidth / 2} ${cy}`}
          fill="none"
          stroke="hsl(var(--border))"
          strokeWidth={strokeWidth}
          strokeLinecap="round"
        />
        {/* Progress arc */}
        <path
          d={`M ${strokeWidth / 2} ${cy} A ${radius} ${radius} 0 0 1 ${size - strokeWidth / 2} ${cy}`}
          fill="none"
          stroke={colour}
          strokeWidth={strokeWidth}
          strokeLinecap="round"
          strokeDasharray={`${progress} ${circumference}`}
          style={{ transition: 'stroke-dasharray 0.8s ease-in-out' }}
        />
        {/* Score text */}
        <text
          x={cx}
          y={cy - 2}
          textAnchor="middle"
          dominantBaseline="middle"
          fontSize={size * 0.22}
          fontWeight="700"
          fill={colour}
        >
          {score.toFixed(0)}
        </text>
      </svg>
      <span className="mt-1 text-xs font-medium text-muted-foreground">{label}</span>
    </div>
  )
}
