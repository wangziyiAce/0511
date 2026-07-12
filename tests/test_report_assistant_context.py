"""智能报告助手 Iteration 2A — 多轮上下文与实体引用测试。

测试目标：
1. 实体引用解析（序号、语义、显式 ID）
2. 上下文校验（权限、越界、伪造）
3. 多轮追问意图检测
"""

from __future__ import annotations

import pytest

from services.reporting.assistant.context import (
    resolve_entity_reference,
    validate_context_access,
)
from services.reporting.assistant.schemas import (
    ReferencedEntity,
    ReportConversationContext,
)


# ============================================================================
# Test Helpers
# ============================================================================


def _make_context(**kwargs) -> ReportConversationContext:
    defaults = {"conversation_id": "test-ctx"}
    defaults.update(kwargs)
    return ReportConversationContext(**defaults)


def _make_entity(position: int, entity_id: str, **meta) -> ReferencedEntity:
    return ReferencedEntity(
        position=position,
        entity_type="application",
        entity_id=entity_id,
        display_name=f"申请 #{entity_id}",
        source_report_id=100,
        metadata={"risk_score": meta.get("risk_score", 50), "risk_level": meta.get("risk_level", "medium")},
    )


# ============================================================================
# 实体引用解析测试
# ============================================================================


class TestEntityReferenceResolution:
    def test_resolve_first_entity(self):
        """'第一个' → 返回 position=1 的实体。"""
        ctx = _make_context(referenced_entities=[
            _make_entity(1, "A1001", risk_score=90, risk_level="high"),
            _make_entity(2, "A1002", risk_score=70, risk_level="medium"),
        ])
        result = resolve_entity_reference(message="第一个为什么这么高", context=ctx)
        assert result is not None
        assert result.entity_id == "A1001"

    def test_resolve_second_entity(self):
        """'第二个' → 返回 position=2 的实体。"""
        ctx = _make_context(referenced_entities=[
            _make_entity(1, "A1001"),
            _make_entity(2, "A1002"),
        ])
        result = resolve_entity_reference(message="第二个什么情况", context=ctx)
        assert result is not None
        assert result.entity_id == "A1002"

    def test_resolve_third_entity(self):
        """'第三个' → position=3。"""
        ctx = _make_context(referenced_entities=[
            _make_entity(1, "A1"), _make_entity(2, "A2"), _make_entity(3, "A3"),
        ])
        result = resolve_entity_reference(message="第三个呢", context=ctx)
        assert result is not None
        assert result.entity_id == "A3"

    def test_resolve_highest_risk_entity(self):
        """'最高风险的' → 返回 risk_score 最高的实体。"""
        ctx = _make_context(referenced_entities=[
            _make_entity(1, "A1001", risk_score=60, risk_level="low"),
            _make_entity(2, "A1002", risk_score=90, risk_level="high"),
            _make_entity(3, "A1003", risk_score=30, risk_level="low"),
        ])
        result = resolve_entity_reference(message="最高风险的那个为什么", context=ctx)
        assert result is not None
        assert result.entity_id == "A1002"

    def test_reference_without_context_returns_none(self):
        """无上下文时问'第一个' → 返回 None。"""
        ctx = _make_context(referenced_entities=[])
        result = resolve_entity_reference(message="第一个为什么这么高", context=ctx)
        assert result is None

    def test_reference_position_out_of_range(self):
        """'第三个'但只有两个实体 → 返回 None（越界）。"""
        ctx = _make_context(referenced_entities=[
            _make_entity(1, "A1"), _make_entity(2, "A2"),
        ])
        result = resolve_entity_reference(message="第三个呢", context=ctx)
        assert result is None

    def test_single_entity_default_for_follow_up(self):
        """唯一实体 + 追问词 → 默认引用该实体。"""
        ctx = _make_context(referenced_entities=[
            _make_entity(1, "A1001", risk_score=90, risk_level="high"),
        ])
        result = resolve_entity_reference(message="为什么这么高", context=ctx)
        assert result is not None
        assert result.entity_id == "A1001"

    def test_explicit_entity_id_in_message(self):
        """消息中包含显式 entity_id → 直接匹配。"""
        ctx = _make_context(
            last_report_id=100,
            referenced_entities=[
                _make_entity(1, "A2048"),
                _make_entity(2, "A3072"),
            ],
        )
        result = resolve_entity_reference(message="A3072 的详细信息", context=ctx)
        assert result is not None
        assert result.entity_id == "A3072"


