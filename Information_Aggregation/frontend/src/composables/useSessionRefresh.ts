import { onMounted, onUnmounted } from 'vue'
import { useUserStore } from '@/stores/user'

/** 两次续期间最短间隔，避免频繁请求 */
const REFRESH_INTERVAL_MS = 30 * 60 * 1000
const ACTIVITY_DEBOUNCE_MS = 3000
const ACTIVITY_EVENTS = ['click', 'keydown', 'scroll', 'touchstart'] as const

function debounce(fn: () => void, ms: number) {
  let timer: ReturnType<typeof setTimeout> | null = null
  return () => {
    if (timer) clearTimeout(timer)
    timer = setTimeout(fn, ms)
  }
}

export function useSessionRefresh() {
  const userStore = useUserStore()
  let lastRefreshAt = 0
  let refreshing = false
  let debouncedOnActivity: (() => void) | null = null

  async function tryRefresh() {
    if (!userStore.token || refreshing) return
    const now = Date.now()
    if (now - lastRefreshAt < REFRESH_INTERVAL_MS) return

    refreshing = true
    try {
      await userStore.refreshSession()
      lastRefreshAt = Date.now()
    } catch {
      // 401 由 request 拦截器统一处理
    } finally {
      refreshing = false
    }
  }

  function onVisibilityChange() {
    if (!document.hidden) {
      void tryRefresh()
    }
  }

  onMounted(() => {
    void tryRefresh()
    debouncedOnActivity = debounce(() => {
      void tryRefresh()
    }, ACTIVITY_DEBOUNCE_MS)
    for (const event of ACTIVITY_EVENTS) {
      window.addEventListener(event, debouncedOnActivity, { passive: true })
    }
    document.addEventListener('visibilitychange', onVisibilityChange)
  })

  onUnmounted(() => {
    if (debouncedOnActivity) {
      for (const event of ACTIVITY_EVENTS) {
        window.removeEventListener(event, debouncedOnActivity)
      }
    }
    document.removeEventListener('visibilitychange', onVisibilityChange)
  })
}
