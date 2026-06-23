import axios from 'axios'
import { ElMessage } from 'element-plus'
import router from '@/router'
import request, { type ApiResponse } from './request'
import { AUTH_ROUTES } from '@/constants/routes'

export interface FeishuBindStatus {
  bound: boolean
  feishu_name: string | null
  token_valid: boolean
  docs_authorized: boolean
  oauth_scope?: string | null
  portal_username?: string | null
  portal_nickname?: string | null
}

export interface FlybookApiErrorDetail {
  code?: string
  message?: string
}

export function isFeishuScopeMissingError(error: unknown): boolean {
  const detail = (error as { response?: { data?: { detail?: FlybookApiErrorDetail | string } } })
    ?.response?.data?.detail
  return typeof detail === 'object' && detail?.code === 'feishu_scope_missing'
}

export function getFlybookErrorMessage(error: unknown, fallback = '飞书服务请求失败'): string {
  const detail = (error as { response?: { data?: { detail?: FlybookApiErrorDetail | string } } })
    ?.response?.data?.detail
  if (typeof detail === 'object' && detail?.message) return detail.message
  if (typeof detail === 'string') return detail
  return fallback
}

export interface FlybookConfig {
  messenger_url: string
  doc_base_url: string
  docs_component_sdk_url: string
  open_api_configured: boolean
}

export interface FeishuDriveFile {
  token: string
  name: string
  type: string
  url?: string
  embed_editable?: boolean
  created_time?: string
  modified_time?: string
}

export interface FeishuCreateType {
  type: string
  label: string
  embed_editable: boolean
}

export interface FeishuFileCreated {
  type: string
  token: string
  title: string
  url?: string
  embed_editable?: boolean
  /** @deprecated 兼容旧 docx 响应 */
  document_id?: string
}

const flybookRequest = axios.create({
  baseURL: '/api/flybook',
  timeout: 30000,
})

flybookRequest.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

flybookRequest.interceptors.response.use(
  (response) => response.data,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('token')
      router.push(AUTH_ROUTES.login)
    }
    const detail = error.response?.data?.detail
    const scopeMissing =
      typeof detail === 'object' && detail !== null && detail.code === 'feishu_scope_missing'
    if (!scopeMissing) {
      ElMessage.error(
        typeof detail === 'object' && detail?.message
          ? detail.message
          : typeof detail === 'string'
            ? detail
            : error.message || '飞书服务请求失败'
      )
    }
    return Promise.reject(error)
  }
)

export function getFeishuBindStatus() {
  return request.get<any, ApiResponse<FeishuBindStatus>>('/auth/feishu/status')
}

export function unbindFeishu() {
  return request.post<any, ApiResponse<{ bound: boolean }>>('/auth/feishu/unbind')
}

export async function startFeishuBind(returnTo = '/flybook/messenger') {
  const data = await flybookRequest.post<{ authorize_url: string }>(
    '/auth/bind/start',
    null,
    { params: { return_to: returnTo } }
  )
  return data.authorize_url
}

export function getFlybookConfig() {
  return flybookRequest.get<FlybookConfig>('/config')
}

export interface FeishuComponentAuth {
  appId: string
  openId: string
  signature: string
  timestamp: number
  nonceStr: string
  url: string
  jsApiList: string[]
}

export function getDocsCreateTypes() {
  return flybookRequest.get<{ types: FeishuCreateType[] }>('/docs/create-types')
}

export function getDocsRootFolder() {
  return flybookRequest.get<{ token?: string; id?: string }>('/docs/root-folder')
}

export function listDocsFiles(params?: { folder_token?: string; page_token?: string }) {
  return flybookRequest.get<{
    files: FeishuDriveFile[]
    has_more: boolean
    page_token: string
  }>('/docs/files', { params })
}

export function createFeishuFile(type: string, title: string, folderToken = '') {
  return flybookRequest.post<FeishuFileCreated>('/docs/files', {
    type,
    title,
    folder_token: folderToken,
  })
}

/** @deprecated 使用 createFeishuFile('docx', title) */
export function createFeishuDoc(title: string, folderToken = '') {
  return createFeishuFile('docx', title, folderToken)
}

export function getDocsComponentAuth(pageUrl: string) {
  return flybookRequest.post<FeishuComponentAuth>('/docs/component-auth', {
    page_url: pageUrl,
  })
}

let sdkLoadPromise: Promise<void> | null = null

export function loadFeishuDocsSdk(sdkUrl: string): Promise<void> {
  if (window.DocComponentSdk) {
    return Promise.resolve()
  }
  if (sdkLoadPromise) {
    return sdkLoadPromise
  }
  sdkLoadPromise = new Promise((resolve, reject) => {
    const existing = document.querySelector(`script[data-feishu-docs-sdk="1"]`)
    if (existing) {
      existing.addEventListener('load', () => resolve())
      existing.addEventListener('error', () => reject(new Error('飞书云文档 SDK 加载失败')))
      return
    }
    const script = document.createElement('script')
    script.src = sdkUrl
    script.async = true
    script.dataset.feishuDocsSdk = '1'
    script.onload = () => resolve()
    script.onerror = () => reject(new Error('飞书云文档 SDK 加载失败'))
    document.head.appendChild(script)
  })
  return sdkLoadPromise
}
