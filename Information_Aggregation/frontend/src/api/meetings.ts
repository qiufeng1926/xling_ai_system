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
  transcript: string | null
  summary: string | null
  summary_visual: VisualSummary | null
  summary_visual_status: string | null
  transcript_file?: string | null
  summary_file?: string | null
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
