/**
 * 智能报告助手 — 数据质量提示组件。
 *
 * 根据后端返回的 data_quality.status 显示不同颜色的提示条。
 * 对齐后端 DataQuality 模型：
 *   ok → 默认不展示，或显示轻量"数据完整"
 *   warning → 黄色提示：部分数据缺失
 *   empty → 空状态：当前周期无有效数据
 *   degraded → 橙色提示：报告处于降级状态
 *   failed → 红色提示：不能基于当前报告分析
 *
 * 前端只负责展示后端结果，不得自行改变回答强度。
 */

import { AlertCircle, CheckCircle2, AlertTriangle, Database, XCircle } from 'lucide-react'
import type { AssistantDataQuality } from '@/types/report-assistant'

/** 数据质量等级对应的展示配置 */
const LEVEL_CONFIG: Record<string, {
  icon: React.ComponentType<{ className?: string }>
  bgClass: string
  borderClass: string
  textClass: string
  label: string
}> = {
  ok: {
    icon: CheckCircle2,
    bgClass: 'bg-green-50',
    borderClass: 'border-green-200',
    textClass: 'text-green-700',
    label: '数据完整',
  },
  warning: {
    icon: AlertTriangle,
    bgClass: 'bg-yellow-50',
    borderClass: 'border-yellow-200',
    textClass: 'text-yellow-700',
    label: '部分数据缺失',
  },
  empty: {
    icon: Database,
    bgClass: 'bg-gray-50',
    borderClass: 'border-gray-200',
    textClass: 'text-gray-600',
    label: '当前周期无有效数据',
  },
  degraded: {
    icon: AlertCircle,
    bgClass: 'bg-orange-50',
    borderClass: 'border-orange-200',
    textClass: 'text-orange-700',
    label: '报告处于降级状态',
  },
  failed: {
    icon: XCircle,
    bgClass: 'bg-red-50',
    borderClass: 'border-red-200',
    textClass: 'text-red-700',
    label: '不能基于当前报告分析',
  },
}

interface Props {
  /** 后端返回的数据质量信息 */
  dataQuality?: AssistantDataQuality | null
}

export default function ReportAssistantDataQuality({ dataQuality }: Props) {
  if (!dataQuality) return null

  // ok 状态且无警告时默认不展示
  if (dataQuality.status === 'ok' && (!dataQuality.warnings || dataQuality.warnings.length === 0)) {
    return null
  }

  const config = LEVEL_CONFIG[dataQuality.status] || LEVEL_CONFIG.warning
  const Icon = config.icon

  return (
    <div className={`mt-2 rounded-md border px-3 py-2 text-sm ${config.bgClass} ${config.borderClass} ${config.textClass}`}>
      <div className="flex items-start gap-2">
        <Icon className="h-4 w-4 mt-0.5 shrink-0" />
        <div>
          <span className="font-medium">{config.label}</span>
          {dataQuality.warnings && dataQuality.warnings.length > 0 && (
            <ul className="mt-1 list-disc list-inside text-xs opacity-80">
              {dataQuality.warnings.map((w, i) => (
                <li key={i}>{w}</li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  )
}
