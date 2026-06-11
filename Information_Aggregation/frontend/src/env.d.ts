/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_INFLUENCER_API_TARGET?: string
  readonly VITE_MEETING_API_TARGET?: string
  readonly VITE_MEETING_APP_PATH?: string
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
