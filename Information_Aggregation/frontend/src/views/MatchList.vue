<template>
  <div class="match-agent">
    <aside class="match-left">
      <div class="left-header">
        <el-button type="primary" size="small" @click="onNewChat">新建商单筛库</el-button>
      </div>
      <p class="left-hint">
        专用筛库智能体（与通用智能体隔离）：只读取达人库并 grounded 总结，不搜索网页。通用智能体可通过 call_influencer_match 单向调用本能力。
      </p>
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

    <main class="match-center">
      <div class="center-title">商单筛库 · ReAct</div>
      <div ref="msgBoxRef" class="msg-box">
        <div v-if="!messages.length && !streaming" class="empty-tip">
          示例：抖音探店商单，粉丝 5 万以上，有联系方式，偏本地生活风格，请从达人库筛至少 5 位并总结合作政策与人设。
        </div>

        <div v-for="(m, idx) in displayMessages" :key="idx" class="msg" :class="m.role">
          <div class="msg-role">{{ roleLabel(m.role) }}</div>
          <div class="msg-content">{{ displayText(m.content) }}</div>
          <div v-if="m.influencers?.length" class="card-grid">
            <button
              v-for="card in m.influencers"
              :key="`${m.id}-${card.id}`"
              type="button"
              class="inf-card"
              @click="openInfluencer(card.id)"
            >
              <div class="inf-card-top">
                <img
                  v-if="card.avatar_url"
                  class="inf-avatar"
                  :src="card.avatar_url"
                  alt=""
                  referrerpolicy="no-referrer"
                />
                <div v-else class="inf-avatar placeholder">{{ (card.nickname || '?').slice(0, 1) }}</div>
                <div class="inf-main">
                  <div class="inf-name">
                    <span class="rank">#{{ card.rank || '' }}</span>
                    {{ card.nickname || '未命名达人' }}
                  </div>
                  <div class="inf-sub">
                    {{ formatPlatform(card.platform || '') }} · UID {{ card.platform_uid || '-' }}
                  </div>
                </div>
                <el-tag v-if="card.match_score != null" size="small" type="success">
                  {{ card.match_score }} 分
                </el-tag>
              </div>
              <div class="inf-meta">
                <span>粉丝 {{ formatFollowers(card.follower_count || 0) }}</span>
                <span v-if="card.agency_name">机构 {{ card.agency_name }}</span>
              </div>
              <div v-if="card.tags?.length" class="inf-tags">
                <el-tag v-for="t in card.tags.slice(0, 4)" :key="t" size="small" effect="plain">{{ t }}</el-tag>
              </div>
              <div v-if="card.persona_traits?.length || card.shooting_style?.length" class="inf-line">
                <template v-if="card.persona_traits?.length">人设：{{ card.persona_traits.slice(0, 3).join('、') }}</template>
                <template v-if="card.shooting_style?.length">
                  {{ card.persona_traits?.length ? ' · ' : '' }}风格：{{ card.shooting_style.slice(0, 3).join('、') }}
                </template>
              </div>
              <div v-if="card.cooperation_policy" class="inf-policy">{{ card.cooperation_policy }}</div>
              <div class="inf-footer">点击查看达人库详情 →</div>
            </button>
          </div>
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
          <div v-if="m.trajectory?.length && !streaming" class="trace-card hist-traj">
            <button type="button" class="trace-header" @click="toggleHistTraj(m.id)">
              <span class="trace-title">
                执行步骤 · {{ m.trajectory.length }} 步
                <span v-if="trajSummary(m.trajectory)" class="trace-summary">{{ trajSummary(m.trajectory) }}</span>
              </span>
              <span class="think-toggle">{{ isHistTrajOpen(m.id) ? '收起' : '展开' }}</span>
            </button>
            <div v-show="isHistTrajOpen(m.id)" class="trace-body">
              <div v-for="(t, ti) in m.trajectory" :key="ti" class="traj-line" :class="t.status">
                <el-tag size="small" :type="trajTagType(t.status)">{{ t.title }}</el-tag>
                <span class="traj-detail" :title="t.detail || t.reason || ''">{{ shortTrajDetail(t) }}</span>
              </div>
            </div>
          </div>
        </div>

        <div v-if="thinkingVisible" class="think-card">
          <button type="button" class="think-header" @click="thinkCollapsed = !thinkCollapsed">
            <span class="think-title">
              <span class="think-dot" :class="{ pulse: streaming && !thinkClosed }" />
              {{ thinkClosed ? 'ReAct 已完成' : 'ReAct 推理中' }}
            </span>
            <span class="think-toggle">{{ thinkCollapsed ? '展开原始推理' : '收起原始推理' }}</span>
          </button>
          <div v-show="!thinkCollapsed" class="think-body">{{ thinkingText }}</div>
        </div>

        <div v-if="trajectorySteps.length" class="trace-card">
          <button type="button" class="trace-header" @click="trajLiveCollapsed = !trajLiveCollapsed">
            <span class="trace-title">
              执行步骤 · {{ trajectorySteps.length }} 步
              <span v-if="trajSummary(trajectorySteps)" class="trace-summary">{{ trajSummary(trajectorySteps) }}</span>
            </span>
            <span class="think-toggle">{{ trajLiveCollapsed ? '展开' : '收起' }}</span>
          </button>
          <div v-show="!trajLiveCollapsed" class="trace-body">
            <div v-for="(t, i) in trajectorySteps" :key="i" class="traj-line" :class="t.status">
              <el-tag size="small" :type="trajTagType(t.status)">{{ t.title }}</el-tag>
              <span class="traj-detail" :title="t.detail || t.reason || ''">{{ shortTrajDetail(t) }}</span>
            </div>
          </div>
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

        <div v-if="streamingContent || liveCards.length" class="msg assistant">
          <div class="msg-role">助手</div>
          <div v-if="streamingContent" class="msg-content">{{ displayText(streamingContent) }}</div>
          <div v-if="liveCards.length" class="card-grid">
            <button
              v-for="card in liveCards"
              :key="`live-${card.id}`"
              type="button"
              class="inf-card"
              @click="openInfluencer(card.id)"
            >
              <div class="inf-card-top">
                <img
                  v-if="card.avatar_url"
                  class="inf-avatar"
                  :src="card.avatar_url"
                  alt=""
                  referrerpolicy="no-referrer"
                />
                <div v-else class="inf-avatar placeholder">{{ (card.nickname || '?').slice(0, 1) }}</div>
                <div class="inf-main">
                  <div class="inf-name">
                    <span class="rank">#{{ card.rank || '' }}</span>
                    {{ card.nickname || '未命名达人' }}
                  </div>
                  <div class="inf-sub">
                    {{ formatPlatform(card.platform || '') }} · UID {{ card.platform_uid || '-' }}
                  </div>
                </div>
              </div>
              <div class="inf-meta">
                <span>粉丝 {{ formatFollowers(card.follower_count || 0) }}</span>
              </div>
              <div class="inf-footer">点击查看达人库详情 →</div>
            </button>
          </div>
        </div>
      </div>

      <div class="composer">
        <el-input
          v-model="input"
          type="textarea"
          :rows="4"
          :disabled="streaming"
          placeholder="粘贴商单 / brief 全文，Enter 发送（Shift+Enter 换行）"
          @keydown.enter.exact.prevent="onSend"
        />
        <div class="composer-actions">
          <el-button type="primary" :loading="streaming" @click="onSend">开始筛库</el-button>
          <el-button v-if="streaming" @click="onStop">停止</el-button>
        </div>
      </div>
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  createMatchConversation,
  deleteMatchConversation,
  downloadWorkspaceFile,
  listMatchConversations,
  listMatchMessages,
  streamMatchChat,
  type ChatMessage,
  type Conversation,
  type MatchInfluencerCard,
  type TrajectoryStep,
} from '@/api/agent'
import { formatFollowers, formatPlatform } from '@/api/influencer'
import { INFLUENCER_ROUTES } from '@/constants/routes'

