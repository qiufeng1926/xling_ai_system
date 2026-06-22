import request, { type ApiResponse } from './request'

export interface WeComApprovalConfig {
  configured: boolean
  corp_id: string | null
  default_template_id: string | null
}

export interface WeComApprovalListItem {
  sp_no: string
  sp_name?: string | null
  sp_status?: number | null
  sp_status_label?: string | null
  template_id?: string | null
  apply_time?: number | null
  applyer_userid?: string | null
}

export interface WeComApprovalListResult {
  sp_list: WeComApprovalListItem[]
  next_cursor: string | null
  has_more: boolean
}

export interface WeComApprovalDetail {
  sp_no: string
  sp_name?: string | null
  sp_status?: number | null
  sp_status_label?: string | null
  template_id?: string | null
  apply_time?: number | null
  applyer?: Record<string, unknown> | null
  apply_data?: { contents?: Array<Record<string, unknown>> } | null
  sp_record?: unknown[] | null
  notifyer?: unknown[] | null
  comments?: unknown[] | null
  process_list?: Record<string, unknown> | null
}

export interface WeComApprovalTemplate {
  template_id: string
  template_names: Array<{ text?: string; lang?: string }>
  template_content?: {
    controls?: Array<{
      property?: {
        control?: string
        id?: string
        title?: Array<{ text?: string }>
        require?: number
      }
    }>
  }
}

export interface WeComApprovalApplyContent {
  control: string
  id: string
  value: Record<string, unknown>
}

export interface WeComApprovalApplyPayload {
  template_id: string
  creator_userid: string
  use_template_approver?: number
  choose_department?: number
  contents: WeComApprovalApplyContent[]
  summary_lines?: string[]
  process?: Record<string, unknown>
}

export function getWeComApprovalConfig() {
  return request.get<any, ApiResponse<WeComApprovalConfig>>('/qywechat/approval/config')
}

export function getWeComApprovalTemplate(templateId: string) {
  return request.post<any, ApiResponse<WeComApprovalTemplate>>('/qywechat/approval/templates/detail', {
    template_id: templateId,
  })
}

export function listWeComApprovals(params?: {
  days?: number
  sp_status?: string
  template_id?: string
  creator?: string
  cursor?: string
  size?: number
}) {
  return request.get<any, ApiResponse<WeComApprovalListResult>>('/qywechat/approval/list', { params })
}

export function getWeComApprovalDetail(spNo: string) {
  return request.get<any, ApiResponse<WeComApprovalDetail>>(
    `/qywechat/approval/detail/${encodeURIComponent(spNo)}`
  )
}

export function submitWeComApproval(data: WeComApprovalApplyPayload) {
  return request.post<any, ApiResponse<{ sp_no: string }>>('/qywechat/approval/submit', data)
}
