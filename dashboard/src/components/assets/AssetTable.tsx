/**
 * AssetTable — paginated, filterable asset fleet table
 */

import { useState } from 'react'
import { Search, ChevronRight } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { Progress } from '@/components/ui/progress'
import { useAssets } from '@/hooks/useAssets'
import { formatPercent, healthScoreColour } from '@/lib/utils'
import type { Asset } from '@/types'

const CRITICALITY_VARIANT: Record<string, 'critical' | 'high' | 'medium' | 'low'> = {
  critical: 'critical',
  high: 'high',
  medium: 'medium',
  low: 'low',
}

export function AssetTable() {
  const [search, setSearch] = useState('')
  const [assetTypeFilter, setAssetTypeFilter] = useState<string>('all')

  const { data, isLoading } = useAssets()
  const assets: Asset[] = data?.assets ?? []

  const filtered = assets.filter((a) => {
    const matchSearch =
      !search ||
      a.name.toLowerCase().includes(search.toLowerCase()) ||
      a.asset_type.toLowerCase().includes(search.toLowerCase()) ||
      (a.location ?? '').toLowerCase().includes(search.toLowerCase())
    const matchType = assetTypeFilter === 'all' || a.asset_type === assetTypeFilter
    return matchSearch && matchType
  })

  const assetTypes = ['all', ...Array.from(new Set(assets.map((a) => a.asset_type)))]

  return (
    <div className="space-y-4">
      {/* Filters */}
      <div className="flex gap-3 flex-wrap items-center">
        <div className="relative flex-1 min-w-[200px]">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Search assets..."
            className="pl-9"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <div className="flex gap-1">
          {assetTypes.slice(0, 6).map((type) => (
            <button
              key={type}
              onClick={() => setAssetTypeFilter(type)}
              className={`px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
                assetTypeFilter === type
                  ? 'bg-primary text-primary-foreground'
                  : 'bg-muted text-muted-foreground hover:bg-secondary'
              }`}
            >
              {type === 'all' ? 'All Types' : type.charAt(0).toUpperCase() + type.slice(1)}
            </button>
          ))}
        </div>
      </div>

      {/* Count */}
      <p className="text-xs text-muted-foreground">
        Showing <strong>{filtered.length}</strong> of <strong>{assets.length}</strong> assets
      </p>

      {/* Table */}
      <div className="rounded-lg border border-border overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border bg-muted/30">
              <th className="text-left py-3 px-4 text-xs font-medium text-muted-foreground uppercase tracking-wider">Asset</th>
              <th className="text-left py-3 px-4 text-xs font-medium text-muted-foreground uppercase tracking-wider">Type</th>
              <th className="text-left py-3 px-4 text-xs font-medium text-muted-foreground uppercase tracking-wider">Location</th>
              <th className="text-left py-3 px-4 text-xs font-medium text-muted-foreground uppercase tracking-wider">Criticality</th>
              <th className="text-left py-3 px-4 text-xs font-medium text-muted-foreground uppercase tracking-wider w-40">Health Score</th>
              <th className="text-left py-3 px-4 text-xs font-medium text-muted-foreground uppercase tracking-wider">Failure 30d</th>
              <th className="py-3 px-4" />
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {isLoading &&
              Array.from({ length: 8 }).map((_, i) => (
                <tr key={i}>
                  {Array.from({ length: 7 }).map((_, j) => (
                    <td key={j} className="py-3 px-4">
                      <Skeleton className="h-4 w-full" />
                    </td>
                  ))}
                </tr>
              ))}

            {!isLoading &&
              filtered.map((asset) => {
                const health = asset.current_health
                return (
                  <tr key={asset.asset_id} className="hover:bg-muted/20 transition-colors">
                    <td className="py-3 px-4">
                      <div className="font-medium text-foreground">{asset.name}</div>
                      <div className="text-xs text-muted-foreground font-mono">
                        {asset.asset_id.slice(0, 12)}…
                      </div>
                    </td>
                    <td className="py-3 px-4 text-muted-foreground capitalize">{asset.asset_type}</td>
                    <td className="py-3 px-4 text-muted-foreground">{asset.location ?? '—'}</td>
                    <td className="py-3 px-4">
                      <Badge variant={CRITICALITY_VARIANT[asset.criticality] ?? 'low'}>
                        {asset.criticality}
                      </Badge>
                    </td>
                    <td className="py-3 px-4">
                      {health?.health_score != null ? (
                        <div className="space-y-1">
                          <div className="flex justify-between text-xs">
                            <span className={healthScoreColour(health.health_score)}>
                              {health.health_score.toFixed(1)}
                            </span>
                            <span className="text-muted-foreground capitalize">
                              {health.risk_level}
                            </span>
                          </div>
                          <Progress value={health.health_score} className="h-1.5" />
                        </div>
                      ) : (
                        <span className="text-muted-foreground text-xs">No data</span>
                      )}
                    </td>
                    <td className="py-3 px-4">
                      {health?.failure_prob_30d != null ? (
                        <span className={health.failure_prob_30d > 0.4 ? 'text-red-400' : 'text-muted-foreground'}>
                          {formatPercent(health.failure_prob_30d * 100)}
                        </span>
                      ) : (
                        <span className="text-muted-foreground">—</span>
                      )}
                    </td>
                    <td className="py-3 px-4">
                      <Button variant="ghost" size="sm" className="h-7">
                        <ChevronRight className="h-4 w-4" />
                      </Button>
                    </td>
                  </tr>
                )
              })}
          </tbody>
        </table>

        {!isLoading && filtered.length === 0 && (
          <div className="py-12 text-center text-muted-foreground text-sm">
            No assets match your search criteria.
          </div>
        )}
      </div>
    </div>
  )
}
