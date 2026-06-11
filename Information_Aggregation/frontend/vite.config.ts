import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'
import { fileURLToPath, URL } from 'node:url'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const influencerApiTarget = env.VITE_INFLUENCER_API_TARGET || env.VITE_API_TARGET || 'http://127.0.0.1:8000'
  const meetingApiTarget = env.VITE_MEETING_API_TARGET || 'http://127.0.0.1:8001'

  const meetingApiPrefixes = [
    '/api/auth',
    '/api/meeting',
    '/api/meetings',
    '/api/ws',
    '/api/admin',
    '/api/export',
    '/api/settings',
  ]

  const proxy: Record<string, object> = {
    '/api/v1': {
      target: influencerApiTarget,
      changeOrigin: true,
    },
    '/meeting-app': {
      target: meetingApiTarget,
      changeOrigin: true,
      rewrite: (path: string) => path.replace(/^\/meeting-app/, '') || '/',
    },
    '/static': {
      target: meetingApiTarget,
      changeOrigin: true,
    },
  }

  for (const prefix of meetingApiPrefixes) {
    proxy[prefix] = {
      target: meetingApiTarget,
      changeOrigin: true,
      ws: prefix === '/api/ws',
    }
  }

  return {
    plugins: [vue()],
    resolve: {
      alias: {
        '@': fileURLToPath(new URL('./src', import.meta.url)),
      },
    },
    server: {
      host: '0.0.0.0',
      port: Number(env.VITE_DEV_PORT || 5173),
      strictPort: false,
      allowedHosts: true,
      proxy,
    },
    preview: {
      host: '0.0.0.0',
      port: Number(env.VITE_PREVIEW_PORT || 4173),
      allowedHosts: true,
      proxy,
    },
  }
})
