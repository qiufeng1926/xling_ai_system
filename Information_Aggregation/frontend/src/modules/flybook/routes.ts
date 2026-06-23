import type { RouteRecordRaw } from 'vue-router'

export const flybookRoutes: RouteRecordRaw[] = [
  {
    path: '',
    redirect: '/flybook/messenger',
  },
  {
    path: 'messenger',
    name: 'FlybookMessenger',
    component: () => import('@/views/flybook/FlybookEmbed.vue'),
    meta: { title: '飞书消息', module: 'flybook' },
  },
  {
    path: 'docs',
    name: 'FlybookDocs',
    component: () => import('@/views/flybook/FlybookDocs.vue'),
    meta: { title: '飞书云文档', module: 'flybook' },
  },
  {
    path: 'doc-library',
    name: 'FlybookDocLibrary',
    component: () => import('@/views/flybook/FlybookDocLibrary.vue'),
    meta: { title: '文档库', module: 'flybook' },
  },
  {
    path: 'minutes-ai',
    name: 'FlybookMinutesAi',
    component: () => import('@/views/flybook/FlybookMinutesAi.vue'),
    meta: { title: '妙纪 AI', module: 'flybook' },
  },
]
