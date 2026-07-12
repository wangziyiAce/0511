import { ROLE_CODES } from '@/types/auth'

export const defaultRoutes: Record<string, string> = {
  admin: '/dashboard',
  manager: '/dashboard',
  employee: '/enterprise-assistant',
  team_leader: '/enterprise-assistant',
  student: '/student-assistant',
}

/** 未知角色进入最小权限学生门户，避免意外落入管理首页。 */
export function getDefaultRoute(role?: string | null) { return defaultRoutes[role || ''] || '/student-assistant' }

export const managementRoles = [ROLE_CODES.ADMIN, ROLE_CODES.MANAGER]
export const staffRoles = [ROLE_CODES.ADMIN, ROLE_CODES.MANAGER, ROLE_CODES.EMPLOYEE, ROLE_CODES.TEAM_LEADER]

/**
 * 学生只进入真实开放的个人服务入口。课程和活动位于客服咨询页内，
 * 因而不额外制造没有独立业务页面的导航地址。
 */
export const studentPortalRoutes = ['/student-assistant', '/customer-service'] as const

/** 员工在学生服务之外，还可以进入客户研判和企业运营工作区。 */
export const staffPortalRoutes = [
  ...studentPortalRoutes,
  '/customer-assessment',
  '/enterprise-assistant',
] as const

/** 管理角色可以使用完整业务工作区和系统诊断入口。 */
export const managementPortalRoutes = [
  ...staffPortalRoutes,
  '/dashboard',
  '/reports',
  '/admin/users',
  '/admin/api-diagnostics',
  '/workbench',
] as const

/**
 * 判断角色是否可以进入指定门户路径。
 * 路由守卫仍是前端体验边界，后端必须继续校验 Token 和数据归属。
 */
export function canAccessPortalRoute(role: string | null | undefined, pathname: string): boolean {
  const allowedRoutes = role === ROLE_CODES.STUDENT
    ? studentPortalRoutes
    : role === ROLE_CODES.EMPLOYEE || role === ROLE_CODES.TEAM_LEADER
      ? staffPortalRoutes
      : role === ROLE_CODES.ADMIN || role === ROLE_CODES.MANAGER
        ? managementPortalRoutes
        : []

  return allowedRoutes.some((route) => pathname === route || pathname.startsWith(`${route}/`))
}

/**
 * 兼容已联调环境中的历史认证响应：新接口优先使用 role_code，旧接口只返回 user_type。
 * 这里只做同义字段归一化，不提升权限；未知值保持为空并落入最小权限入口。
 */
export function normalizeRoleCode(roleCode?: string | null, userType?: string | null): string | undefined {
  const candidate = roleCode || userType
  return Object.values(ROLE_CODES).includes(candidate as (typeof ROLE_CODES)[keyof typeof ROLE_CODES])
    ? candidate || undefined
    : undefined
}
