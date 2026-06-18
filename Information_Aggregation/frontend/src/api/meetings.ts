import meetingRequest from './meetingRooms'

export interface MeetingListItem {
  id: number
  file_id: string
  user_id: number | null
  meeting_name: string | null
  original_filename: string | null
  meeting_type: string
  transcript_length: number | null
  summary_length: number | null
  created_at: string | null
  status: string
  has_summary: boolean
  has_visual_summary: boolean
  summary_visual_status: string | null
  preview: string
  is_collaborative: boolean
  can_access?: boolean
  access_request_status?: 'pending' | 'approved' | 'rejected' | null
  can_download?: boolean
  download_request_status?: 'pending' | 'approved' | 'rejected' | null
  room_code: string | null
  host_username: string | null
}

export interface MeetingListResponse {
  success: boolean
  total: number
  meetings: MeetingListItem[]
  error?: string
}

export interface VisualSummaryCard {
  title?: string
  icon?: string
  tag?: string | null
  bullets?: string[]
  highlight?: string | null
}

export interface VisualSummarySection {
  id?: string
  title?: string
  theme?: string
  layout?: string
  cards?: VisualSummaryCard[]
}

export interface VisualSummary {
  title?: string
  subtitle?: string | null
  sections?: VisualSummarySection[]
  footer?: {
    contacts?: string[]
    next_steps?: string[]
    core_consensus?: string | null
  }
}

export interface MeetingDetail {
  success: boolean
  file_id: string
  meeting_name?: string | null
  created_at?: string | null
  transcript_length?: number | null
  transcript: string | null
  summary: string | null
  summary_visual: VisualSummary | null
  summary_visual_status: string | null
  transcript_file?: string | null
  summary_file?: string | null
  can_download?: boolean
  error?: string
}

export interface MeetingListQuery {
  start_date?: string
  end_date?: string
  limit?: number
  offset?: number
}

export function listMeetings(params: MeetingListQuery = {}) {
  return meetingRequest.get('/meetings/list', { params }) as Promise<MeetingListResponse>
}

export interface MeetingViewAccessRequest {
  id: number
  user_id: number
  username: string | null
  nickname: string | null
  file_id: string
  meeting_name: string | null
  reason: string | null
  status: string
  reviewer_id: number | null
  reviewer_username: string | null
  reviewer_nickname: string | null
  review_note: string | null
  created_at: string | null
  reviewed_at: string | null
}

export interface MeetingAccessApplyResult {
  success: boolean
  created: MeetingViewAccessRequest[]
  skipped: Array<{ file_id: string; reason: string }>
  message: string
}

export type MeetingPermissionRequest = MeetingViewAccessRequest

export interface MeetingAccessRequestStats {
  success: boolean
  my_pending: number
  pending_for_review: number
  view?: { my_pending: number; pending_for_review: number }
  download?: { my_pending: number; pending_for_review: number }
}

export function applyMeetingViewAccess(fileIds: string[], reason?: string) {
  return meetingRequest.post('/meetings/access-requests', {
    file_ids: fileIds,
    reason,
  }) as Promise<MeetingAccessApplyResult>
}

export function getMyMeetingViewRequests(status?: string) {
  return meetingRequest.get('/meetings/access-requests/mine', {
    params: status ? { status } : undefined,
  }) as Promise<{ success: boolean; requests: MeetingViewAccessRequest[] }>
}

export function getMeetingViewRequestStats() {
  return meetingRequest.get('/meetings/access-requests/stats', {
    silent: true,
  }) as Promise<MeetingAccessRequestStats>
}

export function getPendingMeetingViewRequests(status = 'pending') {
  return meetingRequest.get('/meetings/access-requests/pending', {
    params: { status },
  }) as Promise<{ success: boolean; requests: MeetingViewAccessRequest[] }>
}

export function reviewMeetingViewRequest(
  requestId: number,
  approve: boolean,
  reviewNote?: string
) {
  return meetingRequest.post(`/meetings/access-requests/${requestId}/review`, {
    action: approve ? 'approve' : 'reject',
    review_note: reviewNote,
  }) as Promise<{ success: boolean; request: MeetingViewAccessRequest }>
}

