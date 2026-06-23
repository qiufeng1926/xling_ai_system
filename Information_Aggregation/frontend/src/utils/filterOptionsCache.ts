import request, { type ApiResponse } from '@/api/request'
import type { FilterGroup } from '@/constants/collectionFilters'

const cache = new Map<string, FilterGroup[]>()

export function getCachedFilterOptions(platform: string): FilterGroup[] | undefined {
  return cache.get(platform)
}

export async function prefetchFilterOptions(platform = 'douyin'): Promise<FilterGroup[]> {
  const key = platform || 'douyin'
  const cached = cache.get(key)
  if (cached) return cached

  const res = await request.get<any, ApiResponse<{ groups: FilterGroup[] }>>(
    '/collection/filter-options',
    { params: { platform: key } }
  )
  cache.set(key, res.data.groups)
  return res.data.groups
}
