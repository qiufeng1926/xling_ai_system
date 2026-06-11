import axios from 'axios'
import request, { type ApiResponse, type PageResult } from './request'

export interface MatchRequirements {
  platform?: string
  follower_min?: number
  follower_max?: number
  required_tag_ids?: number[]
  preferred_tag_ids?: number[]
  agency_id?: number
  engagement_rate_min?: number
  keyword?: string
  must_have_contact?: boolean
  limit?: number
}

export interface MatchReasonDetail {
  dimension: string
  score: number
  max_score: number
  note: string
}

export interface MatchReason {
  summary: string
  details: MatchReasonDetail[]
}

export interface MatchInfluencerBrief {
  id: number
  platform: string
  platform_uid: string
  nickname: string | null
  avatar_url: string | null
  follower_count: number
  engagement_rate: number | null
  agency_name: string | null
  tags: string[]
}

export interface MatchResult {
  id: number
  request_id: number
  influencer_id: number
  match_score: number | null
  rank_order: number | null
  reason: MatchReason | null
  is_selected: boolean
  influencer: MatchInfluencerBrief | null
}

export interface MatchRequest {
  id: number
  user_id: number
  title: string | null
  requirements: MatchRequirements
  status: string
  result_count: number | null
  created_at: string
  selected_count: number
}

export interface MatchRequestDetail extends MatchRequest {
  top_results: MatchResult[]
}

export function createMatchRequest(data: { title?: string; requirements: MatchRequirements }) {
  return request.post<any, ApiResponse<MatchRequest>>('/match/requests', data)
}

export function getMatchRequests(params: { page?: number; page_size?: number }) {
  return request.get<any, ApiResponse<PageResult<MatchRequest>>>('/match/requests', { params })
}

export function getMatchRequest(id: number) {
  return request.get<any, ApiResponse<MatchRequestDetail>>(`/match/requests/${id}`)
}

export function getMatchResults(
  id: number,
  params: { page?: number; page_size?: number; selected_only?: boolean }
) {
  return request.get<any, ApiResponse<PageResult<MatchResult>>>(`/match/requests/${id}/results`, {
    params,
  })
}

export function updateMatchSelection(
  id: number,
  data: { result_ids: number[]; selected: boolean }
) {
  return request.put<any, ApiResponse<{ updated: number }>>(`/match/requests/${id}/selection`, data)
}

export function deleteMatchRequest(id: number) {
  return request.delete<any, ApiResponse<null>>(`/match/requests/${id}`)
}

export async function downloadMatchExport(requestId: number, selectedOnly = false) {
  const res = await axios.get(`/api/v1/match/requests/${requestId}/export`, {
    params: { selected_only: selectedOnly },
    responseType: 'blob',
    headers: { Authorization: `Bearer ${localStorage.getItem('token') || ''}` },
  })
  const url = window.URL.createObjectURL(res.data)
  const link = document.createElement('a')
  link.href = url
  link.download = `match_${requestId}.xlsx`
  link.click()
  window.URL.revokeObjectURL(url)
}

export const MATCH_STATUS_MAP: Record<string, { label: string; type: string }> = {
  pending: { label: '等待中', type: 'info' },
  running: { label: '匹配中', type: 'warning' },
  completed: { label: '已完成', type: 'success' },
  failed: { label: '失败', type: 'danger' },
}

export const DIMENSION_LABELS: Record<string, string> = {
  tags: '标签',
  followers: '粉丝量',
  engagement: '互动率',
  agency: '机构',
  profile: '档案完整度',
}
