/** 首页以真实报告与角色化服务入口组成，不展示缺少数据来源的 KPI。 */
import { useQuery } from '@tanstack/react-query'
import { ArrowRight, Building2, FilePlus, FileText, GraduationCap, MessageSquare, Users } from 'lucide-react'
import { Link, useNavigate } from 'react-router-dom'
import { getReportList } from '@/api/reports'
import { ArchiveCard } from '@/components/editorial/ArchiveCard'
import { EditorialPageHeader } from '@/components/editorial/EditorialPageHeader'
import { StatusStamp } from '@/components/editorial/StatusStamp'
import { Button } from '@/components/ui/button'
import EmptyState from '@/components/shared/EmptyState'
import ErrorState from '@/components/shared/ErrorState'
import LoadingState from '@/components/shared/LoadingState'
import { useAuthStore } from '@/stores/auth-store'
import editorialHero from '../../design-assets/mockups/b-editorial-academy/02-dashboard.png'

const serviceCards = [
  { title: '客户研判', description: '归档咨询资料，查看画像、风险与产品匹配依据。', path: '/customer-assessment', icon: Users },
  { title: '客服中心', description: '保存咨询会话，检索课程、活动并处理报名。', path: '/customer-service', icon: MessageSquare },
  { title: '学生旅程', description: '处理真实反馈工单，查看当前服务能力边界。', path: '/student-assistant', icon: GraduationCap },
  { title: '企业运营', description: '管理线索、跟进记录、日报与业务汇总。', path: '/enterprise-assistant', icon: Building2 },
]
const statusTone = (status: string) => status === 'success' ? 'success' : status === 'failed' ? 'danger' : 'warning'

export default function DashboardPage() {
  const navigate = useNavigate()
  const user = useAuthStore((state) => state.user)
  const reports = useQuery({ queryKey: ['reports', { page: 1, page_size: 5 }], queryFn: () => getReportList({ page: 1, page_size: 5 }), select: (response) => response.data })
  return <div className="space-y-6">
    <EditorialPageHeader eyebrow="Advisory desk · service archive" title={`欢迎回来，${user?.real_name || user?.username || '用户'}`} description="从真实客户档案、服务会话和报告任务继续今天的工作。" actions={<Button onClick={() => navigate('/reports/generate')}><FilePlus />生成报告</Button>} />
    <section className="relative min-h-[330px] overflow-hidden border border-bronze/45 bg-ink sm:min-h-[400px]">
      <img src={editorialHero} alt="国际教育学院建筑与旅行档案" width="1440" height="960" fetchPriority="high" className="absolute inset-0 h-full w-full object-cover object-center opacity-75" />
      <div className="absolute inset-0 bg-gradient-to-r from-ink/75 via-ink/20 to-transparent" />
      <div className="relative flex min-h-[330px] max-w-xl flex-col justify-end p-6 text-white sm:min-h-[400px] sm:p-10"><p className="text-xs uppercase tracking-[0.24em] text-bronze">Current dossier</p><h2 className="mt-3 font-serif text-3xl font-semibold leading-tight sm:text-5xl">教育决策，需要事实、过程与责任人共同在场。</h2><p className="mt-4 max-w-lg text-sm leading-6 text-white/75">从一份客户资料开始，把每次匹配、沟通、行动与报告留在同一条可追溯链路中。</p></div>
    </section>
    <section aria-labelledby="services-title"><div className="mb-3 flex items-end justify-between"><div><p className="editorial-kicker">Service folios</p><h2 id="services-title" className="font-serif text-2xl font-semibold">服务目录</h2></div></div><div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">{serviceCards.map((item) => { const Icon = item.icon; return <Link key={item.path} to={item.path} className="group border border-bronze/40 bg-paper-raised p-5 text-left shadow-[0_10px_30px_rgb(52_40_24/6%)] transition-transform hover:-translate-y-0.5 hover:border-wine focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"><Icon className="h-6 w-6 text-wine" aria-hidden /><h3 className="mt-5 font-serif text-xl font-semibold">{item.title}</h3><p className="mt-2 min-h-10 text-sm leading-5 text-muted-foreground">{item.description}</p><span className="mt-5 flex items-center gap-2 text-xs font-semibold text-wine">进入工作区 <ArrowRight className="h-3 w-3 transition-transform group-hover:translate-x-1" aria-hidden /></span></Link> })}</div></section>
    <ArchiveCard title="最近报告" index="REPORT LIBRARY" action={<Button variant="ghost" size="sm" onClick={() => navigate('/reports')}>查看全部</Button>}>
      {reports.isLoading && <LoadingState skeleton />}{reports.isError && <ErrorState onRetry={() => reports.refetch()} />}{reports.data?.items?.length === 0 && <EmptyState icon={<FileText className="h-8 w-8" />} title="还没有报告" description="创建第一份报告后，这里会显示真实任务状态。" action={<Button onClick={() => navigate('/reports/generate')}>生成报告</Button>} />}
      <div className="divide-y divide-bronze/25">{reports.data?.items?.map((report) => <button key={report.id} onClick={() => navigate(`/reports/${report.id}`)} className="flex w-full items-center justify-between gap-4 py-4 text-left hover:bg-wine/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"><div className="min-w-0"><p className="truncate text-sm font-medium">{report.report_title}</p><p className="mt-1 text-xs text-muted-foreground">{report.report_type} · {report.create_time ? new Date(report.create_time).toLocaleString() : '时间待同步'}</p></div><StatusStamp label={report.status} tone={statusTone(report.status)} /></button>)}</div>
    </ArchiveCard>
  </div>
}
