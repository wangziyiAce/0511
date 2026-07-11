/**
 * 智能报告助手 API 层。
 *
 * 封装 POST /api/v1/reports/assistant/messages 接口。
 * 职责：
 * 1. 发送用户消息 + 会话上下文
 * 2. 返回 ReportAssistantMessageResponse
 * 3. 复用项目现有 apiClient（自动携带 Token、统一错误处理）
 *
 * 不得在组件中直接写 fetch、拼接 API URL、映射业务报告类型、
 * 解析风险规则或计算风险分、ROI、CPL、CAC、SLA。
 */

import apiClient from '@/lib/api-client'
import type {
  ReportAssistantMessageRequest,
  ReportAssistantMessageResponse,
} from '@/types/report-assistant'

/** 发送智能报告助手对话消息 */
export async function sendReportAssistantMessage(
  request: ReportAssistantMessageRequest,
): Promise<ReportAssistantMessageResponse> {
  const response = await apiClient.post<ReportAssistantMessageResponse>(
    '/reports/assistant/messages',
    request,
  )
  return response.data
}
