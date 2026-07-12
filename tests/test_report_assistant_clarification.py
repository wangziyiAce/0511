"""智能报告助手 — 澄清策略单元测试。

测试目标：验证置信度阈值、权限拒绝、未知意图和写操作拦截。
"""

from __future__ import annotations

import pytest

from services.reporting.assistant.clarification import decide_clarification
from services.reporting.assistant.schemas import ReportAssistantIntent, ReportRequestPlan


class TestHighConfidence:
    def test_high_confidence_proceeds(self):
        """高置信度 + 明确报告类型 → 直接执行。"""
        plan = ReportRequestPlan(
            intent=ReportAssistantIntent.GENERATE_REPORT,
            report_type="application_risk",
            confidence=0.93,
        )
        decision = decide_clarification(
            plan=plan,
            user_role="admin",
            allowed_report_types={"application_risk", "sales_funnel"},
        )
        assert decision.can_proceed is True
        assert decision.needs_clarification is False


class TestMediumConfidence:
    def test_medium_confidence_proceeds_with_caveat(self):
        """中置信度 → 可以执行但明示假设。"""
        plan = ReportRequestPlan(
            intent=ReportAssistantIntent.GENERATE_REPORT,
            report_type="application_risk",
            confidence=0.65,
        )
        decision = decide_clarification(
            plan=plan,
            user_role="admin",
            allowed_report_types={"application_risk", "sales_funnel"},
        )
        assert decision.can_proceed is True
        assert decision.needs_clarification is False


class TestLowConfidence:
    def test_low_confidence_asks_clarification(self):
        """低置信度 → 追问，不执行工具。"""
        plan = ReportRequestPlan(
            intent=ReportAssistantIntent.GENERATE_REPORT,
            report_type="application_risk",
            confidence=0.30,
        )
        decision = decide_clarification(
            plan=plan,
            user_role="admin",
            allowed_report_types={"application_risk", "sales_funnel"},
        )
        assert decision.can_proceed is False
        assert decision.needs_clarification is True
        assert decision.clarification_question


class TestUnknownIntent:
    def test_unknown_intent_asks_clarification(self):
        """意图未知 → 追问。"""
        plan = ReportRequestPlan(
            intent=ReportAssistantIntent.UNKNOWN,
            confidence=0.30,
        )
        decision = decide_clarification(
            plan=plan,
            user_role="admin",
            allowed_report_types={"application_risk", "sales_funnel"},
        )
        assert decision.needs_clarification is True
        assert decision.can_proceed is False


class TestPermissionDenied:
    def test_no_permission_rejected(self):
        """无权限 → 直接拒绝，不追问绕过。"""
        plan = ReportRequestPlan(
            intent=ReportAssistantIntent.GENERATE_REPORT,
            report_type="channel_roi",
            confidence=0.95,
        )
        decision = decide_clarification(
            plan=plan,
            user_role="employee",  # employee 不能访问 channel_roi
            allowed_report_types={"application_risk", "sales_funnel", "complaint_weekly"},
        )
        assert decision.can_proceed is False
        assert decision.needs_clarification is True
        assert "权限" in (decision.clarification_question or "")


class TestWriteIntentBlocked:
    def test_write_intent_blocked_in_iteration_1(self):
        """Iteration 1 写操作一律拦截。"""
        plan = ReportRequestPlan(
            intent=ReportAssistantIntent.GENERATE_ACTION_CANDIDATES,
            report_type="application_risk",
            confidence=0.95,
        )
        decision = decide_clarification(
            plan=plan,
            user_role="admin",
            allowed_report_types={"application_risk"},
        )
        assert decision.can_proceed is False
        assert decision.needs_clarification is True
