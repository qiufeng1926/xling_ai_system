import request, { type ApiResponse, type PageResult } from './request'

export interface OffboardingDocument {
  id: number
  filename: string
  file_size: number
  uploaded_at: string
}

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
  applicant_note: string | null
  handover_confirm_note: string | null
  handover_assigned_at: string | null
  documents_submitted_at: string | null
  handover_confirmed_at: string | null
  documents: OffboardingDocument[]
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

export function getMyHandoverTasks() {
  return request.get<any, ApiResponse<OffboardingRecord[]>>('/offboarding/handover/my')
}

export function getHandoverArchive() {
  return request.get<any, ApiResponse<OffboardingRecord[]>>('/offboarding/handover/archive')
}

export function listOffboarding(params: { page?: number; page_size?: number; status?: string }) {
  return request.get<any, ApiResponse<PageResult<OffboardingRecord>>>('/offboarding', { params })
}

export function getOffboarding(recordId: number) {
  return request.get<any, ApiResponse<OffboardingRecord>>(`/offboarding/${recordId}`)
}

export function assignHandover(recordId: number, handover_user_id: number) {
  return request.post<any, ApiResponse<OffboardingRecord>>(`/offboarding/${recordId}/assign-handover`, {
    handover_user_id,
  })
}

export function submitOffboardingDocuments(recordId: number, files: File[], note?: string) {
  const form = new FormData()
  files.forEach((f) => form.append('files', f))
  if (note) form.append('note', note)
  return request.post<any, ApiResponse<OffboardingRecord>>(`/offboarding/${recordId}/submit-documents`, form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

export function confirmHandover(recordId: number, note?: string) {
  return request.post<any, ApiResponse<OffboardingRecord>>(`/offboarding/${recordId}/confirm-handover`, {
    note,
  })
}

export function approveOffboarding(recordId: number) {
  return request.post<any, ApiResponse<OffboardingRecord>>(`/offboarding/${recordId}/approve`)
}

export function cancelOffboarding(recordId: number) {
  return request.post<any, ApiResponse<OffboardingRecord>>(`/offboarding/${recordId}/cancel`)
}

export async function downloadOffboardingDocument(docId: number, filename: string) {
  const baseURL = import.meta.env.VITE_API_BASE_URL || '/api/v1'
  const token = localStorage.getItem('token')
  const res = await fetch(`${baseURL}/offboarding/documents/${docId}/download`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  })
  if (!res.ok) {
    let msg = '下载失败'
    try {
      const data = await res.json()
      msg = data.detail || data.message || msg
    } catch {
      /* ignore non-json error body */
    }
    throw new Error(typeof msg === 'string' ? msg : '下载失败')
  }
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

export function rehireUser(userId: number) {
  return request.post<any, ApiResponse<{ id: number; username: string; account_status: string }>>(
    `/offboarding/rehire/${userId}`
  )
}

export const OFFBOARDING_STATUS_LABELS: Record<string, string> = {
  pending: '待指定交接人',
  awaiting_documents: '待上传交接文档',
  awaiting_handover_confirm: '待交接人确认',
  awaiting_final_approval: '待超管批准',
  processing: '封存执行中',
  completed: '已完成',
  cancelled: '已取消',
  failed: '执行失败',
}
