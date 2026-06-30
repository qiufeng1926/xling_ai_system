import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'
import basicSsl from '@vitejs/plugin-basic-ssl'
import { fileURLToPath, URL } from 'node:url'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const devHttps = env.VITE_DEV_HTTPS === 'true'
  const influencerApiTarget = env.VITE_INFLUENCER_API_TARGET || env.VITE_API_TARGET || 'http://127.0.0.1:8000'
  const meetingApiTarget = env.VITE_MEETING_API_TARGET || 'http://127.0.0.1:8001'
  const flybookApiTarget = env.VITE_FLYBOOK_API_TARGET || 'http://127.0.0.1:8002'

  const meetingApiPrefixes = [
    '/api/auth',
    '/api/meeting',
    '/api/meetings',
    '/api/notifications',
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
    '/api/flybook': {
      target: flybookApiTarget,
      changeOrigin: true,
      ws: true,
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

  const meetingProxyOptions = {
    target: meetingApiTarget,
    changeOrigin: true,
    timeout: 7200000,
    proxyTimeout: 7200000,
  }

  for (const prefix of meetingApiPrefixes) {
    proxy[prefix] = {
      ...meetingProxyOptions,
      ws: prefix === '/api/ws',
    }
  }

  return {
    plugins: [vue(), ...(devHttps ? [basicSsl()] : [])],
    resolve: {
      alias: {
        '@': fileURLToPath(new URL('./src', import.meta.url)),
      },
    },
    server: {
      host: '0.0.0.0',
      port: Number(env.VITE_DEV_PORT || 5173),
      strictPort: true,
      allowedHosts: true,
      https: devHttps,
      proxy,
    },
    preview: {
      host: '0.0.0.0',
      port: Number(env.VITE_PREVIEW_PORT || 4173),
      allowedHosts: true,
      https: devHttps,
      proxy,
    },
    build: {
      rollupOptions: {
        output: {
          manualChunks: {
            'element-plus': ['element-plus'],
            'vue-vendor': ['vue', 'vue-router', 'pinia'],
          },
        },
      },
    },
  }
})
