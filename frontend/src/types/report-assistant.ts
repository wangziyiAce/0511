/**
 * 智能报告助手 — TypeScript 类型定义。
 *
 * 对齐后端：
 *   - services/reporting/assistant/schemas.py（Pydantic Schema）
 *   - routers/report_assistant.py（FastAPI 路由）
 *
 * 所有字段以后端 OpenAPI 契约为准，不自行设计字段。
 * 前端只负责展示，不计算风险分、ROI、CPL、CAC 或 SLA。
 */

// ============================================================
//  意图枚举 — 对齐后端 ReportAssistantIntent
// ============================================================

/** LLM 可识别的用户意图 */
export type ReportAssistantIntent =
  | 'generate_report'
  | 'query_report'
  | 'query_report_status'
  | 'drill_down'
  | 'explain_risk'
  | 'explain_metric'
  | 'query_data_quality'
  | 'compare_reports'
  | 'cross_report_analysis'
  | 'summarize_for_role'
  | 'generate_action_candidates'
  | 'confirm_actions'
  | 'unknown'

// ============================================================
//  状态枚举 — 对齐后端 status 字段的 Literal
// ============================================================

/** 本轮对话的处理状态 */
export type ReportAssistantStatus =
  | 'generating'
  | 'completed'
  | 'needs_clarification'
  | 'permission_denied'
  | 'not_found'
  | 'error'

// ============================================================
//  引用实体 — 对齐后端 ReferencedEntity
// ============================================================

/** 多轮对话中引用的实体 */
export interface ReferencedEntity {
  /** 在回答列表中的位置（1-based，0=未排序） */
  position: number
  /** 实体类型，如 application、report、student */
  entity_type: string
  /** 实体 ID */
  entity_id: string
  /** 人类可读的简短标签 */
  display_name?: string | null
  /** 实体来源的报告 ID */
  source_report_id: number
  /** 展示需要的最小元数据（如 risk_score、risk_level） */
  metadata?: Record<string, unknown>
}

// ============================================================
//  会话上下文 — 对齐后端 ReportConversationContext
// ============================================================

/** 最小会话上下文，由前端每次请求传回 */
export interface ReportConversationContext {
  /** 会话 ID（UUID 格式），由前端生成并传回 */
  conversation_id: string
  /** 上一轮生成的报告 ID */
  last_report_id?: number | null
  /** 上一轮生成的报告类型 */
  last_report_type?: string | null
  /** 上一轮使用的周期开始 */
  last_period_start?: string | null
  /** 上一轮使用的周期结束 */
  last_period_end?: string | null
  /** 多轮对话中累积引用的实体 */
  referenced_entities: ReferencedEntity[]
  /** 上一轮识别到的意图 */
  previous_intent?: ReportAssistantIntent | null
}

// ============================================================
//  证据项 — 对齐后端 EvidenceItem
// ============================================================

/** 回答中一个数字或结论的证据来源（五元绑定） */
export interface EvidenceItem {
  /** 证据占位符 ID，如 E1、E2 */
  evidence_id: string
  /** 实体类型，如 application */
  entity_type?: string | null
  /** 实体 ID，如 A1024 */
  entity_id?: string | null
  /** 指标名称，如 risk_score */
  metric_name?: string | null
  /** 人类可读标签，如 "申请 A1024 风险分" */
  label: string
  /** 引用值（原始类型） */
  value: unknown
  /** 单位，如 分、%、元、天 */
  unit?: string | null
  /** 来源报告 ID */
  source_report_id: number
  /** 数据来源表 */
  source_tables: string[]
  /** 指标计算公式 */
  formula?: string | null
  /** 来源工具名（向后兼容） */
  source?: string
  /** 数据路径（向后兼容） */
  reference?: string
}

// ============================================================
//  数据质量 — 内联在响应中
// ============================================================

/** 响应中的数据质量信息 */
export interface AssistantDataQuality {
  /** 质量等级 */
  status: 'ok' | 'warning' | 'empty' | 'degraded' | 'failed'
  /** 具体警告信息列表 */
  warnings?: string[]
}

// ============================================================
//  请求/响应 — 对齐后端 ReportAssistantMessageRequest/Response
// ============================================================

/** POST /api/v1/reports/assistant/messages 请求体 */
export interface ReportAssistantMessageRequest {
  /** 用户自然语言输入（1-2000 字符） */
  message: string
  /** 当前会话的最小上下文 */
  conversation_context: ReportConversationContext
  /** 客户端幂等键，用于防重复提交 */
  client_request_id?: string | null
}

