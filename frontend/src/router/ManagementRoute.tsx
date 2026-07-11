/** 管理路由守卫：导航隐藏之外再做前端路由拦截，后端仍是最终权限边界。 */
import { Navigate } from 'react-router-dom'
import { useAuthStore } from '@/stores/auth-store'
import { ROLE_CODES } from '@/types/auth'

export default function ManagementRoute({ children }: { children: React.ReactNode }) {
  const role = useAuthStore((state) => state.user?.role_code)
  if (role !== ROLE_CODES.ADMIN && role !== ROLE_CODES.MANAGER) return <Navigate to="/403" replace />
  return children
}
