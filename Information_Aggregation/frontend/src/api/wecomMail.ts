import request, { type ApiResponse } from './request'

export interface WeComMailConfig {
  configured: boolean
  corp_id: string | null
}

export interface WeComMailListItem {
  mail_id: string
}

export interface WeComMailListResult {
  mail_list: WeComMailListItem[]
  next_cursor: string | null
  has_more: boolean
}

export interface WeComMailDetail {
  mail_id: string
  subject: string
  from_addr: string
  to_addr: string
  date: string
  body_text: string
  body_html: string
}

export interface WeComMailSendPayload {
  to_emails?: string[]
  to_userids?: string[]
  cc_emails?: string[]
  cc_userids?: string[]
  bcc_emails?: string[]
  bcc_userids?: string[]
  subject: string
  content: string
  content_type?: 'html' | 'text'
}

export function getWeComMailConfig() {
  return request.get<any, ApiResponse<WeComMailConfig>>('/wecom/mail/config')
}

export function listWeComInbox(params?: {
  begin_time?: number
  end_time?: number
  cursor?: string
  limit?: number
  days?: number
}) {
  return request.get<any, ApiResponse<WeComMailListResult>>('/wecom/mail/inbox', { params })
}

export function getWeComMailDetail(mailId: string) {
  return request.get<any, ApiResponse<WeComMailDetail>>(
    `/wecom/mail/${encodeURIComponent(mailId)}`
  )
}

export function sendWeComMail(data: WeComMailSendPayload) {
  return request.post<any, ApiResponse<null>>('/wecom/mail/send', data)
}
