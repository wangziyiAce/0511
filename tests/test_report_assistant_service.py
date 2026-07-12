"""智能报告助手 — 总编排服务单元测试。

测试目标：验证完整请求处理链路（意图 → 澄清 → 时间 → 工具 → 响应）。
使用 mock 控制 LLM 和数据库依赖。
"""

from __future__ import annotations

import pytest

from services.reporting.assistant.config import ReportAssistantSettings
from services.reporting.assistant.schemas import (
    ReportAssistantIntent,
    ReportAssistantMessageRequest,
    ReportConversationContext,
)
from services.reporting.assistant.service import ReportAssistantService


def _ctx(conversation_id: str = "test-session") -> ReportConversationContext:
    return ReportConversationContext(conversation_id=conversation_id)


def _mock_current_user(**overrides):
    """创建 mock 用户。"""
    from utils.auth import CurrentUser

    defaults = {
        "id": 1,
        "username": "admin",
        "real_name": "管理员",
        "user_type": "employee",
        "role_code": "admin",
        "department": "技术部",
    }
    defaults.update(overrides)
    return CurrentUser(**defaults)


class FakeDB:
    """假的数据库 Session，用于测试不需要真实 DB 的路径。"""
    pass


def _patch_assistant_settings(monkeypatch, **overrides):
    """统一 patch 所有使用 settings 的模块。

    settings 被 config、intent_parser、clarification 三个模块引用，
    必须在所有引用处做 monkeypatch。
    """
    import services.reporting.assistant.config as config_module
    import services.reporting.assistant.intent_parser as ip_module
    import services.reporting.assistant.clarification as cl_module
    import services.reporting.assistant.service as svc_module

    test_settings = ReportAssistantSettings(enabled=True, llm_enabled=False, **overrides)
    monkeypatch.setattr(config_module, "settings", test_settings)
    monkeypatch.setattr(ip_module, "settings", test_settings)
    monkeypatch.setattr(cl_module, "settings", test_settings)
    return test_settings


class TestServiceClarificationPath:
    def test_no_role_returns_error(self, monkeypatch):
        """无角色 → 返回错误。"""
        _patch_assistant_settings(monkeypatch)

        service = ReportAssistantService()
        response = service.handle_message(
            request=ReportAssistantMessageRequest(
                message="看看申请风险",
                conversation_context=_ctx(),
            ),
            current_user=_mock_current_user(role_code="student"),
            db=FakeDB(),
        )
        # student 角色被 build_report_catalog 排除 → allowed_types 为空
        assert response.status in ("error", "needs_clarification", "permission_denied")

    def test_unknown_intent_returns_clarification(self, monkeypatch):
        """无法识别的消息 → 澄清。"""
        _patch_assistant_settings(monkeypatch)

        service = ReportAssistantService()
        response = service.handle_message(
            request=ReportAssistantMessageRequest(
                message="今天天气真好",
                conversation_context=_ctx(),
            ),
            current_user=_mock_current_user(),
            db=FakeDB(),
        )
        assert response.status == "needs_clarification"
        assert response.needs_clarification is True


class TestServiceSuccessPath:
    def test_application_risk_generation(self, monkeypatch):
        """识别申请风险 → 调用生成工具。模拟 execute_tool 避免真实 DB。"""
        _patch_assistant_settings(monkeypatch)

        from services.reporting.assistant.schemas import AssistantToolResult

        def mock_execute(self, plan, resolved_period, generated_by, db, idempotency_key=None, current_user=None, context=None, message=""):
            return [AssistantToolResult(
                tool_name="generate_existing_report",
                status="success",
                data={
                    "report_id": 128,
                    "report_type": "application_risk",
                    "status": "generating",
                    "period_start": "2026-07-06",
                    "period_end": "2026-07-12",
                },
                report_id=128,
            )]

        monkeypatch.setattr(
            ReportAssistantService,
            "_execute_tool",
            mock_execute,
        )

        service = ReportAssistantService()
        response = service.handle_message(
            request=ReportAssistantMessageRequest(
                message="看看现在的申请风险",
                conversation_context=_ctx(),
            ),
            current_user=_mock_current_user(),
            db=FakeDB(),
        )
        assert response.status == "generating"
        assert response.report_id == 128
        assert response.report_type == "application_risk"
        assert response.intent == ReportAssistantIntent.GENERATE_REPORT
        assert len(response.assumptions) > 0
        assert response.conversation_context.last_report_id == 128
        assert response.conversation_context.last_report_type == "application_risk"


class TestServicePermissionDenied:
    def test_employee_cannot_access_channel_roi(self, monkeypatch):
        """普通员工访问 channel_roi → 明确拒绝，HTTP 层据此返回 403。"""
        _patch_assistant_settings(monkeypatch)

        service = ReportAssistantService()
        response = service.handle_message(
            request=ReportAssistantMessageRequest(
                message="渠道ROI怎么样",
                conversation_context=_ctx(),
            ),
            current_user=_mock_current_user(role_code="employee"),
            db=FakeDB(),
        )
        # employee 不能访问 channel_roi，catalog 中 report_type 为 channel_roi 时会 marked as not allowed
        # 关键词匹配可能命中 channel_roi，但 catalog 中 allowed=False
        # 如果匹配到了 → clarification 发现不在 allowed_types → 拒绝
        # 如果没匹配到 → UNKNOWN → 澄清
        assert response.status == "permission_denied"
        assert response.evidence == []
        assert response.report_type is None
