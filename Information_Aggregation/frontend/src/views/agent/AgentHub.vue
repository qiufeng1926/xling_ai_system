<template>
  <div class="agent-hub">
    <aside class="agent-left">
      <div class="left-header">
        <el-button type="primary" size="small" @click="onNewChat">新建对话</el-button>
      </div>
      <el-scrollbar class="conv-scroll">
        <div
          v-for="c in conversations"
          :key="c.id"
          class="conv-item"
          :class="{ active: c.id === activeId }"
          @click="selectConversation(c.id)"
        >
          <span class="conv-title">{{ c.title }}</span>
          <el-button link type="danger" size="small" @click.stop="onDeleteConv(c.id)">删</el-button>
        </div>
      </el-scrollbar>
    </aside>

    <main class="agent-center">
      <div ref="msgBoxRef" class="msg-box">
        <div v-for="(m, idx) in displayMessages" :key="idx" class="msg" :class="m.role">
          <div class="msg-role">{{ roleLabel(m.role) }}</div>
          <div class="msg-content">{{ displayText(m.content) }}</div>
          <div v-if="m.files?.length" class="msg-files">
            <button
              v-for="f in m.files"
              :key="f.file_id"
              type="button"
              class="file-chip"
              @click="onDownload(f.file_id, f.name)"
            >
              ⬇ {{ f.name || `文件 #${f.file_id}` }}
            </button>
          </div>
        </div>

        <div v-if="thinkingVisible" class="think-card">
          <button type="button" class="think-header" @click="thinkCollapsed = !thinkCollapsed">
            <span class="think-title">
              <span class="think-dot" :class="{ pulse: streaming && !thinkClosed }" />
              {{ thinkClosed ? 'ReAct 已完成' : 'ReAct 推理中' }}
            </span>
            <span class="think-toggle">{{ thinkCollapsed ? '展开' : '收起' }}</span>
          </button>
          <div v-show="!thinkCollapsed" class="think-body">{{ thinkingText }}</div>
        </div>

        <div v-if="pendingFiles.length" class="msg-files inline-files">
          <button
            v-for="f in pendingFiles"
            :key="f.file_id"
            type="button"
            class="file-chip"
            @click="onDownload(f.file_id, f.name)"
          >
            ⬇ {{ f.name || `文件 #${f.file_id}` }}
          </button>
        </div>

        <div v-if="toolTraces.length" class="trace-card">
          <div class="trace-title">ReAct · Action / Observation</div>
          <div v-for="(t, i) in toolTraces" :key="i" class="tool-line">
            <el-tag size="small" :type="t.done ? 'success' : 'warning'">{{ t.tool }}</el-tag>
            <span>{{ t.done ? 'Observation 已回填' : 'Action 执行中…' }}</span>
          </div>
        </div>
        <div v-if="pendingConfirm" class="confirm-bar">
          <div>需要确认：{{ pendingConfirm.action_type }}</div>
          <div class="confirm-actions">
            <el-button type="primary" size="small" @click="onConfirm(true)">同意</el-button>
            <el-button size="small" @click="onConfirm(false)">拒绝</el-button>
          </div>
        </div>
      </div>
      <div class="input-row">
        <el-input
          v-model="input"
          type="textarea"
          :rows="2"
          placeholder="描述你的办公任务…"
          :disabled="streaming"
          @keydown.enter.exact.prevent="onSend"
        />
        <el-button type="primary" :loading="streaming" @click="onSend">发送</el-button>
      </div>
    </main>

    <aside class="agent-right">
      <el-tabs v-model="rightTab">
        <el-tab-pane label="浏览器" name="browser">
          <div class="browser-url">{{ browserUrl || 'about:blank' }}</div>
          <div class="browser-frame">
            <img v-if="browserFrame" :src="`data:image/jpeg;base64,${browserFrame}`" alt="browser" />
            <div v-else class="browser-empty">尚无预览，Agent 打开网页后显示</div>
          </div>
        </el-tab-pane>
        <el-tab-pane label="知识库" name="kb">
          <div class="panel-actions">
            <el-button size="small" @click="onCreateKb">新建私有库</el-button>
            <el-select v-model="activeKbId" placeholder="选择库" size="small" style="width: 140px">
              <el-option v-for="k in allKbs" :key="k.id" :label="k.name" :value="k.id" />
            </el-select>
            <el-upload :show-file-list="false" :http-request="onUpload" :disabled="!activeKbId">
              <el-button size="small" type="primary" :disabled="!activeKbId">上传</el-button>
            </el-upload>
          </div>
          <el-scrollbar height="420px">
            <div v-for="d in docs" :key="d.id" class="doc-row">
              <span>{{ d.filename }}</span>
              <el-tag size="small">{{ d.status }}</el-tag>
            </div>
          </el-scrollbar>
        </el-tab-pane>
        <el-tab-pane label="Skill" name="skill">
          <div class="skill-section">
            <div class="sec-title">官方 Skill</div>
            <div v-for="s in builtinSkills" :key="s.id" class="skill-row">
              <div>
                <strong>{{ s.name }}</strong>
                <div class="muted">{{ s.description }}</div>
              </div>
              <el-button size="small" @click="onInstall(s.id)">安装</el-button>
            </div>
          </div>
          <div class="skill-section">
            <div class="sec-title">我的 Skill</div>
            <el-input
              v-model="skillDraft"
              type="textarea"
              :rows="8"
              placeholder="粘贴 Markdown/YAML Skill…"
            />
            <el-button size="small" type="primary" style="margin-top: 8px" @click="onCreateSkill">创建</el-button>
            <div v-for="s in mySkills" :key="s.id" class="skill-row">
              <strong>{{ s.name }}</strong>
              <el-button size="small" type="danger" @click="onDeleteSkill(s.id)">删除</el-button>
            </div>
          </div>
        </el-tab-pane>
      </el-tabs>
      <div v-if="readyFiles.length" class="files-block">
        <div class="sec-title">工作区产物</div>
        <button
          v-for="f in readyFiles"
          :key="f.file_id"
          type="button"
          class="file-chip"
          @click="onDownload(f.file_id, f.name)"
        >
          ⬇ {{ f.name || `文件 #${f.file_id}` }}
        </button>
      </div>
    </aside>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { UploadRequestOptions } from 'element-plus'
