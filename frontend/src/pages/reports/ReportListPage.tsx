/**
 * 报告列表页面。
 *
 * 职责：
 * 1. 分页展示所有报告生成记录
 * 2. 支持按报告类型、状态、日期范围筛选
 * 3. 点击行跳转报告详情
 */

import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { FileText, Plus, Bot } from 'lucide-react'
import { ReportAssistantPanel } from '@/components/report-assistant'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import PageHeader from '@/components/shared/PageHeader'
import StatusBadge from '@/components/shared/StatusBadge'
import LoadingState from '@/components/shared/LoadingState'
import ErrorState from '@/components/shared/ErrorState'
import EmptyState from '@/components/shared/EmptyState'
import { getReportList, getReportTypes } from '@/api/reports'
import { format } from 'date-fns'

export default function ReportListPage() {
  const navigate = useNavigate()
  const [page, setPage] = useState(1)
  const [reportType, setReportType] = useState<string>('')
  const [statusFilter, setStatusFilter] = useState<string>('')
  const [assistantOpen, setAssistantOpen] = useState(false)
  const pageSize = 20

  // 获取报告类型列表（用于筛选下拉）
  const { data: typesData } = useQuery({
    queryKey: ['report-types'],
    queryFn: getReportTypes,
    select: (res) => res.data,
  })

  // 获取报告列表
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['reports', { page, page_size: pageSize, report_type: reportType, status: statusFilter }],
    queryFn: () => getReportList({
      page,
      page_size: pageSize,
      report_type: reportType || undefined,
      status: statusFilter || undefined,
    }),
    select: (res) => res.data,
  })

  return (
    <div>
      <PageHeader title="报告列表" description="查看和管理所有智能报告生成记录">
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => setAssistantOpen(true)}>
            <Bot className="mr-2 h-4 w-4" />
            智能助手
          </Button>
          <Button onClick={() => navigate('/reports/generate')}>
            <Plus className="mr-2 h-4 w-4" />
            生成报告
          </Button>
        </div>
      </PageHeader>

      {/* 筛选栏 */}
      <Card className="mb-4">
        <CardContent className="flex flex-col gap-3 pt-4 sm:flex-row sm:flex-wrap sm:items-center">
          <Select value={reportType} onValueChange={(v) => { setReportType(v); setPage(1) }}>
            <SelectTrigger className="w-full sm:w-48">
              <SelectValue placeholder="全部报告类型" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="">全部报告类型</SelectItem>
              {typesData?.map((t) => (
                <SelectItem key={t.report_type} value={t.report_type}>{t.label}</SelectItem>
              ))}
            </SelectContent>
          </Select>

          <Select value={statusFilter} onValueChange={(v) => { setStatusFilter(v); setPage(1) }}>
            <SelectTrigger className="w-full sm:w-36">
              <SelectValue placeholder="全部状态" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="">全部状态</SelectItem>
              <SelectItem value="pending">等待生成</SelectItem>
              <SelectItem value="generating">生成中</SelectItem>
              <SelectItem value="completed">已完成</SelectItem>
              <SelectItem value="failed">生成失败</SelectItem>
            </SelectContent>
          </Select>

          <div className="flex-1" />

          <span className="text-sm text-muted-foreground">
            共 {data?.total || 0} 条
          </span>
        </CardContent>
      </Card>

      {/* 表格 */}
      {isLoading && <LoadingState skeleton />}
      {isError && <ErrorState onRetry={() => refetch()} />}
      {!isLoading && !isError && data?.items?.length === 0 && (
        <Card><CardContent className="py-8">
          <EmptyState
            title="暂无报告"
            description={reportType || statusFilter ? '没有匹配当前筛选条件的报告' : '还没有生成任何报告'}
            action={
              <Button onClick={() => navigate('/reports/generate')}>
                <Plus className="mr-2 h-4 w-4" />
                生成第一份报告
              </Button>
            }
          />
        </CardContent></Card>
      )}
      {!isLoading && !isError && data && data.items.length > 0 && (
        <Card>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-12">ID</TableHead>
                <TableHead>报告标题</TableHead>
                <TableHead className="w-40">报告类型</TableHead>
                <TableHead className="w-24">状态</TableHead>
                <TableHead className="w-40">创建时间</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.items.map((report) => (
                <TableRow
                  key={report.id}
                  className="cursor-pointer"
                  onClick={() => navigate(`/reports/${report.id}`)}
                >
                  <TableCell className="text-muted-foreground">{report.id}</TableCell>
                  <TableCell>
                    <div className="flex items-center gap-2">
                      <FileText className="h-4 w-4 text-muted-foreground shrink-0" />
                      <span className="font-medium">{report.report_title}</span>
                    </div>
                  </TableCell>
                  <TableCell className="text-sm text-muted-foreground">{report.report_type}</TableCell>
                  <TableCell><StatusBadge status={report.status} /></TableCell>
                  <TableCell className="text-sm text-muted-foreground">
                    {report.create_time ? format(new Date(report.create_time), 'yyyy-MM-dd HH:mm') : '-'}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Card>
      )}

      {/* 智能报告助手面板 */}
      <ReportAssistantPanel
        open={assistantOpen}
        onClose={() => setAssistantOpen(false)}
      />

      {/* 分页 */}
      {data && data.total > pageSize && (
        <div className="mt-4 flex items-center justify-center gap-2">
          <Button
            variant="outline"
            size="sm"
            disabled={page <= 1}
            onClick={() => setPage((p) => p - 1)}
          >
            上一页
          </Button>
          <span className="text-sm text-muted-foreground">
            第 {page} / {Math.ceil(data.total / pageSize)} 页
          </span>
          <Button
            variant="outline"
            size="sm"
            disabled={page >= Math.ceil(data.total / pageSize)}
            onClick={() => setPage((p) => p + 1)}
          >
            下一页
          </Button>
        </div>
      )}
    </div>
  )
}
