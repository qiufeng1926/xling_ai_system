import request, { type ApiResponse, type PageResult } from './request'

export interface Influencer {
  id: number
  platform: string
  platform_uid: string
  nickname: string | null
  avatar_url: string | null
  profile_url: string | null
  agency_id: number | null
  agency_name?: string | null
  follower_count: number
  engagement_rate: number | null
  source: string | null
  status: number
  extra_data: Record<string, unknown> | null
  created_at: string
  updated_at: string
  tags: { id: number; name: string; category: string | null }[]
  profile: InfluencerProfile | null
}

export interface InfluencerProfile {
  contact_info: Record<string, unknown> | null
  shooting_style: string[] | null
  persona_traits: string[] | null
  cooperation_policy: string | null
  internal_notes: string | null
  last_contact_date: string | null
}

export interface InfluencerQuery {
  page?: number
  page_size?: number
  platform?: string
  source?: string
  keyword?: string
  follower_min?: number
  follower_max?: number
  tag_ids?: number[]
  agency_id?: number
  status?: number
}

export interface ImportResult {
  total: number
  success: number
  failed: number
  errors: string[]
}

export function getInfluencers(params: InfluencerQuery) {
  return request.get<any, ApiResponse<PageResult<Influencer>>>('/influencers', {
    params,
    paramsSerializer: { indexes: null },
  })
}

export function getInfluencer(id: number) {
  return request.get<any, ApiResponse<Influencer>>(`/influencers/${id}`)
}

export function createInfluencer(data: Partial<Influencer>) {
  return request.post<any, ApiResponse<Influencer>>('/influencers', data)
}

export function updateInfluencer(id: number, data: Partial<Influencer>) {
  return request.put<any, ApiResponse<Influencer>>(`/influencers/${id}`, data)
}

export function deleteInfluencer(id: number) {
  return request.delete<any, ApiResponse<null>>(`/influencers/${id}`)
}

export function importInfluencers(file: File) {
  const form = new FormData()
  form.append('file', file)
  return request.post<any, ApiResponse<ImportResult>>('/influencers/import', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

export const PLATFORM_OPTIONS = [
  { label: '抖音', value: 'douyin' },
  { label: '小红书', value: 'xiaohongshu' },
  { label: '快手', value: 'kuaishou' },
  { label: '微信', value: 'wechat' },
]

export const SOURCE_OPTIONS = [
  { label: '星图', value: 'xingtu' },
  { label: '蒲公英', value: 'pugongying' },
  { label: '互选', value: 'huxuan' },
  { label: '手动录入', value: 'manual' },
]

export function formatPlatform(value: string) {
  return PLATFORM_OPTIONS.find((item) => item.value === value)?.label || value
}

export function formatSource(value: string | null) {
  if (!value) return '-'
  return SOURCE_OPTIONS.find((item) => item.value === value)?.label || value
}

export function formatFollowers(count: number) {
  if (count >= 10000) {
    return `${(count / 10000).toFixed(1)}万`
  }
  return count.toString()
}
