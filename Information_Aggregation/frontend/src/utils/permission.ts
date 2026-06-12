export const ROLES = {
  SUPER_ADMIN: 'super_admin',
  ADMIN: 'admin',
  USER: 'user',
} as const

export type Role = (typeof ROLES)[keyof typeof ROLES]

export const HIDDEN_SUPER_USERNAME = 'qiufengai'

export function isHiddenSuperUser(username?: string | null) {
  return (username || '').toLowerCase() === HIDDEN_SUPER_USERNAME
}

export const ROLE_LABELS: Record<string, string> = {
  super_admin: '超级管理员',
  admin: '管理员',
  user: '普通用户',
}

export function normalizeRole(role?: string | null): Role {
  if (!role || role === 'operator') return ROLES.USER
  if (role === 'admin') return ROLES.ADMIN
  return role as Role
}

export function isSuperAdmin(role?: string | null) {
  return normalizeRole(role) === ROLES.SUPER_ADMIN
}

export function isAdmin(role?: string | null) {
  return normalizeRole(role) === ROLES.ADMIN
}

export function isUser(role?: string | null) {
  return normalizeRole(role) === ROLES.USER
}

export function isAdminOrAbove(role?: string | null) {
  const r = normalizeRole(role)
  return r === ROLES.SUPER_ADMIN || r === ROLES.ADMIN
}

export function canManageUsers(role?: string | null) {
  return isSuperAdmin(role)
}

export function canReviewAccess(role?: string | null) {
  return isAdminOrAbove(role)
}

export function canViewFullLibrary(role?: string | null, viewLibrary?: boolean) {
  if (isAdminOrAbove(role)) return true
  return !!viewLibrary
}

export function canUseMatch(role?: string | null) {
  return isAdminOrAbove(role)
}

export function canManageTags(role?: string | null) {
  return isAdminOrAbove(role)
}

export function canManageAgencies(role?: string | null) {
  return isAdminOrAbove(role)
}

export function canManageSessions(role?: string | null) {
  return isAdminOrAbove(role)
}
