import request, { type ApiResponse } from './request'

export interface FeishuDocumentListItem {
  doc_id: string
  feishu_token: string
  feishu_type: string
  title: string
  feishu_url?: string | null
  owner_id: number
  owner_username?: string | null
  owner_nickname?: string | null
  synced_at?: string | null
  has_snapshot: boolean
  preview: string
  can_access: boolean
  can_download: boolean
  access_request_status?: 'pending' | 'approved' | 'rejected' | null
  download_request_status?: 'pending' | 'approved' | 'rejected' | null
}

export interface FeishuDocumentDetail {
  doc_id: string
  feishu_token: string
  feishu_type: string
  title: string
  feishu_url?: string | null
  owner_id: number
  owner_username?: string | null
  synced_at?: string | null
  content: string
  content_format: string
  can_download: boolean
  is_owner?: boolean
  can_sync?: boolean
  has_snapshot?: boolean
}

export interface FeishuDocumentAccessStats {
  my_pending: number
  pending_for_review: number
}

export function listFeishuDocuments(params?: {
  query?: string
  limit?: number
  offset?: number
}) {
  return request.get<any, ApiResponse<{ items: FeishuDocumentListItem[]; total: number }>>(
    '/feishu-documents/list',
    { params }
  )
}

export function getFeishuDocument(docId: string) {
  return request.get<any, ApiResponse<FeishuDocumentDetail>>(`/feishu-documents/${docId}`)
}

export function syncFeishuDocument(docId: string) {
  return request.post<any, ApiResponse<{ doc_id: string; synced_at?: string | null }>>(
    `/feishu-documents/${docId}/sync`
  )
}

export function applyFeishuDocumentViewAccess(docIds: string[], reason?: string) {
  return request.post<any, ApiResponse<{ created: number; skipped: Array<{ doc_id: string; reason: string }> }>>(
    '/feishu-documents/access-requests',
    { doc_ids: docIds, reason: reason || '' }
  )
}

export function applyFeishuDocumentDownloadAccess(docIds: string[], reason?: string) {
  return request.post<any, ApiResponse<{ created: number; skipped: Array<{ doc_id: string; reason: string }> }>>(
    '/feishu-documents/download-requests',
    { doc_ids: docIds, reason: reason || '' }
  )
}

export function getFeishuDocumentAccessStats() {
  return request.get<any, ApiResponse<FeishuDocumentAccessStats>>('/feishu-documents/access-requests/stats')
}

export interface FeishuDocumentAccessRequest {
  id: number
  doc_id: string
  document_title?: string | null
  username?: string | null
  nickname?: string | null
  reason?: string | null
  status: string
  created_at?: string | null
}

export function getPendingFeishuDocumentViewRequests() {
  return request.get<any, ApiResponse<{ requests: FeishuDocumentAccessRequest[] }>>(
    '/feishu-documents/access-requests/pending'
  )
}

export function getPendingFeishuDocumentDownloadRequests() {
  return request.get<any, ApiResponse<{ requests: FeishuDocumentAccessRequest[] }>>(
    '/feishu-documents/download-requests/pending'
  )
}

export function reviewFeishuDocumentViewRequest(requestId: number, approve: boolean, reviewNote?: string) {
  return request.post<any, ApiResponse<{ success: boolean }>>(
    `/feishu-documents/access-requests/${requestId}/review`,
    { action: approve ? 'approve' : 'reject', review_note: reviewNote || '' }
  )
}

export function reviewFeishuDocumentDownloadRequest(requestId: number, approve: boolean, reviewNote?: string) {
  return request.post<any, ApiResponse<{ success: boolean }>>(
    `/feishu-documents/download-requests/${requestId}/review`,
    { action: approve ? 'approve' : 'reject', review_note: reviewNote || '' }
  )
}