type MsgFile = { file_id: number; name?: string }
type UiMessage = ChatMessage & {
  files?: MsgFile[]
  trajectory?: TrajectoryStep[]
  influencers?: MatchInfluencerCard[]
}

const router = useRouter()
const conversations = ref<Conversation[]>([])
const activeId = ref<number | null>(null)
const messages = ref<UiMessage[]>([])
const streamingContent = ref('')
const streaming = ref(false)
const input = ref('')
const thinkingText = ref('')
const thinkingVisible = ref(false)
const thinkCollapsed = ref(true)
const thinkClosed = ref(false)
const trajectorySteps = ref<TrajectoryStep[]>([])
const trajLiveCollapsed = ref(false)
const histTrajOpen = ref<Record<number, boolean>>({})
const pendingFiles = ref<MsgFile[]>([])
const liveCards = ref<MatchInfluencerCard[]>([])
const msgBoxRef = ref<HTMLElement | null>(null)
let chatAbort: AbortController | null = null

const displayMessages = computed(() => messages.value)

function roleLabel(role: string) {
  if (role === 'user') return '商单'
  if (role === 'assistant') return '筛库结果'
  return role
}

function displayText(raw: string) {
  return (raw || '').replace(/\r\n/g, '\n').trim()
}

function openInfluencer(id?: number) {
  if (!id) return
  router.push(INFLUENCER_ROUTES.influencerDetail(id))
}

