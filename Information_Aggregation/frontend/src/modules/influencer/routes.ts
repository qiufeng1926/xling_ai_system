import type { RouteRecordRaw } from 'vue-router'
import { ROLES } from '@/utils/permission'

export const influencerRoutes: RouteRecordRaw[] = [
  {
    path: 'dashboard',
    name: 'Dashboard',
    component: () => import('@/views/Dashboard.vue'),
    meta: { title: '工作台', module: 'influencer' },
  },
  {
    path: 'collection',
    name: 'CollectionTasks',
    component: () => import('@/views/CollectionTasks.vue'),
    meta: { title: '自动采集', module: 'influencer' },
  },
  {
    path: 'review',
    name: 'ReviewQueue',
    component: () => import('@/views/ReviewQueue.vue'),
    meta: { title: '待审核', module: 'influencer' },
  },
  {
    path: 'influencers',
    name: 'InfluencerList',
    component: () => import('@/views/InfluencerList.vue'),
    meta: { title: '达人库', module: 'influencer' },
  },
  {
    path: 'influencers/:id',
    name: 'InfluencerDetail',
    component: () => import('@/views/InfluencerDetail.vue'),
    meta: { title: '达人详情', module: 'influencer' },
  },
  {
    path: 'tags',
    name: 'TagManage',
    component: () => import('@/views/TagManage.vue'),
    meta: { title: '标签管理', module: 'influencer', roles: [ROLES.ADMIN, ROLES.SUPER_ADMIN] },
  },
  {
    path: 'match',
    name: 'MatchList',
    component: () => import('@/views/MatchList.vue'),
    meta: { title: '智能匹配', module: 'influencer', roles: [ROLES.ADMIN, ROLES.SUPER_ADMIN] },
  },
  {
    path: 'match/:id',
    name: 'MatchDetail',
    component: () => import('@/views/MatchDetail.vue'),
    meta: { title: '匹配结果', module: 'influencer', roles: [ROLES.ADMIN, ROLES.SUPER_ADMIN] },
  },
  {
    path: 'agencies',
    name: 'AgencyList',
    component: () => import('@/views/AgencyList.vue'),
    meta: { title: 'MCN机构', module: 'influencer', roles: [ROLES.ADMIN, ROLES.SUPER_ADMIN] },
  },
  {
    path: 'agencies/:id',
    name: 'AgencyDetail',
    component: () => import('@/views/AgencyDetail.vue'),
    meta: { title: '机构详情', module: 'influencer', roles: [ROLES.ADMIN, ROLES.SUPER_ADMIN] },
  },
        {
          path: 'users',
          name: 'UserManage',
          component: () => import('@/views/UserManage.vue'),
          meta: { title: '平台用户管理', module: 'platform', roles: [ROLES.SUPER_ADMIN] },
        },
        {
          path: 'offboarding-manage',
          name: 'OffboardingManage',
          component: () => import('@/views/OffboardingManage.vue'),
          meta: { title: '离职交接管理', module: 'platform', roles: [ROLES.SUPER_ADMIN] },
        },
        {
          path: 'offboarding-apply',
          name: 'OffboardingApply',
          component: () => import('@/views/OffboardingApply.vue'),
          meta: { title: '离职交接申请', module: 'platform' },
        },
        {
          path: 'access-review',
          name: 'AccessReview',
          component: () => import('@/views/AccessReview.vue'),
          meta: {
            title: '平台权限管理',
            module: 'platform',
            roles: [ROLES.ADMIN, ROLES.SUPER_ADMIN, ROLES.USER],
          },
        },
]
