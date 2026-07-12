/**
 * 报告详情页面（最核心页面）。
 *
 * 职责：
 * 1. 根据 URL 参数 report_id 查询报告详情
 * 2. 使用 TanStack Query refetchInterval 轮询直到 completed/failed
 * 3. 通过 ReportRenderer 注册表选择对应的渲染组件
 * 4. 处理四种状态：pending / generating / completed / failed
 * 5. 失败时提供重试按钮
 * 6. 展示数据质量和事实与 AI 内容分区
 */

import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, RefreshCw, Loader2, AlertCircle, Bot } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import PageHeader from '@/components/shared/PageHeader'
import StatusBadge from '@/components/shared/StatusBadge'
import LoadingState from '@/components/shared/LoadingState'
import ErrorState from '@/components/shared/ErrorState'
import DataQualityBanner from '@/components/shared/DataQualityBanner'
import ReportRenderer from '@/components/report/ReportRenderer'
import ReportHeader from '@/components/report/ReportHeader'
import { ReportAssistantPanel } from '@/components/report-assistant'
import { getReportDetail, retryReport } from '@/api/reports'
import { toast } from 'sonner'

export default function ReportDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const reportId = id ? parseInt(id, 10) : null
  const [assistantOpen, setAssistantOpen] = useState(false)

  // 报告详情查询（自动轮询）
  const { data: report, isLoading, isError, refetch } = useQuery({
    queryKey: ['report', reportId],
    queryFn: () => getReportDetail(reportId!),
    enabled: !!reportId && !isNaN(reportId),
    select: (res) => res.data,
    // 轮询逻辑：pending/generating 时每 2 秒查询
    refetchInterval: (query) => {
      const status = query.state.data?.data?.status
      if (status === 'generating' || status === 'pending') return 2000
      return false
    },
    refetchIntervalInBackground: false,
  })

  // 重试 mutation
  const retryMutation = useMutation({
    mutationFn: () => retryReport(reportId!),
    onSuccess: (res) => {
      toast.success('已创建重试任务')
      navigate(`/reports/${res.data.id}`, { replace: true })
    },
    onError: () => {
      toast.error('重试失败')
    },
  })

  const handleRetry = () => {
    if (reportId) {
      // 先清除当前缓存的报告数据
      queryClient.removeQueries({ queryKey: ['report', reportId] })
      retryMutation.mutate()
    }
  }

  if (isLoading) {
    return <LoadingState text="加载报告..." skeleton />
  }

  if (isError || !report) {
    return (
      <div>
        <PageHeader title="报告详情">
          <Button variant="outline" onClick={() => navigate('/reports')}>
            <ArrowLeft className="mr-2 h-4 w-4" />
            返回列表
          </Button>
        </PageHeader>
        <ErrorState
          title="报告不存在或加载失败"
          message={isError ? '网络异常或报告已被删除' : '找不到该报告'}
          onRetry={() => refetch()}
        />
      </div>
    )
  }

  return (
    <div>
      <PageHeader title={report.report_title || '报告详情'}>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => setAssistantOpen(true)}>
            <Bot className="mr-2 h-4 w-4" />
            智能助手
          </Button>
          <Button variant="outline" onClick={() => navigate('/reports')}>
            <ArrowLeft className="mr-2 h-4 w-4" />
            返回列表
          </Button>
        </div>
      </PageHeader>

      {/* 报告元信息 */}
      <ReportHeader report={report} />

      {/* 数据质量横幅 */}
      <DataQualityBanner dataQuality={report.data_quality} />

      {/* ---- 状态：生成中 ---- */}
      {(report.status === 'pending' || report.status === 'generating') && (
        <Card>
          <CardContent className="flex flex-col items-center justify-center py-16">
            <Loader2 className="h-12 w-12 animate-spin text-brand-600" />
            <h3 className="mt-4 text-lg font-semibold">报告生成中</h3>
            <p className="mt-1 text-sm text-muted-foreground">
              系统正在聚合数据并调用 AI 分析，请稍候...
            </p>
            <p className="mt-2 text-xs text-muted-foreground">
              页面会自动刷新，无需手动操作
            </p>
            <StatusBadge status={report.status} className="mt-3" />
          </CardContent>
        </Card>
      )}

      {/* ---- 状态：失败 ---- */}
      {report.status === 'failed' && (
        <Card className="mb-6">
          <CardContent className="flex flex-col items-center justify-center py-16">
            <AlertCircle className="h-12 w-12 text-destructive" />
            <h3 className="mt-4 text-lg font-semibold text-destructive">报告生成失败</h3>
            {report.error_message && (
              <p className="mt-2 max-w-md text-sm text-muted-foreground text-center">
                {report.error_message}
              </p>
            )}
            {report.error_code && (
              <p className="mt-1 text-xs text-muted-foreground">
                错误码：{report.error_code}
              </p>
            )}
            <div className="mt-4 flex gap-3">
              <Button
                variant="outline"
                onClick={handleRetry}
                disabled={retryMutation.isPending}
              >
                {retryMutation.isPending ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <RefreshCw className="mr-2 h-4 w-4" />
                )}
                重试
              </Button>
              <Button variant="ghost" onClick={() => navigate('/reports')}>
                返回列表
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* ---- 状态：成功 ---- */}
      {report.status === 'completed' && (
        <div className="space-y-6">
          {/* 报告内容渲染 */}
          <ReportRenderer report={report} />
        </div>
      )}

      {/* 智能报告助手面板 */}
      <ReportAssistantPanel
        open={assistantOpen}
        onClose={() => setAssistantOpen(false)}
        initialReportId={reportId}
        initialReportType={report.report_type}
      />
    </div>
  )
}
