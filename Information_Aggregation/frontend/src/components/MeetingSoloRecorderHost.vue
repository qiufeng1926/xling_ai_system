<template>
  <div
    class="meeting-solo-host"
    :class="onSoloPage ? 'meeting-solo-host--solo' : 'meeting-solo-host--background'"
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
  </div>

  <transition name="recording-bar-fade">
    <div
      v-if="barVisible && !onSoloPage"
      class="global-recording-bar"
      role="status"
      aria-live="polite"
    >
      <div class="global-recording-bar__main">
        <span
          class="global-recording-bar__dot"
          :class="{ 'global-recording-bar__dot--warn': disconnected }"
        />
        <div class="global-recording-bar__text">
          <strong>{{ barTitle }}</strong>
          <span v-if="meetingName" class="global-recording-bar__name">{{ meetingName }}</span>
          <span v-if="statusText" class="global-recording-bar__status">
            {{ statusText }}
          </span>
        </div>
        <span v-if="recording || generating" class="global-recording-bar__time">
          {{ elapsedLabel }}
        </span>
      </div>
      <el-button v-if="disconnected" type="default" size="small" @click="dismissBar">
        关闭
      </el-button>
      <el-button type="primary" size="small" @click="goToSolo">
        {{ disconnected ? '查看录制' : '返回录制' }}
      </el-button>
    </div>
  </transition>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { MEETING_ROUTES } from '@/constants/routes'
import {
  applyPortalRecordingState,
  dismissRecordingBar,
  pinMeetingIframe,
  resetPortalRecordingState,
  useMeetingSoloRecorder,
} from '@/composables/useMeetingSoloRecorder'
import { useUserStore } from '@/stores/user'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()
const frameRef = ref<HTMLIFrameElement | null>(null)

const {
  recording,
  meetingName,
  statusText,
  disconnected,
  generating,
  barVisible,
  elapsedLabel,
  barTitle,
  frameReady,
  frameLoadError,
} = useMeetingSoloRecorder()

const onSoloPage = computed(() => route.path.startsWith(MEETING_ROUTES.solo))

const meetingAppUrl = computed(() => {
  const base = import.meta.env.VITE_MEETING_APP_PATH || '/meeting-app/'
  const sep = base.includes('?') ? '&' : '?'
  return `${base}${sep}embedded=1&portal_host=1&v=20260703f`
})

function onFrameLoad() {
  frameReady.value = true
  frameLoadError.value = false
  pinMeetingIframe()
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

function dismissBar() {
  dismissRecordingBar()
  requestIframeStateSync()
}

function goToSolo() {
  if (!onSoloPage.value) {
    router.push(MEETING_ROUTES.solo)
  }
}

function handlePortalMessage(event: MessageEvent) {
  if (event.origin !== window.location.origin) return
  const data = event.data
  if (!data || data.type !== 'xlink:recording-state') return
  applyPortalRecordingState({
    recording: data.recording,
    meetingName: data.meetingName,
    statusText: data.statusText,
    startedAt: data.startedAt,
    disconnected: data.disconnected,
    generating: data.generating,
  })
}

watch(onSoloPage, (solo) => {
  if (solo) {
    pinMeetingIframe()
    void nextTick(() => {
      requestIframeStateSync()
    })
  }
}, { immediate: true })

watch(
  () => userStore.token,
  (token) => {
    if (!token) {
      resetPortalRecordingState()
    }
  }
)

onMounted(() => {
  window.addEventListener('message', handlePortalMessage)
})

onUnmounted(() => {
  window.removeEventListener('message', handlePortalMessage)
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

.meeting-solo-host--background {
  z-index: -1;
  opacity: 0;
  pointer-events: none;
}

.meeting-solo-host__frame {
  width: 100%;
  height: 100%;
  border: none;
  display: block;
  background: #fff;
}

.global-recording-bar {
  position: fixed;
  left: 240px;
  right: 0;
  bottom: 0;
  z-index: 2100;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 10px 20px;
  background: linear-gradient(90deg, #1a3a5c 0%, #0d2137 100%);
  color: #fff;
  box-shadow: 0 -4px 16px rgba(0, 0, 0, 0.15);
}

.global-recording-bar__main {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
  flex: 1;
}

.global-recording-bar__dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: #f56c6c;
  flex-shrink: 0;
  animation: recording-pulse 1.2s ease-in-out infinite;
}

.global-recording-bar__dot--warn {
  background: #e6a23c;
  animation: none;
}

.global-recording-bar__text {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.global-recording-bar__text strong {
  font-size: 14px;
  font-weight: 600;
}

.global-recording-bar__name,
.global-recording-bar__status {
  font-size: 12px;
  opacity: 0.88;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.global-recording-bar__time {
  font-variant-numeric: tabular-nums;
  font-size: 15px;
  font-weight: 600;
  flex-shrink: 0;
}

.recording-bar-fade-enter-active,
.recording-bar-fade-leave-active {
  transition: transform 0.2s ease, opacity 0.2s ease;
}

.recording-bar-fade-enter-from,
.recording-bar-fade-leave-to {
  transform: translateY(100%);
  opacity: 0;
}

@keyframes recording-pulse {
  0%,
  100% {
    opacity: 1;
    transform: scale(1);
  }
  50% {
    opacity: 0.5;
    transform: scale(0.85);
  }
}
</style>
