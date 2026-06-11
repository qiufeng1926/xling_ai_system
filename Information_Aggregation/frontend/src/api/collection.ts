import request, { type ApiResponse, type PageResult } from './request'
import type { CollectionFilters } from '@/constants/collectionFilters'

export type { CollectionFilters }

export interface CollectionTask {
  id: number
  user_id: number
  title: string | null
  platform: string
  keyword: string
  filters: CollectionFilters | null
  status: string
  result_count: number
  approved_count: number
  error_message: string | null
  retry_count?: number
  error_category?: string | null
  filter_summary?: string[]
  created_at: string
  started_at: string | null
  completed_at: string | null
}

export interface CollectionTaskDetail extends CollectionTask {
  duration_seconds: number | null
  queue_size: number
  queue_position: number | null
  running_task_id: number | null
  sample_items: CollectedInfluencer[]
}

export interface CollectedInfluencer {
  id: number
  task_id: number
  platform: string
  platform_uid: string
  nickname: string | null
  avatar_url: string | null
  profile_url: string | null
  follower_count: number
  engagement_rate: number | null
  avg_views: number | null
  source: string | null
  matched_tags: string[] | null
  match_score: number | null
  extra_data: Record<string, unknown> | null
  mcn_name?: string | null
  short_id?: string | null
  city?: string | null
  creator_type?: string | null
  expected_play_count?: number | null
  completion_rate?: number | null
  deal_rate?: number | null
  contact_phone?: string | null
  contact_wechat?: string | null
  content_styles?: string[]
  xingtu_homepage?: string | null
  douyin_homepage?: string | null
  xhs_homepage?: string | null
  pgy_homepage?: string | null
  review_status: string
  influencer_id: number | null
  in_library?: boolean
  existing_influencer_id?: number | null
  created_at: string
  reviewed_at?: string | null
}

export interface CollectionStats {
  pending_review: number
  today_tasks: number
  today_collected: number
  success_rate: number
  running_task_id: number | null
  queued_tasks: number
  queue_size: number
}

export interface ReviewResult {
  approved: number
  rejected: number
  skipped: number
}

export function createCollectionTask(data: {
  platform: string
  keyword: string
  title?: string
  filters?: CollectionFilters
}) {
  return request.post<any, ApiResponse<CollectionTask>>('/collection/tasks', data)
}

export function getCollectionTasks(params: { page?: number; page_size?: number }) {
  return request.get<any, ApiResponse<PageResult<CollectionTask>>>('/collection/tasks', { params })
}

export function getCollectionTaskDetail(taskId: number) {
  return request.get<any, ApiResponse<CollectionTaskDetail>>(`/collection/tasks/${taskId}/detail`)
}

export interface PlatformSessionStatus {
  platform: string
  label: string
  login_url: string
  storage_path: string
  mode: string
  ready: boolean
  storage_configured: boolean
  storage_updated_at: string | null
  storage_age_days: number | null
  cookie_count: number
  login_warning: string
  hint: string
  playwright_installed: boolean
  chromium_ready: boolean
  chromium_error: string
  python: string
  login_in_progress: boolean
  login_error: string | null
  save_session_command?: string
}

export function getCollectionSessions() {
  return request.get<any, ApiResponse<PlatformSessionStatus[]>>('/collection/sessions')
}

export function startPlatformLogin(platform: string) {
  return request.post<any, ApiResponse<PlatformSessionStatus>>(
    `/collection/sessions/${platform}/login/start`
  )
}

export function savePlatformLogin(platform: string) {
  return request.post<any, ApiResponse<PlatformSessionStatus>>(
    `/collection/sessions/${platform}/login/save`
  )
}

export function cancelPlatformLogin(platform: string) {
  return request.post<any, ApiResponse<PlatformSessionStatus>>(
    `/collection/sessions/${platform}/login/cancel`
  )
}

export function uploadPlatformSession(platform: string, file: File) {
  const form = new FormData()
  form.append('file', file)
  return request.post<any, ApiResponse<PlatformSessionStatus>>(
    `/collection/sessions/${platform}/upload`,
    form,
    { headers: { 'Content-Type': 'multipart/form-data' } }
  )
}

export function deletePlatformSession(platform: string) {
  return request.delete<any, ApiResponse<PlatformSessionStatus>>(`/collection/sessions/${platform}`)
}

export function importPlatformCookies(platform: string, content: string) {
  return request.post<any, ApiResponse<PlatformSessionStatus>>(
    `/collection/sessions/${platform}/import`,
    { content }
  )
}

export function getCollectionStats() {
  return request.get<any, ApiResponse<CollectionStats>>('/collection/stats')
}

export function retryCollectionTask(taskId: number) {
  return request.post<any, ApiResponse<CollectionTask>>(`/collection/tasks/${taskId}/retry`)
}

export function getPendingReview(params: {
  task_id?: number
  page?: number
  page_size?: number
}) {
  return request.get<any, ApiResponse<PageResult<CollectedInfluencer>>>('/collection/pending', { params })
}

export function getReviewedItems(params: {
  review_status: 'approved' | 'rejected'
  task_id?: number
  page?: number
  page_size?: number
}) {
  return request.get<any, ApiResponse<PageResult<CollectedInfluencer>>>('/collection/reviewed', { params })
}

export function approveCollected(ids: number[]) {
  return request.post<any, ApiResponse<ReviewResult>>('/collection/approve', { ids })
}

export function rejectCollected(ids: number[]) {
  return request.post<any, ApiResponse<ReviewResult>>('/collection/reject', { ids })
}

export const TASK_STATUS_MAP: Record<string, { label: string; type: string }> = {
  pending: { label: '排队中', type: 'info' },
  running: { label: '采集中', type: 'warning' },
  completed: { label: '已完成', type: 'success' },
  failed: { label: '失败', type: 'danger' },
}

export const ERROR_CATEGORY_MAP: Record<string, string> = {
  login_expired: '登录失效',
  timeout: '采集超时',
  no_results: '无匹配结果',
  network: '网络异常',
  unknown: '未知错误',
}

export const COLLECTION_PLATFORM_OPTIONS = [
  { label: '抖音', value: 'douyin' },
  { label: '小红书', value: 'xiaohongshu' },
]

export const PLATFORM_OPTIONS = COLLECTION_PLATFORM_OPTIONS

export function formatPlatform(value: string) {
  return PLATFORM_OPTIONS.find((p) => p.value === value)?.label || value
}

export function formatFollowers(count: number | null | undefined) {
  if (count == null) return '-'
  if (count >= 10000) return `${(count / 10000).toFixed(1)}万`
  return String(count)
}

export function formatDuration(seconds: number | null | undefined) {
  if (!seconds) return '-'
  if (seconds < 60) return `${seconds} 秒`
  return `${Math.floor(seconds / 60)} 分 ${seconds % 60} 秒`
}