/** POST /api/v1/reports/assistant/messages 响应体 */
export interface ReportAssistantMessageResponse {
  /** 本轮对话的处理状态 */
  status: ReportAssistantStatus
  /** 识别到的用户意图 */
  intent: ReportAssistantIntent
  /** 如果生成了报告，返回报告 ID */
  report_id?: number | null
  /** 如果生成了报告，返回报告类型 */
  report_type?: string | null
  /** 面向用户的自然语言回答 */
  answer: string
  /** 是否需要用户进一步澄清 */
  needs_clarification?: boolean
  /** 如果需要澄清，具体的澄清问题 */
  clarification_question?: string | null
  /** 处理中使用的假设，供用户确认 */
  assumptions: string[]
  /** 综合置信度 */
  confidence?: number
  /** 回答中数字的证据来源 */
  evidence: EvidenceItem[]
  /** 建议的后续追问 */
  suggested_follow_ups: string[]
  /** 更新后的会话上下文 */
  conversation_context: ReportConversationContext
  /** 如有关联报告，其数据质量信息 */
  data_quality?: AssistantDataQuality | null
  /** 错误码（status=error 时） */
  error_code?: string | null
}

// ============================================================
//  前端会话消息（组件本地状态）
// ============================================================

/** 对话面板中的单条消息 */
export interface AssistantMessage {
  /** 消息唯一 ID */
  id: string
  /** 消息角色 */
  role: 'user' | 'assistant' | 'system'
  /** 消息内容文本 */
  content: string
  /** 处理状态（仅 assistant 消息） */
  status?: ReportAssistantStatus
  /** 关联的报告 ID */
  reportId?: number | null
  /** 关联的报告类型 */
  reportType?: string | null
  /** 证据列表 */
  evidence?: EvidenceItem[]
  /** 处理假设 */
  assumptions?: string[]
  /** 建议追问 */
  suggestedFollowUps?: string[]
  /** 数据质量信息 */
  dataQuality?: AssistantDataQuality | null
  /** 是否需要澄清 */
  needsClarification?: boolean
  /** 澄清问题 */
  clarificationQuestion?: string | null
  /** 创建时间 */
  createdAt: string
  /** 用户请求使用的幂等键；错误重试时必须复用，避免重复创建后台报告任务。 */
  clientRequestId?: string
  /** 发送时的完整请求快照；重试不能改用后续轮次已经变化的会话上下文。 */
  originalRequest?: ReportAssistantMessageRequest
  /** Iteration 3：指标比较列表 */
  comparison?: MetricComparison[]
  /** Iteration 3：比较周期 */
  comparison_period?: ComparisonPeriod | null
  /** Iteration 3：双周期数据质量 */
  comparison_data_quality?: ComparisonDataQuality | null
  /** Iteration 3：四区关系分析 */
  relationship_sections?: RelationshipSections | null
}

// ============================================================
//  Iteration 3 — 比较与跨报告分析类型
// ============================================================

/** 比较周期 — 对齐后端 ComparisonPeriod */
export interface ComparisonPeriod {
  current_start: string
  current_end: string
  previous_start: string
  previous_end: string
  current_label: string
  previous_label: string
  assumptions: string[]
}

/** 指标比较 — 对齐后端 MetricComparison */
export interface MetricComparison {
  report_type: string
  metric_name: string
  label: string
  dimension?: Record<string, string>
  current_value: number | null
  previous_value: number | null
  delta: number | null
  change_rate: number | null
  direction: 'up' | 'down' | 'flat' | 'unknown'
  unit?: string | null
  current_evidence_id: string
  previous_evidence_id: string
}

/** 双周期数据质量 — 对齐后端 ComparisonDataQuality */
export interface ComparisonDataQuality {
  current: Record<string, unknown>
  previous: Record<string, unknown>
  allow_values: boolean
  allow_trend: boolean
  warnings: string[]
}

/** 四区关系分析 — 对齐后端 RelationshipSections */
export interface RelationshipSections {
  confirmed_facts: string[]
  related_signals: string[]
  possible_explanations: string[]
  cannot_confirm: string[]
}

/** EvidenceItem 扩展字段（Iteration 3） */
export interface EvidenceItem {
  /** 周期标签，如"本周""上周" */
  period_label?: string | null
  /** 比较角色：current/previous/delta/change_rate */
  comparison_role?: 'current' | 'previous' | 'delta' | 'change_rate' | null
  /** 报告类型 */
  report_type?: string | null
}

/** 扩展 ReportAssistantMessageResponse 以包含 Iteration 3 字段 */
export interface ReportAssistantMessageResponseIter3
  extends ReportAssistantMessageResponse {
  /** 指标比较列表 */
  comparison?: MetricComparison[]
  /** 比较周期信息 */
  comparison_period?: ComparisonPeriod | null
  /** 双周期数据质量 */
  comparison_data_quality?: ComparisonDataQuality | null
  /** 四区关系分析 */
  relationship_sections?: RelationshipSections | null
}
