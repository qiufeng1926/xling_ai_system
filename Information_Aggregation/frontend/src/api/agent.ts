import axios from 'axios'
import { ElMessage } from 'element-plus'
import router from '@/router'
import { AUTH_ROUTES } from '@/constants/routes'

const agentRequest = axios.create({
  baseURL: '/api/agent',
  timeout: 120000,
})

agentRequest.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  // FormData 必须由浏览器自动带 boundary，禁止手写 multipart Content-Type
  if (typeof FormData !== 'undefined' && config.data instanceof FormData) {
    if (config.headers) {
      delete (config.headers as Record<string, unknown>)['Content-Type']
      delete (config.headers as Record<string, unknown>)['content-type']
    }
  }
  return config
})

function detailMessage(detail: unknown, fallback: string): string {
  if (typeof detail === 'string') return detail
  if (detail && typeof detail === 'object' && 'message' in detail) {
    const m = (detail as { message?: unknown }).message
    if (typeof m === 'string') return m
  }
  return fallback
}

/** 解析 SSE；流结束时冲刷残留 buffer，避免丢掉最后的 done / match.cards */
async function consumeSseStream(
  body: ReadableStream<Uint8Array>,
  onEvent: (event: string, data: unknown) => void,
) {
  const reader = body.getReader()
  const decoder = new TextDecoder('utf-8')
  let buffer = ''
  let eventName = 'message'

  const feed = (chunk: string) => {
    buffer += chunk
    const parts = buffer.split('\n')
    buffer = parts.pop() || ''
    for (const line of parts) {
      if (line.startsWith('event:')) {
        eventName = line.slice(6).trim()
      } else if (line.startsWith('data:')) {
        const raw = line.slice(5).trim()
        let data: unknown = raw
        try {
          data = JSON.parse(raw)
        } catch {
          /* keep string */
        }
        onEvent(eventName, data)
      } else if (line.trim() === '') {
        eventName = 'message'
      }
    }
  }

  while (true) {
    const { done, value } = await reader.read()
    if (done) {
      feed(decoder.decode())
      if (buffer.trim()) {
        feed('\n')
      }
      break
    }
    feed(decoder.decode(value, { stream: true }))
  }
}

agentRequest.interceptors.response.use(
  (response) => response.data,
  (error) => {
    const status = error.response?.status
    const detail = error.response?.data?.detail
    if (status === 401) {
      ElMessage.error(detailMessage(detail, '登录已过期，请重新登录'))
      localStorage.removeItem('token')
      router.push(AUTH_ROUTES.login)
    } else if (status === 502 || status === 503 || error.code === 'ERR_NETWORK') {
      ElMessage.error('智能体服务不可用，请确认后端已在 :8003 启动')
    } else {
      ElMessage.error(detailMessage(detail, error.message || '智能体请求失败'))
    }
    return Promise.reject(error)
  },
)

export interface Conversation {
  id: number
  title: string
  status: string
  skill_slug?: string | null
  created_at?: string
  updated_at?: string
}

export interface MatchInfluencerCard {
  rank?: number
  id: number
  platform?: string
  platform_uid?: string
  nickname?: string | null
  avatar_url?: string | null
  follower_count?: number
  engagement_rate?: number | null
  agency_name?: string | null
  tags?: string[]
  shooting_style?: string[]
  persona_traits?: string[]
  cooperation_policy?: string | null
  internal_notes?: string | null
  contact?: { phone?: string | null; wechat?: string | null }
  match_score?: number | null
  match_reasons?: string[]
  detail_path?: string
}

export interface ChatMessage {
  id: number
  role: string
  content: string
  created_at?: string
  files?: { file_id: number; name?: string }[]
  citations?: { title: string; url?: string; snippet?: string }[]
  trajectory?: TrajectoryStep[]
  react_steps?: { thought?: string; action?: string; observation?: string; round?: number }[]
  influencers?: MatchInfluencerCard[]
}

export interface TrajectoryStep {
  round?: number
  kind?: string
  title: string
  detail?: string
  status?: string
  reason?: string
  tool?: string
}

export function listConversations(params?: { skill_slug?: string }) {
  return agentRequest.get('/v1/conversations', { params }) as Promise<{ items: Conversation[] }>
}

export function createConversation(
  title = '新对话',
  options?: { skill_slug?: string },
) {
  return agentRequest.post('/v1/conversations', {
    title,
    skill_slug: options?.skill_slug,
  }) as Promise<Conversation>
}

