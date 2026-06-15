import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import MainLayout from '@/layouts/MainLayout.vue'
import { useUserStore } from '@/stores/user'
import { normalizeRole, ROLES } from '@/utils/permission'
import { AUTH_ROUTES, INFLUENCER_ROUTES, LEGACY_REDIRECTS } from '@/constants/routes'
import { influencerRoutes } from '@/modules/influencer/routes'
import { meetingRoutes } from '@/modules/meeting/routes'
import { feishuRoutes } from '@/modules/feishu/routes'
import { wecomRoutes } from '@/modules/wecom/routes'

const legacyRedirectRoutes = Object.entries(LEGACY_REDIRECTS).map(([path, redirect]) => ({
  path,
  redirect,
}))

const legacyParamRedirects: RouteRecordRaw[] = [
  {
    path: '/influencers/:id',
    redirect: (to) => `/influencer/influencers/${String(to.params.id)}`,
  },
  {
    path: '/match/:id',
    redirect: (to) => `/influencer/match/${String(to.params.id)}`,
  },
  {
    path: '/agencies/:id',
    redirect: (to) => `/influencer/agencies/${String(to.params.id)}`,
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: AUTH_ROUTES.login,
      name: 'Login',
      component: () => import('@/views/Login.vue'),
      meta: { public: true },
    },
    {
      path: AUTH_ROUTES.register,
      redirect: { path: AUTH_ROUTES.login, query: { tab: 'register' } },
    },
    ...legacyRedirectRoutes,
    ...legacyParamRedirects,
    {
      path: '/',
      component: MainLayout,
      redirect: INFLUENCER_ROUTES.dashboard,
      children: [
        {
          path: 'influencer',
          children: influencerRoutes,
        },
        {
          path: 'meeting',
          children: meetingRoutes,
        },
        {
          path: 'feishu',
          children: feishuRoutes,
        },
        {
          path: 'wecom',
          children: wecomRoutes,
        },
      ],
    },
  ],
})

function canAccessRoute(requiredRoles: string[] | undefined, role: string) {
  if (!requiredRoles?.length) return true
  if (role === ROLES.SUPER_ADMIN) return true
  return requiredRoles.includes(role)
}

router.beforeEach(async (to) => {
  const token = localStorage.getItem('token')
  if (!to.meta.public && !token) {
    return AUTH_ROUTES.login
  }
  if (to.path === AUTH_ROUTES.login && token) {
    return INFLUENCER_ROUTES.dashboard
  }
  if (to.path === AUTH_ROUTES.register && token) {
    return INFLUENCER_ROUTES.dashboard
  }

  const requiredRoles = to.meta.roles as string[] | undefined
  if (token && requiredRoles?.length) {
    const store = useUserStore()
    if (!store.userInfo) {
      try {
        await store.fetchUserInfo()
      } catch {
        store.logout()
        return AUTH_ROUTES.login
      }
    }
    const role = normalizeRole(store.userInfo?.role)
    if (!canAccessRoute(requiredRoles, role)) {
      return INFLUENCER_ROUTES.dashboard
    }
  }
})

export default router
