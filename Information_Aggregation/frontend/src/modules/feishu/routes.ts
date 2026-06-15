import type { RouteRecordRaw } from 'vue-router'

export const feishuRoutes: RouteRecordRaw[] = [
  {
    path: '',
    name: 'FeishuMessenger',
    component: () => import('@/views/FeishuEmbed.vue'),
    meta: { title: '飞书', module: 'feishu' },
  },
]
