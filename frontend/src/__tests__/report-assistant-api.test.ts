/**
 * 智能报告助手 — API 层测试。
 *
 * 测试目标：
 * 1. 请求正确携带 conversation_context
 * 2. 幂等键在重试时保持不变
 * 3. 各 HTTP 状态码正确处理
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import axios from 'axios'
import type { ReportAssistantMessageResponse } from '@/types/report-assistant'

// Mock apiClient
vi.mock('@/lib/api-client', () => {
  const mockPost = vi.fn()
  return {
    default: {
      post: mockPost,
      get: vi.fn(),
    },
    apiClient: {
      post: mockPost,
      get: vi.fn(),
    },
  }
})

import apiClient from '@/lib/api-client'
import { sendReportAssistantMessage } from '@/api/report-assistant'

const mockPost = apiClient.post as ReturnType<typeof vi.fn>

/** 创建最小有效响应 */
function makeResponse(overrides: Partial<ReportAssistantMessageResponse> = {}): ReportAssistantMessageResponse {
  return {
    status: 'completed',
    intent: 'unknown',
    answer: '测试回答',
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

describe('sendReportAssistantMessage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('发送消息时携带 conversation_context', async () => {
    mockPost.mockResolvedValueOnce({ data: makeResponse() })

    const context = {
      conversation_id: 'my-conv-123',
      last_report_id: 42,
      last_report_type: 'application_risk',
      last_period_start: null,
      last_period_end: null,
      referenced_entities: [
        {
          position: 1,
          entity_type: 'application',
          entity_id: 'A1024',
          source_report_id: 42,
          metadata: { risk_score: 90 },
        },
      ],
      previous_intent: 'drill_down' as const,
    }

    await sendReportAssistantMessage({
      message: '第一个为什么这么高？',
      conversation_context: context,
      client_request_id: 'req-abc',
    })

    expect(mockPost).toHaveBeenCalledTimes(1)
    const [url, body] = mockPost.mock.calls[0]
    expect(url).toBe('/reports/assistant/messages')
    expect(body.message).toBe('第一个为什么这么高？')
    expect(body.conversation_context.conversation_id).toBe('my-conv-123')
    expect(body.conversation_context.last_report_id).toBe(42)
    expect(body.conversation_context.referenced_entities).toHaveLength(1)
    expect(body.client_request_id).toBe('req-abc')
  })

  it('重试时保留原 client_request_id', async () => {
    // 使用 mockResolvedValue 确保每次调用都返回有效响应
    mockPost.mockResolvedValue({ data: makeResponse() })

    const context = {
      conversation_id: 'conv-retry',
      referenced_entities: [],
      last_report_id: null,
      last_report_type: null,
      last_period_start: null,
      last_period_end: null,
      previous_intent: null,
    }

    // 第一次请求
    await sendReportAssistantMessage({
      message: '看看申请风险',
      conversation_context: context,
      client_request_id: 'req-retry-123',
    })

    // 重试：复用同一个幂等键
    await sendReportAssistantMessage({
      message: '看看申请风险',
      conversation_context: context,
      client_request_id: 'req-retry-123',
    })

    const calls = mockPost.mock.calls
    expect(calls).toHaveLength(2)
    expect(calls[0][1].client_request_id).toBe('req-retry-123')
    expect(calls[1][1].client_request_id).toBe('req-retry-123')
  })

  it('处理 HTTP 202 generating 响应', async () => {
    mockPost.mockResolvedValueOnce({
      data: makeResponse({
        status: 'generating',
        intent: 'generate_report',
        report_id: 128,
        report_type: 'application_risk',
        answer: '已创建报告，正在后台生成。',
        assumptions: ['统计周期：最近7天'],
      }),
    })

    const result = await sendReportAssistantMessage({
      message: '看看申请风险',
      conversation_context: {
        conversation_id: 'conv-1',
        referenced_entities: [],
      },
    })

    expect(result.status).toBe('generating')
    expect(result.report_id).toBe(128)
    expect(result.report_type).toBe('application_risk')
    expect(result.intent).toBe('generate_report')
  })

  it('处理 HTTP 403 permission_denied 响应', async () => {
    // 403 由拦截器 toast 提示，但组件需要能捕获
    const axiosError = new axios.AxiosError('Forbidden')
    axiosError.response = {
      status: 403,
      data: { detail: '无权限访问' },
      statusText: 'Forbidden',
      headers: {} as never,
      config: {} as never,
    }
    mockPost.mockRejectedValueOnce(axiosError)

    await expect(
      sendReportAssistantMessage({
        message: '查看渠道ROI',
        conversation_context: {
          conversation_id: 'conv-1',
          referenced_entities: [],
        },
      }),
    ).rejects.toThrow()
  })

  it('处理 HTTP 404 not_found 响应', async () => {
    const axiosError = new axios.AxiosError('Not Found')
    axiosError.response = {
      status: 404,
      data: { detail: '报告不存在' },
      statusText: 'Not Found',
      headers: {} as never,
      config: {} as never,
    }
    mockPost.mockRejectedValueOnce(axiosError)

    await expect(
      sendReportAssistantMessage({
        message: '查看报告详情',
        conversation_context: {
          conversation_id: 'conv-1',
          referenced_entities: [],
        },
      }),
    ).rejects.toThrow()
  })

  it('处理 HTTP 500 服务端错误', async () => {
    const axiosError = new axios.AxiosError('Internal Error')
    axiosError.response = {
      status: 500,
      data: { detail: '服务器内部错误' },
      statusText: 'Internal Server Error',
      headers: {} as never,
      config: {} as never,
    }
    mockPost.mockRejectedValueOnce(axiosError)

    await expect(
      sendReportAssistantMessage({
        message: '任何消息',
        conversation_context: {
          conversation_id: 'conv-1',
          referenced_entities: [],
        },
      }),
    ).rejects.toThrow()
  })

  it('处理 HTTP 503 服务不可用', async () => {
    const axiosError = new axios.AxiosError('Service Unavailable')
    axiosError.response = {
      status: 503,
      data: { detail: '功能未开启' },
      statusText: 'Service Unavailable',
      headers: {} as never,
      config: {} as never,
    }
    mockPost.mockRejectedValueOnce(axiosError)

    await expect(
      sendReportAssistantMessage({
        message: '任何消息',
        conversation_context: {
          conversation_id: 'conv-1',
          referenced_entities: [],
        },
      }),
    ).rejects.toThrow()
  })

  it('返回的 evidence 包含完整五元绑定', async () => {
    mockPost.mockResolvedValueOnce({
      data: makeResponse({
        status: 'completed',
        intent: 'drill_down',
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
            formula: 'base_score + overdue_bonus',
          },
        ],
      }),
    })

    const result = await sendReportAssistantMessage({
      message: '最严重的是哪几个',
      conversation_context: {
        conversation_id: 'conv-1',
        referenced_entities: [],
      },
    })

    expect(result.evidence).toHaveLength(1)
    expect(result.evidence[0].evidence_id).toBe('E1')
    expect(result.evidence[0].value).toBe(90)
    expect(result.evidence[0].unit).toBe('分')
    expect(result.evidence[0].entity_id).toBe('A1024')
  })
})
