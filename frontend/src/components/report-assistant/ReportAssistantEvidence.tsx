/**
 * 智能报告助手 — 证据卡片组件。
 *
 * 展示回答中关键数字的证据来源（五元绑定：实体 + 指标 + 数值 + 单位 + 来源）。
 *
 * 安全要求：
 * - 证据是最终可信数字展示区
 * - 不从 AI 回答文本重新抽取数字生成卡片
 * - 不相信客户端上轮 metadata
 * - 不在前端更改 evidence 数值
 * - 不展示空公式或空表名占位符
 * - 心理报告不展示学生 ID、姓名或原始内容
 *
 * 默认只展示 label + value + unit。
 * 点击"查看依据"后展开来源表、公式、报告 ID。
 */

import { useState } from 'react'
import { ChevronDown, ChevronUp, FileText, Hash, Calculator } from 'lucide-react'
import { Button } from '@/components/ui/button'
import type { EvidenceItem } from '@/types/report-assistant'

interface Props {
  /** 证据项列表 */
  evidence: EvidenceItem[]
}

export default function ReportAssistantEvidence({ evidence }: Props) {
  const [expandedId, setExpandedId] = useState<string | null>(null)

  if (!evidence || evidence.length === 0) return null

  const toggleExpand = (id: string) => {
    setExpandedId((prev) => (prev === id ? null : id))
  }

  return (
    <div className="mt-3 space-y-2">
      <p className="text-xs font-medium text-muted-foreground">
        AI 根据报告数据生成解释，关键数字请以证据卡片和原报告为准。
      </p>
      <div className="space-y-1.5">
        {evidence.map((item) => {
          const isExpanded = expandedId === item.evidence_id
          const hasDetail = (item.source_tables && item.source_tables.length > 0) || item.formula

          return (
            <div
              key={item.evidence_id || `${item.label}-${item.value}`}
              className="rounded-md border bg-card px-3 py-2 text-sm"
            >
              {/* 默认展示行：label + value + unit */}
              <div className="flex items-center justify-between">
                <span className="text-muted-foreground">{item.label || item.metric_name || '指标'}</span>
                <span className="ml-2 font-semibold tabular-nums">
                  {item.value != null ? String(item.value) : '-'}
                  {item.unit ? ` ${item.unit}` : ''}
                </span>
              </div>

              {/* 展开详情 */}
              {hasDetail && (
                <>
                  {isExpanded && (
                    <div className="mt-2 border-t pt-2 text-xs text-muted-foreground space-y-1">
                      {item.entity_id && (
                        <div className="flex items-center gap-1.5">
                          <Hash className="h-3 w-3" />
                          <span>实体: {item.entity_id}</span>
                        </div>
                      )}
                      {item.metric_name && (
                        <div className="flex items-center gap-1.5">
                          <FileText className="h-3 w-3" />
                          <span>指标: {item.metric_name}</span>
                        </div>
                      )}
                      {item.source_tables && item.source_tables.length > 0 && (
                        <div className="flex items-center gap-1.5">
                          <FileText className="h-3 w-3" />
                          <span>来源表: {item.source_tables.join(', ')}</span>
                        </div>
                      )}
                      {item.formula && (
                        <div className="flex items-center gap-1.5">
                          <Calculator className="h-3 w-3" />
                          <span>公式: {item.formula}</span>
                        </div>
                      )}
                      {item.source_report_id > 0 && (
                        <div className="flex items-center gap-1.5">
                          <FileText className="h-3 w-3" />
                          <span>报告 ID: {item.source_report_id}</span>
                        </div>
                      )}
                    </div>
                  )}
                  <Button
                    variant="ghost"
                    size="sm"
                    className="mt-1 h-6 px-1.5 text-xs text-muted-foreground"
                    onClick={() => toggleExpand(item.evidence_id)}
                  >
                    {isExpanded ? (
                      <><ChevronUp className="mr-1 h-3 w-3" />收起依据</>
                    ) : (
                      <><ChevronDown className="mr-1 h-3 w-3" />查看依据</>
                    )}
                  </Button>
                </>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
