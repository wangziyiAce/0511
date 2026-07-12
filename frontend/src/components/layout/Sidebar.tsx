/** 角色化档案导航：学生、员工和管理角色只看见各自门户入口。 */
import { useEffect } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import { BookOpen, Building2, Database, FileText, GraduationCap, LayoutDashboard, MessageSquare, Network, UserCog, Users, X } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { useAuthStore } from '@/stores/auth-store'
import { ROLE_CODES } from '@/types/auth'

interface SidebarProps { open: boolean; onClose: () => void }
interface NavItem { label: string; to: string; icon: React.ComponentType<{ className?: string }> }
interface NavGroup { label: string; items: NavItem[] }

const studentServices: NavItem[] = [
  { label: '学生首页', to: '/student-assistant', icon: GraduationCap },
  { label: '客服咨询', to: '/customer-service', icon: MessageSquare },
]
const staffServices: NavItem[] = [
  { label: '企业运营', to: '/enterprise-assistant', icon: Building2 },
  { label: '客户研判', to: '/customer-assessment', icon: Users },
  { label: '授权学生服务', to: '/student-assistant', icon: GraduationCap },
]
const managementServices: NavItem[] = [
  { label: '管理首页', to: '/dashboard', icon: LayoutDashboard },
  { label: '客户研判', to: '/customer-assessment', icon: Users },
  { label: '企业运营', to: '/enterprise-assistant', icon: Building2 },
  { label: '智能报告', to: '/reports', icon: FileText },
]

export default function Sidebar({ open, onClose }: SidebarProps) {
  const location = useLocation()
  const user = useAuthStore((state) => state.user)
  const role = user?.role_code
  const isManagement = role === ROLE_CODES.ADMIN || role === ROLE_CODES.MANAGER
  useEffect(() => { onClose() }, [location.pathname]) // eslint-disable-line react-hooks/exhaustive-deps

  const groups: NavGroup[] = role === ROLE_CODES.STUDENT
    ? [{ label: '学生门户', items: studentServices }]
    : isManagement
      ? [
          { label: '管理工作区', items: managementServices },
          { label: '门户预览', items: [{ label: '咨询用户端', to: '/customer-service', icon: MessageSquare }, { label: '学生门户', to: '/student-assistant?preview=student', icon: GraduationCap }] },
          { label: '系统管理', items: [{ label: '用户与角色', to: '/admin/users', icon: UserCog }, { label: '报告计划', to: '/reports/schedules', icon: BookOpen }, { label: '数据档案', to: '/reports/data', icon: Database }, { label: '接口诊断', to: '/admin/api-diagnostics', icon: Network }] },
        ]
      : [{ label: '员工门户', items: staffServices }]

  const renderItem = (item: NavItem) => { const Icon = item.icon; return <NavLink key={item.to} to={item.to} className={({ isActive }) => cn('group flex min-h-11 items-center gap-3 border-l-2 px-5 py-2.5 text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-bronze', isActive ? 'border-bronze bg-wine text-white' : 'border-transparent text-sidebar-foreground hover:border-bronze/60 hover:bg-sidebar-accent hover:text-white')}><Icon className="h-4 w-4" aria-hidden /><span>{item.label}</span></NavLink> }
  const portalLabel = role === ROLE_CODES.STUDENT ? '学生门户' : isManagement ? '管理门户' : '员工门户'

  return <aside className={cn('fixed inset-y-0 left-0 z-40 flex w-64 flex-col overscroll-contain bg-sidebar-background pb-[env(safe-area-inset-bottom)] pt-[env(safe-area-inset-top)] text-sidebar-foreground shadow-2xl transition-transform duration-200 lg:translate-x-0', open ? 'translate-x-0' : '-translate-x-full')}>
    <div className="relative flex h-28 items-center border-b border-sidebar-border px-5"><div className="absolute inset-y-0 left-0 w-2 bg-wine" aria-hidden /><div><p className="font-serif text-xl font-semibold tracking-wide text-white">粹教智服</p><p className="mt-1 text-[10px] uppercase tracking-[0.24em] text-bronze">International advisory</p></div><Button variant="ghost" size="icon" className="absolute right-3 top-3 text-white lg:hidden" onClick={onClose} aria-label="关闭导航"><X aria-hidden /></Button></div>
    <nav aria-label="主导航" className="flex-1 overflow-y-auto py-5">{groups.map((group) => <section key={group.label} className="mb-7"><p className="mb-2 px-5 text-[10px] uppercase tracking-[0.22em] text-sidebar-foreground/50">{group.label}</p>{group.items.map(renderItem)}</section>)}</nav>
    <div className="border-t border-sidebar-border p-5"><span className="status-stamp border-bronze/50 text-bronze">{portalLabel}</span><p className="mt-3 truncate text-sm font-medium text-white">{user?.real_name || user?.username || '当前用户'}</p><p className="mt-1 truncate text-xs text-sidebar-foreground/60">{user?.department || role || '国际教育服务平台'}</p></div>
  </aside>
}
