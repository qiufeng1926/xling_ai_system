<template>
  <div
    ref="ballRef"
    class="recording-float-ball"
    :style="ballStyle"
    role="status"
    aria-live="polite"
    @pointerdown="onPointerDown"
  >
    <button type="button" class="recording-float-ball__main" @click.stop="emit('expand')">
      <span
        class="recording-float-ball__dot"
        :class="{ 'recording-float-ball__dot--warn': disconnected }"
      />
      <span class="recording-float-ball__info">
        <strong>{{ title }}</strong>
        <span v-if="meetingName" class="recording-float-ball__name">{{ meetingName }}</span>
        <span v-if="showTime" class="recording-float-ball__time">{{ elapsedLabel }}</span>
      </span>
    </button>
    <button
      type="button"
      class="recording-float-ball__pip"
      title="屏幕置顶，切到其他网页时仍可看到"
      aria-label="屏幕置顶"
      @click.stop="emit('pip')"
    >
      📌
    </button>
    <button
      v-if="disconnected"
      type="button"
      class="recording-float-ball__close"
      aria-label="关闭"
      @click.stop="emit('dismiss')"
    >
      ×
    </button>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

const props = defineProps<{
  title: string
  meetingName?: string
  elapsedLabel?: string
  disconnected?: boolean
  recording?: boolean
  generating?: boolean
}>()

const emit = defineEmits<{
  expand: []
  dismiss: []
  pip: []
}>()

const ballRef = ref<HTMLElement | null>(null)
const posX = ref<number | null>(null)
const posY = ref<number | null>(null)
const dragging = ref(false)

const showTime = computed(() => props.recording || props.generating)

const ballStyle = computed(() => {
  if (posX.value === null || posY.value === null) return undefined
  return {
    left: `${posX.value}px`,
    top: `${posY.value}px`,
    right: 'auto',
    bottom: 'auto',
  }
})

let dragOffsetX = 0
let dragOffsetY = 0

function clampPosition(x: number, y: number) {
  const el = ballRef.value
  if (!el) return { x, y }
  const rect = el.getBoundingClientRect()
  const maxX = window.innerWidth - rect.width - 8
  const maxY = window.innerHeight - rect.height - 8
  return {
    x: Math.min(Math.max(8, x), maxX),
    y: Math.min(Math.max(8, y), maxY),
  }
}

function onPointerDown(event: PointerEvent) {
  const target = event.target as HTMLElement
  if (target.closest('.recording-float-ball__close')) return
  if (target.closest('.recording-float-ball__pip')) return
  const el = ballRef.value
  if (!el) return
  dragging.value = true
  const rect = el.getBoundingClientRect()
  if (posX.value === null) {
    posX.value = rect.left
    posY.value = rect.top
  }
  dragOffsetX = event.clientX - rect.left
  dragOffsetY = event.clientY - rect.top
  el.setPointerCapture(event.pointerId)

  const onMove = (e: PointerEvent) => {
    if (!dragging.value) return
    const next = clampPosition(e.clientX - dragOffsetX, e.clientY - dragOffsetY)
    posX.value = next.x
    posY.value = next.y
  }

  const onUp = (e: PointerEvent) => {
    dragging.value = false
    el.releasePointerCapture(e.pointerId)
    window.removeEventListener('pointermove', onMove)
    window.removeEventListener('pointerup', onUp)
  }

  window.addEventListener('pointermove', onMove)
  window.addEventListener('pointerup', onUp)
}

onMounted(() => {
  posX.value = null
  posY.value = null
})
</script>

<style scoped>
.recording-float-ball {
  position: fixed;
  right: 24px;
  bottom: 88px;
  z-index: 2200;
  display: flex;
  align-items: stretch;
  max-width: min(320px, calc(100vw - 280px));
  border-radius: 999px;
  box-shadow: 0 8px 28px rgba(0, 0, 0, 0.22);
  background: linear-gradient(135deg, #1a3a5c 0%, #0d2137 100%);
  color: #fff;
  user-select: none;
  touch-action: none;
}

.recording-float-ball__main {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
  padding: 10px 16px;
  border: none;
  background: transparent;
  color: inherit;
  cursor: pointer;
  text-align: left;
}

.recording-float-ball__dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: #f56c6c;
  flex-shrink: 0;
  animation: recording-ball-pulse 1.2s ease-in-out infinite;
}

.recording-float-ball__dot--warn {
  background: #e6a23c;
  animation: none;
}

.recording-float-ball__info {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.recording-float-ball__info strong {
  font-size: 13px;
  font-weight: 600;
}

.recording-float-ball__name {
  font-size: 11px;
  opacity: 0.9;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.recording-float-ball__time {
  font-size: 12px;
  font-variant-numeric: tabular-nums;
  opacity: 0.92;
}

.recording-float-ball__pip {
  width: 36px;
  border: none;
  border-left: 1px solid rgba(255, 255, 255, 0.15);
  background: transparent;
  color: #fff;
  font-size: 14px;
  cursor: pointer;
}

.recording-float-ball__pip:hover {
  background: rgba(255, 255, 255, 0.08);
}

.recording-float-ball__close {
  width: 32px;
  border: none;
  border-left: 1px solid rgba(255, 255, 255, 0.15);
  background: transparent;
  color: #fff;
  font-size: 18px;
  line-height: 1;
  cursor: pointer;
  border-radius: 0 999px 999px 0;
}

.recording-float-ball__close:hover {
  background: rgba(255, 255, 255, 0.08);
}

@keyframes recording-ball-pulse {
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
