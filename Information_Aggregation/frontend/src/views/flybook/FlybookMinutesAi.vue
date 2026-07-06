<template>
  <div class="flybook-minutes">
    <aside class="flybook-minutes__sidebar">
      <div class="flybook-minutes__sidebar-head">
        <div>
          <h2>妙纪 AI</h2>
          <p v-if="portalLabel" class="flybook-minutes__account">xlink：{{ portalLabel }}</p>
        </div>
        <el-button size="small" :loading="loadingList" :disabled="!canUse" @click="loadMinutes">
          刷新
        </el-button>
      </div>

      <el-alert
        v-if="!bindStatus?.bound"
        type="warning"
        :closable="false"
        show-icon
        title="尚未绑定飞书"
        class="flybook-minutes__alert"
      >
        <template #default>
          妙纪 AI 基于飞书妙记，请先绑定飞书账号。
          <el-button link type="primary" :loading="binding" @click="handleBind">去绑定</el-button>
        </template>
      </el-alert>

      <el-alert
        v-else-if="needsMinutesReauth"
        type="warning"
        :closable="false"
        show-icon
        title="需要重新授权妙记权限"
        class="flybook-minutes__alert"
      >
        <template #default>
          缺少妙记相关权限（minutes:minutes.upload:write、minutes:minutes.search:read 等）。
          请先在飞书开放平台开通「上传音视频并创建妙记」用户身份权限，再点击重新授权。
          <el-button type="primary" size="small" :loading="binding" @click="handleBind">
            重新授权
          </el-button>
        </template>
      </el-alert>

      <el-skeleton v-if="loadingList" :rows="8" animated />
      <el-scrollbar v-else class="flybook-minutes__list-wrap">
        <ul v-if="minutesList.length" class="flybook-minutes__list">
          <li
            v-for="item in minutesList"
            :key="item.token"
            :class="{ active: selectedToken === item.token }"
            @click="selectMinute(item)"
          >
            <span class="flybook-minutes__icon">记</span>
            <span class="flybook-minutes__name" :title="item.title">{{ item.title }}</span>
          </li>
        </ul>
        <el-empty v-else description="暂无妙记，开始录音后将出现在飞书" />
      </el-scrollbar>
    </aside>

    <section class="flybook-minutes__main">
      <div class="flybook-minutes__toolbar">
        <el-button
          v-if="!recording"
          type="primary"
          :disabled="!canUse || finishing"
          @click="startRecording"
        >
          开始录音
        </el-button>
        <el-button v-else type="danger" :loading="finishing" @click="stopRecording">
          结束并生成妙记
        </el-button>
        <span v-if="recording" class="flybook-minutes__rec-dot">● 录音中 {{ formatDuration(elapsedSec) }}</span>
        <span v-if="wsConnected" class="flybook-minutes__ws-tag">飞书实时转写已连接</span>
      </div>

      <el-row :gutter="16" class="flybook-minutes__panels">
        <el-col :span="12">
          <el-card shadow="never" header="实时转写（飞书 ASR）">
            <div ref="transcriptRef" class="flybook-minutes__transcript">
              <p v-if="!transcriptLines.length" class="flybook-minutes__placeholder">
                点击「开始录音」后，语音将经 flybook 转发至飞书流式识别 API。
              </p>
              <p v-for="(line, idx) in transcriptLines" :key="idx">{{ line }}</p>
            </div>
          </el-card>
        </el-col>
        <el-col :span="12">
          <el-card shadow="never">
            <template #header>
              <div class="flybook-minutes__card-head">
                <span>飞书妙记 AI 纪要</span>
                <el-button
                  v-if="selectedToken && !artifacts?.ready"
                  link
                  type="primary"
                  :loading="loadingArtifacts"
                  @click="refreshArtifacts(true)"
                >
                  刷新
                </el-button>
                <el-button
                  v-if="selectedMinute?.url"
                  link
                  type="primary"
                  @click="openInFeishu(selectedMinute.url!)"
                >
                  在飞书打开
                </el-button>
              </div>
            </template>
            <div v-if="loadingArtifacts || finishing" class="flybook-minutes__loading">
              <el-icon class="is-loading"><Loading /></el-icon>
              <span>飞书正在生成 AI 纪要…</span>
            </div>
            <template v-else-if="artifacts?.ready">
              <h4>总结</h4>
              <p class="flybook-minutes__summary">{{ artifacts.summary || '（暂无总结）' }}</p>
              <template v-if="artifacts.chapters?.length">
                <h4>章节</h4>
                <ul class="flybook-minutes__chapters">
                  <li v-for="(ch, i) in artifacts.chapters" :key="i">
                    <strong>{{ ch.title }}</strong>
                    <p>{{ ch.summary_content }}</p>
                  </li>
                </ul>
              </template>
              <template v-if="artifacts.todos?.length">
                <h4>待办</h4>
                <ul class="flybook-minutes__todos">
                  <li v-for="(td, i) in artifacts.todos" :key="i">
                    {{ td.content }}
                    <span v-if="td.assignees?.length">（{{ td.assignees.join('、') }}）</span>
                  </li>
                </ul>
              </template>
            </template>
            <p v-else class="flybook-minutes__placeholder">
              结束录音后将上传至飞书妙记，AI 总结/章节/待办由飞书生成。
            </p>
          </el-card>
        </el-col>
      </el-row>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Loading } from '@element-plus/icons-vue'
