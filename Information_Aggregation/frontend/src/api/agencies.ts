import request, { type ApiResponse, type PageResult } from './request'

export interface Agency {
  id: number
  name: string
  platform: string | null
  contact_person: string | null
  contact_phone: string | null
  contact_wechat: string | null
  policy_notes: string | null
  cooperation_terms: Record<string, unknown> | null
  created_at: string
  updated_at: string
  influencer_count?: number
  avg_follower_count?: number
  total_followers?: number
}

export interface AgencyInfluencer {
  id: number
  nickname: string | null
  platform: string
  platform_uid: string
  follower_count: number
  source: string | null
}

export function getAgencies(params: {
  page?: number
  page_size?: number
  keyword?: string
  platform?: string
}) {
  return request.get<any, ApiResponse<PageResult<Agency>>>('/agencies', { params })
}

export function getAgencyOptions() {
  return request.get<any, ApiResponse<Agency[]>>('/agencies/options')
}

export function getAgency(id: number) {
  return request.get<any, ApiResponse<Agency>>(`/agencies/${id}`)
}

export function getAgencyInfluencers(id: number, params: { page?: number; page_size?: number }) {
  return request.get<any, ApiResponse<PageResult<AgencyInfluencer>>>(
    `/agencies/${id}/influencers`,
    { params }
  )
}

export function createAgency(data: Partial<Agency>) {
  return request.post<any, ApiResponse<Agency>>('/agencies', data)
}

export function updateAgency(id: number, data: Partial<Agency>) {
  return request.put<any, ApiResponse<Agency>>(`/agencies/${id}`, data)
}

export function deleteAgency(id: number) {
  return request.delete<any, ApiResponse<null>>(`/agencies/${id}`)
}

export const AGENCY_PLATFORM_OPTIONS = [
  { label: '抖音', value: 'douyin' },
  { label: '小红书', value: 'xiaohongshu' },
  { label: '快手', value: 'kuaishou' },
  { label: '全平台', value: 'all' },
]

export function formatAgencyPlatform(value: string | null) {
  if (!value) return '-'
  if (value === 'all') return '全平台'
  return AGENCY_PLATFORM_OPTIONS.find((p) => p.value === value)?.label || value
}

export function formatFollowers(count: number) {
  if (count >= 10000) return `${(count / 10000).toFixed(1)}万`
  return count.toString()
}