import {
  connectBrowserWs,
  createConversation,
  createKnowledgeBase,
  createSkill,
  deleteConversation,
  deleteSkill,
  downloadWorkspaceFile,
  installSkill,
  listConversations,
  listDocuments,
  listKnowledgeBases,
  listMessages,
  listSkills,
  resolveConfirmation,
  streamChat,
  uploadDocument,
  type ChatMessage,
  type Conversation,
} from '@/api/agent'

type MsgFile = { file_id: number; name?: string }
type UiMessage = ChatMessage & { files?: MsgFile[] }

const conversations = ref<Conversation[]>([])
const activeId = ref<number | null>(null)
const messages = ref<UiMessage[]>([])
const streamingContent = ref('')
const streaming = ref(false)
const input = ref('')
const thinkingText = ref('')
const thinkingVisible = ref(false)
const thinkCollapsed = ref(false)
const thinkClosed = ref(false)
const toolTraces = ref<{ tool: string; done: boolean }[]>([])
const pendingConfirm = ref<{ id: number; action_type: string } | null>(null)
const readyFiles = ref<MsgFile[]>([])
const pendingFiles = ref<MsgFile[]>([])
const msgBoxRef = ref<HTMLElement | null>(null)

const rightTab = ref('browser')
const browserUrl = ref('')
const browserFrame = ref('')
let browserWs: WebSocket | null = null
let chatAbort: AbortController | null = null

