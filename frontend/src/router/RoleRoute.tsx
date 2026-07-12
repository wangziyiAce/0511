/** 通用角色守卫；前端负责体验边界，后端继续负责最终数据授权。 */
import { Navigate } from 'react-router-dom'
import { useAuthStore } from '@/stores/auth-store'

export default function RoleRoute({ allow, children }: { allow: string[]; children: React.ReactNode }) {
  const role = useAuthStore((state) => state.user?.role_code)
  if (!role || !allow.includes(role)) return <Navigate to="/403" replace />
  return children
}
