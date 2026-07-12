/** 报告事实数据档案：四类来源使用各自真实字段录入，不暴露通用 JSON。 */
import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Database, Plus } from 'lucide-react'
import { toast } from 'sonner'
import { createReportData, listReportData, type ReportDataKind, type ReportDataRecord } from '@/api/report-data'
import { ArchiveCard } from '@/components/editorial/ArchiveCard'
import { EditorialPageHeader } from '@/components/editorial/EditorialPageHeader'
import { WriteConfirmDialog } from '@/components/api/WriteConfirmDialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import EmptyState from '@/components/shared/EmptyState'
import ErrorState from '@/components/shared/ErrorState'
import LoadingState from '@/components/shared/LoadingState'

interface Field { key: string; label: string; type?: string; required?: boolean }
const definitions: Record<ReportDataKind, { label: string; description: string; fields: Field[] }> = {
  'application-materials': { label: '申请材料', description: '支持申请风险报告', fields: [{ key: 'application_id', label: '申请 ID', type: 'number', required: true }, { key: 'student_id', label: '学生 ID', type: 'number' }, { key: 'material_name', label: '材料名称', required: true }, { key: 'deadline', label: '截止日期', type: 'date' }, { key: 'status', label: '状态', required: true }] },
  'channel-costs': { label: '渠道成本', description: '支持渠道 ROI 报告', fields: [{ key: 'channel', label: '渠道', required: true }, { key: 'cost_date', label: '成本日期', type: 'date', required: true }, { key: 'campaign', label: '活动名称' }, { key: 'cost_amount', label: '成本金额', type: 'number', required: true }] },
  contracts: { label: '客户合同', description: '支持签约与 ROI 报告', fields: [{ key: 'customer_id', label: '客户 ID', type: 'number', required: true }, { key: 'lead_id', label: '线索 ID', type: 'number' }, { key: 'channel', label: '来源渠道' }, { key: 'contract_amount', label: '合同金额', type: 'number', required: true }, { key: 'status', label: '状态', required: true }] },
  payments: { label: '客户回款', description: '支持现金流与 ROI 报告', fields: [{ key: 'contract_id', label: '合同 ID', type: 'number', required: true }, { key: 'payment_amount', label: '回款金额', type: 'number', required: true }, { key: 'payment_time', label: '回款时间', type: 'datetime-local' }, { key: 'status', label: '状态', required: true }] },
}

export default function ReportDataPage() {
  const queryClient = useQueryClient()
  const [kind, setKind] = useState<ReportDataKind>('application-materials')
  const [form, setForm] = useState<Record<string, string>>({ status: 'pending' })
  const [confirmOpen, setConfirmOpen] = useState(false)
  const definition = definitions[kind]
  const query = useQuery({ queryKey: ['report-data', kind], queryFn: () => listReportData(kind) })
  const mutation = useMutation({ mutationFn: (payload: ReportDataRecord) => createReportData(kind, payload), onSuccess: async () => { setForm({ status: 'pending' }); setConfirmOpen(false); toast.success(`${definition.label}已归档`); await queryClient.invalidateQueries({ queryKey: ['report-data', kind] }) } })
  const valid = definition.fields.filter((field) => field.required).every((field) => form[field.key]?.trim())
  const payload = useMemo(() => Object.fromEntries(definition.fields.filter((field) => form[field.key]?.trim()).map((field) => [field.key, field.type === 'number' ? Number(form[field.key]) : form[field.key]])) as ReportDataRecord, [definition, form])

  return <div className="space-y-6">
    <EditorialPageHeader eyebrow="Source archive · records and quality" title="数据档案" description="维护报告计算所需的最小事实数据。所有新增记录都会进入真实业务库，并受管理角色权限约束。" />
    <div className="flex gap-2 overflow-x-auto pb-1" role="tablist" aria-label="数据类型">{(Object.keys(definitions) as ReportDataKind[]).map((item) => <Button key={item} role="tab" aria-selected={kind === item} variant={kind === item ? 'default' : 'outline'} onClick={() => { setKind(item); setForm({ status: 'pending' }) }}>{definitions[item].label}</Button>)}</div>
    <div className="grid gap-6 xl:grid-cols-[360px_minmax(0,1fr)]">
      <ArchiveCard title={`新增${definition.label}`} index="NEW RECORD"><p className="mb-4 text-xs text-muted-foreground">{definition.description}</p><div className="space-y-4">{definition.fields.map((field) => <div key={field.key}><Label htmlFor={`data-${field.key}`}>{field.label}{field.required ? ' *' : ''}</Label><Input id={`data-${field.key}`} type={field.type || 'text'} value={form[field.key] || ''} onChange={(event) => setForm((current) => ({ ...current, [field.key]: event.target.value }))} /></div>)}</div><Button className="mt-5 w-full" disabled={!valid || mutation.isPending} onClick={() => setConfirmOpen(true)}><Plus />保存记录</Button>{mutation.isError && <div className="mt-4"><ErrorState title="记录保存失败" message="请核对关联 ID、金额和日期格式。" /></div>}</ArchiveCard>
      <ArchiveCard title={`${definition.label}台账`} index="LEDGER">{query.isLoading && <LoadingState skeleton />}{query.isError && <ErrorState onRetry={() => query.refetch()} />}{query.data?.length === 0 && <EmptyState icon={<Database className="h-8 w-8" />} title="暂无记录" description={`保存第一条${definition.label}后，将在这里形成数据台账。`} />}{query.data && query.data.length > 0 && <div className="overflow-x-auto"><table className="w-full min-w-[680px] border-collapse text-left text-sm"><thead><tr className="border-b border-bronze/40">{Object.keys(query.data[0]).map((key) => <th key={key} className="px-3 py-3 font-medium text-muted-foreground">{key}</th>)}</tr></thead><tbody>{query.data.map((row, index) => <tr key={String(row.id ?? index)} className="border-b border-bronze/20 hover:bg-wine/5">{Object.values(row).map((value, cell) => <td key={cell} className="max-w-56 truncate px-3 py-3">{value === null ? '—' : String(value)}</td>)}</tr>)}</tbody></table></div>}</ArchiveCard>
    </div>
    <WriteConfirmDialog open={confirmOpen} operationLabel={`新增${definition.label}`} submitting={mutation.isPending} onOpenChange={setConfirmOpen} onConfirm={() => mutation.mutate(payload)} />
  </div>
}