import {
  buildMinutesTranscribeWsUrl,
  finishFeishuMinutesSession,
  getFeishuBindStatus,
  getFeishuMinuteArtifacts,
  getFlybookErrorMessage,
  getMinutesBindStatus,
  searchFeishuMinutes,
  startFeishuBind,
  type FeishuBindStatus,
  type FeishuMinutesArtifacts,
  type FeishuMinutesItem,
} from '@/api/flybook'
import { FLYBOOK_ROUTES } from '@/constants/routes'
import { useUserStore } from '@/stores/user'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()

const bindStatus = ref<FeishuBindStatus | null>(null)
const minutesAuthorized = ref(false)
const binding = ref(false)
const loadingList = ref(false)
const loadingArtifacts = ref(false)
const finishing = ref(false)
const recording = ref(false)
const wsConnected = ref(false)
const elapsedSec = ref(0)
const minutesList = ref<FeishuMinutesItem[]>([])
const selectedToken = ref('')
const selectedMinute = ref<FeishuMinutesItem | null>(null)
const artifacts = ref<FeishuMinutesArtifacts | null>(null)
const transcriptLines = ref<string[]>([])
const transcriptRef = ref<HTMLElement | null>(null)

let ws: WebSocket | null = null
let mediaStream: MediaStream | null = null
let audioContext: AudioContext | null = null
let processor: ScriptProcessorNode | null = null
let mediaRecorder: MediaRecorder | null = null
const recordedChunks: Blob[] = []
let elapsedTimer: ReturnType<typeof setInterval> | null = null

const portalLabel = computed(
  () =>
    bindStatus.value?.portal_nickname ||
    bindStatus.value?.portal_username ||
    userStore.userInfo?.nickname ||
    userStore.userInfo?.username ||
    ''
)

const needsMinutesReauth = computed(
  () => bindStatus.value?.bound === true && !minutesAuthorized.value
)

const canUse = computed(
  () => bindStatus.value?.bound && minutesAuthorized.value && bindStatus.value.token_valid !== false
)

function formatDuration(sec: number) {
  const m = Math.floor(sec / 60)
  const s = sec % 60
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}

function openInFeishu(url: string) {
  window.open(url, '_blank', 'noopener,noreferrer')
}

function floatTo16BitPCM(input: Float32Array) {
  const output = new Int16Array(input.length)
  for (let i = 0; i < input.length; i++) {
    const s = Math.max(-1, Math.min(1, input[i]))
    output[i] = s < 0 ? s * 0x8000 : s * 0x7fff
  }
  return output
}

function appendTranscript(text: string) {
  if (!text) return
  const last = transcriptLines.value[transcriptLines.value.length - 1]
  if (last === text) return
  transcriptLines.value.push(text)
  void nextTick(() => {
    if (transcriptRef.value) transcriptRef.value.scrollTop = transcriptRef.value.scrollHeight
  })
}

