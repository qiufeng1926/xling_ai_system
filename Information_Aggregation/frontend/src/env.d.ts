/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_INFLUENCER_API_TARGET?: string
  readonly VITE_MEETING_API_TARGET?: string
  readonly VITE_FLYBOOK_API_TARGET?: string
  readonly VITE_MEETING_APP_PATH?: string
  readonly VITE_FLYBOOK_URL?: string
  /** @deprecated 使用 VITE_FLYBOOK_URL */
  readonly VITE_FEISHU_URL?: string
  readonly VITE_API_BASE_URL?: string
  readonly VITE_API_TARGET?: string
  readonly VITE_DEV_PORT?: string
  readonly VITE_PREVIEW_PORT?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}

declare module '*.vue' {
  import type { DefineComponent } from 'vue'
  const component: DefineComponent<{}, {}, any>
  export default component
}

declare module 'axios' {
  export interface AxiosRequestConfig {
    /** 为 true 时不弹出 ElMessage（用于后台轮询等） */
    silent?: boolean
  }
}
