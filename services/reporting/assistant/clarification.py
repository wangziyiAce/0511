"""智能报告助手 — 澄清策略。

本模块判断在给定意图计划的置信度和权限下，是否应该直接执行、
附带假设执行，还是向用户追问澄清。

规则（来自 Iteration 计划 §4.2-§4.3）：
1. 高置信度（>= 0.80）只读请求 → 直接执行，明示假设
2. 中置信度（0.55 ~ 0.80）→ 只读请求使用安全默认值，必须返回 assumptions
3. 低置信度（< 0.55）→ 不调用业务工具，返回具体澄清问题
4. 无权限 → 直接拒绝，不通过追问绕过
5. 写操作 → 一律要求确认（Iteration 4 实现）

澄清问题必须具体，不能是"你想做什么"这种空泛提问。
"""

from __future__ import annotations

import logging

from services.reporting.assistant.config import settings
from services.reporting.assistant.schemas import (
    ClarificationDecision,
    ReportAssistantIntent,
    ReportRequestPlan,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 公开接口
# ---------------------------------------------------------------------------


def decide_clarification(
    *,
    plan: ReportRequestPlan,
    user_role: str,
    allowed_report_types: set[str],
) -> ClarificationDecision:
    """根据意图计划的置信度、用户角色和权限决定下一步动作。

    Args:
        plan: LLM 或关键词路由输出的候选计划。
        user_role: 当前用户的角色编码。
        allowed_report_types: 当前用户有权访问的报告类型集合。

    Returns:
        ClarificationDecision，包含是否需要澄清和执行建议。
    """
    # ---- 无权限 → 直接拒绝 ----
    if plan.report_type and plan.report_type not in allowed_report_types:
        return ClarificationDecision(
            needs_clarification=True,
            clarification_question=f"你没有权限访问'{plan.report_type}'类型的报告。",
            can_proceed=False,
            confidence=0.0,
            reason=f"用户角色 {user_role} 无权访问 {plan.report_type}",
        )

    # ---- 意图未知 → 追问 ----
    if plan.intent == ReportAssistantIntent.UNKNOWN:
        return ClarificationDecision(
            needs_clarification=True,
            clarification_question=_build_unknown_clarification(allowed_report_types),
            can_proceed=False,
            confidence=plan.confidence,
            reason="意图识别失败，无法确定报告类型",
        )

    # ---- 写操作 → 要求确认（Iteration 4） ----
    write_intents = {
        ReportAssistantIntent.GENERATE_ACTION_CANDIDATES,
        ReportAssistantIntent.CONFIRM_ACTIONS,
    }
    if plan.intent in write_intents:
        return ClarificationDecision(
            needs_clarification=True,
            clarification_question="创建行动项需要确认，请在报告生成后再操作。",
            can_proceed=False,
            confidence=plan.confidence,
            reason="写操作暂不支持（Iteration 4 实现）",
        )

    # ---- 高置信度 + （报告类型明确 或 多轮追问意图） → 直接执行 ----
    # 多轮追问意图（drill_down/explain_risk 等）不需要 report_type，
    # 它们使用上下文中已有的 report 信息
    _MULTI_TURN_INTENTS = {
        ReportAssistantIntent.DRILL_DOWN,
        ReportAssistantIntent.EXPLAIN_RISK,
        ReportAssistantIntent.EXPLAIN_METRIC,
        ReportAssistantIntent.QUERY_DATA_QUALITY,
        ReportAssistantIntent.QUERY_REPORT_STATUS,
    }
    has_valid_intent = bool(plan.report_type) or plan.intent in _MULTI_TURN_INTENTS

    if plan.confidence >= settings.confidence_high and has_valid_intent:
        return ClarificationDecision(
            needs_clarification=False,
            can_proceed=True,
            confidence=plan.confidence,
            reason=f"高置信度（{plan.confidence} >= {settings.confidence_high}），直接执行",
        )

    # ---- 中置信度 → 用默认值执行但明示假设 ----
    if plan.confidence >= settings.confidence_low and has_valid_intent:
        return ClarificationDecision(
            needs_clarification=False,
            can_proceed=True,
            confidence=plan.confidence,
            reason=f"中置信度（{plan.confidence} >= {settings.confidence_low}），使用安全默认值执行",
        )

    # ---- 低置信度 → 不调用工具，返回澄清问题 ----
    return ClarificationDecision(
        needs_clarification=True,
        clarification_question=_build_low_confidence_clarification(plan, allowed_report_types),
        can_proceed=False,
        confidence=plan.confidence,
        reason=f"低置信度（{plan.confidence} < {settings.confidence_low}），需要用户澄清",
    )


# ---------------------------------------------------------------------------
# 内部辅助
# ---------------------------------------------------------------------------


def _build_unknown_clarification(allowed_report_types: set[str]) -> str:
    """对未知意图构建具体的澄清问题。"""
    if not allowed_report_types:
        return "当前角色没有可访问的报告类型，请联系管理员。"
    return "我还不能确定你要查看哪类报告。你可以说'申请风险'、'销售漏斗'、'渠道ROI'或'投诉处理'等，我会帮你生成对应的管理报告。"


def _build_low_confidence_clarification(
    plan: ReportRequestPlan, allowed_report_types: set[str]
) -> str:
    """对低置信度构建具体澄清问题。"""
    if plan.report_type:
        return f"你是指'{plan.report_type}'类型的报告吗？请确认报告类型和时间范围。"
    return "请具体说明你想查看的报告类型，例如'申请风险'、'销售转化'或'渠道投放效果'。"
