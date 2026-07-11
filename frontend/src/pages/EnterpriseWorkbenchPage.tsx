/**
 * 企业工作台：把 CRM 线索、跟进与日报串成顾问日常工作的最小闭环。
 * 数据来自 crm 领域 API；写操作均经确认弹窗，服务端权限或校验错误由统一 Client 和页面错误区展示。
 */
import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ClipboardPlus, FileText, Plus, Users } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import EmptyState from '@/components/shared/EmptyState'
import ErrorState from '@/components/shared/ErrorState'
import LoadingState from '@/components/shared/LoadingState'
import PageHeader from '@/components/shared/PageHeader'
import { WriteConfirmDialog } from '@/components/api/WriteConfirmDialog'
import { createDailyReport, createFollowUp, createLead, getDailyReports, getDailySummary, getFollowUps, getLeads, updateLeadStatus } from '@/api/crm'
import type { FollowUpType, LeadResponse, LeadStatus } from '@/types/crm'
import { useAuthStore } from '@/stores/auth-store'

const statuses: Array<{ value: LeadStatus; label: string }> = [{ value: 'new', label: '新线索' }, { value: 'contacting', label: '跟进中' }, { value: 'qualified', label: '已确认' }, { value: 'signed', label: '已签约' }, { value: 'lost', label: '已流失' }]
const today = () => new Date().toISOString().slice(0, 10)