/** 商单筛库专用（与通用对话隔离） */
export function listMatchConversations() {
  return agentRequest.get('/v1/match/conversations') as Promise<{ items: Conversation[] }>
}

export function createMatchConversation(title = '新商单筛库') {
  return agentRequest.post('/v1/match/conversations', { title }) as Promise<Conversation>
}

export function deleteMatchConversation(id: number) {
  return agentRequest.delete(`/v1/match/conversations/${id}`) as Promise<{ ok: boolean }>
}

export function listMatchMessages(id: number) {
  return agentRequest.get(`/v1/match/conversations/${id}/messages`) as Promise<{ items: ChatMessage[] }>
}

export async function downloadMatchConversationExport(
  conversationId: number,
  messageId?: number,
  filename?: string,
) {
  const token = localStorage.getItem('token') || ''
  const qs =
    messageId != null ? `?message_id=${encodeURIComponent(String(messageId))}` : ''
  const resp = await fetch(
    `/api/agent/v1/match/conversations/${conversationId}/export${qs}`,
    {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    },
  )
  if (!resp.ok) {
    let detail = `导出失败: ${resp.status}`
    try {
      const errBody = await resp.json()
      if (typeof errBody?.detail === 'string') detail = errBody.detail
    } catch {
      /* ignore */
    }
    throw new Error(detail)
  }
  const blob = await resp.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename || `match_export_${conversationId}.xlsx`
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

export function streamMatchChat(
  conversationId: number,
  message: string,
  handlers: {
    onEvent: (event: string, data: unknown) => void
    onError?: (err: Error) => void
    onDone?: () => void
  },
) {
  const controller = new AbortController()
  const token = localStorage.getItem('token') || ''

  ;(async () => {
    try {
      const resp = await fetch(`/api/agent/v1/match/conversations/${conversationId}/chat`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
          Accept: 'text/event-stream',
        },
        body: JSON.stringify({ message }),
        signal: controller.signal,
      })
      if (!resp.ok) {
        let detail = `商单筛库请求失败: ${resp.status}`
        try {
          const errBody = await resp.json()
          if (typeof errBody?.detail === 'string') detail = errBody.detail
        } catch {
          /* ignore */
        }
        if (resp.status === 401) {
          localStorage.removeItem('token')
          router.push(AUTH_ROUTES.login)
        }
        throw new Error(detail)
      }
      if (!resp.body) throw new Error('商单筛库响应为空')
      await consumeSseStream(resp.body, handlers.onEvent)
      handlers.onDone?.()
    } catch (e) {
      if ((e as Error).name === 'AbortError') return
      handlers.onError?.(e as Error)
    }
  })()

  return controller
}

export function deleteConversation(id: number) {
  return agentRequest.delete(`/v1/conversations/${id}`) as Promise<{ ok: boolean }>
}

export function listMessages(id: number) {
  return agentRequest.get(`/v1/conversations/${id}/messages`) as Promise<{ items: ChatMessage[] }>
}

export function listSkills() {
  return agentRequest.get('/v1/skills') as Promise<{ builtin: any[]; mine: any[] }>
}

export function createSkill(body_md: string) {
  return agentRequest.post('/v1/skills', { body_md })
}

export function installSkill(id: number) {
  return agentRequest.post(`/v1/skills/install/${id}`)
}

export function uninstallSkill(id: number) {
  return agentRequest.delete(`/v1/skills/install/${id}`)
}

export function deleteSkill(id: number) {
  return agentRequest.delete(`/v1/skills/${id}`)
}

export function listKnowledgeBases() {
  return agentRequest.get('/v1/knowledge-bases') as Promise<{ private: any[]; global: any[] }>
}

export function createKnowledgeBase(name: string, kind: 'private' | 'global' = 'private') {
  return agentRequest.post('/v1/knowledge-bases', { name, kind }) as Promise<{ id: number; name: string }>
}

export function listDocuments(kbId: number) {
  return agentRequest.get(`/v1/knowledge-bases/${kbId}/documents`) as Promise<{ items: any[] }>
}

export function uploadDocument(kbId: number, file: File) {
  const fd = new FormData()
  fd.append('file', file)
  // 不要设置 Content-Type，由浏览器自动带 boundary
  return agentRequest.post(`/v1/knowledge-bases/${kbId}/documents`, fd)
}

