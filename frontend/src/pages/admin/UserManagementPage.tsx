/** 管理员账号档案：使用现有用户与角色接口创建可登录的学生/员工账号。 */
import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Search, UserPlus } from 'lucide-react'
import { toast } from 'sonner'
import { createUser, getOrganizations, getRoles, getUsers } from '@/api/admin-users'
import { WriteConfirmDialog } from '@/components/api/WriteConfirmDialog'
import { ArchiveCard } from '@/components/editorial/ArchiveCard'
import { EditorialPageHeader } from '@/components/editorial/EditorialPageHeader'
import { StatusStamp } from '@/components/editorial/StatusStamp'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import EmptyState from '@/components/shared/EmptyState'
import ErrorState from '@/components/shared/ErrorState'
import LoadingState from '@/components/shared/LoadingState'

const typeForRole = (code: string): 'student' | 'employee' | 'admin' => code === 'student' ? 'student' : code === 'admin' ? 'admin' : 'employee'

export default function UserManagementPage() {
  const queryClient = useQueryClient()
  const [keyword, setKeyword] = useState('')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [realName, setRealName] = useState('')
  const [roleId, setRoleId] = useState('')
  const [department, setDepartment] = useState('')
  const [confirmOpen, setConfirmOpen] = useState(false)
  const usersQuery = useQuery({ queryKey: ['admin', 'users', keyword], queryFn: () => getUsers({ keyword: keyword || undefined, page: 1, page_size: 50 }) })
  const rolesQuery = useQuery({ queryKey: ['admin', 'roles'], queryFn: getRoles })
  const organizationsQuery = useQuery({ queryKey: ['admin', 'organizations'], queryFn: getOrganizations })
  const role = useMemo(() => rolesQuery.data?.find((item) => item.id === Number(roleId)), [roleId, rolesQuery.data])
  const mutation = useMutation({ mutationFn: () => createUser({ username: username.trim(), password, real_name: realName.trim(), role_id: Number(roleId), user_type: typeForRole(role!.role_code), department: department.trim() || undefined }), onSuccess: async () => { setUsername(''); setPassword(''); setRealName(''); setRoleId(''); setDepartment(''); setConfirmOpen(false); toast.success('用户账号已创建'); await queryClient.invalidateQueries({ queryKey: ['admin', 'users'] }) } })
  const valid = username.trim() && password && realName.trim() && role

  return <div className="space-y-6"><EditorialPageHeader eyebrow="Identity archive · roles and access" title="用户与角色" description="创建真实登录账号并分配现有角色。密码只提交到认证接口，不在页面或日志中保存。" />
    <div className="grid gap-6 xl:grid-cols-[380px_minmax(0,1fr)]"><ArchiveCard title="创建账号" index="IDENTITY"><div className="space-y-4"><div><Label htmlFor="new-username">登录账号</Label><Input id="new-username" name="username" autoComplete="off" spellCheck={false} value={username} onChange={(event) => setUsername(event.target.value)} placeholder="例如：student_001…" /></div><div><Label htmlFor="new-password">初始密码</Label><Input id="new-password" name="new-password" type="password" autoComplete="new-password" value={password} onChange={(event) => setPassword(event.target.value)} /></div><div><Label htmlFor="new-real-name">姓名</Label><Input id="new-real-name" name="real_name" autoComplete="off" value={realName} onChange={(event) => setRealName(event.target.value)} /></div><div><Label htmlFor="new-role">角色</Label><Select value={roleId} onValueChange={setRoleId}><SelectTrigger id="new-role"><SelectValue placeholder="选择现有角色…" /></SelectTrigger><SelectContent>{rolesQuery.data?.filter((item) => item.status === 1).map((item) => <SelectItem key={item.id} value={String(item.id)}>{item.role_name} · {item.role_code}</SelectItem>)}</SelectContent></Select></div><div><Label htmlFor="new-department">部门/院系</Label><Select value={department || '__none__'} onValueChange={(value) => setDepartment(value === '__none__' ? '' : value)} disabled={organizationsQuery.isLoading || organizationsQuery.isError}><SelectTrigger id="new-department" aria-describedby="organization-help"><SelectValue placeholder="选择现有组织…" /></SelectTrigger><SelectContent><SelectItem value="__none__">暂不分配</SelectItem>{organizationsQuery.data?.filter((item) => item.status === undefined || item.status === 1).map((item) => <SelectItem key={item.id} value={item.org_name}>{item.org_name}</SelectItem>)}</SelectContent></Select><p id="organization-help" className="mt-1 text-xs leading-5 text-muted-foreground">选择现有组织；账号接口仍使用 department 字段保存名称。</p>{organizationsQuery.isError && <p className="mt-2 text-xs text-danger" role="status">组织目录加载失败，暂时不能分配部门。</p>}</div><Button className="w-full" disabled={!valid || mutation.isPending} onClick={() => setConfirmOpen(true)}><UserPlus aria-hidden />创建用户</Button>{mutation.isError && <ErrorState title="账号创建失败" message="请检查账号是否重复、角色是否有效，然后重试。" />}</div></ArchiveCard>
      <ArchiveCard title="账号目录" index="USERS" action={<div className="relative"><Search className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" aria-hidden /><Input aria-label="搜索用户" name="user_search" autoComplete="off" className="pl-9" value={keyword} onChange={(event) => setKeyword(event.target.value)} placeholder="搜索账号或姓名…" /></div>}>{usersQuery.isLoading && <LoadingState />}{usersQuery.isError && <ErrorState onRetry={() => usersQuery.refetch()} />}{usersQuery.data?.items.length === 0 && <EmptyState title="没有匹配账号" description="调整搜索词，或创建第一个学生测试账号。" />}<div className="overflow-x-auto"><table className="w-full min-w-[620px] text-left text-sm"><thead><tr className="border-b border-bronze/40"><th scope="col" className="px-3 py-3">账号</th><th scope="col" className="px-3 py-3">姓名</th><th scope="col" className="px-3 py-3">类型</th><th scope="col" className="px-3 py-3">部门</th><th scope="col" className="px-3 py-3">状态</th></tr></thead><tbody>{usersQuery.data?.items.map((user) => <tr key={user.id} className="border-b border-bronze/20"><td className="px-3 py-3 font-mono">{user.username}</td><td className="px-3 py-3">{user.real_name}</td><td className="px-3 py-3">{user.user_type}</td><td className="px-3 py-3">{user.department || '—'}</td><td className="px-3 py-3"><StatusStamp label={user.status} tone={user.status === 'normal' ? 'success' : 'neutral'} /></td></tr>)}</tbody></table></div></ArchiveCard></div>
    <WriteConfirmDialog open={confirmOpen} operationLabel={`创建账号 ${username}`} submitting={mutation.isPending} onOpenChange={setConfirmOpen} onConfirm={() => mutation.mutate()} />
  </div>
}
