import type { RouteRecordRaw } from 'vue-router'
import { ROLES } from '@/utils/permission'

export const qywechatRoutes: RouteRecordRaw[] = [
  {
    path: 'mail',
    name: 'QyWechatMail',
    component: () => import('@/views/qywechat/QyWechatMail.vue'),
    meta: {
      title: '企业微信邮箱',
      module: 'qywechat',
      roles: [ROLES.ADMIN, ROLES.SUPER_ADMIN],
    },
  },
  {
    path: 'approval',
    name: 'QyWechatApproval',
    component: () => import('@/views/qywechat/QyWechatApproval.vue'),
    meta: {
      title: '企业微信审批',
      module: 'qywechat',
      roles: [ROLES.ADMIN, ROLES.SUPER_ADMIN],
    },
  },
]