export function deleteDocument(kbId: number, docId: number) {
  return agentRequest.delete(`/v1/knowledge-bases/${kbId}/documents/${docId}`)
}

export function listWorkspaceFiles() {
  return agentRequest.get('/v1/workspace/files') as Promise<{ items: any[] }>
}

export function workspaceDownloadUrl(fileId: number) {
  const token = localStorage.getItem('token') || ''
  const q = token ? `?token=${encodeURIComponent(token)}` : ''
  return `/api/agent/v1/workspace/files/${fileId}/download${q}`
}

export async function downloadWorkspaceFile(fileId: number, filename?: string) {
  const token = localStorage.getItem('token') || ''
  const resp = await fetch(`/api/agent/v1/workspace/files/${fileId}/download`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  })
  if (!resp.ok) {
    throw new Error(`下载失败: ${resp.status}`)
  }
  const blob = await resp.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename || `file-${fileId}`
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

export function resolveConfirmation(id: number, approved: boolean) {
  return agentRequest.post(`/v1/confirmations/${id}`, { approved })
}

/** SSE：确认后续跑（同意继续 ReAct / 拒绝结束） */
export function streamResumeConfirmation(
  confirmationId: number,
  approved: boolean,
  handlers: {
    onEvent: (event: string, data: unknown) => void
    onError?: (err: Error) => void
    onDone?: () => void
  },
) {
  const controller = new AbortController()
  const token = localStorage.getItem('token') || ''

  ;(async () => {
    try {
      const resp = await fetch(`/api/agent/v1/confirmations/${confirmationId}/resume`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
          Accept: 'text/event-stream',
        },
        body: JSON.stringify({ approved }),
        signal: controller.signal,
      })
      if (!resp.ok) {
        let detail = `确认续跑失败: ${resp.status}`
        try {
          const errBody = await resp.json()
          if (typeof errBody?.detail === 'string') detail = errBody.detail
        } catch {
          /* ignore */
        }
        throw new Error(detail)
      }
      if (!resp.body) throw new Error('确认续跑响应为空')
      await consumeSseStream(resp.body, handlers.onEvent)
      handlers.onDone?.()
    } catch (e) {
      if ((e as Error).name === 'AbortError') return
      handlers.onError?.(e as Error)
    }
  })()

  return controller
}

export function getMemoryProfile() {
  return agentRequest.get('/v1/memory/profile')
}

/** SSE 聊天：返回 AbortController，回调处理事件 */
export function streamChat(
  conversationId: number,
  message: string,
  handlers: {
    onEvent: (event: string, data: unknown) => void
    onError?: (err: Error) => void
    onDone?: () => void
  },
) {
  const controller = new AbortController()
  const token = localStorage.getItem('token') || ''

  ;(async () => {
    try {
      const resp = await fetch(`/api/agent/v1/conversations/${conversationId}/chat`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
          Accept: 'text/event-stream',
        },
        body: JSON.stringify({ message }),
        signal: controller.signal,
      })
      if (!resp.ok) {
        let detail = `聊天请求失败: ${resp.status}`
        try {
          const errBody = await resp.json()
          if (typeof errBody?.detail === 'string') detail = errBody.detail
          else if (errBody?.detail?.message) detail = errBody.detail.message
        } catch {
          /* ignore */
        }
        if (resp.status === 401) {
          localStorage.removeItem('token')
          router.push(AUTH_ROUTES.login)
        }
        throw new Error(detail)
      }
      if (!resp.body) {
        throw new Error('聊天响应为空（请确认代理已指向 :8003）')
      }
      await consumeSseStream(resp.body, handlers.onEvent)
      handlers.onDone?.()
    } catch (e) {
      if ((e as Error).name === 'AbortError') return
      handlers.onError?.(e as Error)
    }
  })()

  return controller
}

export function connectBrowserWs(onMessage: (data: Record<string, unknown>) => void) {
  const token = localStorage.getItem('token') || ''
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  const ws = new WebSocket(
    `${proto}://${location.host}/api/agent/v1/ws/browser?token=${encodeURIComponent(token)}`,
  )
  ws.onmessage = (ev) => {
    try {
      onMessage(JSON.parse(ev.data))
    } catch {
      /* ignore */
    }
  }
  ws.onerror = () => {
    ElMessage.warning('浏览器预览通道连接失败（不影响对话，确认 :8003 已启动）')
  }
  return ws
}

export default agentRequest
