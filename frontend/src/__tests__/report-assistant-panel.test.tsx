/**
 * 智能报告助手 — ReportAssistantPanel 集成测试。
 *
 * 测试完整的 Panel 状态链路，而不是单独测试子组件。
 * Mock API 层，验证多轮状态传递、幂等键规则、防重复提交、路由跳转等。
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { ReportAssistantPanel } from '@/components/report-assistant'
import type { ReportAssistantMessageResponse } from '@/types/report-assistant'

// ============================================================
//  Mock API 层
// ============================================================

const mockSendMessage = vi.fn()

vi.mock('@/api/report-assistant', () => ({
  sendReportAssistantMessage: (...args: unknown[]) => mockSendMessage(...args),
}))

// ============================================================
//  Mock localStorage / sessionStorage
// ============================================================

const storageSpies = {
  localStorageSetItem: vi.spyOn(Storage.prototype, 'setItem'),
  sessionStorageSetItem: vi.spyOn(Storage.prototype, 'setItem'),
}

// ============================================================
//  响应工厂函数
// ============================================================

let responseCounter = 0

/** 创建最小有效响应 */
function makeResponse(overrides: Partial<ReportAssistantMessageResponse> = {}): ReportAssistantMessageResponse {
  responseCounter++
  return {
    status: 'completed',
    intent: 'unknown',
    answer: `测试回答 #${responseCounter}`,
    assumptions: [],
    evidence: [],
    suggested_follow_ups: [],
    conversation_context: {
      conversation_id: 'test-conv-id',
      referenced_entities: [],
    },
    ...overrides,
  }
}

/** 创建 generating 响应 */
function makeGeneratingResponse(reportId = 128): ReportAssistantMessageResponse {
  return makeResponse({
    status: 'generating',
    intent: 'generate_report',
    report_id: reportId,
    report_type: 'application_risk',
    answer: '已创建报告任务，正在后台生成。',
    assumptions: ['统计周期：最近7天（2026-07-04 至 2026-07-10）'],
    suggested_follow_ups: ['报告生成好了吗？', '检查生成状态'],
    conversation_context: {
      conversation_id: 'conv-001',
      last_report_id: reportId,
      last_report_type: 'application_risk',
      last_period_start: '2026-07-04',
      last_period_end: '2026-07-10',
      referenced_entities: [],
      previous_intent: 'generate_report',
    },
  })
}

/** 创建 drill_down 响应 */
function makeDrillDownResponse(reportId = 128): ReportAssistantMessageResponse {
  return makeResponse({
    status: 'completed',
    intent: 'drill_down',
    answer: '当前共有 3 个高风险申请。最严重的是 A1024（90分）、A1058（70分）、A2001（40分）。',
    evidence: [
      {
        evidence_id: 'E1',
        entity_type: 'application',
        entity_id: 'A1024',
        metric_name: 'risk_score',
        label: '申请 #A1024 风险分',
        value: 90,
        unit: '分',
        source_report_id: reportId,
        source_tables: ['application_risk_fact'],
      },
      {
        evidence_id: 'E2',
        entity_type: 'application',
        entity_id: 'A1058',
        metric_name: 'risk_score',
        label: '申请 #A1058 风险分',
        value: 70,
        unit: '分',
        source_report_id: reportId,
        source_tables: ['application_risk_fact'],
      },
    ],
    suggested_follow_ups: ['第一个为什么这么高？', '这个风险分怎么算？'],
    conversation_context: {
      conversation_id: 'conv-001',
      last_report_id: reportId,
      last_report_type: 'application_risk',
      last_period_start: '2026-07-04',
      last_period_end: '2026-07-10',
      referenced_entities: [
        {
          position: 1,
          entity_type: 'application',
          entity_id: 'A1024',
          display_name: '申请 A1024',
          source_report_id: reportId,
          metadata: { risk_score: 90, risk_level: 'high' },
        },
        {
          position: 2,
          entity_type: 'application',
          entity_id: 'A1058',
          display_name: '申请 A1058',
          source_report_id: reportId,
          metadata: { risk_score: 70, risk_level: 'high' },
        },
      ],
      previous_intent: 'drill_down',
    },
  })
}

