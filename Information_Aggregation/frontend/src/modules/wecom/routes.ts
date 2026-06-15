import type { RouteRecordRaw } from 'vue-router'
import { ROLES } from '@/utils/permission'

export const wecomRoutes: RouteRecordRaw[] = [
  {
    path: 'mail',
    name: 'WeComMail',
    component: () => import('@/views/wecom/WecomMail.vue'),
    meta: {
      title: '企业微信邮箱',
      module: 'wecom',
      roles: [ROLES.ADMIN, ROLES.SUPER_ADMIN],
    },
  },
  {
    path: 'approval',
    name: 'WeComApproval',
    component: () => import('@/views/wecom/WecomApproval.vue'),
    meta: {
      title: '企业微信审批',
      module: 'wecom',
      roles: [ROLES.ADMIN, ROLES.SUPER_ADMIN],
    },
  },
]
