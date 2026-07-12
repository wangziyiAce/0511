/**
 * 认证状态管理（Zustand Store）。
 *
 * 职责：
 * 1. 存储当前用户信息和 JWT Token
 * 2. 提供 login/logout/fetchMe 操作
 * 3. 通过 localStorage persist 持久化，页面刷新不丢失
 *
 * Token 存储在 localStorage 中，api-client.ts 的拦截器自动读取并注入请求头。
 */

import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { CurrentUser, TokenResponse, LoginRequest } from '@/types/auth'
import { login as loginApi, getMe as getMeApi } from '@/api/auth'
import { normalizeRoleCode } from '@/lib/role-navigation'

interface AuthState {
  /** 当前登录用户信息 */
  user: CurrentUser | null
  /** JWT Access Token */
  token: string | null
  /** 是否已登录（派生状态） */
  isAuthenticated: boolean

  /** 登录操作 */
  login: (credentials: LoginRequest) => Promise<void>
  /** 退出登录 */
  logout: () => void
  /** 获取当前用户信息（用于刷新） */
  fetchMe: () => Promise<void>
  /** 从 TokenResponse 设置认证信息 */
  setAuth: (res: TokenResponse) => void
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      user: null,
      token: null,
      isAuthenticated: false,

      setAuth: (res: TokenResponse) => {
        const user: CurrentUser = {
          user_id: res.user_id,
          username: res.username,
          real_name: res.real_name,
          user_type: res.user_type,
          role_code: normalizeRoleCode(res.role_code, res.user_type),
          department: null,
        }
        set({
          token: res.access_token,
          user,
          isAuthenticated: true,
        })
      },

      login: async (credentials: LoginRequest) => {
        const res = await loginApi(credentials)
        // 登录响应在部分历史数据库中没有 role_code；先保存 Token，再以 /auth/me 作为角色真值来源。
        get().setAuth(res)
        const currentUser = await getMeApi()
        set({
          user: {
            ...currentUser,
            role_code: normalizeRoleCode(currentUser.role_code, currentUser.user_type),
          },
          isAuthenticated: true,
        })
      },

      logout: () => {
        set({
          token: null,
          user: null,
          isAuthenticated: false,
        })
        localStorage.removeItem('auth-storage')
      },

      fetchMe: async () => {
        try {
          const res = await getMeApi()
          // 保持 Store 与 CurrentUser 类型一致，避免把 Axios Response 写入持久化状态。
          set({
            user: {
              ...res,
              role_code: normalizeRoleCode(res.role_code, res.user_type),
            },
          })
        } catch {
          // 如果获取用户信息失败，清除登录状态
          get().logout()
        }
      },
    }),
    {
      name: 'auth-storage',
      // 只持久化 token 和 user，不持久化 isAuthenticated（由 token 派生）
      partialize: (state) => ({
        token: state.token,
        user: state.user,
      }),
    }
  )
)
