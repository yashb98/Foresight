import { useQuery } from '@tanstack/react-query'
import { fetchAssets, fetchAssetDetail } from '@/api/endpoints'
import { useAuthStore } from '@/store/auth'
import type { AssetFilters } from '@/api/endpoints'

export function useAssets(filters: AssetFilters = {}) {
  const tenantId = useAuthStore((s) => s.tenantId)

  return useQuery({
    queryKey: ['assets', tenantId, filters],
    queryFn: () => fetchAssets(tenantId!, filters),
    enabled: !!tenantId,
    staleTime: 60_000,
  })
}

export function useAssetDetail(assetId: string | null) {
  const tenantId = useAuthStore((s) => s.tenantId)

  return useQuery({
    queryKey: ['asset-detail', tenantId, assetId],
    queryFn: () => fetchAssetDetail(tenantId!, assetId!),
    enabled: !!tenantId && !!assetId,
  })
}
