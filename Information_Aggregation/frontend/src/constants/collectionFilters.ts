export interface FilterOption {
  label: string
  value: string
}

export interface FilterField {
  key: string
  label: string
  type: 'single' | 'multi' | 'number' | 'range'
  options?: FilterOption[]
  placeholder?: string
  unit?: string
  step?: number
  min?: number
  max?: number
  default?: number
}

export interface FilterGroup {
  key: string
  label: string
  fields: FilterField[]
}

export interface CollectionFilters {
  cooperation_purpose?: string
  incentive_method?: string
  cooperation_form?: string
  creator_level?: string
  creator_type?: string
  follower_tier?: string
  content_theme?: string
  creator_gender?: string
  follower_gender?: string
  follower_age?: string
  verified?: string
  follower_min?: number
  follower_max?: number
  avg_views_min?: number
  interaction_rate_min?: number
  quote_duration?: string
  quote_min?: number
  quote_max?: number
  expected_play_min?: number
  expected_cpm_max?: number
  expected_cpe_max?: number
  completion_rate_min?: number
  theme_tags?: string[]
  limit?: number
}

export function createEmptyFilters(): CollectionFilters {
  return { limit: 30 }
}

export function buildFiltersPayload(form: CollectionFilters): CollectionFilters {
  const payload: CollectionFilters = {}
  for (const [key, value] of Object.entries(form)) {
    if (value === undefined || value === null || value === '') continue
    if (Array.isArray(value) && value.length === 0) continue
    ;(payload as Record<string, unknown>)[key] = value
  }
  if (!payload.limit) payload.limit = 30
  return payload
}
