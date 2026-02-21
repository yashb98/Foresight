import { useQuery } from '@tanstack/react-query'
import { fetchAssets, fetchAssetDetail } from '@/api/endpoints'
import type { AssetFilters } from '@/api/endpoints'

export function useAssets(filters: AssetFilters = {}) {
  return useQuery({
    queryKey: ['assets', filters],
    queryFn: () => fetchAssets(filters),
    staleTime: 60_000,
  })
}

export function useAssetDetail(assetId: string | null) {
  return useQuery({
    queryKey: ['asset-detail', assetId],
    queryFn: () => fetchAssetDetail(assetId!),
    enabled: !!assetId,
  })
}
