/**
 * 认证相关 API。
 *
 * 对应后端 routers/tools.py（当前唯一注册的认证实现）:
 *   - POST /api/v1/auth/login
 *   - GET  /api/v1/auth/me
 */

import apiClient from '@/lib/api-client'
import type { LoginRequest, TokenResponse, CurrentUser } from '@/types/auth'

/** 后端统一响应信封；认证模块在此解包，避免页面层感知后端包装格式。 */
interface ApiEnvelope<T> {
  code: number
  message: string
  data: T
}

/**
 * 用户登录并返回纯 Token 领域对象。
 *
 * 后端返回 ``{ code, message, data }``；如果不在 API 层解包，Store 会把 Axios
 * Response 误当成 Token，导致 ``access_token`` 读取失败。
 */
export async function login(data: LoginRequest): Promise<TokenResponse> {
  const response = await apiClient.post<ApiEnvelope<TokenResponse>>('/auth/login', data)
  return response.data.data
}

/** 获取当前登录用户的纯领域对象，供 Store 刷新登录状态。 */
export async function getMe(): Promise<CurrentUser> {
  const response = await apiClient.get<ApiEnvelope<CurrentUser>>('/auth/me')
  return response.data.data
}
