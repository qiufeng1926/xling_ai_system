<template>
  <div
    class="meeting-solo-host"
    :class="iframeModeClass"
  >
    <iframe
      ref="frameRef"
      class="meeting-solo-host__frame"
      :src="meetingAppUrl"
      title="会议 AI 单人录制"
      allow="microphone; autoplay"
      @load="onFrameLoad"
      @error="onFrameError"
    />
    <button
      v-if="overlayExpanded"
      type="button"
      class="meeting-solo-host__overlay-close"
      aria-label="收起录制窗口"
      @click="collapseOverlay"
    >
      收起
    </button>
  </div>

  <button
    v-if="showPipHint"
    type="button"
    class="recording-pip-hint"
    @click="openPipPanel"
  >
    📌 屏幕置顶（切到其他网页时保持可见）
  </button>

  <transition name="recording-ball-fade">
    <RecordingFloatBall
      v-if="showFloatBall"
      :title="barTitle"
      :meeting-name="meetingName"
      :elapsed-label="elapsedLabel"
      :disconnected="disconnected"
      :recording="recording"
      :generating="generating"
      @expand="expandOverlay"
      @dismiss="dismissBar"
      @pip="openPipPanel"
    />
  </transition>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { MEETING_ROUTES } from '@/constants/routes'
import RecordingFloatBall from '@/components/RecordingFloatBall.vue'
import {
  applyPortalRecordingState,
  dismissRecordingBar,
  pinMeetingIframe,
  resetPortalRecordingState,
  useMeetingSoloRecorder,
} from '@/composables/useMeetingSoloRecorder'
import {
  isRecordingPipOpen,
  notifyBackgroundRecording,
  openRecordingPip,
  resetRecordingPipSession,
  updateRecordingPip,
} from '@/composables/useRecordingPip'
import { useUserStore } from '@/stores/user'

const route = useRoute()
const userStore = useUserStore()
const frameRef = ref<HTMLIFrameElement | null>(null)
const overlayExpanded = ref(false)
const pipTipShown = ref(false)
const iframeLoadCount = ref(0)
const lastIframeLoadAt = ref<number | null>(null)

function logPortalDiagnostic(event: string, detail: Record<string, unknown>) {
  console.warn(`[xlink][portal-diagnostic] ${event}`, detail)
}

const {
  recording,
  meetingName,
  disconnected,
  generating,
  barVisible,
  elapsedLabel,
  barTitle,
  frameReady,
  frameLoadError,
} = useMeetingSoloRecorder()

const onSoloPage = computed(() => route.path.startsWith(MEETING_ROUTES.solo))

const showFloatBall = computed(
  () => barVisible.value && !onSoloPage.value && !overlayExpanded.value
)

const showPipHint = computed(
  () => barVisible.value && !isRecordingPipOpen()
)

const iframeModeClass = computed(() => {
  if (overlayExpanded.value) return 'meeting-solo-host--overlay'
  if (onSoloPage.value) return 'meeting-solo-host--solo'
  return 'meeting-solo-host--backstage'
})

const meetingAppUrl = computed(() => {
  const base = import.meta.env.VITE_MEETING_APP_PATH || '/meeting-app/'
  const sep = base.includes('?') ? '&' : '?'
  return `${base}${sep}embedded=1&portal_host=1&v=20260706c`
})

const pipState = computed(() => ({
  title: barTitle.value,
  meetingName: meetingName.value,
  elapsedLabel: elapsedLabel.value,
  disconnected: disconnected.value,
}))

function onFrameLoad() {
  iframeLoadCount.value += 1
  lastIframeLoadAt.value = Date.now()
  frameReady.value = true
  frameLoadError.value = false
  pinMeetingIframe()
  logPortalDiagnostic('iframe_load', {
    load_count: iframeLoadCount.value,
    route: route.path,
    recording: recording.value,
    generating: generating.value,
    disconnected: disconnected.value,
    bar_visible: barVisible.value,
    iframe_mode: iframeModeClass.value,
    meeting_app_url: meetingAppUrl.value,
  })
  if (iframeLoadCount.value > 1 && (recording.value || generating.value || disconnected.value)) {
    logPortalDiagnostic('iframe_reload_during_session', {
      load_count: iframeLoadCount.value,
      route: route.path,
      recording: recording.value,
      generating: generating.value,
      disconnected: disconnected.value,
    })
  }
}

function onFrameError() {
  frameLoadError.value = true
}

function requestIframeStateSync() {
  const win = frameRef.value?.contentWindow
  if (win) {
    win.postMessage({ type: 'xlink:recording-state-request' }, window.location.origin)
  }
}

function relayPortalVisibility() {
  const win = frameRef.value?.contentWindow
  if (!win) return
  const hidden = document.visibilityState === 'hidden'
  win.postMessage({ type: 'xlink:portal-visibility', hidden }, window.location.origin)
  if (hidden && barVisible.value && (recording.value || generating.value)) {
    void notifyBackgroundRecording(barTitle.value)
  }
}

