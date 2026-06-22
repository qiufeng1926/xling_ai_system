import type { RouteRecordRaw } from 'vue-router'

export const flybookRoutes: RouteRecordRaw[] = [
  {
    path: '',
    name: 'FlybookMessenger',
    component: () => import('@/views/flybook/FlybookEmbed.vue'),
    meta: { title: '飞书', module: 'flybook' },
  },
]
