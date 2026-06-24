import { onMounted, onUnmounted } from 'vue'
import { notificationBus } from '@/utils/notificationBus'

const FALLBACK_POLL_MS = 30000
const DEBOUNCE_MS = 600

function debounce(fn: () => void, ms: number) {
  let timer: ReturnType<typeof setTimeout> | null = null
  return () => {
    if (timer) clearTimeout(timer)
    timer = setTimeout(fn, ms)
  }
}

function connectStream(url: string, onMessage: () => void): () => void {
  let source: EventSource | null = null
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null
  let stopped = false
  let retryDelay = 5000

  function connect() {
    const token = localStorage.getItem('token')
    if (!token || stopped) return

    source = new EventSource(`${url}?token=${encodeURIComponent(token)}`)
    source.onmessage = () => {
      retryDelay = 5000
      onMessage()
    }
    source.onerror = () => {
      source?.close()
      source = null
      if (!stopped) {
        reconnectTimer = setTimeout(() => {
          retryDelay = Math.min(retryDelay * 2, 60000)
          connect()
        }, retryDelay)
      }
    }
  }

  connect()

  return () => {
    stopped = true
    if (reconnectTimer) clearTimeout(reconnectTimer)
    source?.close()
  }
}

export function useUserNotifications(onRefresh: () => void | Promise<void>) {
  let stopPortal: (() => void) | null = null
  let stopMeeting: (() => void) | null = null
  let fallbackTimer: ReturnType<typeof setInterval> | null = null

  const triggerRefresh = debounce(() => {
    notificationBus.emit()
    void onRefresh()
  }, DEBOUNCE_MS)

  function connect() {
    stopPortal?.()
    stopMeeting?.()
    stopPortal = connectStream('/api/v1/notifications/stream', triggerRefresh)
    stopMeeting = connectStream('/api/notifications/stream', triggerRefresh)
  }

  function onVisibilityChange() {
    if (!document.hidden) {
      triggerRefresh()
    }
  }

  onMounted(() => {
    connect()
    fallbackTimer = setInterval(() => {
      if (!document.hidden) {
        triggerRefresh()
      }
    }, FALLBACK_POLL_MS)
    document.addEventListener('visibilitychange', onVisibilityChange)
  })

  onUnmounted(() => {
    stopPortal?.()
    stopMeeting?.()
    if (fallbackTimer) clearInterval(fallbackTimer)
    document.removeEventListener('visibilitychange', onVisibilityChange)
  })

  return { reconnect: connect }
}

export function useNotificationListener(handler: () => void | Promise<void>) {
  let stop: (() => void) | null = null
  const debouncedHandler = debounce(() => {
    void handler()
  }, DEBOUNCE_MS)

  onMounted(() => {
    stop = notificationBus.on(() => {
      debouncedHandler()
    })
  })

  onUnmounted(() => {
    stop?.()
  })
}