const builtinSkills = ref<any[]>([])
const mySkills = ref<any[]>([])
const skillDraft = ref(`---
name: my-skill
slug: my-skill
description: 自定义技能
version: 1
tools:
  - kb_search
  - file_write_markdown
---

# 说明
在此写给模型的使用指引。
`)

const privateKbs = ref<any[]>([])
const globalKbs = ref<any[]>([])
const activeKbId = ref<number | null>(null)
const docs = ref<any[]>([])

const allKbs = computed(() => [...privateKbs.value, ...globalKbs.value])

const displayMessages = computed(() => {
  const list = [...messages.value]
  if (streamingContent.value) {
    list.push({
      id: -1,
      role: 'assistant',
      content: streamingContent.value,
      files: pendingFiles.value.length ? [...pendingFiles.value] : undefined,
    })
  }
  return list
})

function roleLabel(role: string) {
  if (role === 'user') return '我'
  if (role === 'assistant') return '智能体'
  return role
}

/** 给普通人看的文案：去掉 JSON / 协议残留 / 串题要点 dump */
function displayText(content: string) {
  let raw = (content || '').trim()
  if (!raw) return ''

  const fence = raw.match(/```(?:json)?\s*([\s\S]*?)```/i)
  if (fence) {
    const inner = fence[1].trim()
    try {
      const obj = JSON.parse(inner)
      if (obj?.content) return String(obj.content)
      if (obj?.action_input) {
        return typeof obj.action_input === 'string'
          ? obj.action_input
          : String(obj.action_input.content || JSON.stringify(obj.action_input))
      }
    } catch {
      /* ignore */
    }
  }

  if (raw.startsWith('{')) {
    try {
      const obj = JSON.parse(raw)
      if (obj && typeof obj === 'object') {
        if (obj.content) return String(obj.content)
        if (obj.action_input) {
          return typeof obj.action_input === 'string'
            ? obj.action_input
            : String(obj.action_input.content || '')
        }
      }
    } catch {
      /* ignore */
    }
  }

  const contentMatch = raw.match(/"content"\s*:\s*"((?:\\.|[^"\\])*)"/)
  if (contentMatch && (raw.includes('"action"') || raw.includes('最终回答'))) {
    try {
      return JSON.parse(`"${contentMatch[1]}"`)
    } catch {
      return contentMatch[1].replace(/\\n/g, '\n')
    }
  }

  if (raw.includes('（内部步骤）') || raw.includes('(内部步骤)')) {
    return '正在处理中，请稍候或换个问法再试。'
  }
  if (raw.startsWith('根据已收集到的信息') || raw.startsWith('这是我目前整理到的要点')) {
    // 疑似串题垃圾；若同时含新闻+无关英文标签，前端兜底提示
    if (
      /台风|七一|天气预报|知识库未命中|InspirationalBooks/i.test(raw) &&
      !/书名|小说|著|推荐.*书/.test(raw)
    ) {
      return '这一轮没有整理出与你问题相关的内容。请再发一次，或把需求说得更具体一点。'
    }
  }
  return content
}

async function onDownload(fileId: number, name?: string) {
  try {
    await downloadWorkspaceFile(fileId, name)
  } catch (e: any) {
    ElMessage.error(e?.message || '下载失败')
  }
}

async function refreshConversations() {
  const data = await listConversations()
  conversations.value = data.items || []
}

async function selectConversation(id: number) {
  activeId.value = id
  thinkingText.value = ''
  thinkingVisible.value = false
  thinkCollapsed.value = false
  thinkClosed.value = false
  toolTraces.value = []
  pendingConfirm.value = null
  streamingContent.value = ''
  const data = await listMessages(id)
  messages.value = (data.items || []).map((m) => ({
    ...m,
    files: m.files?.length ? m.files : undefined,
  }))
  readyFiles.value = messages.value.flatMap((m) => m.files || []).reverse()
  await nextTick()
  scrollBottom()
}

