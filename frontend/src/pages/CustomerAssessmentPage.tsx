/** 客户研判工作区：资料进入、异步分析与结果解释形成同页闭环。 */
import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { FileSearch, Play, Upload } from 'lucide-react'
import { toast } from 'sonner'
import { analyzeProfile, getCustomerSources, getProfileDetail, getProfileRules, updateProfileRule, uploadCustomerSource } from '@/api/profile'
import { ArchiveCard } from '@/components/editorial/ArchiveCard'
import { EditorialPageHeader } from '@/components/editorial/EditorialPageHeader'
import { StatusStamp } from '@/components/editorial/StatusStamp'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import EmptyState from '@/components/shared/EmptyState'
import ErrorState from '@/components/shared/ErrorState'
import LoadingState from '@/components/shared/LoadingState'
import { useAuthStore } from '@/stores/auth-store'

const toneFor = (status: string) => status === 'success' ? 'success' : status === 'failed' ? 'danger' : 'warning'

export default function CustomerAssessmentPage() {
  const queryClient = useQueryClient()
  const role = useAuthStore((state) => state.user?.role_code)
  const canManageRules = role === 'admin' || role === 'manager'
  const [content, setContent] = useState('')
  const [file, setFile] = useState<File | undefined>()
  const [selectedId, setSelectedId] = useState<number>()
  const sourcesQuery = useQuery({ queryKey: ['profile', 'sources'], queryFn: () => getCustomerSources({ page: 1, page_size: 50 }), refetchInterval: (query) => query.state.data?.items.some((item) => item.parse_status === 'pending') ? 2500 : false })
  const detailQuery = useQuery({ queryKey: ['profile', selectedId], queryFn: () => getProfileDetail(selectedId!), enabled: Boolean(selectedId), refetchInterval: (query) => query.state.data?.parse_status === 'pending' ? 2000 : false })
  const rulesQuery = useQuery({ queryKey: ['profile', 'rules'], queryFn: getProfileRules, enabled: canManageRules })
  const uploadMutation = useMutation({ mutationFn: uploadCustomerSource, onSuccess: async (result) => { setContent(''); setFile(undefined); setSelectedId(result.source_id); await queryClient.invalidateQueries({ queryKey: ['profile', 'sources'] }); toast.success('资料已归档') } })
  const analyzeMutation = useMutation({ mutationFn: (id: number) => analyzeProfile(id), onSuccess: async () => { await queryClient.invalidateQueries({ queryKey: ['profile'] }); toast.success('研判任务已启动') } })
  const ruleMutation = useMutation({ mutationFn: ({ id, status }: { id: number; status: number }) => updateProfileRule(id, { status }), onSuccess: async () => queryClient.invalidateQueries({ queryKey: ['profile', 'rules'] }) })
  const sources = sourcesQuery.data?.items ?? []
  const detail = detailQuery.data
  const recommendation = useMemo(() => detail?.recommended_programs ? JSON.stringify(detail.recommended_programs, null, 2) : '', [detail])

  return <div className="space-y-6">
    <EditorialPageHeader eyebrow="Applicant dossier · matching evidence" title="客户研判" description="把咨询资料沉淀为可追溯档案，查看 AI 匹配结论、风险依据和建议项目。" />
    <div className="grid gap-6 xl:grid-cols-[360px_minmax(0,1fr)]">
      <div className="space-y-6">
        <ArchiveCard title="录入资料" index="SOURCE">
          <div className="space-y-4"><div><Label htmlFor="profile-file">客户文件</Label><Input id="profile-file" type="file" accept=".pdf,.xlsx,.xls,.txt,.docx" onChange={(event) => setFile(event.target.files?.[0])} /><p className="mt-1 text-xs text-muted-foreground">PDF、Excel、TXT 或 DOCX，最大 10MB。</p></div><div><Label htmlFor="profile-content">补充背景</Label><textarea id="profile-content" className="mt-1 min-h-32 w-full border border-input bg-background p-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring" value={content} onChange={(event) => setContent(event.target.value)} placeholder="教育背景、目标国家、预算、语言成绩与时间计划" /></div><Button className="w-full" disabled={uploadMutation.isPending || (!file && !content.trim())} onClick={() => uploadMutation.mutate({ source_type: file ? 'import' : 'text', file, content_text: content.trim() || undefined })}><Upload />{uploadMutation.isPending ? '正在归档…' : '归档客户资料'}</Button>{uploadMutation.isError && <ErrorState title="资料归档失败" message="请检查文件类型、大小与必填内容后重试。" />}</div>
        </ArchiveCard>
        <ArchiveCard title="资料档案" index="ARCHIVE">
          {sourcesQuery.isLoading && <LoadingState />}{sourcesQuery.isError && <ErrorState onRetry={() => sourcesQuery.refetch()} />}{!sourcesQuery.isLoading && sources.length === 0 && <EmptyState title="暂无客户资料" description="录入第一份客户资料后，可在这里启动研判。" />}
          <div className="space-y-2">{sources.map((source) => <button key={source.id} onClick={() => setSelectedId(source.id)} className={`w-full border p-3 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${selectedId === source.id ? 'border-wine bg-wine/5' : 'border-bronze/30 hover:bg-muted/60'}`}><div className="flex items-center justify-between gap-2"><span className="truncate text-sm font-medium">{source.file_name || `文本资料 #${source.id}`}</span><StatusStamp label={source.parse_status} tone={toneFor(source.parse_status)} /></div><p className="mt-2 text-xs text-muted-foreground">{new Date(source.create_time).toLocaleString()}</p></button>)}</div>
        </ArchiveCard>
      </div>
      <div className="space-y-6">
        <ArchiveCard title="研判结论" index="ASSESSMENT" action={selectedId && <Button size="sm" onClick={() => analyzeMutation.mutate(selectedId)} disabled={analyzeMutation.isPending || detail?.parse_status === 'pending'}><Play />启动研判</Button>}>
          {!selectedId && <EmptyState icon={<FileSearch className="h-8 w-8" />} title="选择客户档案" description="从左侧选择资料，查看解析状态并启动 AI 研判。" />}{detailQuery.isLoading && <LoadingState text="正在读取研判档案…" />}{detailQuery.isError && <ErrorState onRetry={() => detailQuery.refetch()} />}{detail && <div className="space-y-5"><div className="flex flex-wrap items-center gap-3"><StatusStamp label={detail.parse_status} tone={toneFor(detail.parse_status)} /><span className="text-sm text-muted-foreground">档案 #{detail.source_id}</span></div>{detail.parse_error && <ErrorState title="研判失败" message={detail.parse_error} />}{detail.parse_status === 'pending' && <LoadingState text="正在分析客户背景与产品匹配关系…" />}<div className="grid gap-4 md:grid-cols-2"><div className="border-l-2 border-wine pl-4"><p className="text-xs text-muted-foreground">匹配产品</p><p className="mt-1 font-serif text-xl">{detail.matched_product || '等待研判'}</p></div><div className="border-l-2 border-bronze pl-4"><p className="text-xs text-muted-foreground">匹配评分</p><p className="mt-1 font-mono text-xl">{detail.match_score ?? '—'}</p></div></div>{detail.match_reason && <div><h3 className="font-medium">匹配依据</h3><p className="mt-2 whitespace-pre-wrap text-sm leading-7 text-muted-foreground">{detail.match_reason}</p></div>}{detail.match_result && <div><h3 className="font-medium">研判摘要</h3><p className="mt-2 whitespace-pre-wrap text-sm leading-7">{detail.match_result}</p></div>}{recommendation && <div><h3 className="font-medium">建议项目</h3><pre className="mt-2 max-h-72 overflow-auto bg-ink p-4 text-xs text-paper">{recommendation}</pre></div>}</div>}
        </ArchiveCard>
        {canManageRules && <ArchiveCard title="画像规则" index="RULES"><div className="grid gap-3 md:grid-cols-2">{rulesQuery.data?.map((rule) => <div key={rule.id} className="border border-bronze/30 p-4"><div className="flex items-start justify-between gap-3"><div><p className="font-medium">{rule.rule_name}</p><p className="text-xs text-muted-foreground">{rule.product_line} · 优先级 {rule.priority}</p></div><StatusStamp label={rule.status ? '启用' : '停用'} tone={rule.status ? 'success' : 'neutral'} /></div><Button className="mt-4" size="sm" variant="outline" disabled={ruleMutation.isPending} onClick={() => ruleMutation.mutate({ id: rule.id, status: rule.status ? 0 : 1 })}>{rule.status ? '停用规则' : '启用规则'}</Button></div>)}</div></ArchiveCard>}
      </div>
    </div>
  </div>
}
