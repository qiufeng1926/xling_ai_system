import type { RouteRecordRaw } from 'vue-router'
import { influencerRoutes } from '@/modules/influencer/routes'
import { meetingRoutes } from '@/modules/meeting/routes'
import { flybookRoutes } from '@/modules/flybook/routes'
import { agentRoutes } from '@/modules/agent/routes'

export interface PlatformModule {
  id: string
  title: string
  basePath: string
  routes: RouteRecordRaw[]
}

export const platformModules: PlatformModule[] = [
  {
    id: 'influencer',
    title: '达人信息管理',
    basePath: '/influencer',
    routes: influencerRoutes,
  },
  {
    id: 'meeting',
    title: '会议 AI',
    basePath: '/meeting',
    routes: meetingRoutes,
  },
  {
    id: 'flybook',
    title: '飞书',
    basePath: '/flybook',
    routes: flybookRoutes,
  },
  {
    id: 'agent',
    title: '智能体',
    basePath: '/agent',
    routes: agentRoutes,
  },
]