async function onNewChat() {
  try {
    const data = await createConversation()
    await refreshConversations()
    await selectConversation(data.id)
  } catch {
    /* 错误提示已由 agent API 拦截器处理 */
  }
}

async function onDeleteConv(id: number) {
  try {
    await deleteConversation(id)
    if (activeId.value === id) {
      activeId.value = null
      messages.value = []
    }
    await refreshConversations()
  } catch {
    /* interceptor */
  }
}

function scrollBottom() {
  const el = msgBoxRef.value
  if (el) el.scrollTop = el.scrollHeight
}

async function onSend() {
  const text = input.value.trim()
  if (!text || streaming.value) return
  try {
    if (!activeId.value) {
      await onNewChat()
    }
  } catch {
    return
  }
  if (!activeId.value) {
    ElMessage.error('无法创建会话，请确认智能体后端已启动')
    return
  }

  const conversationId = activeId.value
  input.value = ''
  streaming.value = true
  streamingContent.value = ''
  thinkingText.value = ''
  thinkingVisible.value = false
  thinkCollapsed.value = false
  thinkClosed.value = false
  toolTraces.value = []
  pendingFiles.value = []
  messages.value.push({ id: Date.now(), role: 'user', content: text })
  await nextTick()
  scrollBottom()

  chatAbort = streamChat(conversationId, text, {
    onEvent(event, data) {
      const d = data as Record<string, any>
      if (event === 'think.open') {
        thinkingVisible.value = true
        thinkCollapsed.value = false
        thinkClosed.value = false
        thinkingText.value = ''
      } else if (event === 'think.delta') {
        thinkingVisible.value = true
        thinkingText.value += d.content || ''
        scrollBottom()
      } else if (event === 'think.close') {
        thinkClosed.value = true
        thinkCollapsed.value = true
      } else if (event === 'message.delta') {
        streamingContent.value += d.content || ''
        scrollBottom()
      } else if (event === 'tool.started') {
        toolTraces.value.push({ tool: d.tool, done: false })
        thinkingVisible.value = true
      } else if (event === 'tool.finished') {
        const last = [...toolTraces.value].reverse().find((t) => t.tool === d.tool && !t.done)
        if (last) last.done = true
      } else if (event === 'browser.frame') {
        if (d.frame) browserFrame.value = d.frame
        if (d.url) browserUrl.value = d.url
        rightTab.value = 'browser'
      } else if (event === 'confirmation.required') {
        pendingConfirm.value = { id: d.id, action_type: d.action_type }
      } else if (event === 'file.ready') {
        const item = { file_id: d.file_id, name: d.name }
        readyFiles.value.unshift(item)
        pendingFiles.value.push(item)
        scrollBottom()
      }
    },
    onError(err) {
      ElMessage.error(err.message)
      streaming.value = false
      thinkClosed.value = true
    },
    async onDone() {
      streaming.value = false
      thinkClosed.value = true
      const files = pendingFiles.value.length ? [...pendingFiles.value] : undefined
      if (streamingContent.value || files?.length) {
        messages.value.push({
          id: Date.now() + 1,
          role: 'assistant',
          content: displayText(streamingContent.value || '文件已生成'),
          files,
        })
        streamingContent.value = ''
        pendingFiles.value = []
      }
      try {
        if (activeId.value) {
          const data = await listMessages(activeId.value)
          messages.value = (data.items || []).map((m) => ({
            ...m,
            files: m.files?.length ? m.files : undefined,
          }))
          readyFiles.value = messages.value.flatMap((m) => m.files || []).reverse()
        }
        await refreshConversations()
      } catch {
        /* interceptor */
      }
      await nextTick()
      scrollBottom()
    },
  })
}

async function onConfirm(approved: boolean) {
  if (!pendingConfirm.value) return
  try {
    await resolveConfirmation(pendingConfirm.value.id, approved)
    ElMessage.success(approved ? '已同意并执行' : '已拒绝')
    pendingConfirm.value = null
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '确认失败')
  }
}

