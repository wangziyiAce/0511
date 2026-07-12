/**
 * 生成报告页面。
 *
 * 职责：
 * 1. 从 GET /reports/types 动态加载可用报告类型
 * 2. 表单：选择报告类型 → 填写标题/周期/筛选条件
 * 3. 提交 → POST /reports/generate (202) → 跳转详情页
 */

import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { useQuery, useMutation } from '@tanstack/react-query'
import { FilePlus, Loader2 } from 'lucide-react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import PageHeader from '@/components/shared/PageHeader'
import LoadingState from '@/components/shared/LoadingState'
import { getReportTypes, generateReport } from '@/api/reports'
import { toast } from 'sonner'

const generateSchema = z.object({
  report_type: z.string().min(1, '请选择报告类型'),
  report_title: z.string().min(1, '请输入报告标题').max(255, '标题不能超过255个字符'),
  period_start: z.string().optional(),
  period_end: z.string().optional(),
})

type GenerateFormData = z.infer<typeof generateSchema>

export default function ReportGeneratePage() {
  const navigate = useNavigate()
  const [filters, setFilters] = useState<Record<string, string>>({})

  // 获取报告类型列表
  const { data: typesData, isLoading: typesLoading } = useQuery({
    queryKey: ['report-types'],
    queryFn: getReportTypes,
    select: (res) => res.data,
  })

  const { register, handleSubmit, setValue, watch, formState: { errors } } = useForm<GenerateFormData>({
    resolver: zodResolver(generateSchema),
    defaultValues: { report_type: '', report_title: '', period_start: '', period_end: '' },
  })

  const selectedType = watch('report_type')
  const selectedDef = typesData?.find((t) => t.report_type === selectedType)

  // 生成报告 mutation
  const generateMutation = useMutation({
    mutationFn: generateReport,
    onSuccess: (res) => {
      toast.success('报告任务已创建，正在生成...')
      navigate(`/reports/${res.data.id}`, { replace: true })
    },
    onError: () => {
      toast.error('创建报告任务失败')
    },
  })

  const onSubmit = (data: GenerateFormData) => {
    const filterObj: Record<string, unknown> = {}
    Object.entries(filters).forEach(([key, value]) => {
      if (value) filterObj[key] = value
    })

    generateMutation.mutate({
      report_type: data.report_type,
      report_title: data.report_title,
      period_start: data.period_start || undefined,
      period_end: data.period_end || undefined,
      filters: Object.keys(filterObj).length > 0 ? filterObj : undefined,
    })
  }

  if (typesLoading) return <LoadingState skeleton />

  return (
    <div>
      <PageHeader title="生成报告" description="选择报告类型，填写生成条件，系统将自动聚合数据并生成智能分析报告" />

      <Card className="max-w-2xl">
        <CardHeader>
          <CardTitle>报告配置</CardTitle>
          <CardDescription>请填写以下信息以生成报告</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit(onSubmit)} className="space-y-6">
            {/* 报告类型 */}
            <div className="space-y-2">
              <Label htmlFor="report_type">报告类型 <span className="text-destructive">*</span></Label>
              <Select
                value={selectedType}
                onValueChange={(v) => {
                  setValue('report_type', v)
                  setFilters({})
                }}
              >
                <SelectTrigger>
                  <SelectValue placeholder="选择报告类型" />
                </SelectTrigger>
                <SelectContent>
                  {typesData?.map((t) => (
                    <SelectItem key={t.report_type} value={t.report_type}>{t.label}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {errors.report_type && <p className="text-xs text-destructive">{errors.report_type.message}</p>}
              {selectedDef && (
                <p className="text-xs text-muted-foreground">
                  权限角色：{selectedDef.allowed_roles.join(', ')} · 默认周期：{selectedDef.default_period_rule}
                </p>
              )}
            </div>

            {/* 报告标题 */}
            <div className="space-y-2">
              <Label htmlFor="report_title">报告标题 <span className="text-destructive">*</span></Label>
              <Input
                id="report_title"
                placeholder="例如：2026年第28周申请风险报告"
                {...register('report_title')}
              />
              {errors.report_title && <p className="text-xs text-destructive">{errors.report_title.message}</p>}
            </div>

            {/* 统计周期 */}
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="period_start">统计开始日期</Label>
                <Input id="period_start" type="date" {...register('period_start')} />
              </div>
              <div className="space-y-2">
                <Label htmlFor="period_end">统计结束日期</Label>
                <Input id="period_end" type="date" {...register('period_end')} />
              </div>
            </div>

            {/* 可用过滤条件 */}
            {selectedDef && selectedDef.available_filters.length > 0 && (
              <div className="space-y-2">
                <Label>筛选条件（可选）</Label>
                <div className="grid gap-3 sm:grid-cols-2">
                  {selectedDef.available_filters.map((filterKey) => (
                    <Input
                      key={filterKey}
                      placeholder={filterKey}
                      value={filters[filterKey] || ''}
                      onChange={(e) => setFilters((prev) => ({ ...prev, [filterKey]: e.target.value }))}
                    />
                  ))}
                </div>
              </div>
            )}

            {/* 提交按钮 */}
            <Button
              type="submit"
              className="w-full"
              disabled={generateMutation.isPending}
            >
              {generateMutation.isPending ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  创建任务中...
                </>
              ) : (
                <>
                  <FilePlus className="mr-2 h-4 w-4" />
                  生成报告
                </>
              )}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  )
}
