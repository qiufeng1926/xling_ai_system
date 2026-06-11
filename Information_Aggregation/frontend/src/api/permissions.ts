import request, { type ApiResponse, type PageResult } from './request'

export interface AccessRequest {
  id: number
  user_id: number
  request_type: string
  request_type_label?: string
  status: string
  reason: string | null
  reviewer_id: number | null
  review_note: string | null
  created_at: string
  reviewed_at: string | null
  username: string | null
  nickname: string | null
  reviewer_username: string | null
  reviewer_nickname: string | null
}

export interface RequestTypeOption {
  value: string
  label: string
}

export interface AccessRequestStats {
  my_pending: number
  my_total: number
  pending_for_review: number
  can_review: boolean
}

export function getApplicableRequestTypes() {
  return request.get<any, ApiResponse<RequestTypeOption[]>>('/permissions/access-requests/types')
}

export function getAccessRequestStats() {
  return request.get<any, ApiResponse<AccessRequestStats>>('/permissions/access-requests/stats')
}

export function submitAccessRequest(request_type: string, reason?: string) {
  return request.post<any, ApiResponse<AccessRequest>>('/permissions/access-requests', {
    request_type,
    reason,
  })
}

export function getAccessRequests(params: {
  status?: string
  request_type?: string
  scope?: 'mine' | 'review'
  page?: number
  page_size?: number
}) {
  return request.get<any, ApiResponse<PageResult<AccessRequest>>>('/permissions/access-requests', {
    params,
  })
}

export function reviewAccessRequest(requestId: number, approve: boolean, review_note?: string) {
  return request.post<any, ApiResponse<AccessRequest>>(
    `/permissions/access-requests/${requestId}/review`,
    { approve, review_note }
  )
}

export function revokeLibraryAccess(userId: number) {
  return request.post<any, ApiResponse<{ user_id: number; view_library: boolean }>>(
    `/permissions/users/${userId}/revoke-library`
  )
}

export function getPermissionSettings() {
  return request.get<any, ApiResponse<{ block_upper_role_tasks: boolean }>>('/permissions/settings')
}

export function updatePermissionSettings(block_upper_role_tasks: boolean) {
  return request.put<any, ApiResponse<{ block_upper_role_tasks: boolean }>>(
    '/permissions/settings',
    null,
    { params: { block_upper_role_tasks } }
  )
}

export const PERMISSION_LABELS: Record<string, string> = {
  view_library: '查阅达人库',
  view_all_meetings: '查阅全部会议',
  view_root_meetings: '查阅超管会议',
  view_all_root_meetings: '查阅全部超管会议',
  download_meetings: '会议导出/下载',
  approve_meeting_download: '审批会议下载',
}

export const REQUEST_TYPE_LABELS: Record<string, string> = {
  view_library: '查阅达人库',
  view_all_meetings: '查阅全部会议',
  download_meetings: '会议导出/下载',
  view_root_meetings: '查阅超管会议（限3天）',
  promote_admin: '升级为管理员',
}