async function refreshSkills() {
  const data = await listSkills()
  builtinSkills.value = data.builtin || []
  mySkills.value = data.mine || []
}

async function onInstall(id: number) {
  try {
    await installSkill(id)
    ElMessage.success('已安装')
    await refreshSkills()
  } catch {
    /* interceptor */
  }
}

async function onCreateSkill() {
  try {
    await createSkill(skillDraft.value)
    ElMessage.success('已创建')
    await refreshSkills()
  } catch {
    /* interceptor */
  }
}

async function onDeleteSkill(id: number) {
  try {
    await deleteSkill(id)
    await refreshSkills()
  } catch {
    /* interceptor */
  }
}

async function refreshKbs() {
  const data = await listKnowledgeBases()
  privateKbs.value = data.private || []
  globalKbs.value = data.global || []
  if (!activeKbId.value && privateKbs.value[0]) {
    activeKbId.value = privateKbs.value[0].id
  }
}

async function onCreateKb() {
  try {
    const { value } = await ElMessageBox.prompt('知识库名称', '新建私有知识库')
    if (!value) return
    const data = await createKnowledgeBase(value, 'private')
    await refreshKbs()
    activeKbId.value = data.id
    ElMessage.success('知识库已创建')
  } catch (e: any) {
    if (e === 'cancel' || e?.action === 'cancel') return
    /* interceptor */
  }
}

async function refreshDocs() {
  if (!activeKbId.value) {
    docs.value = []
    return
  }
  const data = await listDocuments(activeKbId.value)
  docs.value = data.items || []
}

async function onUpload(opt: UploadRequestOptions) {
  if (!activeKbId.value) return
  try {
    await uploadDocument(activeKbId.value, opt.file as File)
    ElMessage.success('上传成功')
    await refreshDocs()
    opt.onSuccess?.({} as any)
  } catch (e: any) {
    opt.onError?.(e as any)
  }
}

watch(activeKbId, () => {
  refreshDocs().catch(() => undefined)
})

onMounted(async () => {
  try {
    await refreshConversations()
    if (conversations.value[0]) {
      await selectConversation(conversations.value[0].id)
    }
    await refreshSkills()
    await refreshKbs()
    await refreshDocs()
  } catch {
    ElMessage.error('智能体初始化失败：请确认后端 uvicorn 已在 8003 端口运行，并重启前端 Vite')
  }
  browserWs = connectBrowserWs((data) => {
    if (data.type === 'browser.frame') {
      if (data.frame) browserFrame.value = String(data.frame)
      if (data.url) browserUrl.value = String(data.url)
    }
  })
})

onUnmounted(() => {
  chatAbort?.abort()
  browserWs?.close()
})
</script>