export default function EnterpriseWorkbenchPage() {
  const queryClient = useQueryClient()
  const currentUser = useAuthStore((state) => state.user)
  const [employeeIdText, setEmployeeIdText] = useState(currentUser?.user_type === 'employee' ? String(currentUser.user_id) : '')
  const employeeId = Number(employeeIdText) || 0
  const [keyword, setKeyword] = useState('')
  const [status, setStatus] = useState<LeadStatus | undefined>()
  const [selectedLead, setSelectedLead] = useState<LeadResponse | null>(null)
  const [confirm, setConfirm] = useState<(() => void) | null>(null)
  const [leadName, setLeadName] = useState('')
  const [leadContact, setLeadContact] = useState('')
  const [followContent, setFollowContent] = useState('')
  const [followType, setFollowType] = useState<FollowUpType>('wechat')
  const [dailyContent, setDailyContent] = useState('')
  const [summaryDate, setSummaryDate] = useState(today())

  const leadsQuery = useQuery({ queryKey: ['crm', 'leads', { keyword, status }], queryFn: () => getLeads({ keyword: keyword || undefined, status, page: 1, page_size: 50 }) })
  const followUpsQuery = useQuery({ queryKey: ['crm', 'followUps', selectedLead?.id], queryFn: () => getFollowUps(selectedLead!.id), enabled: Boolean(selectedLead) })
  const dailyQuery = useQuery({ queryKey: ['crm', 'dailyReports'], queryFn: getDailyReports })
  const summaryQuery = useQuery({ queryKey: ['crm', 'dailySummary', summaryDate], queryFn: () => getDailySummary(summaryDate) })
  const invalidate = async () => { await queryClient.invalidateQueries({ queryKey: ['crm'] }) }
  const leadMutation = useMutation({ mutationFn: createLead, onSuccess: async () => { setLeadName(''); setLeadContact(''); await invalidate() } })
  const statusMutation = useMutation({ mutationFn: ({ id, value }: { id: number; value: LeadStatus }) => updateLeadStatus(id, { status: value }), onSuccess: async () => { await invalidate() } })
  const followMutation = useMutation({ mutationFn: ({ leadId, content, type }: { leadId: number; content: string; type: FollowUpType }) => createFollowUp(leadId, { employee_id: employeeId, content, follow_type: type }), onSuccess: async () => { setFollowContent(''); await invalidate() } })
  const dailyMutation = useMutation({ mutationFn: () => createDailyReport({ employee_id: employeeId, report_date: today(), status: 'submitted', content: dailyContent, key_progress: [dailyContent] }), onSuccess: async () => { setDailyContent(''); await invalidate() } })
  const writing = leadMutation.isPending || statusMutation.isPending || followMutation.isPending || dailyMutation.isPending
  const canWrite = employeeId > 0
  const leads = useMemo(() => leadsQuery.data?.items ?? [], [leadsQuery.data])

  const askConfirm = (action: () => void) => setConfirm(() => action)
  const runConfirm = () => { confirm?.(); setConfirm(null) }

  return <div className="mx-auto max-w-7xl space-y-6">
    <PageHeader title="企业工作台" description="线索、跟进与日报的顾问日常工作闭环；高级排错请使用接口联调工作台。" />
    <div className="flex max-w-sm items-center gap-3 rounded-lg border border-brand-100 bg-brand-50/40 p-3"><Label htmlFor="employee-id">当前顾问 ID</Label><Input id="employee-id" inputMode="numeric" value={employeeIdText} onChange={(event) => setEmployeeIdText(event.target.value)} placeholder="例如：2" /></div>
    {!canWrite && <ErrorState title="请选择顾问" message="管理员需填写有效的员工 ID；员工账号会自动带入本人 ID。" />}
    <div className="grid gap-6 xl:grid-cols-[1.35fr_.85fr]">
      <Card><CardHeader><CardTitle className="flex items-center gap-2"><Users className="h-5 w-5 text-brand-600" />线索档案</CardTitle></CardHeader><CardContent className="space-y-4">
        <div className="flex flex-col gap-3 md:flex-row"><Input value={keyword} onChange={(event) => setKeyword(event.target.value)} placeholder="搜索姓名或联系方式" /><Select value={status ?? 'all'} onValueChange={(value) => setStatus(value === 'all' ? undefined : value as LeadStatus)}><SelectTrigger className="md:w-36"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">全部状态</SelectItem>{statuses.map((item) => <SelectItem key={item.value} value={item.value}>{item.label}</SelectItem>)}</SelectContent></Select></div>
        <div className="grid gap-2 rounded-lg border border-brand-100 bg-brand-50/40 p-3 md:grid-cols-[1fr_1fr_auto]"><Input value={leadName} onChange={(event) => setLeadName(event.target.value)} placeholder="新线索姓名" /><Input value={leadContact} onChange={(event) => setLeadContact(event.target.value)} placeholder="联系方式（可选）" /><Button disabled={!canWrite || !leadName.trim()} onClick={() => askConfirm(() => leadMutation.mutate({ customer_name: leadName.trim(), contact_info: leadContact || undefined, owner_employee_id: employeeId }))}><Plus />新增线索</Button></div>
        {leadsQuery.isLoading && <LoadingState skeleton />}{leadsQuery.isError && <ErrorState onRetry={() => leadsQuery.refetch()} />}{!leadsQuery.isLoading && !leadsQuery.isError && leads.length === 0 && <EmptyState title="暂无匹配线索" description="可录入第一位咨询客户，或调整筛选条件。" />}
        <div className="space-y-2">{leads.map((lead) => <button key={lead.id} onClick={() => setSelectedLead(lead)} className={`w-full rounded-lg border p-3 text-left transition-colors ${selectedLead?.id === lead.id ? 'border-brand-600 bg-brand-50' : 'border-border hover:bg-muted/50'}`}><div className="flex justify-between gap-3"><span className="font-medium">{lead.customer_name}</span><span className="text-xs text-brand-700">{statuses.find((item) => item.value === lead.status)?.label ?? lead.status}</span></div><p className="mt-1 text-xs text-muted-foreground">{lead.intended_country || '目的地待补充'} · {lead.contact_info || '联系方式待补充'}</p></button>)}</div>
      </CardContent></Card>
      <Card><CardHeader><CardTitle>跟进与状态</CardTitle></CardHeader><CardContent className="space-y-4">{selectedLead ? <><div><p className="font-medium">{selectedLead.customer_name}</p><p className="text-sm text-muted-foreground">{selectedLead.remark || '暂无备注'}</p></div><div className="flex flex-wrap gap-2">{statuses.map((item) => <Button key={item.value} size="sm" variant={item.value === selectedLead.status ? 'default' : 'outline'} disabled={!canWrite || item.value === selectedLead.status} onClick={() => askConfirm(() => statusMutation.mutate({ id: selectedLead.id, value: item.value }))}>{item.label}</Button>)}</div><div className="space-y-2"><Label>新增跟进</Label><Select value={followType} onValueChange={(value) => setFollowType(value as FollowUpType)}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="wechat">微信</SelectItem><SelectItem value="phone">电话</SelectItem><SelectItem value="meeting">面谈</SelectItem><SelectItem value="email">邮件</SelectItem><SelectItem value="other">其他</SelectItem></SelectContent></Select><textarea className="min-h-24 w-full rounded-md border border-input bg-background p-3 text-sm" value={followContent} onChange={(event) => setFollowContent(event.target.value)} placeholder="记录沟通结论与下一步安排" /><Button disabled={!canWrite || !followContent.trim()} onClick={() => askConfirm(() => followMutation.mutate({ leadId: selectedLead.id, content: followContent.trim(), type: followType }))}>保存跟进</Button></div><div className="space-y-2 border-t pt-3"><p className="text-sm font-medium">跟进历史</p>{followUpsQuery.isLoading && <LoadingState />}{followUpsQuery.data?.map((item) => <div key={item.id} className="border-l-2 border-brand-300 pl-3 text-sm"><p>{item.content}</p><p className="text-xs text-muted-foreground">{item.follow_type} · {item.create_time || '-'}</p></div>)}</div></> : <EmptyState title="选择一条线索" description="选择后可更新状态、记录跟进与查看历史。" />}</CardContent></Card>
    </div>
    <div className="grid gap-6 lg:grid-cols-2"><Card><CardHeader><CardTitle className="flex items-center gap-2"><ClipboardPlus className="h-5 w-5 text-brand-600" />今日日报</CardTitle></CardHeader><CardContent className="space-y-3"><textarea className="min-h-28 w-full rounded-md border border-input bg-background p-3 text-sm" value={dailyContent} onChange={(event) => setDailyContent(event.target.value)} placeholder="填写今日客户进展、风险和下一步计划" /><Button disabled={!canWrite || !dailyContent.trim()} onClick={() => askConfirm(() => dailyMutation.mutate())}>提交日报</Button><div className="space-y-2 border-t pt-3">{dailyQuery.isLoading && <LoadingState />}{dailyQuery.isError && <ErrorState title="日报列表暂不可用" message="服务端数据契约错误会在这里显示；请到接口工作台查看原始错误。" onRetry={() => dailyQuery.refetch()} />}{dailyQuery.data?.map((item) => <div key={item.id} className="rounded border p-2 text-sm"><p>{item.content}</p><p className="text-xs text-muted-foreground">{item.report_date} · {item.status}</p></div>)}</div></CardContent></Card><Card><CardHeader><CardTitle className="flex items-center gap-2"><FileText className="h-5 w-5 text-brand-600" />日报汇总</CardTitle></CardHeader><CardContent className="space-y-3"><Input type="date" value={summaryDate} onChange={(event) => setSummaryDate(event.target.value)} /><p className="text-3xl font-semibold">{summaryQuery.data?.total_submitted ?? 0}</p><p className="text-sm text-muted-foreground">当日已提交日报数</p>{summaryQuery.isError && <ErrorState onRetry={() => summaryQuery.refetch()} />}{summaryQuery.data?.employees.map((item) => <div key={item.employee_id} className="border-l-2 border-brand-300 pl-3 text-sm">员工 #{item.employee_id}：{item.key_progress?.join('；') || '暂无进展'}</div>)}</CardContent></Card></div>
    <WriteConfirmDialog open={Boolean(confirm)} operationLabel="企业工作台写操作" submitting={writing} onOpenChange={(open) => { if (!open) setConfirm(null) }} onConfirm={runConfirm} />
  </div>
}
