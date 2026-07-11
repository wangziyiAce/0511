"""Prompt Builder 和数据脱敏单元测试。"""

from __future__ import annotations

from services.reporting.prompt_builder import (
    REPORT_FOCUS,
    REPORT_GROUPS,
    build_chat_messages,
    build_repair_messages,
    sanitize_report_data,
)
from services.reporting.registry import get_report_definition
from services.reporting.schemas import DataQuality


class TestSanitizeReportData:
    """数据脱敏功能。"""

    def test_psych_report_strips_sensitive_fields(self):
        """心理报告只保留白名单字段。"""
        content = {
            "summary": "周报摘要",
            "explanation": "趋势说明",
            "metrics": {"alert_count": 5},
            "emotion_trend": [],
            "alert_status": [
                {
                    "alert_id": 1,
                    "student_id": 100,
                    "risk_level": "high",
                    "status": "pending",
                    "owner_id": 3,
                    "first_follow_hours": 2.5,
                    "high_risk_follow_overdue": False,
                    "sensitive_original_text": "学生原文内容，不应传给 LLM",
                    "diagnosis_note": "诊断性描述",
                }
            ],
            "processing_timeliness": {"avg_hours": 1.2},
            "metric_traces": [],
            "_internal_secret": "不应出现在输出中",
        }
        safe = sanitize_report_data("psych_weekly", content)

        # 白名单字段存在
        assert "summary" in safe
        assert "metrics" in safe
        assert "alert_status" in safe
        assert "processing_timeliness" in safe

        # 不在白名单的字段被移除
        assert "_internal_secret" not in safe

        # alert_status 内只有白名单字段
        for alert in safe["alert_status"]:
            assert "sensitive_original_text" not in alert
            assert "diagnosis_note" not in alert
            assert "alert_id" in alert
            assert "risk_level" in alert

    def test_non_psych_report_passes_through(self):
        """非心理报告保持内容不变（浅层清理内部标记）。"""
        content = {
            "summary": "渠道摘要",
            "channel_metrics": [{"channel": "抖音", "cost": 1000}],
            "_internal": "secret",
        }
        safe = sanitize_report_data("channel_roi", content)
        assert "summary" in safe
        assert "channel_metrics" in safe
        assert "_internal" not in safe

    def test_original_content_not_mutated(self):
        """脱敏不修改原始内容。"""
        content = {
            "summary": "test",
            "sensitive_field": "should stay in original",
        }
        safe = sanitize_report_data("psych_weekly", content)
        assert "sensitive_field" in content  # 原始不受影响
        assert "sensitive_field" not in safe  # 脱敏版本不含


class TestReportGroups:
    """报告分组映射。"""

    def test_ten_types_map_to_five_groups(self):
        """10 类报告映射到 5 个分组。"""
        groups = set(REPORT_GROUPS.values())
        assert groups == {
            "application_risk",
            "sales_funnel",
            "channel_roi",
            "service_privacy",
            "management",
        }

    def test_all_registered_types_have_group_and_focus(self):
        """每类报告都有 group 和 focus。"""
        for report_type in REPORT_GROUPS:
            assert report_type in REPORT_FOCUS, f"{report_type} 缺少 focus 描述"


class TestBuildChatMessages:
    """Prompt 构建。"""

    def test_builds_two_messages(self):
        """返回 system + user 两条消息。"""
        definition = get_report_definition("application_risk")
        messages = build_chat_messages(
            definition=definition,
            title="测试报告",
            period={"start": "2026-01-01", "end": "2026-01-07"},
            content={"summary": "初始摘要", "metrics": {"total_applications": 1}},
            data_quality=DataQuality(),
        )
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"

    def test_system_prompt_contains_key_rules(self):
        """System Prompt 包含核心约束。"""
        definition = get_report_definition("sales_funnel")
        messages = build_chat_messages(
            definition=definition,
            title="测试",
            period={"start": "2026-01-01", "end": "2026-01-07"},
            content={},
            data_quality=DataQuality(),
        )
        system = messages[0]["content"]
        assert "summary" in system
        assert "explanation" in system
        assert "JSON" in system
        assert "禁止改写" in system

    def test_user_message_contains_context_json(self):
        """User 消息包含标准化上下文。"""
        definition = get_report_definition("channel_roi")
        messages = build_chat_messages(
            definition=definition,
            title="测试",
            period={"start": "2026-01-01", "end": "2026-01-07"},
            content={"channel_metrics": []},
            data_quality=DataQuality(),
        )
        user = messages[1]["content"]
        assert "aggregated_data" in user
        assert "expected_schema" in user
        assert "report_type" in user

    def test_psych_report_has_privacy_rules(self):
        """心理报告的 context 包含隐私规则。"""
        definition = get_report_definition("psych_weekly")
        messages = build_chat_messages(
            definition=definition,
            title="心理周报",
            period={"start": "2026-01-01", "end": "2026-01-07"},
            content={"metrics": {"alert_count": 3}},
            data_quality=DataQuality(),
        )
        user = messages[1]["content"]
        assert "心理咨询原文" in user or "privacy_rules" in user


class TestBuildRepairMessages:
    """修复 Prompt 构建。"""

    def test_repair_mode_flag_set(self):
        """修复消息中 is_repair_mode=True。"""
        definition = get_report_definition("application_risk")
        messages = build_repair_messages(
            definition=definition,
            title="测试",
            period={"start": "2026-01-01", "end": "2026-01-07"},
            content={"summary": "test"},
            data_quality=DataQuality(),
            invalid_output={"summary": {"bad": "type"}},
            validation_error="summary must be a string",
        )
        user = messages[1]["content"]
        assert "validation_error" in user
        assert "is_repair_mode" in user
        assert "invalid_output" in user

    def test_repair_contains_validation_error_text(self):
        """修复 Prompt 包含具体的校验错误文本。"""
        definition = get_report_definition("application_risk")
        messages = build_repair_messages(
            definition=definition,
            title="测试",
            period={"start": "2026-01-01", "end": "2026-01-07"},
            content={"summary": "test"},
            data_quality=DataQuality(),
            invalid_output={},
            validation_error="1 validation error: summary field required",
        )
        user = messages[1]["content"]
        assert "summary field required" in user
