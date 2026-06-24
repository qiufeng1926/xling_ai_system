/** 门户路由常量（统一维护，便于后续扩展模块） */

export const INFLUENCER_BASE = '/influencer'

export const INFLUENCER_ROUTES = {
  dashboard: `${INFLUENCER_BASE}/dashboard`,
  collection: `${INFLUENCER_BASE}/collection`,
  review: `${INFLUENCER_BASE}/review`,
  influencers: `${INFLUENCER_BASE}/influencers`,
  influencerDetail: (id: number | string) => `${INFLUENCER_BASE}/influencers/${id}`,
  tags: `${INFLUENCER_BASE}/tags`,
  match: `${INFLUENCER_BASE}/match`,
  matchDetail: (id: number | string) => `${INFLUENCER_BASE}/match/${id}`,
  agencies: `${INFLUENCER_BASE}/agencies`,
  agencyDetail: (id: number | string) => `${INFLUENCER_BASE}/agencies/${id}`,
  accessReview: `${INFLUENCER_BASE}/access-review`,
  users: `${INFLUENCER_BASE}/users`,
  offboardingApply: `${INFLUENCER_BASE}/offboarding-apply`,
  offboardingManage: `${INFLUENCER_BASE}/offboarding-manage`,
} as const

export const MEETING_ROUTES = {
  home: '/meeting',
  create: '/meeting/create',
  solo: '/meeting/solo',
  records: '/meeting/records',
  recordDetail: (fileId: string) => `/meeting/records/${fileId}`,
  room: (code: string) => `/meeting/room/${code}`,
} as const

export const FLYBOOK_ROUTES = {
  home: '/flybook/messenger',
  messenger: '/flybook/messenger',
  docs: '/flybook/docs',
  docLibrary: '/flybook/doc-library',
  minutesAi: '/flybook/minutes-ai',
} as const

export const QYWECHAT_ROUTES = {
  mail: '/qywechat/mail',
  approval: '/qywechat/approval',
} as const

/** @deprecated 使用 FLYBOOK_ROUTES */
export const FEISHU_ROUTES = FLYBOOK_ROUTES

/** @deprecated 使用 QYWECHAT_ROUTES */
export const WECOM_ROUTES = QYWECHAT_ROUTES

export const AUTH_ROUTES = {
  login: '/login',
  register: '/register',
} as const

/** 旧路径 → 新路径（兼容书签） */
export const LEGACY_REDIRECTS: Record<string, string> = {
  '/dashboard': INFLUENCER_ROUTES.dashboard,
  '/collection': INFLUENCER_ROUTES.collection,
  '/review': INFLUENCER_ROUTES.review,
  '/influencers': INFLUENCER_ROUTES.influencers,
  '/tags': INFLUENCER_ROUTES.tags,
  '/match': INFLUENCER_ROUTES.match,
  '/agencies': INFLUENCER_ROUTES.agencies,
  '/access-review': INFLUENCER_ROUTES.accessReview,
  '/users': INFLUENCER_ROUTES.users,
  '/feishu': FLYBOOK_ROUTES.messenger,
  '/feishu/': FLYBOOK_ROUTES.messenger,
  '/flybook': FLYBOOK_ROUTES.messenger,
  '/flybook/': FLYBOOK_ROUTES.messenger,
  '/wecom/mail': QYWECHAT_ROUTES.mail,
  '/wecom/approval': QYWECHAT_ROUTES.approval,
  '/wecom': QYWECHAT_ROUTES.mail,
}
