/**
 * 智能报告助手 — 对话面板主组件。
 *
 * 管理端右侧滑出式对话面板，提供：
 * 1. 自然语言对话交互
 * 2. 多轮 conversation_context 自动传回
 * 3. 消息展示（用户/助手/系统消息）
 * 4. 所有状态展示（generating/completed/needs_clarification/permission_denied/not_found/error）
 * 5. 证据卡片、数据质量提示、建议追问
 * 6. 报告详情跳转
 *
 * 状态持久化策略：
 * - Iteration 2B 仅使用组件本地状态
 * - 不写入 localStorage、IndexedDB、URL 参数或服务端数据库
 * - 刷新页面后会话丢失是可接受的限制
 *
 * 安全要求：
 * - 不在前端重建 referenced_entities、last_report_id、previous_intent
 * - 不在前端更改 evidence 数值
 * - 不在前端解析风险规则或计算业务指标
 * - 心理预警相关上下文不进入持久浏览器存储
 */

import { useState, useRef, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { X, Bot, Sparkles, AlertCircle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { toast } from 'sonner'
import { sendReportAssistantMessage } from '@/api/report-assistant'
import ReportAssistantMessage from './ReportAssistantMessage'
import ReportAssistantComposer from './ReportAssistantComposer'
import type {
  AssistantMessage,
  ReportAssistantMessageRequest,
  ReportConversationContext,
  ReportAssistantStatus,
} from '@/types/report-assistant'

// ============================================================
//  空状态示例问题
// ============================================================

/** 通用示例问题（当前角色可用且后端可靠支持） */
const EXAMPLE_QUESTIONS = [
  '查看最近的申请风险',
  '上周投诉处理得怎么样',
  '哪个渠道最不划算',
  '生成一份经营周报',
]

// ============================================================
//  工具函数
// ============================================================

/** 生成新的会话 ID */
function generateConversationId(): string {
  return crypto.randomUUID()
}

/** 生成消息 ID */
function generateMessageId(): string {
  return `msg-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`
}

/** 生成客户端幂等键 */
function generateClientRequestId(): string {
  return `req-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`
}

/** 创建空的会话上下文 */
function createEmptyContext(reportId?: number | null, reportType?: string | null): ReportConversationContext {
  return {
    conversation_id: generateConversationId(),
    last_report_id: reportId ?? null,
    last_report_type: reportType ?? null,
    last_period_start: null,
    last_period_end: null,
    referenced_entities: [],
    previous_intent: null,
  }
}

/** 根据后端状态生成用户可见的系统消息 */
function statusToUserMessage(status: ReportAssistantStatus): string {
  switch (status) {
    case 'generating':
      return '已创建报告任务，正在后台生成。你可以在生成完成后继续追问。'
    case 'permission_denied':
      return '抱歉，你没有权限执行此操作。'
    case 'not_found':
      return '未找到相关报告。你可以尝试重新生成。'
    case 'error':
      return '处理请求时出错，请稍后重试。'
    default:
      return ''
  }
}

// ============================================================
//  组件 Props
// ============================================================

interface Props {
  /** 面板是否打开 */
  open: boolean
  /** 关闭面板回调 */
  onClose: () => void
  /** 从报告详情页打开时，传入当前报告 ID */
  initialReportId?: number | null
  /** 从报告详情页打开时，传入当前报告类型 */
  initialReportType?: string | null
}

// ============================================================
//  主组件
// ============================================================

export default function ReportAssistantPanel({ open, onClose, initialReportId, initialReportType }: Props) {
  const navigate = useNavigate()

  // 消息列表
  const [messages, setMessages] = useState<AssistantMessage[]>([])
  // 会话上下文（每次响应后更新）
  const [context, setContext] = useState<ReportConversationContext>(
    createEmptyContext(initialReportId, initialReportType)
  )
  // 当前请求幂等键
  const [clientRequestId, setClientRequestId] = useState<string | null>(null)
  // 是否正在等待响应
  const [isSending, setIsSending] = useState(false)
  // 功能是否关闭（503）
  const [isDisabled, setIsDisabled] = useState(false)

  // 消息列表底部引用（用于自动滚动）
  const bottomRef = useRef<HTMLDivElement>(null)

  // 自动滚动到底部
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // 当 initialReportId 变化时更新上下文
  useEffect(() => {
    if (initialReportId) {
      setContext((prev) => ({
        ...prev,
        last_report_id: initialReportId,
        last_report_type: initialReportType ?? prev.last_report_type,
      }))
    }
  }, [initialReportId, initialReportType])

  // 面板打开时，如果还没有消息，显示欢迎消息
  useEffect(() => {
    if (open && messages.length === 0 && !isDisabled) {
      // 不自动发送欢迎消息，由空状态展示
    }
  }, [open])

  /** 添加一条消息到列表 */
  const addMessage = useCallback((msg: AssistantMessage) => {
    setMessages((prev) => [...prev, msg])
  }, [])

  /** 更新最后一条 assistant 消息 */
  const updateLastAssistantMessage = useCallback((updates: Partial<AssistantMessage>) => {
    setMessages((prev) => {
      const updated = [...prev]
      for (let i = updated.length - 1; i >= 0; i--) {
        if (updated[i].role === 'assistant') {
          updated[i] = { ...updated[i], ...updates }
          break
        }
      }
      return updated
    })
  }, [])

  /** 发送消息 */
  const handleSend = useCallback(async (
    text: string,
    originalRequest?: ReportAssistantMessageRequest,
  ) => {
    if (isSending || isDisabled) return

    const trimmed = text.trim()
    if (!trimmed) return

    setIsSending(true)

    // 新消息使用当前上下文生成请求；错误重试则复用发送时保存的完整快照。
    // 如果重试时改用最新 context 或新 ID，同一业务操作可能创建第二条报告任务。
    const requestSnapshot: ReportAssistantMessageRequest = originalRequest
      ? structuredClone(originalRequest)
      : {
          message: trimmed,
          conversation_context: structuredClone(context),
          client_request_id: generateClientRequestId(),
        }
    const requestId = requestSnapshot.client_request_id as string
    setClientRequestId(requestId)

    // 添加用户消息
    const userMsg: AssistantMessage = {
      id: generateMessageId(),
      role: 'user',
      content: requestSnapshot.message,
      createdAt: new Date().toISOString(),
      clientRequestId: requestId,
      originalRequest: requestSnapshot,
    }
    addMessage(userMsg)

    // 添加 loading 占位消息
    const loadingMsg: AssistantMessage = {
      id: generateMessageId(),
      role: 'assistant',
      content: '',
      status: 'generating' as ReportAssistantStatus,
      createdAt: new Date().toISOString(),
    }
    addMessage(loadingMsg)

    try {
      const response = await sendReportAssistantMessage(requestSnapshot)

      // 处理 503 功能关闭
      if (response.status === 'error' && response.error_code === 'SERVICE_UNAVAILABLE') {
        setIsDisabled(true)
        updateLastAssistantMessage({
          content: '智能报告助手当前未启用，原报告功能仍可正常使用。',
          status: 'error',
        })
        return
      }

      // 更新上下文（后端返回什么就传什么，不自行重建）
      if (response.conversation_context) {
        setContext(response.conversation_context)
      }

      // 用真实响应替换 loading 消息
      const answerContent = response.answer || statusToUserMessage(response.status)
      updateLastAssistantMessage({
        content: answerContent,
        status: response.status,
        reportId: response.report_id,
        reportType: response.report_type,
        evidence: response.evidence,
        assumptions: response.assumptions,
        suggestedFollowUps: response.suggested_follow_ups,
        dataQuality: response.data_quality,
        needsClarification: response.needs_clarification,
        clarificationQuestion: response.clarification_question,
      })

      // 如果后端建议追问中包含"检查生成状态"，且状态为 generating
      if (response.status === 'generating' && response.report_id) {
        // 无需自动操作，用户可手动点击追问
      }
    } catch (error: unknown) {
      // 提取错误信息（不展示堆栈、类名、SQL 等）
      let errorMessage = '处理请求时出错，请稍后重试。'

      if (error && typeof error === 'object' && 'response' in error) {
        const axiosError = error as { response?: { status?: number; data?: { detail?: string } } }
        const status = axiosError.response?.status

        if (status === 503) {
          setIsDisabled(true)
          errorMessage = '智能报告助手当前未启用，原报告功能仍可正常使用。'
        } else if (status === 403) {
          errorMessage = '权限不足，无法执行此操作。'
          updateLastAssistantMessage({
            content: errorMessage,
            status: 'permission_denied',
          })
          return
        } else if (status === 404) {
          errorMessage = '报告不存在或已不可访问。你可以尝试重新生成报告。'
          updateLastAssistantMessage({
            content: errorMessage,
            status: 'not_found',
          })
          return
        }
      } else if (error instanceof Error) {
        // 网络错误等，只显示稳定提示
        if (error.message?.includes('Network') || error.message?.includes('connect')) {
          errorMessage = '无法连接到服务器，请确认后端已启动。'
        }
      }

      updateLastAssistantMessage({
        content: errorMessage,
        status: 'error',
      })
    } finally {
      setIsSending(false)
      setClientRequestId(null)
    }
  }, [context, isSending, isDisabled, addMessage, updateLastAssistantMessage])

  /** 处理建议追问点击（依赖 handleSend，确保始终使用最新的发送逻辑和 context） */
  const handleFollowUp = useCallback((text: string) => {
    handleSend(text)
  }, [handleSend])

  /** 重试上一次请求（复用原 client_request_id） */
  const handleRetry = useCallback(() => {
    // 找到最后一条用户消息
    const lastUserMsg = [...messages].reverse().find(
      (message) => message.role === 'user' && message.originalRequest,
    )
    if (lastUserMsg?.originalRequest && !isSending) {
      // 移除最后一条 assistant 消息
      setMessages((prev) => prev.slice(0, -1))
      // 复用原消息、原 context 快照和原幂等键，保持重试的业务语义不变。
      handleSend(lastUserMsg.content, lastUserMsg.originalRequest)
    }
  }, [messages, handleSend, isSending])

  /** 跳转报告详情 */
  const handleNavigateToReport = useCallback((reportId: number) => {
    navigate(`/reports/${reportId}`)
  }, [navigate])

  if (!open) return null

  return (
    <>
      {/* 遮罩层 */}
      <div
        className="fixed inset-0 z-40 bg-black/30 transition-opacity"
        onClick={onClose}
        aria-hidden="true"
      />

      {/* 侧边面板 */}
      <div className="fixed inset-y-0 right-0 z-50 flex w-full max-w-md flex-col border-l bg-background shadow-xl transition-transform">
        {/* 标题栏 */}
        <div className="flex items-center justify-between border-b px-4 py-3">
          <div className="flex items-center gap-2">
            <Bot className="h-5 w-5 text-primary" />
            <div>
              <h2 className="text-sm font-semibold">智能报告助手</h2>
              <p className="text-xs text-muted-foreground">
                自然语言查询和分析报告
              </p>
            </div>
          </div>
          <Button variant="ghost" size="sm" className="h-8 w-8 p-0" onClick={onClose}>
            <X className="h-4 w-4" />
          </Button>
        </div>

        {/* 消息区域 */}
        <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
          {messages.length === 0 && !isDisabled ? (
            /* 空状态 */
            <div className="flex flex-col items-center justify-center h-full text-center px-4">
              <Sparkles className="h-10 w-10 text-muted-foreground mb-3" />
              <h3 className="text-sm font-medium">智能报告助手</h3>
              <p className="text-xs text-muted-foreground mt-1 max-w-xs">
                通过自然语言生成报告、钻取风险、解释指标、查询数据质量。
              </p>
              <p className="text-xs text-muted-foreground mt-1 max-w-xs">
                AI 根据报告数据生成解释，关键数字请以证据卡片和原报告为准。
              </p>
              <div className="mt-4 w-full space-y-1.5">
                <p className="text-xs font-medium text-muted-foreground">试试这些</p>
                {EXAMPLE_QUESTIONS.map((q) => (
                  <Button
                    key={q}
                    variant="outline"
                    size="sm"
                    className="w-full justify-start text-xs h-8"
                    onClick={() => handleSend(q)}
                  >
                    {q}
                  </Button>
                ))}
              </div>
            </div>
          ) : isDisabled ? (
            /* 功能关闭状态 */
            <div className="flex flex-col items-center justify-center h-full text-center px-4">
              <AlertCircle className="h-10 w-10 text-muted-foreground mb-3" />
              <h3 className="text-sm font-medium">功能未开启</h3>
              <p className="text-xs text-muted-foreground mt-1">
                智能报告助手当前未启用，原报告功能仍可正常使用。
              </p>
            </div>
          ) : (
            /* 消息列表 */
            messages.map((msg) => (
              <ReportAssistantMessage
                key={msg.id}
                message={msg}
                onFollowUp={handleFollowUp}
                isSending={isSending}
              />
            ))
          )}

          {/* 错误时显示重试按钮（最后一条 assistant 消息为 error） */}
          {messages.length > 0 && messages[messages.length - 1]?.status === 'error' && (
            <div className="flex justify-center">
              <Button variant="outline" size="sm" onClick={handleRetry} className="text-xs">
                重试
              </Button>
            </div>
          )}

          <div ref={bottomRef} />
        </div>

        {/* 输入区域 */}
        {!isDisabled && (
          <ReportAssistantComposer
            onSend={handleSend}
            disabled={isSending}
          />
        )}
      </div>
    </>
  )
}
