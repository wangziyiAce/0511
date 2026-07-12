import { Navigate } from 'react-router-dom'
import { useAuthStore } from '@/stores/auth-store'
import { getDefaultRoute } from '@/lib/role-navigation'

export default function RoleLanding() {
  const role = useAuthStore((state) => state.user?.role_code)
  return <Navigate to={getDefaultRoute(role)} replace />
}