# ============================================================================
# 上下文校验测试
# ============================================================================


class TestContextValidation:
    def test_admin_can_access_any_report(self):
        """admin 角色 → 始终通过。"""
        ctx = _make_context(last_report_id=999)
        assert validate_context_access(
            context=ctx, current_user_id=1, current_user_role="admin",
            accessible_report_ids=set(),
        ) is True

    def test_employee_can_access_own_report(self):
        """员工可访问自己 generated_by 的报告。"""
        ctx = _make_context(last_report_id=100)
        assert validate_context_access(
            context=ctx, current_user_id=5, current_user_role="employee",
            accessible_report_ids={100},
        ) is True

    def test_employee_cannot_access_others_report(self):
        """员工不能访问他人报告。"""
        ctx = _make_context(last_report_id=999)
        assert validate_context_access(
            context=ctx, current_user_id=5, current_user_role="employee",
            accessible_report_ids={100, 200},  # 999 不在其中
        ) is False

    def test_entity_source_report_checked(self):
        """referenced_entity 的 source_report_id 也受校验。"""
        entity = _make_entity(1, "A1001")
        entity.source_report_id = 999
        ctx = _make_context(
            last_report_id=100,
            referenced_entities=[entity],
        )
        assert validate_context_access(
            context=ctx, current_user_id=5, current_user_role="employee",
            accessible_report_ids={100},  # 999 不在其中
        ) is False


# ============================================================================
# 多轮意图检测测试
# ============================================================================


class TestMultiTurnIntentDetection:
    def test_status_query_detected(self):
        """'生成好了吗' + 有上下文 → query_report_status。"""
        from services.reporting.assistant.intent_parser import _detect_multi_turn_intent_keywords
        from services.reporting.assistant.schemas import ReportAssistantIntent

        ctx = _make_context(last_report_id=100)
        intent = _detect_multi_turn_intent_keywords("报告生成好了吗", ctx)
        assert intent == ReportAssistantIntent.QUERY_REPORT_STATUS

    def test_drill_down_detected(self):
        """'最严重的是哪几个' + 有上下文 → drill_down。"""
        from services.reporting.assistant.intent_parser import _detect_multi_turn_intent_keywords
        from services.reporting.assistant.schemas import ReportAssistantIntent

        ctx = _make_context(last_report_id=100)
        intent = _detect_multi_turn_intent_keywords("最严重的是哪几个", ctx)
        assert intent == ReportAssistantIntent.DRILL_DOWN

    def test_explain_risk_detected(self):
        """'为什么这么高' + 有上下文 → explain_risk。"""
        from services.reporting.assistant.intent_parser import _detect_multi_turn_intent_keywords
        from services.reporting.assistant.schemas import ReportAssistantIntent

        ctx = _make_context(last_report_id=100)
        intent = _detect_multi_turn_intent_keywords("为什么风险这么高", ctx)
        assert intent == ReportAssistantIntent.EXPLAIN_RISK

    def test_no_context_no_multi_turn_intent(self):
        """无上下文 → 不触发多轮意图。"""
        from services.reporting.assistant.intent_parser import _detect_multi_turn_intent_keywords

        ctx = _make_context()  # 无 last_report_id
        intent = _detect_multi_turn_intent_keywords("最严重的是哪几个", ctx)
        assert intent is None
