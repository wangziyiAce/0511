/**
 * 认证相关 TypeScript 类型。
 *
 * 对齐后端 schemas/auth.py 中的 LoginRequest、TokenResponse、CurrentUserResponse。
 * 实际字段结构已在阶段 0 契约审查中通过 Python 代码确认。
 */

/** POST /api/v1/auth/login 请求体 */
export interface LoginRequest {
  username: string
  password: string
}

/** POST /api/v1/auth/login 响应体 */
export interface TokenResponse {
  access_token: string
  token_type: string
  expires_in: number
  user_id: number
  username: string
  real_name: string
  user_type: string
  role_code?: string
}

/** GET /api/v1/auth/me 响应体（当前登录用户信息） */
export interface CurrentUser {
  user_id: number
  username: string
  real_name: string
  user_type: string
  role_code?: string
  department: string | null
}

/** 角色编码常量 */
export const ROLE_CODES = {
  ADMIN: 'admin',
  MANAGER: 'manager',
  EMPLOYEE: 'employee',
  TEAM_LEADER: 'team_leader',
  STUDENT: 'student',
} as const

/** 管理端角色（可访问报告等管理功能） */
export const MANAGEMENT_ROLES = [
  ROLE_CODES.ADMIN,
  ROLE_CODES.MANAGER,
  ROLE_CODES.EMPLOYEE,
  ROLE_CODES.TEAM_LEADER,
] as const
