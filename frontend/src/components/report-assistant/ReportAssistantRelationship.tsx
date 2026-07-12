/**
 * 智能报告助手 — 跨报告关系分析展示组件（Iteration 3）。
 *
 * 渲染四区结构化回答：已确认事实、相关信号、可能解释、无法确认。
 * 只负责展示，不执行计算或因果判断。
 */

import { CheckCircle, Activity, Lightbulb, AlertTriangle } from 'lucide-react'
import { Card } from '@/components/ui/card'
import type { RelationshipSections } from '@/types/report-assistant'

interface Props {
  /** 后端返回的四区关系分析 */
  sections: RelationshipSections
}

function SectionBlock({
  title,
  icon,
  items,
  variant,
}: {
  title: string
  icon: React.ReactNode
  items: string[]
  variant: 'fact' | 'signal' | 'explanation' | 'warning'
}) {
  if (!items || items.length === 0) return null

  const borderColors = {
    fact: 'border-l-green-400',
    signal: 'border-l-blue-400',
    explanation: 'border-l-amber-400',
    warning: 'border-l-red-400',
  }

  const bgColors = {
    fact: 'bg-green-50 dark:bg-green-950/20',
    signal: 'bg-blue-50 dark:bg-blue-950/20',
    explanation: 'bg-amber-50 dark:bg-amber-950/20',
    warning: 'bg-red-50 dark:bg-red-950/20',
  }

  return (
    <div className={`border-l-2 ${borderColors[variant]} ${bgColors[variant]} px-3 py-2 rounded-r`}>
      <div className="flex items-center gap-1.5 mb-1">
        {icon}
        <h5 className="text-xs font-semibold">{title}</h5>
      </div>
      <ul className="space-y-1">
        {items.map((item, i) => (
          <li key={i} className="text-xs text-muted-foreground leading-relaxed">
            {item}
          </li>
        ))}
      </ul>
    </div>
  )
}

export default function ReportAssistantRelationship({ sections }: Props) {
  if (!sections) return null

  const { confirmed_facts, related_signals, possible_explanations, cannot_confirm } = sections

  const hasContent =
    confirmed_facts.length > 0 ||
    related_signals.length > 0 ||
    possible_explanations.length > 0 ||
    cannot_confirm.length > 0

  if (!hasContent) return null

  return (
    <div className="mt-3 space-y-2">
      <h4 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
        关系分析
      </h4>
      <Card className="p-3 space-y-2">
        <SectionBlock
          title="已确认事实"
          icon={<CheckCircle className="h-3.5 w-3.5 text-green-600" />}
          items={confirmed_facts}
          variant="fact"
        />
        <SectionBlock
          title="相关信号"
          icon={<Activity className="h-3.5 w-3.5 text-blue-600" />}
          items={related_signals}
          variant="signal"
        />
        <SectionBlock
          title="可能解释"
          icon={<Lightbulb className="h-3.5 w-3.5 text-amber-600" />}
          items={possible_explanations}
          variant="explanation"
        />
        <SectionBlock
          title="无法确认"
          icon={<AlertTriangle className="h-3.5 w-3.5 text-red-600" />}
          items={cannot_confirm}
          variant="warning"
        />
      </Card>
    </div>
  )
}
