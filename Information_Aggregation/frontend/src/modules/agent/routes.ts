import type { RouteRecordRaw } from 'vue-router'

export const agentRoutes: RouteRecordRaw[] = [
  {
    path: '',
    name: 'AgentHub',
    component: () => import('@/views/agent/AgentHub.vue'),
    meta: { title: '智能体', module: 'agent' },
  },
]
