/** 学生旅程严格呈现当前可用工单能力；未开放能力使用说明卡，不产生模拟数据。 */
import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { ClipboardCheck, FileClock, GraduationCap, HeartHandshake, MessageSquare, ArrowRight } from 'lucide-react'
import { Link, useSearchParams } from 'react-router-dom'
import { toast } from 'sonner'
import { updateFeedbackTicket } from '@/api/student'
import { ArchiveCard } from '@/components/editorial/ArchiveCard'
import { EditorialPageHeader } from '@/components/editorial/EditorialPageHeader'
import { StatusStamp } from '@/components/editorial/StatusStamp'
import { WriteConfirmDialog } from '@/components/api/WriteConfirmDialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import ErrorState from '@/components/shared/ErrorState'
import { useAuthStore } from '@/stores/auth-store'
import { ROLE_CODES } from '@/types/auth'

const unavailable = [
  { title: '申请与签证进度', description: '当前后端尚未提供学生申请或签证进度查询接口。', icon: FileClock },
  { title: '成绩与课程记录', description: '当前后端尚未提供成绩、考试或论文节点接口。', icon: GraduationCap },
  { title: '关怀与人工介入', description: '心理关怀数据仅在后端报告域使用，尚无学生端查询接口。', icon: HeartHandshake },
]

function StudentHome({ preview = false }: { preview?: boolean }) {
  const user = useAuthStore((state) => state.user)
  return <div className="space-y-6"><EditorialPageHeader eyebrow="Student journey · personal services" title={preview ? '学生门户预览' : `你好，${user?.real_name || user?.username || '同学'}`} description={preview ? '当前仅切换前端视图，所有请求仍使用管理员本人权限，不会模拟学生身份。' : '从咨询服务进入课程与活动，也可以查看当前学生服务的开放范围。'} />
    <ArchiveCard title="咨询与活动" index="AVAILABLE"><div className="grid min-w-0 gap-4 md:grid-cols-2"><Link to="/customer-service" className="group min-w-0 border border-wine/30 bg-wine/5 p-5 transition-colors hover:border-wine hover:bg-wine/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"><MessageSquare className="h-6 w-6 text-wine" aria-hidden /><h2 className="mt-4 font-serif text-xl font-semibold">进入客服咨询</h2><p className="mt-2 text-sm leading-6 text-muted-foreground">保存自己的咨询会话，查找课程和近期活动，并完成报名或取消报名。</p><span className="mt-5 flex items-center gap-2 text-xs font-semibold text-wine">打开咨询中心 <ArrowRight className="h-3 w-3" aria-hidden /></span></Link><div className="min-w-0 border border-bronze/35 p-5"><GraduationCap className="h-6 w-6 text-wine" aria-hidden /><h2 className="mt-4 font-serif text-xl font-semibold">学生服务说明</h2><p className="mt-2 text-sm leading-6 text-muted-foreground">系统只展示后端已开放的真实能力；成绩、签证与申请进度不会使用模拟数据。</p><div className="mt-4"><StatusStamp label="真实数据边界" tone="info" /></div></div></div></ArchiveCard>
    <ArchiveCard title="后续服务" index="PLANNED"><div className="grid min-w-0 gap-5 sm:grid-cols-2 xl:grid-cols-3">{unavailable.map((item) => { const Icon = item.icon; return <article key={item.title} className="min-w-0 border-l border-bronze pl-4"><Icon className="h-5 w-5 text-wine" aria-hidden /><h3 className="mt-3 text-sm font-medium">{item.title}</h3><p className="mt-1 text-xs leading-5 text-muted-foreground">{item.description}</p><div className="mt-3"><StatusStamp label="接口未开放" tone="neutral" /></div></article> })}</div></ArchiveCard>
  </div>
}

export default function StudentJourneyPage() {
  const role = useAuthStore((state) => state.user?.role_code)
  const [searchParams] = useSearchParams()
  const preview = searchParams.get('preview') === 'student'
  const [ticketId, setTicketId] = useState('')
  const [status, setStatus] = useState('processing')
  const [result, setResult] = useState('')
  const [confirmOpen, setConfirmOpen] = useState(false)
  const mutation = useMutation({ mutationFn: () => updateFeedbackTicket(Number(ticketId), { status, handle_result: result.trim() || undefined }), onSuccess: (ticket) => { toast.success('工单状态已更新'); setConfirmOpen(false); return ticket } })
  const valid = Number(ticketId) > 0 && Boolean(status)

  if (role === ROLE_CODES.STUDENT || preview) return <StudentHome preview={preview && role !== ROLE_CODES.STUDENT} />

  return <div className="space-y-6">
    <EditorialPageHeader eyebrow="Student journey · care support" title="学生旅程" description="处理已存在的学生反馈工单，并清晰标示当前系统尚未开放的数据能力。" />
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_360px]">
      <ArchiveCard title="反馈工单处理" index="AVAILABLE">
        <div className="grid gap-5 md:grid-cols-2"><div><Label htmlFor="ticket-id">工单编号</Label><Input id="ticket-id" inputMode="numeric" value={ticketId} onChange={(event) => setTicketId(event.target.value)} placeholder="输入已有工单 ID" /></div><div><Label>处理状态</Label><Select value={status} onValueChange={setStatus}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="processing">处理中</SelectItem><SelectItem value="resolved">已解决</SelectItem><SelectItem value="closed">已关闭</SelectItem></SelectContent></Select></div><div className="md:col-span-2"><Label htmlFor="ticket-result">处理结果</Label><textarea id="ticket-result" className="mt-1 min-h-32 w-full border border-input bg-background p-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" value={result} onChange={(event) => setResult(event.target.value)} placeholder="记录处理结论、后续安排或人工介入说明" /></div></div>
        <Button className="mt-5" disabled={!valid || mutation.isPending} onClick={() => setConfirmOpen(true)}><ClipboardCheck />更新工单</Button>
        {mutation.isError && <div className="mt-4"><ErrorState title="工单更新失败" message="请确认工单编号存在，并检查当前账号是否有处理权限。" /></div>}
        {mutation.data && <div className="mt-5 border border-success/30 bg-success/5 p-4"><div className="flex items-center gap-2"><StatusStamp label={mutation.data.status} tone="success" /><span className="text-sm">工单 #{mutation.data.id ?? mutation.data.ticket_id ?? ticketId}</span></div>{mutation.data.handle_result && <p className="mt-3 text-sm">{mutation.data.handle_result}</p>}</div>}
      </ArchiveCard>
      <ArchiveCard title="能力边界" index="PLANNED"><div className="space-y-5">{unavailable.map((item) => { const Icon = item.icon; return <div key={item.title} className="border-l border-bronze pl-4"><Icon className="h-5 w-5 text-wine" /><p className="mt-2 text-sm font-medium">{item.title}</p><p className="mt-1 text-xs leading-5 text-muted-foreground">{item.description}</p><StatusStamp label="接口未开放" tone="neutral" /></div> })}</div></ArchiveCard>
    </div>
    <WriteConfirmDialog open={confirmOpen} operationLabel={`更新工单 #${ticketId}`} submitting={mutation.isPending} onOpenChange={setConfirmOpen} onConfirm={() => mutation.mutate()} />
  </div>
}
