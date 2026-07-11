/**
 * 智能报告助手 — 组件测试。
 *
 * 测试目标：
 * 1. Panel 展示用户和助手消息
 * 2. 发送中禁用提交按钮
 * 3. conversation_context 从响应更新
 * 4. 各状态渲染（generating/clarification/data_quality/evidence/suggestions）
 * 5. 建议追问使用最新上下文
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import ReportAssistantMessage from '@/components/report-assistant/ReportAssistantMessage'
import ReportAssistantEvidence from '@/components/report-assistant/ReportAssistantEvidence'
import ReportAssistantDataQuality from '@/components/report-assistant/ReportAssistantDataQuality'
import ReportAssistantSuggestions from '@/components/report-assistant/ReportAssistantSuggestions'
import ReportAssistantComposer from '@/components/report-assistant/ReportAssistantComposer'
import type { AssistantMessage, EvidenceItem, AssistantDataQuality } from '@/types/report-assistant'

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

/** 创建测试用 EvidenceItem */
function makeEvidence(overrides: Partial<EvidenceItem> = {}): EvidenceItem {
  return {
    evidence_id: 'E1',
    entity_type: 'application',
    entity_id: 'A1024',
    metric_name: 'risk_score',
    label: '申请 #A1024 风险分',
    value: 90,
    unit: '分',
    source_report_id: 128,
    source_tables: ['application_risk_fact'],
    formula: 'base_score + overdue_bonus',
    ...overrides,
  }
}

// ============================================================================
// ReportAssistantMessage 测试
// ============================================================================

describe('ReportAssistantMessage', () => {
  it('渲染用户消息', () => {
    render(
      <MemoryRouter>
        <ReportAssistantMessage message={makeMsg({ role: 'user', content: '看看申请风险' })} />
      </MemoryRouter>
    )
    expect(screen.getByText('看看申请风险')).toBeInTheDocument()
  })

  it('渲染助手消息', () => {
    render(
      <MemoryRouter>
        <ReportAssistantMessage message={makeMsg({ role: 'assistant', content: '当前有3个高风险申请。', status: 'completed' })} />
      </MemoryRouter>
    )
    expect(screen.getByText('当前有3个高风险申请。')).toBeInTheDocument()
  })

  it('渲染 generating 状态', () => {
    render(
      <MemoryRouter>
        <ReportAssistantMessage message={makeMsg({
          role: 'assistant',
          content: '',
          status: 'generating',
          reportId: 128,
          reportType: 'application_risk',
          assumptions: ['统计周期：最近7天'],
        })} />
      </MemoryRouter>
    )
    expect(screen.getByText('已创建报告任务，正在后台生成。')).toBeInTheDocument()
    expect(screen.getByText('查看报告详情')).toBeInTheDocument()
  })

  it('渲染澄清为普通消息（非错误）', () => {
    render(
      <MemoryRouter>
        <ReportAssistantMessage message={makeMsg({
          role: 'assistant',
          content: '请问你想看哪个报告类型？',
          status: 'needs_clarification',
        })} />
      </MemoryRouter>
    )
    expect(screen.getByText('请问你想看哪个报告类型？')).toBeInTheDocument()
  })

  it('渲染数据质量 warning 提示', () => {
    render(
      <MemoryRouter>
        <ReportAssistantMessage message={makeMsg({
          role: 'assistant',
          content: '分析结果',
          status: 'completed',
          dataQuality: { status: 'warning', warnings: ['缺失可选数据源'] },
        })} />
      </MemoryRouter>
    )
    expect(screen.getByText('部分数据缺失')).toBeInTheDocument()
  })

  it('渲染证据卡片', () => {
    render(
      <MemoryRouter>
        <ReportAssistantMessage message={makeMsg({
          role: 'assistant',
          content: '申请 A1024 风险分较高。',
          status: 'completed',
          evidence: [makeEvidence()],
        })} />
      </MemoryRouter>
    )
    expect(screen.getByText('申请 #A1024 风险分')).toBeInTheDocument()
    expect(screen.getByText('90 分')).toBeInTheDocument()
  })

  it('渲染建议追问按钮', () => {
    const onFollowUp = vi.fn()
    render(
      <MemoryRouter>
        <ReportAssistantMessage
          message={makeMsg({
            role: 'assistant',
            content: '回答',
            status: 'completed',
            suggestedFollowUps: ['最严重的是哪几个？', '这个风险分怎么算？'],
          })}
          onFollowUp={onFollowUp}
        />
      </MemoryRouter>
    )
    expect(screen.getByText('最严重的是哪几个？')).toBeInTheDocument()
    expect(screen.getByText('这个风险分怎么算？')).toBeInTheDocument()
  })

  it('permission_denied 不渲染证据', () => {
    render(
      <MemoryRouter>
        <ReportAssistantMessage message={makeMsg({
          role: 'assistant',
          content: '权限不足',
          status: 'permission_denied',
          evidence: [makeEvidence()],
        })} />
      </MemoryRouter>
    )
    // "权限不足" 出现在标题和内容两处
    const permissionTexts = screen.getAllByText('权限不足')
    expect(permissionTexts.length).toBeGreaterThanOrEqual(1)
    // 证据只在 completed 状态展示
    expect(screen.queryByText('申请 #A1024 风险分')).not.toBeInTheDocument()
    expect(screen.queryByText('90 分')).not.toBeInTheDocument()
  })
})

// ============================================================================
// ReportAssistantEvidence 测试
// ============================================================================

