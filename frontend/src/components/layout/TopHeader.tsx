/** 顶部工具栏提供移动导航、环境状态、当前身份与退出操作。 */
import { LogOut, Menu, UserRound } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { useAuthStore } from '@/stores/auth-store'

const roleLabels: Record<string, string> = { admin: '管理员', manager: '经理', employee: '顾问', team_leader: '团队主管', student: '学生' }

export default function TopHeader({ onMenu }: { onMenu: () => void }) {
  const { user, logout } = useAuthStore()
  const navigate = useNavigate()
  const handleLogout = () => { logout(); navigate('/login', { replace: true }) }
  return <header className="sticky top-0 z-20 flex h-16 items-center justify-between border-b border-bronze/35 bg-paper-raised/95 px-4 backdrop-blur-sm sm:px-6 lg:px-8">
    <div className="flex items-center gap-3">
      <Button variant="ghost" size="icon" className="lg:hidden" onClick={onMenu} aria-label="打开导航"><Menu /></Button>
      <div><p className="font-serif text-sm font-semibold text-ink">国际教育服务档案</p><p className="text-[10px] uppercase tracking-[0.2em] text-wine">Advisory archive</p></div>
    </div>
    <div className="flex items-center gap-2 sm:gap-4">
      <div className="hidden items-center gap-2 text-sm sm:flex"><UserRound className="h-4 w-4 text-wine" /><span className="font-medium">{user?.real_name || user?.username}</span><span className="text-xs text-muted-foreground">{roleLabels[user?.role_code ?? ''] ?? '用户'}</span></div>
      <Button variant="ghost" size="icon" onClick={handleLogout} aria-label="退出登录" title="退出登录"><LogOut /></Button>
    </div>
  </header>
}