function connectWs() {
  return new Promise<void>((resolve, reject) => {
    ws = new WebSocket(buildMinutesTranscribeWsUrl())
    ws.binaryType = 'arraybuffer'
    ws.onopen = () => {
      wsConnected.value = true
      resolve()
    }
    ws.onerror = () => reject(new Error('飞书转写 WebSocket 连接失败'))
    ws.onclose = () => {
      wsConnected.value = false
    }
    ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(String(ev.data))
        if (msg.type === 'transcript' && msg.text) {
          appendTranscript(msg.text)
        } else if (msg.type === 'error') {
          ElMessage.error(msg.message || '飞书转写错误')
        }
      } catch {
        /* ignore */
      }
    }
  })
}

async function startRecording() {
  if (!canUse.value) {
    ElMessage.warning('请先完成飞书绑定并授权妙记权限')
    return
  }
  transcriptLines.value = []
  recordedChunks.length = 0
  elapsedSec.value = 0

  try {
    mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true })
    await connectWs()

    audioContext = new AudioContext({ sampleRate: 16000 })
    const source = audioContext.createMediaStreamSource(mediaStream)
    processor = audioContext.createScriptProcessor(4096, 1, 1)
    processor.onaudioprocess = (ev) => {
      if (!recording.value || !ws || ws.readyState !== WebSocket.OPEN) return
      const input = ev.inputBuffer.getChannelData(0)
      const pcm = floatTo16BitPCM(input)
      ws.send(pcm.buffer)
    }
    source.connect(processor)
    processor.connect(audioContext.destination)

    mediaRecorder = new MediaRecorder(mediaStream, { mimeType: 'audio/webm' })
    mediaRecorder.ondataavailable = (e) => {
      if (e.data.size > 0) recordedChunks.push(e.data)
    }
    mediaRecorder.start(1000)

    recording.value = true
    elapsedTimer = setInterval(() => {
      elapsedSec.value += 1
    }, 1000)
  } catch (err) {
    cleanupRecording()
    ElMessage.error(err instanceof Error ? err.message : '无法启动麦克风')
  }
}

function cleanupRecording() {
  if (elapsedTimer) {
    clearInterval(elapsedTimer)
    elapsedTimer = null
  }
  processor?.disconnect()
  processor = null
  if (audioContext) {
    void audioContext.close()
    audioContext = null
  }
  mediaStream?.getTracks().forEach((t) => t.stop())
  mediaStream = null
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: 'stop' }))
    ws.close()
  }
  ws = null
  wsConnected.value = false
  recording.value = false
}

async function stopRecording() {
  if (!recording.value) return
  finishing.value = true
  cleanupRecording()

  if (mediaRecorder && mediaRecorder.state !== 'inactive') {
    await new Promise<void>((resolve) => {
      mediaRecorder!.onstop = () => resolve()
      mediaRecorder!.stop()
    })
  }
  mediaRecorder = null

  const blob = new Blob(recordedChunks, { type: 'audio/webm' })
  if (!blob.size) {
    finishing.value = false
    ElMessage.warning('未录到有效音频')
    return
  }

  try {
    const filename = `xlink-minutes-${new Date().toISOString().replace(/[:.]/g, '-')}.webm`
    const res = await finishFeishuMinutesSession(blob, filename)
    const minute = res.minute
    artifacts.value = res.artifacts
    selectedToken.value = minute.token
    selectedMinute.value = {
      token: minute.token,
      title: minute.title || '新妙记',
      url: minute.url,
    }
    minutesList.value = [selectedMinute.value, ...minutesList.value.filter((m) => m.token !== minute.token)]
    ElMessage.success('已上传至飞书妙记，AI 纪要已生成')
  } catch (err) {
    ElMessage.error(getFlybookErrorMessage(err, '生成飞书妙记失败'))
  } finally {
    finishing.value = false
  }
}

async function selectMinute(item: FeishuMinutesItem) {
  selectedToken.value = item.token
  selectedMinute.value = item
  await refreshArtifacts(false)
}