async function openPipPanel() {
  const ok = await openRecordingPip(pipState.value)
  if (ok) {
    ElMessage.success('已开启屏幕置顶，切换其他网页时仍可看到录音状态')
    return
  }
  ElMessage.warning('无法打开置顶窗口，请允许弹窗后重试')
}

function dismissBar() {
  dismissRecordingBar()
  overlayExpanded.value = false
  resetRecordingPipSession()
  requestIframeStateSync()
}

function expandOverlay() {
  overlayExpanded.value = true
  void nextTick(() => {
    requestIframeStateSync()
    relayPortalVisibility()
  })
}

function collapseOverlay() {
  overlayExpanded.value = false
}

function handlePortalMessage(event: MessageEvent) {
  if (event.origin !== window.location.origin) return
  const data = event.data
  if (!data) return

  if (data.type === 'xlink:ws-disconnect-diagnostic') {
    logPortalDiagnostic('ws_disconnect', {
      ...(data.diagnostics || {}),
      portal_route: route.path,
      portal_visibility: document.visibilityState,
      iframe_load_count: iframeLoadCount.value,
      last_iframe_load_at: lastIframeLoadAt.value,
      ms_since_iframe_load: lastIframeLoadAt.value
        ? Date.now() - lastIframeLoadAt.value
        : null,
      recording: recording.value,
      generating: generating.value,
      disconnected: disconnected.value,
    })
    return
  }

  if (data.type !== 'xlink:recording-state') return
  applyPortalRecordingState({
    recording: data.recording,
    meetingName: data.meetingName,
    statusText: data.statusText,
    startedAt: data.startedAt,
    disconnected: data.disconnected,
    generating: data.generating,
  })
}

watch(pipState, (state) => {
  if (isRecordingPipOpen()) {
    updateRecordingPip(state)
  }
}, { deep: true })

watch(recording, (active) => {
  if (active && !pipTipShown.value) {
    pipTipShown.value = true
    ElMessage.info({
      message: '如需浏览其他网页，请点击「屏幕置顶」，录音将在后台继续',
      duration: 5000,
      showClose: true,
    })
  }
  if (!active && !generating.value && !disconnected.value) {
    pipTipShown.value = false
    resetRecordingPipSession()
  }
})

watch(onSoloPage, (solo) => {
  if (solo) {
    overlayExpanded.value = false
    pinMeetingIframe()
    void nextTick(() => {
      requestIframeStateSync()
      relayPortalVisibility()
    })
  }
}, { immediate: true })

watch(barVisible, (visible) => {
  if (!visible) {
    overlayExpanded.value = false
    resetRecordingPipSession()
  }
})

watch(
  () => userStore.token,
  (token) => {
    if (!token) {
      overlayExpanded.value = false
      resetRecordingPipSession()
      resetPortalRecordingState()
    }
  }
)

onMounted(() => {
  window.addEventListener('message', handlePortalMessage)
  document.addEventListener('visibilitychange', relayPortalVisibility)
  relayPortalVisibility()
})

onUnmounted(() => {
  window.removeEventListener('message', handlePortalMessage)
  document.removeEventListener('visibilitychange', relayPortalVisibility)
})
</script>

<style scoped>
.meeting-solo-host {
  position: fixed;
  left: calc(240px + 20px);
  top: calc(60px + 20px);
  right: 20px;
  bottom: 20px;
  border-radius: 8px;
  overflow: hidden;
  background: #fff;
}

.meeting-solo-host--solo {
  z-index: 50;
  opacity: 1;
  pointer-events: auto;
}

.meeting-solo-host--backstage {
  z-index: 1;
  opacity: 0.01;
  pointer-events: none;
}

.meeting-solo-host--overlay {
  z-index: 2100;
  opacity: 1;
  pointer-events: auto;
  box-shadow: 0 12px 48px rgba(0, 0, 0, 0.2);
}

.meeting-solo-host__frame {
  width: 100%;
  height: 100%;
  border: none;
  display: block;
  background: #fff;
}

.meeting-solo-host__overlay-close {
  position: absolute;
  top: 12px;
  right: 12px;
  z-index: 2;
  padding: 6px 14px;
  border: none;
  border-radius: 6px;
  background: rgba(0, 0, 0, 0.55);
  color: #fff;
  font-size: 13px;
  cursor: pointer;
}

.meeting-solo-host__overlay-close:hover {
  background: rgba(0, 0, 0, 0.72);
}

.recording-pip-hint {
  position: fixed;
  right: 24px;
  bottom: 24px;
  z-index: 2190;
  padding: 8px 14px;
  border: none;
  border-radius: 999px;
  background: linear-gradient(135deg, #1a3a5c 0%, #0d2137 100%);
  color: #fff;
  font-size: 12px;
  cursor: pointer;
  box-shadow: 0 6px 20px rgba(0, 0, 0, 0.18);
}

.recording-pip-hint:hover {
  filter: brightness(1.08);
}

.recording-ball-fade-enter-active,
.recording-ball-fade-leave-active {
  transition: transform 0.2s ease, opacity 0.2s ease;
}

.recording-ball-fade-enter-from,
.recording-ball-fade-leave-to {
  transform: translateY(12px) scale(0.92);
  opacity: 0;
}
</style>