function trajTagType(status?: string) {
  if (status === 'error' || status === 'failed') return 'danger'
  if (status === 'ok' || status === 'done') return 'success'
  return 'info'
}

function shortTrajDetail(t: TrajectoryStep) {
  const s = (t.detail || t.reason || t.tool || '').trim()
  return s.length > 80 ? `${s.slice(0, 80)}…` : s
}

function trajSummary(steps: TrajectoryStep[]) {
  const tools = steps.map((s) => s.tool || s.title).filter(Boolean)
  const uniq = [...new Set(tools)].slice(0, 4)
  return uniq.join(' · ')
}

function toggleHistTraj(id?: number) {
  if (id == null) return
  histTrajOpen.value[id] = !histTrajOpen.value[id]
}

function isHistTrajOpen(id?: number) {
  if (id == null) return false
  return !!histTrajOpen.value[id]
}

function handleAgentEvent(event: string, data: unknown) {
  const payload = (data && typeof data === 'object' ? data : {}) as Record<string, unknown>
  if (event === 'message.delta') {
    streamingContent.value += String(payload.content || '')
    nextTick(scrollBottom)
  } else if (event === 'think.delta' || event === 'thought.delta') {
    thinkingVisible.value = true
    thinkingText.value += String(payload.content || payload.text || '')
  } else if (event === 'think.open') {
    thinkingVisible.value = true
    thinkClosed.value = false
  } else if (event === 'think.close') {
    thinkClosed.value = true
  } else if (event === 'trajectory.step') {
    trajectorySteps.value.push({
      round: payload.round as number | undefined,
      kind: payload.kind as string | undefined,
      title: String(payload.title || payload.tool || '步骤'),
      detail: String(payload.detail || ''),
      status: String(payload.status || 'ok'),
      reason: String(payload.reason || ''),
      tool: String(payload.tool || ''),
    })
  } else if (event === 'match.cards' || event === 'done') {
    const items = payload.items || payload.influencers
    if (Array.isArray(items) && items.length) {
      liveCards.value = items as MatchInfluencerCard[]
      nextTick(scrollBottom)
    }
  } else if (event === 'file.ready') {
    const fileId = Number(payload.file_id)
    if (fileId) {
      pendingFiles.value.push({ file_id: fileId, name: String(payload.name || '') })
    }
  } else if (event === 'error') {
    ElMessage.error(String(payload.message || '筛库失败'))
  }
}

async function refreshMessagesFromServer() {
  if (!activeId.value) return
  const data = await listMatchMessages(activeId.value)
  messages.value = (data.items || []).map((m) => ({
    ...m,
    files: m.files?.length ? m.files : undefined,
    trajectory: m.trajectory?.length ? m.trajectory : undefined,
    influencers: m.influencers?.length ? m.influencers : undefined,
  }))
}