export function applyMeetingDownloadAccess(fileIds: string[], reason?: string) {
  return meetingRequest.post('/meetings/download-requests', {
    file_ids: fileIds,
    reason,
  }) as Promise<MeetingAccessApplyResult>
}

export function getMyMeetingDownloadRequests(status?: string) {
  return meetingRequest.get('/meetings/download-requests/mine', {
    params: status ? { status } : undefined,
  }) as Promise<{ success: boolean; requests: MeetingPermissionRequest[] }>
}

export function getPendingMeetingDownloadRequests(status = 'pending') {
  return meetingRequest.get('/meetings/download-requests/pending', {
    params: { status },
  }) as Promise<{ success: boolean; requests: MeetingPermissionRequest[] }>
}

export function reviewMeetingDownloadRequest(
  requestId: number,
  approve: boolean,
  reviewNote?: string
) {
  return meetingRequest.post(`/meetings/download-requests/${requestId}/review`, {
    action: approve ? 'approve' : 'reject',
    review_note: reviewNote,
  }) as Promise<{ success: boolean; request: MeetingPermissionRequest }>
}

export function batchReviewMeetingPermissionRequests(
  kind: 'view' | 'download',
  requestIds: number[],
  approve: boolean,
  reviewNote?: string
) {
  return meetingRequest.post('/meetings/permission-requests/batch-review', {
    kind,
    request_ids: requestIds,
    action: approve ? 'approve' : 'reject',
    review_note: reviewNote,
  }) as Promise<{
    success: boolean
    reviewed: MeetingPermissionRequest[]
    errors: Array<{ request_id: number; reason: string }>
    message: string
  }>
}

export function deleteMeetingViewRequestRecord(requestId: number) {
  return meetingRequest.delete(`/meetings/access-requests/${requestId}`) as Promise<{
    success: boolean
    message: string
  }>
}

export function deleteMeetingDownloadRequestRecord(requestId: number) {
  return meetingRequest.delete(`/meetings/download-requests/${requestId}`) as Promise<{
    success: boolean
    message: string
  }>
}

export function getMeetingDetail(fileId: string) {
  return meetingRequest.get(`/meetings/${encodeURIComponent(fileId)}`) as Promise<MeetingDetail>
}

export function deleteMeetingRecord(fileId: string) {
  return meetingRequest.delete(`/admin/meetings/${encodeURIComponent(fileId)}`) as Promise<{
    success: boolean
    message: string
  }>
}

function parseFilenameFromDisposition(header: string | null | undefined, fallback: string) {
  if (!header) return fallback
  const utf8Match = header.match(/filename\*=UTF-8''([^;]+)/i)
  if (utf8Match?.[1]) {
    try {
      return decodeURIComponent(utf8Match[1])
    } catch {
      return fallback
    }
  }
  const plainMatch = header.match(/filename="?([^";]+)"?/i)
  return plainMatch?.[1] || fallback
}

function triggerBlobDownload(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  anchor.click()
  URL.revokeObjectURL(url)
}

export async function exportMeetingSummaryDocx(fileId: string) {
  const token = localStorage.getItem('token')
  const resp = await fetch(`/api/meetings/${encodeURIComponent(fileId)}/export/summary`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  })
  if (!resp.ok) {
    const detail = await resp.json().catch(() => ({}))
    throw new Error(typeof detail.detail === 'string' ? detail.detail : '导出 Word 失败')
  }
  const blob = await resp.blob()
  const filename = parseFilenameFromDisposition(resp.headers.get('Content-Disposition'), '会议总结.docx')
  triggerBlobDownload(blob, filename)
}

export async function exportMeetingVisual(fileId: string, format: 'html' | 'json' = 'html') {
  const token = localStorage.getItem('token')
  const resp = await fetch(
    `/api/meetings/${encodeURIComponent(fileId)}/export/visual?format=${format}`,
    { headers: token ? { Authorization: `Bearer ${token}` } : {} }
  )
  if (!resp.ok) {
    const detail = await resp.json().catch(() => ({}))
    throw new Error(typeof detail.detail === 'string' ? detail.detail : '导出图文失败')
  }
  const blob = await resp.blob()
  const ext = format === 'json' ? 'json' : 'html'
  const filename = parseFilenameFromDisposition(
    resp.headers.get('Content-Disposition'),
    `会议图文.${ext}`
  )
  triggerBlobDownload(blob, filename)
}
