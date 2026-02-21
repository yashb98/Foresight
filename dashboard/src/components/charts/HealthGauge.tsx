/**
 * HealthGauge — SVG circular gauge for fleet/asset health scores (0–100)
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
  size = 160,
  strokeWidth = 12,
  label,
  className,
}: HealthGaugeProps) {
  const radius = (size - strokeWidth) / 2
  const circumference = 2 * Math.PI * radius
  const normalizedScore = Math.min(100, Math.max(0, score))
  const offset = circumference - (normalizedScore / 100) * circumference

  // Color based on score
  const getColor = (score: number) => {
    if (score >= 85) return 'stroke-emerald-400'
    if (score >= 70) return 'stroke-green-400'
    if (score >= 50) return 'stroke-yellow-400'
    if (score >= 30) return 'stroke-orange-400'
    return 'stroke-red-400'
  }

  return (
    <div className={cn('relative flex flex-col items-center', className)}>
      <div className="relative" style={{ width: size, height: size }}>
        <svg
          width={size}
          height={size}
          viewBox={`0 0 ${size} ${size}`}
          className="transform -rotate-90"
        >
          {/* Background circle */}
          <circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            fill="none"
            className="stroke-muted/30"
            strokeWidth={strokeWidth}
          />
          {/* Progress circle */}
          <circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            fill="none"
            className={cn('transition-all duration-1000 ease-out', getColor(normalizedScore))}
            strokeWidth={strokeWidth}
            strokeLinecap="round"
            strokeDasharray={circumference}
            strokeDashoffset={offset}
          />
        </svg>
        {/* Center content */}
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className={cn('text-4xl font-bold', getColor(normalizedScore).replace('stroke-', 'text-'))}>
            {normalizedScore.toFixed(1)}
          </span>
          {label && <span className="text-xs text-muted-foreground mt-1">{label}</span>}
        </div>
      </div>
    </div>
  )
}