async function refreshArtifacts(wait: boolean) {
  if (!selectedToken.value) return
  loadingArtifacts.value = true
  try {
    artifacts.value = await getFeishuMinuteArtifacts(selectedToken.value, wait)
  } catch (err) {
    artifacts.value = null
    ElMessage.error(getFlybookErrorMessage(err, '获取妙记 AI 产物失败'))
  } finally {
    loadingArtifacts.value = false
  }
}

async function loadMinutes() {
  if (!canUse.value) return
  loadingList.value = true
  try {
    const res = await searchFeishuMinutes()
    minutesList.value = res.items || []
  } catch (err) {
    minutesList.value = []
    ElMessage.error(getFlybookErrorMessage(err, '加载妙记列表失败'))
  } finally {
    loadingList.value = false
  }
}

async function handleBind() {
  binding.value = true
  try {
    window.location.href = await startFeishuBind(FLYBOOK_ROUTES.minutesAi)
  } finally {
    binding.value = false
  }
}

async function initPage() {
  try {
    const statusRes = await getFeishuBindStatus()
    bindStatus.value = statusRes.data
  } catch {
    bindStatus.value = null
  }
  try {
    const mins = await getMinutesBindStatus()
    minutesAuthorized.value = mins.minutes_authorized
  } catch {
    minutesAuthorized.value = bindStatus.value?.minutes_authorized ?? false
  }
  if (canUse.value) {
    await loadMinutes()
  }
}

onMounted(() => {
  if (route.query.bind === 'success') {
    ElMessage.success('飞书授权成功')
    router.replace({ path: FLYBOOK_ROUTES.minutesAi })
  }
  void initPage()
})

onBeforeUnmount(() => {
  cleanupRecording()
})
</script>

<style scoped>
.flybook-minutes {
  display: flex;
  min-height: calc(100vh - 120px);
  margin: -12px -16px;
  background: #f5f7fa;
}

.flybook-minutes__sidebar {
  width: 280px;
  flex-shrink: 0;
  background: #fff;
  border-right: 1px solid #ebeef5;
  display: flex;
  flex-direction: column;
}

.flybook-minutes__sidebar-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  padding: 16px;
  border-bottom: 1px solid #ebeef5;
  gap: 12px;
}

.flybook-minutes__sidebar-head h2 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
}

.flybook-minutes__account {
  margin: 4px 0 0;
  font-size: 12px;
  color: #909399;
}

.flybook-minutes__alert {
  margin: 12px;
}

.flybook-minutes__list-wrap {
  flex: 1;
  min-height: 0;
}

.flybook-minutes__list {
  list-style: none;
  margin: 0;
  padding: 8px;
}

.flybook-minutes__list li {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  border-radius: 6px;
  cursor: pointer;
}

.flybook-minutes__list li:hover,
.flybook-minutes__list li.active {
  background: #ecf5ff;
}

.flybook-minutes__icon {
  width: 28px;
  height: 28px;
  border-radius: 6px;
  background: #7b61ff;
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  flex-shrink: 0;
}

.flybook-minutes__name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13px;
}

.flybook-minutes__main {
  flex: 1;
  padding: 16px;
  min-width: 0;
}

.flybook-minutes__toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}

.flybook-minutes__rec-dot {
  color: #f56c6c;
  font-size: 13px;
}

.flybook-minutes__ws-tag {
  font-size: 12px;
  color: #67c23a;
}

.flybook-minutes__panels {
  min-height: 420px;
}

.flybook-minutes__transcript {
  height: 360px;
  overflow-y: auto;
  font-size: 14px;
  line-height: 1.7;
  color: #303133;
}

.flybook-minutes__placeholder {
  color: #909399;
  font-size: 13px;
  line-height: 1.6;
}

.flybook-minutes__card-head {
  display: flex;
  align-items: center;
  gap: 8px;
}

.flybook-minutes__summary {
  white-space: pre-wrap;
  line-height: 1.7;
  font-size: 14px;
}

.flybook-minutes__chapters,
.flybook-minutes__todos {
  padding-left: 18px;
  font-size: 13px;
  line-height: 1.6;
}

.flybook-minutes__loading {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #909399;
  padding: 24px 0;
}

h4 {
  margin: 16px 0 8px;
  font-size: 14px;
}
</style>