async function onDownload(fileId: number, name?: string) {
  try {
    await downloadWorkspaceFile(fileId, name)
  } catch (e: any) {
    ElMessage.error(e?.message || '下载失败')
  }
}

async function refreshConversations() {
  const data = await listMatchConversations()
  conversations.value = data.items || []
}

async function selectConversation(id: number) {
  activeId.value = id
  thinkingText.value = ''
  thinkingVisible.value = false
  thinkCollapsed.value = true
  thinkClosed.value = false
  trajectorySteps.value = []
  trajLiveCollapsed.value = true
  streamingContent.value = ''
  liveCards.value = []
  histTrajOpen.value = {}
  pendingFiles.value = []
  await refreshMessagesFromServer()
  await nextTick()
  scrollBottom()
}

async function onNewChat() {
  try {
    const data = await createMatchConversation('新商单筛库')
    await refreshConversations()
    await selectConversation(data.id)
  } catch {
    /* interceptor */
  }
}

async function onDeleteConv(id: number) {
  try {
    await deleteMatchConversation(id)
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

function onStop() {
  chatAbort?.abort()
  streaming.value = false
  thinkClosed.value = true
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
    ElMessage.error('无法创建会话，请确认智能体后端已在 :8003 启动')
    return
  }

  const conversationId = activeId.value
  input.value = ''
  streaming.value = true
  streamingContent.value = ''
  liveCards.value = []
  thinkingText.value = ''
  thinkingVisible.value = false
  thinkCollapsed.value = true
  thinkClosed.value = false
  trajectorySteps.value = []
  trajLiveCollapsed.value = false
  pendingFiles.value = []
  messages.value.push({ id: Date.now(), role: 'user', content: text })
  await nextTick()
  scrollBottom()

  chatAbort = streamMatchChat(conversationId, text, {
    onEvent: handleAgentEvent,
    onError(err) {
      ElMessage.error(err.message)
      streaming.value = false
      thinkClosed.value = true
    },
    async onDone() {
      streaming.value = false
      thinkClosed.value = true
      trajLiveCollapsed.value = true
      const files = pendingFiles.value.length ? [...pendingFiles.value] : undefined
      const traj = trajectorySteps.value.length ? [...trajectorySteps.value] : undefined
      const cards = liveCards.value.length ? [...liveCards.value] : undefined
      if (streamingContent.value || files?.length || cards?.length) {
        messages.value.push({
          id: Date.now() + 1,
          role: 'assistant',
          content: displayText(streamingContent.value || '筛库完成'),
          files,
          trajectory: traj,
          influencers: cards,
        })
        streamingContent.value = ''
        pendingFiles.value = []
        liveCards.value = []
      }
      try {
        await refreshMessagesFromServer()
        await refreshConversations()
      } catch {
        /* interceptor */
      }
      await nextTick()
      scrollBottom()
    },
  })
}

onMounted(async () => {
  await refreshConversations()
  if (conversations.value.length) {
    await selectConversation(conversations.value[0].id)
  }
})

onUnmounted(() => {
  chatAbort?.abort()
})
</script>

<style scoped>
.match-agent {
  display: flex;
  height: calc(100vh - 120px);
  min-height: 520px;
  gap: 12px;
}
.match-left {
  width: 260px;
  flex-shrink: 0;
  background: #fff;
  border: 1px solid #ebeef5;
  border-radius: 8px;
  padding: 12px;
  display: flex;
  flex-direction: column;
}
.left-header {
  margin-bottom: 8px;
}
.left-hint {
  margin: 0 0 10px;
  font-size: 12px;
  color: #909399;
  line-height: 1.5;
}
.conv-scroll {
  flex: 1;
  min-height: 0;
}
.conv-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 10px;
  border-radius: 6px;
  cursor: pointer;
  margin-bottom: 4px;
}
.conv-item:hover,
.conv-item.active {
  background: #ecf5ff;
}
.conv-title {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13px;
}
.match-center {
  flex: 1;
  min-width: 0;
  background: #fff;
  border: 1px solid #ebeef5;
  border-radius: 8px;
  display: flex;
  flex-direction: column;
  padding: 12px;
}
.center-title {
  font-weight: 600;
  margin-bottom: 8px;
  color: #303133;
}
.msg-box {
  flex: 1;
  overflow: auto;
  padding: 8px 4px 16px;
}
.empty-tip {
  color: #909399;
  font-size: 13px;
  line-height: 1.6;
  padding: 24px 12px;
  background: #f5f7fa;
  border-radius: 8px;
}
.msg {
  margin-bottom: 14px;
}
.msg-role {
  font-size: 12px;
  color: #909399;
  margin-bottom: 4px;
}
.msg-content {
  background: #f5f7fa;
  border-radius: 8px;
  padding: 10px 12px;
  white-space: pre-wrap;
  word-break: break-word;
  line-height: 1.55;
}
.msg.user .msg-content {
  background: #ecf5ff;
}
.card-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 10px;
  margin-top: 10px;
}
.inf-card {
  text-align: left;
  border: 1px solid #e4e7ed;
  background: #fff;
  border-radius: 10px;
  padding: 12px;
  cursor: pointer;
  transition: border-color 0.15s, box-shadow 0.15s;
}
.inf-card:hover {
  border-color: #409eff;
  box-shadow: 0 2px 10px rgba(64, 158, 255, 0.12);
}
.inf-card-top {
  display: flex;
  align-items: flex-start;
  gap: 10px;
}
.inf-avatar {
  width: 44px;
  height: 44px;
  border-radius: 50%;
  object-fit: cover;
  flex-shrink: 0;
  background: #f2f3f5;
}
.inf-avatar.placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  color: #909399;
  font-weight: 600;
}
.inf-main {
  flex: 1;
  min-width: 0;
}
.inf-name {
  font-weight: 600;
  color: #303133;
  font-size: 14px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.inf-name .rank {
  color: #409eff;
  margin-right: 4px;
}
.inf-sub {
  margin-top: 2px;
  font-size: 12px;
  color: #909399;
}
.inf-meta {
  margin-top: 8px;
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  font-size: 12px;
  color: #606266;
}
.inf-tags {
  margin-top: 8px;
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}
.inf-line {
  margin-top: 8px;
  font-size: 12px;
  color: #606266;
  line-height: 1.4;
}
.inf-policy {
  margin-top: 8px;
  font-size: 12px;
  color: #909399;
  line-height: 1.45;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.inf-footer {
  margin-top: 10px;
  font-size: 12px;
  color: #409eff;
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
.trace-card {
  background: #fff;
  border: 1px dashed #dcdfe6;
  border-radius: 8px;
  margin: 8px 0 12px;
  overflow: hidden;
}
.trace-header,
.think-header {
  width: 100%;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  border: 0;
  background: transparent;
  cursor: pointer;
  text-align: left;
}
.trace-title,
.think-title {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
  font-size: 13px;
  color: #606266;
}
.trace-summary {
  font-weight: 400;
  color: #909399;
  font-size: 12px;
}
.think-toggle {
  font-size: 12px;
  color: #909399;
}
.trace-body,
.think-body {
  padding: 0 12px 10px;
  max-height: 220px;
  overflow: auto;
  border-top: 1px dashed #ebeef5;
  white-space: pre-wrap;
  font-size: 12px;
  color: #606266;
}
.traj-line {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin: 6px 0;
  line-height: 1.4;
}
.traj-detail {
  color: #909399;
  font-size: 12px;
}
.think-card {
  border: 1px solid #e4e7ed;
  border-radius: 8px;
  margin-bottom: 12px;
  overflow: hidden;
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
  animation: pulse 1.2s infinite;
}
@keyframes pulse {
  0% {
    opacity: 0.4;
  }
  50% {
    opacity: 1;
  }
  100% {
    opacity: 0.4;
  }
}
.composer {
  border-top: 1px solid #ebeef5;
  padding-top: 12px;
}
.composer-actions {
  margin-top: 8px;
  display: flex;
  gap: 8px;
}
</style>
