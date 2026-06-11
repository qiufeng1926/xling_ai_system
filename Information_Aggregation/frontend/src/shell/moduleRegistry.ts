import type { RouteRecordRaw } from 'vue-router'
import { influencerRoutes } from '@/modules/influencer/routes'
import { meetingRoutes } from '@/modules/meeting/routes'

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
]