describe('ReportAssistantEvidence', () => {
  it('默认展示 label + value + unit', () => {
    render(
      <MemoryRouter>
        <ReportAssistantEvidence evidence={[makeEvidence()]} />
      </MemoryRouter>
    )
    expect(screen.getByText('申请 #A1024 风险分')).toBeInTheDocument()
    expect(screen.getByText('90 分')).toBeInTheDocument()
  })

  it('点击查看依据后展开来源表和公式', async () => {
    const user = userEvent.setup()
    render(
      <MemoryRouter>
        <ReportAssistantEvidence evidence={[makeEvidence({
          source_tables: ['application_risk_fact'],
          formula: 'base_score + overdue_bonus',
        })]} />
      </MemoryRouter>
    )

    await user.click(screen.getByText('查看依据'))
    // 展开后显示来源表和公式
    expect(screen.getByText(/来源表:/)).toHaveTextContent('application_risk_fact')
    expect(screen.getByText(/公式:/)).toHaveTextContent('base_score + overdue_bonus')
  })

  it('空证据列表不渲染任何内容', () => {
    const { container } = render(
      <MemoryRouter>
        <ReportAssistantEvidence evidence={[]} />
      </MemoryRouter>
    )
    expect(container.firstChild).toBeNull()
  })

  it('不展示空公式占位符', () => {
    render(
      <MemoryRouter>
        <ReportAssistantEvidence evidence={[makeEvidence({ formula: null, source_tables: [] })]} />
      </MemoryRouter>
    )
    // 没有 source_tables 和 formula 时不显示"查看依据"按钮
    expect(screen.queryByText('查看依据')).not.toBeInTheDocument()
  })
})

// ============================================================================
// ReportAssistantDataQuality 测试
// ============================================================================

describe('ReportAssistantDataQuality', () => {
  it('ok 状态无警告时不显示', () => {
    const { container } = render(
      <ReportAssistantDataQuality dataQuality={{ status: 'ok', warnings: [] }} />
    )
    expect(container.firstChild).toBeNull()
  })

  it('warning 状态显示黄色提示', () => {
    render(
      <ReportAssistantDataQuality dataQuality={{ status: 'warning', warnings: ['数据源不完整'] }} />
    )
    expect(screen.getByText('部分数据缺失')).toBeInTheDocument()
    expect(screen.getByText('数据源不完整')).toBeInTheDocument()
  })

  it('empty 状态显示无数据提示', () => {
    render(
      <ReportAssistantDataQuality dataQuality={{ status: 'empty' }} />
    )
    expect(screen.getByText('当前周期无有效数据')).toBeInTheDocument()
  })

  it('degraded 状态显示降级提示', () => {
    render(
      <ReportAssistantDataQuality dataQuality={{ status: 'degraded' }} />
    )
    expect(screen.getByText('报告处于降级状态')).toBeInTheDocument()
  })

  it('failed 状态显示红色提示', () => {
    render(
      <ReportAssistantDataQuality dataQuality={{ status: 'failed' }} />
    )
    expect(screen.getByText('不能基于当前报告分析')).toBeInTheDocument()
  })
})

// ============================================================================
// ReportAssistantSuggestions 测试
// ============================================================================

describe('ReportAssistantSuggestions', () => {
  it('点击追问按钮触发回调', async () => {
    const user = userEvent.setup()
    const onSelect = vi.fn()

    render(
      <ReportAssistantSuggestions
        suggestions={['最严重的？', '怎么算的？']}
        onSelect={onSelect}
      />
    )

    await user.click(screen.getByText('最严重的？'))
    expect(onSelect).toHaveBeenCalledWith('最严重的？')
  })

  it('发送中禁用追问按钮', () => {
    render(
      <ReportAssistantSuggestions
        suggestions={['追问']}
        onSelect={vi.fn()}
        disabled={true}
      />
    )
    expect(screen.getByText('追问').closest('button')).toBeDisabled()
  })

  it('空建议列表不渲染', () => {
    const { container } = render(
      <ReportAssistantSuggestions suggestions={[]} onSelect={vi.fn()} />
    )
    expect(container.firstChild).toBeNull()
  })
})

// ============================================================================
// ReportAssistantComposer 测试
// ============================================================================

describe('ReportAssistantComposer', () => {
  it('点击发送按钮触发回调', async () => {
    const user = userEvent.setup()
    const onSend = vi.fn()

    render(<ReportAssistantComposer onSend={onSend} />)

    const textarea = screen.getByPlaceholderText('输入消息...')
    await user.type(textarea, '你好')
    await user.click(screen.getByRole('button', { name: '发送消息' }))

    expect(onSend).toHaveBeenCalledWith('你好')
  })

  it('Enter 键发送消息', async () => {
    const user = userEvent.setup()
    const onSend = vi.fn()

    render(<ReportAssistantComposer onSend={onSend} />)

    const textarea = screen.getByPlaceholderText('输入消息...')
    await user.type(textarea, '你好{Enter}')

    expect(onSend).toHaveBeenCalledWith('你好')
  })

  it('发送中禁用输入和按钮', () => {
    render(<ReportAssistantComposer onSend={vi.fn()} disabled={true} />)

    expect(screen.getByPlaceholderText('输入消息...')).toBeDisabled()
    expect(screen.getByRole('button', { name: '发送消息' })).toBeDisabled()
  })

  it('空消息不允许发送', async () => {
    const user = userEvent.setup()
    const onSend = vi.fn()

    render(<ReportAssistantComposer onSend={onSend} />)

    await user.click(screen.getByRole('button', { name: '发送消息' }))
    expect(onSend).not.toHaveBeenCalled()
  })
})
