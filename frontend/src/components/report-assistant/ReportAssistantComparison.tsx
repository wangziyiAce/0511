/**
 * 智能报告助手 — 周期比较展示组件（Iteration 3）。
 *
 * 只负责渲染后端返回的 MetricComparison 列表，不执行任何计算。
 * 展示指标名、维度、当前值、上一周期值、差值、变化率和方向。
 */

import { ArrowUp, ArrowDown, Minus, HelpCircle } from 'lucide-react'
import { Card } from '@/components/ui/card'
import type { MetricComparison } from '@/types/report-assistant'

interface Props {
  /** 后端返回的指标比较列表 */
  items: MetricComparison[]
  /** 当前周期标签，如"本周" */
  currentLabel?: string
  /** 上一周期标签，如"上周" */
  previousLabel?: string
}

/** 方向图标映射 */
function DirectionIcon({ direction }: { direction: MetricComparison['direction'] }) {
  switch (direction) {
    case 'up':
      return <ArrowUp className="h-3.5 w-3.5 text-red-500" />
    case 'down':
      return <ArrowDown className="h-3.5 w-3.5 text-green-500" />
    case 'flat':
      return <Minus className="h-3.5 w-3.5 text-muted-foreground" />
    default:
      return <HelpCircle className="h-3.5 w-3.5 text-muted-foreground" />
  }
}

/** 格式化数值，None 显示为"——" */
function fmtValue(value: number | null, unit?: string | null): string {
  if (value === null || value === undefined) return '——'
  const numStr = Number.isInteger(value) ? value.toString() : value.toFixed(2)
  return unit ? `${numStr} ${unit}` : numStr
}

/** 格式化变化率 */
function fmtRate(rate: number | null): string {
  if (rate === null || rate === undefined) return '——'
  const pct = (rate * 100).toFixed(1)
  const sign = rate > 0 ? '+' : ''
  return `${sign}${pct}%`
}

export default function ReportAssistantComparison({
  items,
  currentLabel = '当前周期',
  previousLabel = '上一周期',
}: Props) {
  if (!items || items.length === 0) return null

  return (
    <div className="mt-3 space-y-2">
      <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
        周期比较
      </h4>
      <Card className="overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b bg-muted/50">
                <th className="px-2 py-1.5 text-left font-medium">指标</th>
                <th className="px-2 py-1.5 text-right font-medium">{previousLabel}</th>
                <th className="px-2 py-1.5 text-right font-medium">{currentLabel}</th>
                <th className="px-2 py-1.5 text-right font-medium">差值</th>
                <th className="px-2 py-1.5 text-right font-medium">变化率</th>
                <th className="px-2 py-1.5 text-center font-medium">方向</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item, idx) => {
                const dimensionStr = item.dimension
                  ? Object.entries(item.dimension)
                      .map(([k, v]) => `${k}=${v}`)
                      .join(', ')
                  : null

                return (
                  <tr key={`${item.metric_name}-${idx}`} className="border-b last:border-0">
                    <td className="px-2 py-1.5">
                      <span className="font-medium">{item.label}</span>
                      {dimensionStr && (
                        <span className="text-muted-foreground ml-1">({dimensionStr})</span>
                      )}
                    </td>
                    <td className="px-2 py-1.5 text-right tabular-nums">
                      {fmtValue(item.previous_value, item.unit)}
                    </td>
                    <td className="px-2 py-1.5 text-right tabular-nums">
                      {fmtValue(item.current_value, item.unit)}
                    </td>
                    <td className="px-2 py-1.5 text-right tabular-nums">
                      {fmtValue(item.delta, item.unit)}
                    </td>
                    <td className="px-2 py-1.5 text-right tabular-nums">
                      {fmtRate(item.change_rate)}
                    </td>
                    <td className="px-2 py-1.5 text-center">
                      <DirectionIcon direction={item.direction} />
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  )
}
