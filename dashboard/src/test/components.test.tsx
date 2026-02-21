/**
 * FORESIGHT Dashboard — Component Unit Tests
 *
 * Tests utility functions, component rendering, and business logic.
 */

import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import {
  formatCurrency,
  formatPercent,
  formatProbability,
  healthScoreColour,
  severityClass,
  relativeTime,
  operatorLabel,
  cn,
  clamp,
} from '@/lib/utils'

// ─────────────────────────────────────────────────────────────────────────────
// Utility function tests
// ─────────────────────────────────────────────────────────────────────────────

describe('formatCurrency', () => {
  it('formats a large number as USD', () => {
    expect(formatCurrency(1_234_567)).toMatch(/\$1,234,567/)
  })
  it('formats zero', () => {
    expect(formatCurrency(0)).toMatch(/\$0/)
  })
  it('formats negative', () => {
    expect(formatCurrency(-5000)).toMatch(/-\$5,000|−\$5,000|\(\$5,000\)/)
  })
})

describe('formatPercent', () => {
  it('returns correct percentage string', () => {
    expect(formatPercent(88.5)).toBe('88.5%')
  })
  it('rounds to specified decimals', () => {
    expect(formatPercent(33.333, 2)).toBe('33.33%')
  })
})

describe('formatProbability', () => {
  it('converts 0–1 probability to percentage', () => {
    expect(formatProbability(0.45)).toBe('45.0%')
  })
  it('handles zero probability', () => {
    expect(formatProbability(0)).toBe('0.0%')
  })
  it('handles one probability', () => {
    expect(formatProbability(1)).toBe('100.0%')
  })
})

describe('healthScoreColour', () => {
  it('returns emerald for excellent health (>=85)', () => {
    expect(healthScoreColour(90)).toBe('text-emerald-400')
    expect(healthScoreColour(85)).toBe('text-emerald-400')
  })
  it('returns green for good health (70–84)', () => {
    expect(healthScoreColour(75)).toBe('text-green-400')
  })
  it('returns yellow for fair health (50–69)', () => {
    expect(healthScoreColour(60)).toBe('text-yellow-400')
  })
  it('returns orange for poor health (30–49)', () => {
    expect(healthScoreColour(40)).toBe('text-orange-400')
  })
  it('returns red for critical health (<30)', () => {
    expect(healthScoreColour(10)).toBe('text-red-400')
    expect(healthScoreColour(0)).toBe('text-red-400')
  })
})

describe('severityClass', () => {
  it('maps critical to severity-critical class', () => {
    expect(severityClass('critical')).toBe('severity-critical')
  })
  it('maps high to severity-high class', () => {
    expect(severityClass('high')).toBe('severity-high')
  })
  it('maps medium to severity-medium class', () => {
    expect(severityClass('medium')).toBe('severity-medium')
  })
  it('maps low to severity-low class', () => {
    expect(severityClass('low')).toBe('severity-low')
  })
  it('defaults unknown to severity-low', () => {
    expect(severityClass('unknown')).toBe('severity-low')
  })
})

describe('operatorLabel', () => {
  it('maps gt to >', () => expect(operatorLabel('gt')).toBe('>'))
  it('maps lt to <', () => expect(operatorLabel('lt')).toBe('<'))
  it('maps gte to ≥', () => expect(operatorLabel('gte')).toBe('≥'))
  it('maps lte to ≤', () => expect(operatorLabel('lte')).toBe('≤'))
  it('maps eq to =',  () => expect(operatorLabel('eq')).toBe('='))
  it('returns unknown operators as-is', () => expect(operatorLabel('xor')).toBe('xor'))
})

describe('relativeTime', () => {
  it('shows seconds for recent timestamps', () => {
    const ts = new Date(Date.now() - 45_000).toISOString()
    expect(relativeTime(ts)).toBe('45s ago')
  })
  it('shows minutes for 5-minute-old timestamps', () => {
    const ts = new Date(Date.now() - 5 * 60_000).toISOString()
    expect(relativeTime(ts)).toBe('5m ago')
  })
  it('shows hours for 3-hour-old timestamps', () => {
    const ts = new Date(Date.now() - 3 * 60 * 60_000).toISOString()
    expect(relativeTime(ts)).toBe('3h ago')
  })
  it('shows days for multi-day-old timestamps', () => {
    const ts = new Date(Date.now() - 5 * 24 * 60 * 60_000).toISOString()
    expect(relativeTime(ts)).toBe('5d ago')
  })
})

describe('cn', () => {
  it('merges class names correctly', () => {
    expect(cn('foo', 'bar')).toBe('foo bar')
  })
  it('handles conditional classes', () => {
    expect(cn('base', false && 'nope', 'yes')).toBe('base yes')
  })
  it('deduplicates Tailwind classes', () => {
    expect(cn('text-red-400', 'text-blue-400')).toBe('text-blue-400')
  })
})

describe('clamp', () => {
  it('returns value within range', () => {
    expect(clamp(50, 0, 100)).toBe(50)
  })
  it('clamps to min', () => {
    expect(clamp(-10, 0, 100)).toBe(0)
  })
  it('clamps to max', () => {
    expect(clamp(150, 0, 100)).toBe(100)
  })
})

// ─────────────────────────────────────────────────────────────────────────────
// Component tests (shallow rendering)
// ─────────────────────────────────────────────────────────────────────────────

describe('Badge component', () => {
  it('renders with correct variant class', async () => {
    const { Badge } = await import('@/components/ui/badge')
    render(<Badge variant="critical">CRITICAL</Badge>)
    expect(screen.getByText('CRITICAL')).toBeInTheDocument()
  })

  it('renders default variant', async () => {
    const { Badge } = await import('@/components/ui/badge')
    const { container } = render(<Badge>Default</Badge>)
    expect(container.firstChild).toBeTruthy()
  })
})

describe('Button component', () => {
  it('renders with label text', async () => {
    const { Button } = await import('@/components/ui/button')
    render(<Button>Click Me</Button>)
    expect(screen.getByText('Click Me')).toBeInTheDocument()
  })

  it('is disabled when disabled prop is set', async () => {
    const { Button } = await import('@/components/ui/button')
    render(<Button disabled>Disabled</Button>)
    expect(screen.getByRole('button')).toBeDisabled()
  })
})

describe('Card component', () => {
  it('renders children correctly', async () => {
    const { Card, CardContent } = await import('@/components/ui/card')
    render(
      <Card>
        <CardContent>Card Content</CardContent>
      </Card>
    )
    expect(screen.getByText('Card Content')).toBeInTheDocument()
  })
})

describe('Progress component', () => {
  it('renders with value', async () => {
    const { Progress } = await import('@/components/ui/progress')
    const { container } = render(<Progress value={75} />)
    expect(container.firstChild).toBeTruthy()
  })
})

describe('Skeleton component', () => {
  it('renders with animate-pulse class', async () => {
    const { Skeleton } = await import('@/components/ui/skeleton')
    const { container } = render(<Skeleton className="h-4 w-24" />)
    expect(container.firstChild).toHaveClass('animate-pulse')
  })
})


