import request, { type ApiResponse, type PageResult } from './request'

export interface OffboardingRecord {
  id: number
  user_id: number
  operator_id: number | null
  handover_user_id: number | null
  status: string
  reason: string | null
  last_work_day: string | null
  content_snapshot: Record<string, unknown> | null
  error_message: string | null
  created_at: string
  started_at: string | null
  completed_at: string | null
  expires_at: string | null
  user_username: string | null
  user_nickname: string | null
  handover_username: string | null
  handover_nickname: string | null
}

export function applyOffboarding(data: { reason?: string; last_work_day?: string }) {
  return request.post<any, ApiResponse<OffboardingRecord>>('/offboarding/apply', data)
}

export function getMyOffboarding() {
  return request.get<any, ApiResponse<OffboardingRecord | null>>('/offboarding/my')
}

export function listOffboarding(params: { page?: number; page_size?: number; status?: string }) {
  return request.get<any, ApiResponse<PageResult<OffboardingRecord>>>('/offboarding', { params })
}

export function getOffboarding(recordId: number) {
  return request.get<any, ApiResponse<OffboardingRecord>>(`/offboarding/${recordId}`)
}

export function completeOffboarding(recordId: number, handover_user_id: number) {
  return request.post<any, ApiResponse<OffboardingRecord>>(`/offboarding/${recordId}/complete`, {
    handover_user_id,
  })
}

export function cancelOffboarding(recordId: number) {
  return request.post<any, ApiResponse<OffboardingRecord>>(`/offboarding/${recordId}/cancel`)
}

export function rehireUser(userId: number) {
  return request.post<any, ApiResponse<{ id: number; username: string; account_status: string }>>(
    `/offboarding/rehire/${userId}`
  )
}
