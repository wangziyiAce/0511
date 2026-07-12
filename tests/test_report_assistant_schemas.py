"""智能报告助手 — Schema 单元测试。

测试目标：验证智能层的请求/响应 Schema、意图枚举、计划模型、会话上下文、
置信度约束和降级配置。

TDD 顺序：
1. 非法置信度、风险等级、输出风格测试先失败
2. 响应必填字段测试先失败
3. 实现最小模型
4. 测试通过
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from services.reporting.assistant.schemas import (
    AssistantToolResult,
    ClarificationDecision,
    EvidenceItem,
    ReferencedEntity,
    ReportAssistantIntent,
    ReportAssistantMessageRequest,
    ReportAssistantMessageResponse,
    ReportConversationContext,
    ReportRequestPlan,
    ReportTypeOption,
)


# ---------------------------------------------------------------------------
# ReportAssistantIntent
# ---------------------------------------------------------------------------


class TestReportAssistantIntent:
    def test_all_expected_intents_exist(self):
        """验证所有计划中的意图类型都已定义。"""
        expected = {
            "generate_report",
            "query_report",
            "compare_reports",
            "cross_report_analysis",
            "explain_metric",
            "explain_risk",
            "drill_down",
            "summarize_for_role",
            "generate_action_candidates",
            "confirm_actions",
            "query_data_quality",
            "query_report_status",
            "unknown",
        }
        actual = {v.value for v in ReportAssistantIntent}
        assert actual == expected

    def test_intent_is_string_enum(self):
        """意图必须是字符串枚举，方便 JSON 序列化。"""
        assert ReportAssistantIntent.GENERATE_REPORT.value == "generate_report"


# ---------------------------------------------------------------------------
# ReportTypeOption
# ---------------------------------------------------------------------------


class TestReportTypeOption:
    def test_valid_option(self):
        option = ReportTypeOption(
            report_type="application_risk",
            label="申请风险报告",
            default_period_rule="previous_week",
            allowed=True,
            keywords=["申请", "材料", "截止"],
        )
        assert option.report_type == "application_risk"
        assert option.keywords == ["申请", "材料", "截止"]

    def test_keywords_max_10(self):
        """业务关键词最多 10 项。"""
        with pytest.raises(ValidationError):
            ReportTypeOption(
                report_type="application_risk",
                label="申请风险报告",
                default_period_rule="previous_week",
                allowed=True,
                keywords=[f"kw_{i}" for i in range(11)],
            )


# ---------------------------------------------------------------------------
# ReportRequestPlan
# ---------------------------------------------------------------------------


class TestReportRequestPlan:
    def test_minimal_plan(self):
        plan = ReportRequestPlan(
            intent=ReportAssistantIntent.UNKNOWN,
            confidence=0.5,
        )
        assert plan.intent == ReportAssistantIntent.UNKNOWN
        assert plan.report_type is None

    def test_confidence_out_of_range_low(self):
        """置信度 < 0 应拒绝。"""
        with pytest.raises(ValidationError):
            ReportRequestPlan(intent=ReportAssistantIntent.GENERATE_REPORT, confidence=-0.1)

    def test_confidence_out_of_range_high(self):
        """置信度 > 1.0 应拒绝。"""
        with pytest.raises(ValidationError):
            ReportRequestPlan(intent=ReportAssistantIntent.GENERATE_REPORT, confidence=1.5)

    def test_invalid_risk_level(self):
        """非法风险等级应拒绝。"""
        with pytest.raises(ValidationError):
            ReportRequestPlan(
                intent=ReportAssistantIntent.GENERATE_REPORT,
                confidence=0.9,
                risk_level="critical",  # 不是 high/medium/low
            )

    def test_invalid_output_style(self):
        """非法输出风格应拒绝。"""
        with pytest.raises(ValidationError):
            ReportRequestPlan(
                intent=ReportAssistantIntent.GENERATE_REPORT,
                confidence=0.9,
                output_style="raw_data",  # 不是允许的风格
            )

    def test_valid_full_plan(self):
        plan = ReportRequestPlan(
            intent=ReportAssistantIntent.GENERATE_REPORT,
            report_type="application_risk",
            relative_period="this_week",
            confidence=0.93,
            output_style="management_summary",
            need_actions=False,
            assumptions=["“现在”按本周截至当前时间处理"],
        )
        assert plan.intent == ReportAssistantIntent.GENERATE_REPORT
        assert len(plan.assumptions) == 1


# ---------------------------------------------------------------------------
# ReportConversationContext
# ---------------------------------------------------------------------------


class TestReportConversationContext:
    def test_minimal_context(self):
        ctx = ReportConversationContext(conversation_id="test-uuid")
        assert ctx.conversation_id == "test-uuid"
        assert ctx.last_report_id is None
        assert ctx.last_report_type is None

    def test_conversation_id_max_length(self):
        """conversation_id 最大 64 字符。"""
        with pytest.raises(ValidationError):
            ReportConversationContext(conversation_id="a" * 65)


# ---------------------------------------------------------------------------
# ReferencedEntity
# ---------------------------------------------------------------------------


class TestReferencedEntity:
    def test_valid_entity(self):
        entity = ReferencedEntity(
            entity_type="report",
            entity_id="128",
            label="申请风险报告 #128",
        )
        assert entity.entity_type == "report"


# ---------------------------------------------------------------------------
# EvidenceItem
# ---------------------------------------------------------------------------


class TestEvidenceItem:
    def test_valid_evidence(self):
        evidence = EvidenceItem(
            source="tool_result",
            reference="application_risk.metrics.high_risk_count",
            value="5",
        )
        assert evidence.source == "tool_result"


# ---------------------------------------------------------------------------
# AssistantToolResult
# ---------------------------------------------------------------------------


class TestAssistantToolResult:
    def test_success_result(self):
        result = AssistantToolResult(
            tool_name="list_report_types",
            status="success",
            data={"report_types": ["application_risk"]},
        )
        assert result.status == "success"
        assert result.error is None

    def test_error_result(self):
        result = AssistantToolResult(
            tool_name="generate_existing_report",
            status="error",
            error="权限不足",
        )
        assert result.status == "error"


# ---------------------------------------------------------------------------
# ClarificationDecision
# ---------------------------------------------------------------------------


class TestClarificationDecision:
    def test_needs_clarification(self):
        decision = ClarificationDecision(
            needs_clarification=True,
            clarification_question="你想查看哪种报告？",
            confidence=0.35,
        )
        assert decision.needs_clarification is True


# ---------------------------------------------------------------------------
# ReportAssistantMessageRequest
# ---------------------------------------------------------------------------


class TestReportAssistantMessageRequest:
    def test_minimal_request(self):
        req = ReportAssistantMessageRequest(
            message="看看现在的申请风险",
            conversation_context=ReportConversationContext(conversation_id="test"),
        )
        assert req.message == "看看现在的申请风险"

    def test_message_max_length(self):
        """message 最大 2000 字符。"""
        with pytest.raises(ValidationError):
            ReportAssistantMessageRequest(
                message="a" * 2001,
                conversation_context=ReportConversationContext(conversation_id="test"),
            )

    def test_message_min_length(self):
        """空消息应拒绝。"""
        with pytest.raises(ValidationError):
            ReportAssistantMessageRequest(
                message="",
                conversation_context=ReportConversationContext(conversation_id="test"),
            )


# ---------------------------------------------------------------------------
# ReportAssistantMessageResponse
# ---------------------------------------------------------------------------


class TestReportAssistantMessageResponse:
    def test_generating_response(self):
        resp = ReportAssistantMessageResponse(
            status="generating",
            intent=ReportAssistantIntent.GENERATE_REPORT,
            report_id=128,
            report_type="application_risk",
            answer="已创建申请风险报告，正在生成。",
            needs_clarification=False,
            assumptions=["“现在”按本周截至当前时间处理"],
            confidence=0.93,
            conversation_context=ReportConversationContext(
                conversation_id="test",
                last_report_id=128,
                last_report_type="application_risk",
            ),
        )
        assert resp.status == "generating"
        assert resp.report_id == 128

    def test_clarification_response(self):
        resp = ReportAssistantMessageResponse(
            status="needs_clarification",
            intent=ReportAssistantIntent.UNKNOWN,
            answer="我还不能确定你要查看什么报告。",
            needs_clarification=True,
            clarification_question="你主要想查看申请风险、销售经营，还是服务质量？",
            confidence=0.42,
            conversation_context=ReportConversationContext(conversation_id="test"),
        )
        assert resp.needs_clarification is True
        assert resp.report_id is None

    def test_assumptions_max_10(self):
        """assumptions 最多 10 条。"""
        with pytest.raises(ValidationError):
            ReportAssistantMessageResponse(
                status="generating",
                intent=ReportAssistantIntent.GENERATE_REPORT,
                answer="测试",
                needs_clarification=False,
                assumptions=[f"assumption_{i}" for i in range(11)],
                confidence=0.9,
                conversation_context=ReportConversationContext(conversation_id="test"),
            )
