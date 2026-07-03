import { computed, ref } from 'vue'

export interface PortalRecordingState {
  recording?: boolean
  meetingName?: string
  statusText?: string
  startedAt?: number | null
  disconnected?: boolean
  generating?: boolean
}

const recording = ref(false)
const meetingName = ref('')
const statusText = ref('')
const startedAt = ref<number | null>(null)
const disconnected = ref(false)
const generating = ref(false)
const elapsedSeconds = ref(0)
const frameReady = ref(false)
const frameLoadError = ref(false)
/** 保持 iframe 实例存活，避免切页/返回时重新加载导致录音中断 */
const iframePinned = ref(false)

let tickTimer: ReturnType<typeof setInterval> | null = null

function stopTick() {
  if (tickTimer) {
    clearInterval(tickTimer)
    tickTimer = null
  }
}

function startTick() {
  stopTick()
  tickTimer = setInterval(() => {
    if (startedAt.value) {
      elapsedSeconds.value = Math.floor((Date.now() - startedAt.value) / 1000)
    }
  }, 1000)
}

function clearIdleState() {
  stopTick()
  elapsedSeconds.value = 0
  recording.value = false
  generating.value = false
  disconnected.value = false
  startedAt.value = null
  meetingName.value = ''
  statusText.value = ''
}

export function pinMeetingIframe() {
  iframePinned.value = true
}

export function unpinMeetingIframe() {
  iframePinned.value = false
  frameReady.value = false
}

export function applyPortalRecordingState(data: PortalRecordingState) {
  if (data.recording !== undefined) {
    recording.value = data.recording
  }
  if (data.meetingName !== undefined) {
    meetingName.value = data.meetingName
  }
  if (data.statusText !== undefined) {
    statusText.value = data.statusText
  }
  if (data.startedAt !== undefined) {
    startedAt.value = data.startedAt
  }
  if (data.disconnected !== undefined) {
    disconnected.value = data.disconnected
  }
  if (data.generating !== undefined) {
    generating.value = data.generating
  }

  const sessionActive = recording.value || generating.value || disconnected.value
  if (sessionActive) {
    pinMeetingIframe()
    if (startedAt.value && (recording.value || generating.value)) {
      elapsedSeconds.value = Math.floor((Date.now() - startedAt.value) / 1000)
      startTick()
    } else {
      stopTick()
    }
    return
  }

  clearIdleState()
}

export function resetPortalRecordingState() {
  clearIdleState()
  unpinMeetingIframe()
}

export function dismissRecordingBar() {
  clearIdleState()
}

export function useMeetingSoloRecorder() {
  const barVisible = computed(
    () => recording.value || generating.value || disconnected.value
  )

  const elapsedLabel = computed(() => {
    const total = elapsedSeconds.value
    const minutes = Math.floor(total / 60)
    const seconds = total % 60
    return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`
  })

  const barTitle = computed(() => {
    if (disconnected.value) return '录音连接已断开'
    if (generating.value) return '正在生成会议纪要'
    return '录音进行中'
  })

  return {
    recording,
    meetingName,
    statusText,
    startedAt,
    disconnected,
    generating,
    barVisible,
    iframePinned,
    elapsedLabel,
    barTitle,
    frameReady,
    frameLoadError,
    applyPortalRecordingState,
    resetPortalRecordingState,
    dismissRecordingBar,
    pinMeetingIframe,
    unpinMeetingIframe,
  }
}