/** 创建 explain_risk 响应 */
function makeExplainRiskResponse(reportId = 128): ReportAssistantMessageResponse {
  return makeResponse({
    status: 'completed',
    intent: 'explain_risk',
    answer: '申请 A1024 风险分为 90 分，属于高风险。主要原因：逾期提交材料（+30分）、缺少推荐信（+30分）、临近截止日期（+30分）。',
    evidence: [
      {
        evidence_id: 'E1',
        entity_type: 'application',
        entity_id: 'A1024',
        metric_name: 'risk_score',
        label: '申请 #A1024 风险分',
        value: 90,
        unit: '分',
        source_report_id: reportId,
        source_tables: ['application_risk_fact'],
        formula: 'base_score + overdue_bonus + missing_material_bonus',
      },
    ],
    suggested_follow_ups: ['这个风险分怎么算？'],
    conversation_context: {
      conversation_id: 'conv-001',
      last_report_id: reportId,
      last_report_type: 'application_risk',
      last_period_start: '2026-07-04',
      last_period_end: '2026-07-10',
      referenced_entities: [
        {
          position: 1,
          entity_type: 'application',
          entity_id: 'A1024',
          display_name: '申请 A1024',
          source_report_id: reportId,
          metadata: { risk_score: 90, risk_level: 'high' },
        },
      ],
      previous_intent: 'explain_risk',
    },
  })
}

// ============================================================
//  辅助函数
// ============================================================

/** 渲染面板 */
function renderPanel(overrides: { initialReportId?: number; initialReportType?: string } = {}) {
  return render(
    <MemoryRouter initialEntries={['/reports']}>
      <ReportAssistantPanel
        open={true}
        onClose={vi.fn()}
        initialReportId={overrides.initialReportId ?? null}
        initialReportType={overrides.initialReportType ?? null}
      />
    </MemoryRouter>
  )
}

/** 等待 API 调用完成 */
async function waitForApiCall() {
  await waitFor(() => {
    expect(mockSendMessage).toHaveBeenCalled()
  })
}

// ============================================================
//  测试
// ============================================================

