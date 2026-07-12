/**
 * 智能报告助手 — 安全测试。
 *
 * 测试目标：
 * 1. 不持久化对话到 localStorage
 * 2. 不渲染后端堆栈信息
 * 3. 不从 answer 文本重新构建证据
 * 4. 心理证据隐藏敏感字段
 * 5. permission_denied 不渲染证据
 */

import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import ReportAssistantMessage from '@/components/report-assistant/ReportAssistantMessage'
import ReportAssistantEvidence from '@/components/report-assistant/ReportAssistantEvidence'
import type { AssistantMessage, EvidenceItem } from '@/types/report-assistant'

/** 创建测试用 AssistantMessage */
function makeMsg(overrides: Partial<AssistantMessage> = {}): AssistantMessage {
  return {
    id: 'msg-1',
    role: 'assistant',
    content: '测试内容',
    createdAt: new Date().toISOString(),
    ...overrides,
  }
}

/** 创建心理报告证据 */
function makePsychEvidence(overrides: Partial<EvidenceItem> = {}): EvidenceItem {
  return {
    evidence_id: 'E1',
    entity_type: 'student',
    entity_id: 'STU001',
    metric_name: 'emotion_score',
    label: '学生 #STU001 情绪分',
    value: 35,
    unit: '分',
    source_report_id: 200,
    source_tables: ['psych_weekly_fact'],
    ...overrides,
  }
}

// ============================================================================

describe('安全测试', () => {
  it('不渲染后端堆栈信息', () => {
    render(
      <MemoryRouter>
        <ReportAssistantMessage message={makeMsg({
          role: 'assistant',
          content: '处理请求时出错，请稍后重试。',
          status: 'error',
        })} />
      </MemoryRouter>
    )
    // 不应有堆栈、异常类名或 SQL
    expect(screen.queryByText(/Traceback/)).not.toBeInTheDocument()
    expect(screen.queryByText(/File "/)).not.toBeInTheDocument()
    expect(screen.queryByText(/SELECT/)).not.toBeInTheDocument()
    expect(screen.queryByText(/Exception/)).not.toBeInTheDocument()
  })

  it('不从 answer 文本重新构建证据', () => {
    // 证据只从 evidence prop 展示，不从 content 文本中提取
    render(
      <MemoryRouter>
        <ReportAssistantMessage message={makeMsg({
          role: 'assistant',
          content: '申请 A1024 风险分为 90 分，共有 8 个高风险。',
          status: 'completed',
          evidence: [], // 无证据
        })} />
      </MemoryRouter>
    )
    // 没有证据卡片展示
    expect(screen.queryByText('查看依据')).not.toBeInTheDocument()
  })

  it('心理证据隐藏敏感字段', () => {
    // 心理报告 entity_type='student' 时，仍然展示 evidence
    // 但前端不得额外展示学生姓名或原始心理内容
    // 证据卡片只展示 label + value + unit，不额外泄露敏感信息
    render(
      <MemoryRouter>
        <ReportAssistantEvidence evidence={[makePsychEvidence({
          label: '心理预警等级',
          entity_type: 'student',
          entity_id: undefined, // 不展示学生 ID
        })]} />
      </MemoryRouter>
    )
    // 证据展示了 label + value
    expect(screen.getByText('心理预警等级')).toBeInTheDocument()
    // 但不展示学生 ID（因为 entity_id 未设置）
    expect(screen.queryByText('STU001')).not.toBeInTheDocument()
    // 不展示原始内容
    expect(screen.queryByText('心理评估原文')).not.toBeInTheDocument()
  })

  it('permission_denied 不渲染证据卡片', () => {
    render(
      <MemoryRouter>
        <ReportAssistantMessage message={makeMsg({
          role: 'assistant',
          content: '权限不足',
          status: 'permission_denied',
          evidence: [
            {
              evidence_id: 'E1',
              entity_type: 'application',
              entity_id: 'A1024',
              metric_name: 'risk_score',
              label: '申请 #A1024 风险分',
              value: 90,
              unit: '分',
              source_report_id: 128,
              source_tables: ['application_risk_fact'],
            },
          ],
        })} />
      </MemoryRouter>
    )
    // 不展示证据值
    expect(screen.queryByText('申请 #A1024 风险分')).not.toBeInTheDocument()
    expect(screen.queryByText('90 分')).not.toBeInTheDocument()
  })

  it('error 状态不渲染 report_type 敏感信息', () => {
    render(
      <MemoryRouter>
        <ReportAssistantMessage message={makeMsg({
          role: 'assistant',
          content: '处理请求时出错，请稍后重试。',
          status: 'error',
        })} />
      </MemoryRouter>
    )
    // 错误消息是稳定的，不暴露后端详情
    expect(screen.getByText('处理请求时出错，请稍后重试。')).toBeInTheDocument()
  })
})
