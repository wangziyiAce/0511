"""智能报告助手 — Pydantic Schema 定义。

本文件定义智能交互层的请求/响应结构、意图枚举、计划模型和会话上下文。
这些 Schema 是 API 契约的核心，前端、LLM Structured Output 和 Python
校验全部按此对齐。

设计原则：
1. LLM 输出的候选计划（ReportRequestPlan）必须经过 Python 二次校验
2. 会话上下文由前端每次请求传回，不在服务端持久化（Iteration 1-2）
3. 置信度、风险等级、输出风格等枚举值必须在 Pydantic 中约束
4. 消息和上下文大小有硬上限，防止滥用
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any, Literal, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# 意图枚举 — 来自 Iteration 计划 §3.1
# ---------------------------------------------------------------------------


class ReportAssistantIntent(str, Enum):
    """智能报告助手可识别的用户意图。

    每种意图对应不同的工具调用策略和回答模板。
    Iteration 1 只实现 GENERATE_REPORT、QUERY_REPORT_STATUS 和 UNKNOWN。
    """

    GENERATE_REPORT = "generate_report"
    QUERY_REPORT = "query_report"
    QUERY_REPORT_STATUS = "query_report_status"
    DRILL_DOWN = "drill_down"
    EXPLAIN_RISK = "explain_risk"
    EXPLAIN_METRIC = "explain_metric"
    QUERY_DATA_QUALITY = "query_data_quality"
    COMPARE_REPORTS = "compare_reports"
    SUMMARIZE_FOR_ROLE = "summarize_for_role"
    GENERATE_ACTION_CANDIDATES = "generate_action_candidates"
    CONFIRM_ACTIONS = "confirm_actions"
    UNKNOWN = "unknown"


# ---------------------------------------------------------------------------
# 报告类型选项 — 从 REPORT_REGISTRY 动态生成，供 LLM 选择
# ---------------------------------------------------------------------------


class ReportTypeOption(BaseModel):
    """LLM 可选的报告类型。

    由 ``build_report_catalog()`` 从 ``REPORT_REGISTRY`` 动态生成，
    不单独维护。``keywords`` 是助手模块维护的业务关键词映射。
    """

    report_type: str = Field(..., description="报告类型编码，如 application_risk")
    label: str = Field(..., description="中文名称，如 申请风险报告")
    default_period_rule: str = Field(..., description="默认统计周期规则")
    allowed: bool = Field(..., description="当前角色是否有权访问")
    keywords: list[str] = Field(
        default_factory=list,
        max_length=10,
        description="该报告类型的业务关键词，用于本地关键词降级匹配",
    )


# ---------------------------------------------------------------------------
# 结构化请求计划 — LLM 输出的候选计划
# ---------------------------------------------------------------------------


class ReportRequestPlan(BaseModel):
    """LLM 意图解析后的候选计划。

    模型只输出候选，Python 必须再做白名单、权限、时间和字段校验后才执行。
    Iteration 1 只使用 intent、report_type、relative_period、confidence。
    """

    intent: ReportAssistantIntent = Field(
        default=ReportAssistantIntent.UNKNOWN,
        description="识别出的用户意图",
    )
    report_type: Optional[str] = Field(
        default=None,
        description="LLM 建议的报告类型编码；必须来自 Registry 白名单",
    )
    report_id: Optional[int] = Field(
        default=None,
        description="LLM 引用的已有报告 ID",
    )
    entity_id: Optional[str] = Field(
        default=None,
        description="LLM 引用的实体 ID（如申请 ID、学生 ID 等）",
    )
    relative_period: Optional[str] = Field(
        default=None,
        description="相对时间表达，如 this_week、last_week、this_month、last_month",
    )
    period_start: Optional[date] = Field(
        default=None,
        description="解析后的统计周期开始日期",
    )
    period_end: Optional[date] = Field(
        default=None,
        description="解析后的统计周期结束日期",
    )
    comparison_relative_period: Optional[str] = Field(
        default=None,
        description="对比周期（Iteration 3 使用）",
    )
    risk_level: Optional[Literal["high", "medium", "low"]] = Field(
        default=None,
        description="关注的风险等级",
    )
    priority: Optional[Literal["urgent", "high", "medium", "low"]] = Field(
        default=None,
        description="关注的优先级",
    )
    focus_metrics: list[str] = Field(
        default_factory=list,
        max_length=10,
        description="用户关注的具体指标名称",
    )
    target_role: Optional[str] = Field(
        default=None,
        description="用户要求面向的目标角色，如 老板、运营主管",
    )
    output_style: Literal[
        "management_summary",
        "operational_detail",
        "personal_tasks",
        "data_trace",
    ] = Field(
        default="management_summary",
        description="输出风格：管理摘要/运营详情/个人任务/数据追溯",
    )
    need_actions: bool = Field(
        default=False,
        description="用户是否需要生成候选行动项",
    )
    requires_clarification: bool = Field(
        default=False,
        description="LLM 是否判断需要人类澄清",
    )
    clarification_question: Optional[str] = Field(
        default=None,
        description="如果需要澄清，具体的澄清问题",
    )
    assumptions: list[str] = Field(
        default_factory=list,
        max_length=10,
        description="模型在解析时所做的假设",
    )
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="模型对当前意图识别的置信度 [0.0, 1.0]",
    )


# ---------------------------------------------------------------------------
# 会话上下文 — 由前端每次请求传回
# ---------------------------------------------------------------------------


class ReferencedEntity(BaseModel):
    """多轮对话中引用的实体。

    Iteration 2A 开始正式使用：
    - ``position`` 表示在回答中的序号（1-based）
    - ``source_report_id`` 标记实体来自哪份报告
    - ``metadata`` 保存展示需要的最小字段

    客户端传入的实体不被信任，必须重新校验权限和数据存在性。
    """

    position: int = Field(default=0, ge=0, description="在回答列表中的位置（1-based，0=未排序）")
    entity_type: str = Field(..., description="实体类型，如 application、report、student")
    entity_id: str = Field(..., description="实体 ID")
    display_name: Optional[str] = Field(default=None, description="人类可读的简短标签")
    source_report_id: int = Field(default=0, description="实体来源的报告 ID")
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="展示需要的最小元数据（如 risk_score、risk_level）",
    )


class ReportConversationContext(BaseModel):
    """最小会话上下文。

    Iteration 1 不持久化上下文，由前端每次请求时传回。
    ``conversation_id`` 用于日志关联和后续审计。
    """

    conversation_id: str = Field(
        ...,
        max_length=64,
        description="会话 ID（UUID 格式），由前端生成并传回",
    )
    last_report_id: Optional[int] = Field(
        default=None,
        description="上一轮生成的报告 ID",
    )
    last_report_type: Optional[str] = Field(
        default=None,
        description="上一轮生成的报告类型",
    )
    last_period_start: Optional[date] = Field(
        default=None,
        description="上一轮使用的周期开始",
    )
    last_period_end: Optional[date] = Field(
        default=None,
        description="上一轮使用的周期结束",
    )
    referenced_entities: list[ReferencedEntity] = Field(
        default_factory=list,
        max_length=20,
        description="多轮对话中累积引用的实体（Iteration 2 使用）",
    )
    previous_intent: Optional[ReportAssistantIntent] = Field(
        default=None,
        description="上一轮识别到的意图",
    )


# ---------------------------------------------------------------------------
# 证据项 — 回答中的数字来源追溯
# ---------------------------------------------------------------------------


class EvidenceItem(BaseModel):
    """回答中一个数字或结论的证据来源（Iteration 2A.1 增强版）。

    每个 EvidenceItem 建立完整绑定关系：
    **实体 + 指标 + 数值 + 单位 + 来源证据**

    这个五元绑定保证：
    1. 模型不能交换两个合法数字的含义（E1=90 不能标注为 risk_count）
    2. 模型不能将 A1024 的 risk_score 说成 A1058 的
    3. 所有业务数字必须来自工具结果，不能由 LLM 自由生成

    旧字段（source, reference, value）保留用于简单场景的向后兼容。
    """

    evidence_id: str = Field(default="", description="证据占位符 ID，如 E1、E2")
    entity_type: Optional[str] = Field(default=None, description="实体类型，如 application")
    entity_id: Optional[str] = Field(default=None, description="实体 ID，如 A1024")
    metric_name: Optional[str] = Field(default=None, description="指标名称，如 risk_score")
    label: str = Field(default="", description="人类可读标签，如 申请 A1024 风险分")
    value: Any = Field(default=None, description="引用值（原始类型）")
    unit: Optional[str] = Field(default=None, description="单位，如 分、%、元、天")
    source_report_id: int = Field(default=0, description="来源报告 ID")
    source_tables: list[str] = Field(default_factory=list, description="数据来源表")
    formula: Optional[str] = Field(default=None, description="指标计算公式")
    # 向后兼容字段
    source: str = Field(default="", description="来源工具名")
    reference: str = Field(default="", description="数据路径")


# ---------------------------------------------------------------------------
# 工具结果 — 统一工具返回格式
# ---------------------------------------------------------------------------


class AssistantToolResult(BaseModel):
    """受控工具的统一返回格式。

    所有工具（list_report_types、generate_existing_report 等）都返回此结构。
    调用方不需要知道具体工具的内部实现。
    """

    tool_name: str = Field(..., description="工具名称")
    status: Literal["success", "error", "pending"] = Field(..., description="工具执行状态")
    data: Any = Field(default=None, description="工具返回的数据（success 时）")
    error: Optional[str] = Field(default=None, description="错误信息（error 时）")
    report_id: Optional[int] = Field(default=None, description="关联的报告 ID")
    data_quality: Optional[dict[str, Any]] = Field(
        default=None,
        description="关联的数据质量信息",
    )


# ---------------------------------------------------------------------------
# 澄清决策 — 由 clarification.py 输出
# ---------------------------------------------------------------------------


class ClarificationDecision(BaseModel):
    """澄清策略的决策结果。

    由 ``decide_clarification()`` 输出，服务层据此决定直接执行、
    附带假设执行还是返回澄清问题。
    """

    needs_clarification: bool = Field(
        default=False,
        description="是否需要向用户追问",
    )
    clarification_question: Optional[str] = Field(
        default=None,
        description="需要追问时，具体的澄清问题",
    )
    can_proceed: bool = Field(
        default=False,
        description="尽管需要澄清，是否仍可用默认值继续",
    )
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="决策的综合置信度",
    )
    reason: str = Field(
        default="",
        description="决策原因，方便日志排查",
    )


# ---------------------------------------------------------------------------
# 请求/响应 — FastAPI 接口契约
# ---------------------------------------------------------------------------


class ReportAssistantMessageRequest(BaseModel):
    """POST /api/v1/reports/assistant/messages 请求体。

    用户发送自然语言消息，附带最小会话上下文。
    """

    message: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="用户自然语言输入",
    )
    conversation_context: ReportConversationContext = Field(
        default_factory=lambda: ReportConversationContext(
            conversation_id=str(uuid4()),
        ),
        description="当前会话的最小上下文",
    )
    client_request_id: Optional[str] = Field(
        default=None,
        max_length=128,
        description="客户端幂等键，用于防重复提交",
    )


class ReportAssistantMessageResponse(BaseModel):
    """POST /api/v1/reports/assistant/messages 响应体。

    包含意图、计划、回答、证据、建议追问和更新后的会话上下文。
    """

    status: Literal["generating", "completed", "needs_clarification", "permission_denied", "not_found", "error"] = Field(
        ...,
        description="本轮对话的处理状态",
    )
    intent: ReportAssistantIntent = Field(
        default=ReportAssistantIntent.UNKNOWN,
        description="识别到的用户意图",
    )
    report_id: Optional[int] = Field(
        default=None,
        description="如果生成了报告，返回报告 ID",
    )
    report_type: Optional[str] = Field(
        default=None,
        description="如果生成了报告，返回报告类型",
    )
    answer: str = Field(
        ...,
        description="面向用户的自然语言回答",
    )
    needs_clarification: bool = Field(
        default=False,
        description="是否需要用户进一步澄清",
    )
    clarification_question: Optional[str] = Field(
        default=None,
        description="如果需要澄清，具体的澄清问题",
    )
    assumptions: list[str] = Field(
        default_factory=list,
        max_length=10,
        description="处理中使用的假设，供用户确认",
    )
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="综合置信度",
    )
    evidence: list[EvidenceItem] = Field(
        default_factory=list,
        description="回答中数字的证据来源",
    )
    suggested_follow_ups: list[str] = Field(
        default_factory=list,
        max_length=5,
        description="建议的后续追问",
    )
    data_quality: Optional[dict[str, Any]] = Field(
        default=None,
        description="如有关联报告，其数据质量信息",
    )
    conversation_context: ReportConversationContext = Field(
        ...,
        description="更新后的会话上下文，前端需在下一次请求中传回",
    )
    error_code: Optional[str] = Field(
        default=None,
        description="错误码（status=error 时）",
    )