describe('ReportAssistantPanel 集成测试', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    responseCounter = 0
    mockSendMessage.mockReset()
    storageSpies.localStorageSetItem.mockClear()
    storageSpies.sessionStorageSetItem.mockClear()
  })

  afterEach(() => {
    storageSpies.localStorageSetItem.mockClear()
    storageSpies.sessionStorageSetItem.mockClear()
  })

  // ========================================================================
  //  1. conversation_context 更新
  // ========================================================================

  describe('conversation_context 更新', () => {
    it('第一轮 generating 后 context 被更新为 last_report_id=128', async () => {
      mockSendMessage.mockResolvedValueOnce(makeGeneratingResponse(128))
      const user = userEvent.setup()
      renderPanel()

      // 发送第一轮消息
      const textarea = screen.getByPlaceholderText('输入消息...')
      await user.type(textarea, '看看申请风险')
      await user.click(screen.getByRole('button', { name: '发送消息' })) // Send button

      await waitForApiCall()

      // 验证 API 调用参数
      expect(mockSendMessage).toHaveBeenCalledTimes(1)
      const firstCall = mockSendMessage.mock.calls[0][0]
      expect(firstCall.message).toBe('看看申请风险')
    })

    it('第二轮请求携带上一轮更新的 context', async () => {
      mockSendMessage
        .mockResolvedValueOnce(makeGeneratingResponse(128))
        .mockResolvedValueOnce(makeResponse({
          status: 'completed',
          intent: 'query_report_status',
          answer: '报告 #128 已生成完成。',
          report_id: 128,
          report_type: 'application_risk',
          conversation_context: {
            conversation_id: 'conv-001',
            last_report_id: 128,
            last_report_type: 'application_risk',
            referenced_entities: [],
          },
        }))

      const user = userEvent.setup()
      renderPanel()

      // 第一轮
      const textarea = screen.getByPlaceholderText('输入消息...')
      await user.type(textarea, '看看申请风险')
      await user.click(screen.getByRole('button', { name: '发送消息' }))

      await waitFor(() => {
        expect(mockSendMessage).toHaveBeenCalledTimes(1)
      })

      // 第二轮
      await user.type(textarea, '报告生成好了吗？')
      await user.click(screen.getByRole('button', { name: '发送消息' }))

      await waitFor(() => {
        expect(mockSendMessage).toHaveBeenCalledTimes(2)
      })

      // 验证第二轮请求携带了第一轮更新的 context
      const secondCall = mockSendMessage.mock.calls[1][0]
      expect(secondCall.message).toBe('报告生成好了吗？')
      expect(secondCall.conversation_context.last_report_id).toBe(128)
      expect(secondCall.conversation_context.last_report_type).toBe('application_risk')
      // 不应继续发送初始化时的空 context
      expect(secondCall.conversation_context.conversation_id).toBe('conv-001')
    })
  })

  // ========================================================================
  //  2. referenced_entities 回传
  // ========================================================================

  describe('referenced_entities 回传', () => {
    it('钻取响应中的 referenced_entities 被下一轮原样回传', async () => {
      mockSendMessage
        .mockResolvedValueOnce(makeGeneratingResponse(128))
        .mockResolvedValueOnce(makeDrillDownResponse(128))
        .mockResolvedValueOnce(makeExplainRiskResponse(128))

      const user = userEvent.setup()
      renderPanel()

      const textarea = screen.getByPlaceholderText('输入消息...')

      // Turn 1: 生成报告
      await user.type(textarea, '看看申请风险')
      await user.click(screen.getByRole('button', { name: '发送消息' }))
      await waitFor(() => {
        expect(mockSendMessage).toHaveBeenCalledTimes(1)
      })

      // Turn 2: 钻取
      await user.type(textarea, '最严重的是哪几个？')
      await user.click(screen.getByRole('button', { name: '发送消息' }))
      await waitFor(() => {
        expect(mockSendMessage).toHaveBeenCalledTimes(2)
      })

      // Turn 3: 解释第一个
      await user.type(textarea, '第一个为什么这么高？')
      await user.click(screen.getByRole('button', { name: '发送消息' }))
      await waitFor(() => {
        expect(mockSendMessage).toHaveBeenCalledTimes(3)
      })

      // 验证第三轮请求携带了 referenced_entities
      const thirdCall = mockSendMessage.mock.calls[2][0]
      expect(thirdCall.message).toBe('第一个为什么这么高？')
      expect(thirdCall.conversation_context.referenced_entities).toHaveLength(2)
      expect(thirdCall.conversation_context.referenced_entities[0].entity_id).toBe('A1024')
      expect(thirdCall.conversation_context.referenced_entities[0].position).toBe(1)
      expect(thirdCall.conversation_context.referenced_entities[0].source_report_id).toBe(128)
      // 前端不得自行修改实体 metadata
      expect(thirdCall.conversation_context.referenced_entities[0].metadata.risk_score).toBe(90)
    })
  })

  // ========================================================================
  //  3. 建议追问使用最新 context
  // ========================================================================

  describe('建议追问使用最新 context', () => {
    it('点击 suggested_follow_up 使用更新后的 context', async () => {
      mockSendMessage
        .mockResolvedValueOnce(makeDrillDownResponse(128))
        .mockResolvedValueOnce(makeExplainRiskResponse(128))

      const user = userEvent.setup()
      renderPanel()

      // 发送钻取请求
      const textarea = screen.getByPlaceholderText('输入消息...')
      await user.type(textarea, '最严重的是哪几个？')
      await user.click(screen.getByRole('button', { name: '发送消息' }))

      await waitFor(() => {
        expect(mockSendMessage).toHaveBeenCalledTimes(1)
      })

      // 等待 suggested_follow_ups 渲染
      await waitFor(() => {
        expect(screen.getByText('第一个为什么这么高？')).toBeInTheDocument()
      })

      // 点击建议追问
      await user.click(screen.getByText('第一个为什么这么高？'))

      await waitFor(() => {
        expect(mockSendMessage).toHaveBeenCalledTimes(2)
      })

      // 验证追问请求使用了上一轮更新的 context
      const followUpCall = mockSendMessage.mock.calls[1][0]
      expect(followUpCall.message).toBe('第一个为什么这么高？')
      expect(followUpCall.conversation_context.last_report_id).toBe(128)
      expect(followUpCall.conversation_context.referenced_entities).toHaveLength(2)
      expect(followUpCall.conversation_context.previous_intent).toBe('drill_down')
    })
  })

  // ========================================================================
  //  4. client_request_id 规则
  // ========================================================================

  describe('client_request_id 规则', () => {
    it('新消息生成新的 client_request_id', async () => {
      mockSendMessage
        .mockResolvedValueOnce(makeResponse())
        .mockResolvedValueOnce(makeResponse())

      const user = userEvent.setup()
      renderPanel()

      const textarea = screen.getByPlaceholderText('输入消息...')

      // 第一轮
      await user.type(textarea, '消息1')
      await user.click(screen.getByRole('button', { name: '发送消息' }))
      await waitFor(() => {
        expect(mockSendMessage).toHaveBeenCalledTimes(1)
      })

      // 第二轮
      await user.type(textarea, '消息2')
      await user.click(screen.getByRole('button', { name: '发送消息' }))
      await waitFor(() => {
        expect(mockSendMessage).toHaveBeenCalledTimes(2)
      })

      const id1 = mockSendMessage.mock.calls[0][0].client_request_id
      const id2 = mockSendMessage.mock.calls[1][0].client_request_id

      expect(id1).toBeTruthy()
      expect(id2).toBeTruthy()
      expect(id1).not.toBe(id2)
    })

    it('追问生成新的 client_request_id', async () => {
      mockSendMessage
        .mockResolvedValueOnce(makeDrillDownResponse(128))
        .mockResolvedValueOnce(makeExplainRiskResponse(128))

      const user = userEvent.setup()
      renderPanel()

      // 钻取
      const textarea = screen.getByPlaceholderText('输入消息...')
      await user.type(textarea, '最严重的是哪几个？')
      await user.click(screen.getByRole('button', { name: '发送消息' }))
      await waitFor(() => {
        expect(mockSendMessage).toHaveBeenCalledTimes(1)
      })

      // 等待追问按钮
      await waitFor(() => {
        expect(screen.getByText('第一个为什么这么高？')).toBeInTheDocument()
      })

      await user.click(screen.getByText('第一个为什么这么高？'))
      await waitFor(() => {
        expect(mockSendMessage).toHaveBeenCalledTimes(2)
      })

      const drillId = mockSendMessage.mock.calls[0][0].client_request_id
      const followUpId = mockSendMessage.mock.calls[1][0].client_request_id

      expect(drillId).toBeTruthy()
      expect(followUpId).toBeTruthy()
      // 追问应生成新 ID，不复用钻取的 ID
      expect(followUpId).not.toBe(drillId)
    })
  })

  // ========================================================================
  //  5. Loading 消息替换
  // ========================================================================

  describe('Loading 消息替换', () => {
    it('发送后显示 loading，API 返回后 loading 被真实消息替换', async () => {
      // 使用延迟 mock 确保 loading 状态可以被观察到
      let resolvePromise: (value: ReportAssistantMessageResponse) => void = () => {}
      const delayedPromise = new Promise<ReportAssistantMessageResponse>((resolve) => {
        resolvePromise = resolve
      })
      mockSendMessage.mockReturnValueOnce(delayedPromise)

      const user = userEvent.setup()
      renderPanel()

      const textarea = screen.getByPlaceholderText('输入消息...')
      await user.type(textarea, '测试消息')
      await user.click(screen.getByRole('button', { name: '发送消息' }))

      // 应该显示 loading
      await waitFor(() => {
        expect(screen.getByText('正在处理...')).toBeInTheDocument()
      })

      // 应该只有 1 条 assistant 消息（loading）
      expect(screen.getAllByText('正在处理...')).toHaveLength(1)

      // API 返回
      await act(async () => {
        resolvePromise(makeResponse({
          status: 'completed',
          answer: '这是真实回答内容',
        }))
      })

      // loading 被替换为真实内容
      await waitFor(() => {
        expect(screen.getByText('这是真实回答内容')).toBeInTheDocument()
      })

      // loading 文本不再存在
      expect(screen.queryByText('正在处理...')).not.toBeInTheDocument()
    })

    it('不出现重复的助手消息', async () => {
      mockSendMessage.mockResolvedValueOnce(makeResponse({
        status: 'completed',
        answer: '唯一回答',
      }))

      const user = userEvent.setup()
      renderPanel()

      const textarea = screen.getByPlaceholderText('输入消息...')
      await user.type(textarea, '测试')
      await user.click(screen.getByRole('button', { name: '发送消息' }))

      await waitFor(() => {
        expect(mockSendMessage).toHaveBeenCalledTimes(1)
      })

      // 消息区域应该只有用户消息和助手消息各一条（通过 Bot 头像数量判断）
      await waitFor(() => {
        const answerElements = screen.getAllByText('唯一回答')
        expect(answerElements).toHaveLength(1)
      })
    })
  })

  // ========================================================================
  //  6. 防重复提交
  // ========================================================================

  describe('防重复提交', () => {
    it('快速连续点击只发送一次', async () => {
      let resolvePromise: (value: ReportAssistantMessageResponse) => void = () => {}
      const delayedPromise = new Promise<ReportAssistantMessageResponse>((resolve) => {
        resolvePromise = resolve
      })
      mockSendMessage.mockReturnValueOnce(delayedPromise)

      const user = userEvent.setup()
      renderPanel()

      const textarea = screen.getByPlaceholderText('输入消息...')
      await user.type(textarea, '测试')

      // 快速连续点击发送按钮
      const sendButton = screen.getByRole('button', { name: '发送消息' })
      await user.click(sendButton)
      await user.click(sendButton)
      await user.click(sendButton)

      // API 只调用一次
      expect(mockSendMessage).toHaveBeenCalledTimes(1)

      // 清除 pending 请求
      await act(async () => {
        resolvePromise(makeResponse())
      })
    })
  })

  // ========================================================================
  //  7. 报告跳转
  // ========================================================================

  describe('报告跳转', () => {
    it('generating 状态显示"查看报告详情"链接', async () => {
      mockSendMessage.mockResolvedValueOnce(makeGeneratingResponse(128))

      const user = userEvent.setup()
      renderPanel()

      const textarea = screen.getByPlaceholderText('输入消息...')
      await user.type(textarea, '看看申请风险')
      await user.click(screen.getByRole('button', { name: '发送消息' }))

      await waitForApiCall()

      // 应显示"查看报告详情"按钮
      await waitFor(() => {
        expect(screen.getByText('查看报告详情')).toBeInTheDocument()
      })
    })

    it('completed 状态显示"查看完整报告"链接', async () => {
      mockSendMessage.mockResolvedValueOnce(makeResponse({
        status: 'completed',
        intent: 'drill_down',
        report_id: 42,
        answer: '分析完成。',
      }))

      const user = userEvent.setup()
      renderPanel()

      const textarea = screen.getByPlaceholderText('输入消息...')
      await user.type(textarea, '最严重的？')
      await user.click(screen.getByRole('button', { name: '发送消息' }))

      await waitForApiCall()

      // 应显示"查看完整报告"链接
      await waitFor(() => {
        expect(screen.getByText('查看完整报告')).toBeInTheDocument()
      })
    })
  })

  // ========================================================================
  //  8. 不持久化会话
  // ========================================================================

  describe('不持久化会话', () => {
    it('多轮交互后不写入 localStorage', async () => {
      mockSendMessage
        .mockResolvedValueOnce(makeGeneratingResponse(128))
        .mockResolvedValueOnce(makeDrillDownResponse(128))

      const user = userEvent.setup()
      renderPanel()

      const textarea = screen.getByPlaceholderText('输入消息...')

      await user.type(textarea, '看看申请风险')
      await user.click(screen.getByRole('button', { name: '发送消息' }))
      await waitFor(() => {
        expect(mockSendMessage).toHaveBeenCalledTimes(1)
      })

      await user.type(textarea, '最严重的是哪几个？')
      await user.click(screen.getByRole('button', { name: '发送消息' }))
      await waitFor(() => {
        expect(mockSendMessage).toHaveBeenCalledTimes(2)
      })

      // 检查没有任何业务数据写入 localStorage
      const allSetItemCalls = storageSpies.localStorageSetItem.mock.calls
      for (const call of allSetItemCalls) {
        const key = call[0] as string
        // 排除自动的非业务 key（如 auth-storage）
        if (key === 'auth-storage') continue
        // 不应包含业务数据
        expect(key).not.toMatch(/conversation|context|message|evidence|report|psych/i)
        if (typeof call[1] === 'string') {
          expect(call[1]).not.toMatch(/"conversation_context"|"referenced_entities"|risk_score/)
        }
      }
    })
  })

  // ========================================================================
  //  9. 权限和错误安全
  // ========================================================================

  describe('权限和错误安全', () => {
    it('错误重试复用原 client_request_id 和 conversation_context 快照', async () => {
      mockSendMessage
        .mockResolvedValueOnce(makeGeneratingResponse(128))
        .mockRejectedValueOnce({ response: { status: 500, data: { detail: 'controlled failure' } } })
        .mockResolvedValueOnce(makeResponse({
          report_id: 128,
          report_type: 'application_risk',
          conversation_context: {
            conversation_id: 'conv-001',
            last_report_id: 128,
            last_report_type: 'application_risk',
            referenced_entities: [],
          },
        }))

      const user = userEvent.setup()
      renderPanel()
      const textarea = screen.getByPlaceholderText('输入消息...')

      await user.type(textarea, '看看申请风险')
      await user.click(screen.getByRole('button', { name: '发送消息' }))
      await waitFor(() => expect(mockSendMessage).toHaveBeenCalledTimes(1))

      await user.type(textarea, '报告生成好了吗？')
      await user.click(screen.getByRole('button', { name: '发送消息' }))
      await waitFor(() => expect(mockSendMessage).toHaveBeenCalledTimes(2))

      const failedRequest = structuredClone(mockSendMessage.mock.calls[1][0])
      const retryButton = await screen.findByRole('button', { name: '重试' })
      await user.click(retryButton)
      await user.click(retryButton)

      await waitFor(() => expect(mockSendMessage).toHaveBeenCalledTimes(3))
      const retryRequest = mockSendMessage.mock.calls[2][0]

      expect(retryRequest.message).toBe(failedRequest.message)
      expect(retryRequest.client_request_id).toBe(failedRequest.client_request_id)
      expect(retryRequest.conversation_context).toEqual(failedRequest.conversation_context)
    })

    it('permission_denied 不显示 evidence', async () => {
      mockSendMessage.mockRejectedValueOnce({
        response: { status: 403, data: { detail: '无权限访问' } },
      })

      const user = userEvent.setup()
      renderPanel()

      const textarea = screen.getByPlaceholderText('输入消息...')
      await user.type(textarea, '查看渠道ROI')
      await user.click(screen.getByRole('button', { name: '发送消息' }))

      await waitFor(() => {
        expect(mockSendMessage).toHaveBeenCalledTimes(1)
      })

      // 显示权限不足
      await waitFor(() => {
        expect(screen.getByText('权限不足，无法执行此操作。')).toBeInTheDocument()
      })

      // 不显示 evidence 相关内容
      expect(screen.queryByText('查看依据')).not.toBeInTheDocument()
    })

    it('500 错误不展示堆栈信息', async () => {
      mockSendMessage.mockRejectedValueOnce({
        response: {
          status: 500,
          data: { detail: 'Internal Server Error: Traceback (most recent call last):\n  File "main.py", line 42\nSQL: SELECT * FROM users' },
        },
      })

      const user = userEvent.setup()
      renderPanel()

      const textarea = screen.getByPlaceholderText('输入消息...')
      await user.type(textarea, '测试')
      await user.click(screen.getByRole('button', { name: '发送消息' }))

      await waitFor(() => {
        expect(mockSendMessage).toHaveBeenCalledTimes(1)
      })

      // 应显示稳定错误文案
      await waitFor(() => {
        expect(screen.getByText('处理请求时出错，请稍后重试。')).toBeInTheDocument()
      })

      // 不显示堆栈、SQL、异常类名
      expect(screen.queryByText(/Traceback/)).not.toBeInTheDocument()
      expect(screen.queryByText(/File "/)).not.toBeInTheDocument()
      expect(screen.queryByText(/SELECT/)).not.toBeInTheDocument()
      expect(screen.queryByText(/Exception/)).not.toBeInTheDocument()
    })

    it('503 错误显示功能关闭状态', async () => {
      mockSendMessage.mockRejectedValueOnce({
        response: {
          status: 503,
          data: { detail: '智能报告助手功能未开启' },
        },
      })

      const user = userEvent.setup()
      renderPanel()

      const textarea = screen.getByPlaceholderText('输入消息...')
      await user.type(textarea, '测试')
      await user.click(screen.getByRole('button', { name: '发送消息' }))

      await waitFor(() => {
        expect(mockSendMessage).toHaveBeenCalledTimes(1)
      })

      // 应显示功能关闭
      await waitFor(() => {
        expect(screen.getByText('功能未开启')).toBeInTheDocument()
      })
      expect(screen.getByText('智能报告助手当前未启用，原报告功能仍可正常使用。')).toBeInTheDocument()
    })

    it('404 错误显示报告不存在提示', async () => {
      mockSendMessage.mockRejectedValueOnce({
        response: { status: 404, data: { detail: '报告不存在' } },
      })

      const user = userEvent.setup()
      renderPanel()

      const textarea = screen.getByPlaceholderText('输入消息...')
      await user.type(textarea, '查看报告999')
      await user.click(screen.getByRole('button', { name: '发送消息' }))

      await waitFor(() => {
        expect(mockSendMessage).toHaveBeenCalledTimes(1)
      })

      await waitFor(() => {
        expect(screen.getByText('报告不存在或已不可访问。你可以尝试重新生成报告。')).toBeInTheDocument()
      })
    })
  })
})