<style scoped>
.agent-hub {
  display: grid;
  grid-template-columns: 220px 1fr 340px;
  height: calc(100vh - 120px);
  max-height: calc(100vh - 120px);
  min-height: 0;
  gap: 0;
  background: #f5f7fa;
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  overflow: hidden;
}
.agent-left,
.agent-right {
  background: #fff;
  border-right: 1px solid #ebeef5;
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
}
.agent-right {
  border-right: none;
  border-left: 1px solid #ebeef5;
  padding: 8px 12px;
  overflow: auto;
}
.left-header {
  padding: 12px;
  border-bottom: 1px solid #ebeef5;
  flex-shrink: 0;
}
.conv-scroll {
  flex: 1;
  min-height: 0;
}
.conv-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 12px;
  cursor: pointer;
  border-bottom: 1px solid #f2f3f5;
}
.conv-item:hover,
.conv-item.active {
  background: #ecf5ff;
}
.conv-title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 150px;
  font-size: 13px;
}
.agent-center {
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
  background: #fafbfc;
}
.msg-box {
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
  padding: 16px 20px;
  -webkit-overflow-scrolling: touch;
}
.msg {
  margin-bottom: 14px;
  max-width: 860px;
}
.msg-role {
  font-size: 12px;
  color: #909399;
  margin-bottom: 4px;
}
.msg.user .msg-content {
  background: #ecf5ff;
  border-radius: 8px;
  padding: 10px 12px;
  white-space: pre-wrap;
  word-break: break-word;
}
.msg.assistant .msg-content {
  background: #fff;
  border: 1px solid #ebeef5;
  border-radius: 8px;
  padding: 10px 12px;
  white-space: pre-wrap;
  word-break: break-word;
}
.msg-files {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 8px;
}
.msg-files.inline-files {
  margin-bottom: 12px;
}
.file-chip {
  border: 1px solid #b3d8ff;
  background: #ecf5ff;
  color: #409eff;
  border-radius: 6px;
  padding: 6px 10px;
  font-size: 13px;
  cursor: pointer;
}
.file-chip:hover {
  background: #d9ecff;
}
.trace-card {
  background: #fff;
  border: 1px dashed #dcdfe6;
  border-radius: 8px;
  padding: 10px 12px;
  margin-bottom: 12px;
  font-size: 13px;
}
.think-card {
  background: #f7f8fa;
  border: 1px solid #e4e7ed;
  border-radius: 10px;
  margin-bottom: 12px;
  overflow: hidden;
}
.think-header {
  width: 100%;
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 12px;
  border: 0;
  background: transparent;
  cursor: pointer;
  font-size: 13px;
  color: #606266;
}
.think-title {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
}
.think-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #909399;
  display: inline-block;
}
.think-dot.pulse {
  background: #409eff;
  animation: think-pulse 1.2s ease-in-out infinite;
}
@keyframes think-pulse {
  0%, 100% { opacity: 0.35; transform: scale(0.9); }
  50% { opacity: 1; transform: scale(1.15); }
}
.think-toggle {
  color: #909399;
  font-size: 12px;
}
.think-body {
  padding: 0 12px 12px;
  color: #909399;
  font-size: 12px;
  line-height: 1.7;
  white-space: pre-wrap;
  max-height: 220px;
  overflow: auto;
  border-top: 1px dashed #ebeef5;
}
.trace-title,
.sec-title {
  font-weight: 600;
  margin-bottom: 6px;
  font-size: 13px;
}
.tool-line {
  display: flex;
  gap: 8px;
  align-items: center;
  margin: 4px 0;
}
.confirm-bar {
  background: #fdf6ec;
  border: 1px solid #faecd8;
  border-radius: 8px;
  padding: 10px 12px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.input-row {
  display: flex;
  gap: 8px;
  padding: 12px;
  border-top: 1px solid #ebeef5;
  background: #fff;
  align-items: flex-end;
  flex-shrink: 0;
}
.browser-url {
  font-size: 12px;
  color: #606266;
  margin-bottom: 8px;
  word-break: break-all;
}
.browser-frame {
  background: #111;
  min-height: 360px;
  border-radius: 6px;
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
}
.browser-frame img {
  width: 100%;
  display: block;
}
.browser-empty {
  color: #909399;
  font-size: 13px;
  padding: 24px;
  text-align: center;
}
.panel-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 10px;
}
.doc-row,
.skill-row {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  align-items: center;
  padding: 8px 0;
  border-bottom: 1px solid #f2f3f5;
  font-size: 13px;
}
.muted {
  color: #909399;
  font-size: 12px;
}
.skill-section {
  margin-bottom: 16px;
}
.files-block {
  margin-top: 12px;
  border-top: 1px solid #ebeef5;
  padding-top: 8px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.files-block .file-chip {
  text-align: left;
}
@media (max-width: 1100px) {
  .agent-hub {
    grid-template-columns: 180px 1fr;
  }
  .agent-right {
    display: none;
  }
}
</style>
