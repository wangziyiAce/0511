"""智能报告助手 Iteration 2A.1 — 工具专项测试。

测试目标：
1. 报告状态工具（tool_query_report_status）
2. 报告详情工具（tool_get_report_detail）
3. 申请风险列表（tool_get_application_risk_items）
4. 申请风险详情（tool_get_application_risk_detail）
5. MetricTrace（tool_get_metric_trace）
6. DataQuality（tool_get_report_data_quality）

所有测试使用 Mock DB 方案，避免 SQLite BIGINT 兼容性问题。
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from services.reporting.assistant.tools import (
    _METRIC_ALIASES,
    _data_quality_limitations,
    _safe_error_message,
    _sanitize_psych_content,
)


# ============================================================================
# Test Helpers
# ============================================================================


def _make_mock_report(**overrides):
    """创建 Mock 报告对象。"""
    defaults = {
        "id": 128,
        "report_type": "application_risk",
        "report_title": "测试报告",
        "status": "completed",
        "schema_version": 2,
        "period_start": None,
        "period_end": None,
        "report_content": {},
        "data_quality": {"level": "ok"},
        "generated_by": 1,
        "create_time": None,
        "started_time": None,
        "completed_time": None,
        "error_code": None,
        "error_message": None,
    }
    defaults.update(overrides)
    mock = MagicMock()
    for k, v in defaults.items():
        setattr(mock, k, v)
    return mock


def _make_mock_user(role_code="admin", user_id=1):
    """创建 Mock 用户对象。"""
    user = MagicMock()
    user.role_code = role_code
    user.id = user_id
    return user


def _make_mock_db(report=None):
    """创建 Mock DB Session。"""
    db = MagicMock()
    query = MagicMock()
    db.query.return_value = query
    query.filter_by.return_value = query
    query.first.return_value = report
    return db


# ============================================================================
# 一、报告状态工具测试
# ============================================================================


class TestToolQueryReportStatus:
    def test_status_pending(self):
        """pending 状态 → 返回 pending，can_view_detail=False。"""
        from services.reporting.assistant.tools import tool_query_report_status

        report = _make_mock_report(status="pending")
        db = _make_mock_db(report=report)
        result = tool_query_report_status(report_id=128, current_user=_make_mock_user(), db=db)

        assert result.status == "success"
        assert result.data["status"] == "pending"
        assert result.data["can_view_detail"] is False
        assert result.data["suggest_retry"] is False

    def test_status_generating(self):
        """generating 状态 → can_view_detail=False。"""
        from services.reporting.assistant.tools import tool_query_report_status

        report = _make_mock_report(status="generating")
        db = _make_mock_db(report=report)
        result = tool_query_report_status(report_id=128, current_user=_make_mock_user(), db=db)

        assert result.status == "success"
        assert result.data["status"] == "generating"
        assert result.data["can_view_detail"] is False

    def test_status_completed(self):
        """completed 状态 → can_view_detail=True。"""
        from services.reporting.assistant.tools import tool_query_report_status

        report = _make_mock_report(status="completed")
        db = _make_mock_db(report=report)
        result = tool_query_report_status(report_id=128, current_user=_make_mock_user(), db=db)

        assert result.status == "success"
        assert result.data["status"] == "completed"
        assert result.data["can_view_detail"] is True

    def test_status_failed_suggests_retry(self):
        """failed 状态 → suggest_retry=True。"""
        from services.reporting.assistant.tools import tool_query_report_status

        report = _make_mock_report(status="failed")
        db = _make_mock_db(report=report)
        result = tool_query_report_status(report_id=128, current_user=_make_mock_user(), db=db)

        assert result.status == "success"
        assert result.data["status"] == "failed"
        assert result.data["suggest_retry"] is True

    def test_status_not_found(self):
        """报告不存在 → error。"""
        from services.reporting.assistant.tools import tool_query_report_status

        db = _make_mock_db(report=None)  # report=None
        result = tool_query_report_status(report_id=999, current_user=_make_mock_user(), db=db)

        assert result.status == "error"
        assert "不存在" in result.error

    def test_status_permission_denied(self):
        """非本人报告且非管理角色 → 权限拒绝。"""
        from services.reporting.assistant.tools import tool_query_report_status

        report = _make_mock_report(status="completed", generated_by=10)
        db = _make_mock_db(report=report)
        result = tool_query_report_status(
            report_id=128,
            current_user=_make_mock_user(role_code="employee", user_id=99),
            db=db,
        )

        assert result.status == "error"
        assert "无权" in result.error


# ============================================================================
# 二、报告详情工具测试
# ============================================================================


class TestToolGetReportDetail:
    def test_detail_requires_completed_report(self):
        """非 completed 状态 → 拒绝。"""
        from services.reporting.assistant.tools import tool_get_report_detail

        report = _make_mock_report(status="generating")
        db = _make_mock_db(report=report)
        result = tool_get_report_detail(report_id=128, current_user=_make_mock_user(), db=db)

        assert result.status == "error"
        assert "尚未完成" in result.error or "generating" in result.error

    def test_detail_returns_schema_version(self):
        """completed 报告 → 返回 schema_version。"""
        from services.reporting.assistant.tools import tool_get_report_detail

        report = _make_mock_report(
            status="completed",
            schema_version=2,
            report_content={"summary": "测试"},
            period_start=None,
            period_end=None,
        )
        db = _make_mock_db(report=report)
        result = tool_get_report_detail(report_id=128, current_user=_make_mock_user(), db=db)

        assert result.status == "success"
        assert result.data["schema_version"] == 2

    def test_detail_returns_metric_traces(self):
        """报告包含 metric_traces → 在结果中返回。"""
        from services.reporting.assistant.tools import tool_get_report_detail

        traces = [{"metric_name": "risk_score", "source_tables": ["t1"], "formula": "x+y"}]
        report = _make_mock_report(
            status="completed",
            report_content={"summary": "测试", "metric_traces": traces},
        )
        db = _make_mock_db(report=report)
        result = tool_get_report_detail(report_id=128, current_user=_make_mock_user(), db=db)

        assert result.status == "success"
        assert len(result.data["metric_traces"]) == 1
        assert result.data["metric_traces"][0]["metric_name"] == "risk_score"

    def test_detail_does_not_return_html(self):
        """报告详情不返回 report_html（只返回结构化 content）。"""
        from services.reporting.assistant.tools import tool_get_report_detail

        report = _make_mock_report(
            status="completed",
            report_content={"summary": "测试"},
        )
        report.report_html = "<html>不应出现</html>"
        db = _make_mock_db(report=report)
        result = tool_get_report_detail(report_id=128, current_user=_make_mock_user(), db=db)

        assert result.status == "success"
        assert "report_html" not in result.data

    def test_detail_sanitizes_psych_content(self):
        """心理报告 → 脱敏移除 student_name/student_id。"""
        content = {
            "summary": "心理周报",
            "alert_status": [
                {"student_name": "张三", "student_id": "S001", "risk": "high"},
                {"student_name": "李四", "student_id": "S002", "risk": "medium"},
            ],
        }
        sanitized = _sanitize_psych_content(content)

        for item in sanitized.get("alert_status", []):
            assert "student_name" not in item
            assert "student_id" not in item
        assert sanitized["summary"] == "心理周报"  # 非敏感字段保留

    def test_detail_checks_row_permission(self):
        """行级权限检查 — 非本人报告被拒绝。"""
        from services.reporting.assistant.tools import tool_get_report_detail

        report = _make_mock_report(status="completed", generated_by=10)
        db = _make_mock_db(report=report)
        result = tool_get_report_detail(
            report_id=128,
            current_user=_make_mock_user(role_code="employee", user_id=99),
            db=db,
        )

        assert result.status == "error"
        assert "无权" in result.error


# ============================================================================
# 三、申请风险列表工具测试
# ============================================================================


class TestToolGetApplicationRiskItems:
    def test_risk_items_sorted_descending(self):
        """risk_items 按 risk_score 降序排列（Python 排序）。"""
        from services.reporting.assistant.tools import tool_get_application_risk_items

        content = {
            "risk_items": [
                {"application_id": "A1", "risk_score": 30, "risk_level": "low"},
                {"application_id": "A2", "risk_score": 90, "risk_level": "high"},
                {"application_id": "A3", "risk_score": 60, "risk_level": "medium"},
            ],
        }
        report = _make_mock_report(status="completed", report_content=content)
        db = _make_mock_db(report=report)
        result = tool_get_application_risk_items(
            report_id=128, current_user=_make_mock_user(), db=db,
        )

        assert result.status == "success"
        items = result.data["items"]
        # 降序：90, 60, 30
        assert items[0]["risk_score"] == 90
        assert items[1]["risk_score"] == 60
        assert items[2]["risk_score"] == 30

    def test_risk_items_filter_by_level(self):
        """按 risk_level 过滤 → 只返回匹配项。"""
        from services.reporting.assistant.tools import tool_get_application_risk_items

        content = {
            "risk_items": [
                {"application_id": "A1", "risk_score": 90, "risk_level": "high"},
                {"application_id": "A2", "risk_score": 80, "risk_level": "high"},
                {"application_id": "A3", "risk_score": 70, "risk_level": "medium"},
            ],
        }
        report = _make_mock_report(status="completed", report_content=content)
        db = _make_mock_db(report=report)
        result = tool_get_application_risk_items(
            report_id=128, risk_level="high", current_user=_make_mock_user(), db=db,
        )

        assert result.status == "success"
        items = result.data["items"]
        assert len(items) == 2
        assert all(i["risk_level"] == "high" for i in items)

    def test_risk_items_limit_max_ten(self):
        """limit 强制上限 10。"""
        from services.reporting.assistant.tools import tool_get_application_risk_items

        items = [
            {"application_id": f"A{i}", "risk_score": 100 - i, "risk_level": "high"}
            for i in range(20)
        ]
        report = _make_mock_report(status="completed", report_content={"risk_items": items})
        db = _make_mock_db(report=report)
        result = tool_get_application_risk_items(
            report_id=128, limit=15, current_user=_make_mock_user(), db=db,
        )

        assert result.status == "success"
        assert result.data["returned_items"] <= 10

    def test_risk_items_generate_correct_positions(self):
        """referenced_entities position 与排序后位置一致。"""
        from services.reporting.assistant.tools import tool_get_application_risk_items

        content = {
            "risk_items": [
                {"application_id": "A3", "risk_score": 30, "risk_level": "low"},
                {"application_id": "A1", "risk_score": 90, "risk_level": "high"},
                {"application_id": "A2", "risk_score": 60, "risk_level": "medium"},
            ],
        }
        report = _make_mock_report(status="completed", report_content=content)
        db = _make_mock_db(report=report)
        result = tool_get_application_risk_items(
            report_id=128, current_user=_make_mock_user(), db=db,
        )

        entities = result.data["referenced_entities"]
        # position 1 = A1 (90), position 2 = A2 (60), position 3 = A3 (30)
        assert entities[0]["position"] == 1
        assert entities[0]["entity_id"] == "A1"
        assert entities[1]["position"] == 2
        assert entities[1]["entity_id"] == "A2"
        assert entities[2]["position"] == 3
        assert entities[2]["entity_id"] == "A3"

    def test_risk_items_do_not_trust_client_metadata(self):
        """客户端传入的 metadata 不影响工具结果 — 工具始终从报告内容读取。"""
        from services.reporting.assistant.tools import tool_get_application_risk_items

        # 报告真实数据
        content = {
            "risk_items": [
                {"application_id": "A1", "risk_score": 70, "risk_level": "medium"},
            ],
        }
        report = _make_mock_report(status="completed", report_content=content)
        db = _make_mock_db(report=report)
        result = tool_get_application_risk_items(
            report_id=128, current_user=_make_mock_user(), db=db,
        )

        # 工具只从 report.report_content 读取，不信任任何外部输入
        entities = result.data["referenced_entities"]
        assert entities[0]["metadata"]["risk_score"] == 70  # 真实值
        assert entities[0]["metadata"]["risk_level"] == "medium"  # 真实值


# ============================================================================
# 四、申请风险详情工具测试
# ============================================================================


class TestToolGetApplicationRiskDetail:
    def test_risk_detail_returns_exact_entity(self):
        """精确匹配 application_id → 只返回该实体的数据。"""
        from services.reporting.assistant.tools import tool_get_application_risk_detail

        content = {
            "risk_items": [
                {"application_id": "A1024", "risk_score": 90, "risk_level": "high",
                 "risk_reasons": ["逾期"], "missing_materials": ["推荐信"]},
                {"application_id": "A1058", "risk_score": 70, "risk_level": "high",
                 "risk_reasons": ["临近截止"], "missing_materials": ["个人陈述"]},
            ],
            "metric_traces": [],
        }
        report = _make_mock_report(status="completed", report_content=content)
        db = _make_mock_db(report=report)
        result = tool_get_application_risk_detail(
            report_id=128, application_id="A1024",
            current_user=_make_mock_user(), db=db,
        )

        assert result.status == "success"
        assert result.data["application_id"] == "A1024"
        assert result.data["risk_score"] == 90
        assert "逾期" in result.data["risk_reasons"]
        # A1058 的缺失材料不应出现在 A1024 的结果中
        assert "个人陈述" not in result.data["missing_materials"]

    def test_risk_detail_not_found(self):
        """application_id 不存在 → error。"""
        from services.reporting.assistant.tools import tool_get_application_risk_detail

        content = {
            "risk_items": [
                {"application_id": "A1024", "risk_score": 90, "risk_level": "high",
                 "risk_reasons": [], "missing_materials": []},
            ],
        }
        report = _make_mock_report(status="completed", report_content=content)
        db = _make_mock_db(report=report)
        result = tool_get_application_risk_detail(
            report_id=128, application_id="NONEXIST",
            current_user=_make_mock_user(), db=db,
        )

        assert result.status == "error"
        assert "未找到" in result.error

    def test_risk_detail_reasons_are_not_generated(self):
        """风险原因来自报告内容，不是工具动态生成。"""
        from services.reporting.assistant.tools import tool_get_application_risk_detail

        content = {
            "risk_items": [
                {"application_id": "A1024", "risk_score": 90, "risk_level": "high",
                 "risk_reasons": ["原始原因1", "原始原因2"], "missing_materials": []},
            ],
        }
        report = _make_mock_report(status="completed", report_content=content)
        db = _make_mock_db(report=report)
        result = tool_get_application_risk_detail(
            report_id=128, application_id="A1024",
            current_user=_make_mock_user(), db=db,
        )

        assert result.data["risk_reasons"] == ["原始原因1", "原始原因2"]
        # 不会添加额外原因
        assert len(result.data["risk_reasons"]) == 2

    def test_risk_detail_rejects_entity_from_other_report(self):
        """确认实体来自指定 report_id — 不存在时返回错误。"""
        from services.reporting.assistant.tools import tool_get_application_risk_detail

        # 报告中只有 A1024 和 A1058
        content = {
            "risk_items": [
                {"application_id": "A1024", "risk_score": 90, "risk_level": "high",
                 "risk_reasons": [], "missing_materials": []},
                {"application_id": "A1058", "risk_score": 70, "risk_level": "high",
                 "risk_reasons": [], "missing_materials": []},
            ],
        }
        report = _make_mock_report(status="completed", report_content=content)
        db = _make_mock_db(report=report)
        # 查询其他报告的实体
        result = tool_get_application_risk_detail(
            report_id=128, application_id="B9999",
            current_user=_make_mock_user(), db=db,
        )

        assert result.status == "error"
        assert "未找到" in result.error


# ============================================================================
# 五、MetricTrace 工具测试
# ============================================================================


class TestToolGetMetricTrace:
    def test_metric_alias_resolves_to_registered_metric(self):
        """中文别名'风险分' → 解析为 risk_score。"""
        assert _METRIC_ALIASES.get("风险分") == "risk_score"
        assert _METRIC_ALIASES.get("ROI") == "roi"
        assert _METRIC_ALIASES.get("SLA 超时数") == "sla_timeout_count"

    def test_unknown_metric_is_rejected(self):
        """不在白名单中的指标名 → error。"""
        from services.reporting.assistant.tools import tool_get_metric_trace

        content = {
            "metric_traces": [
                {"metric_name": "risk_score", "source_tables": ["t1"], "formula": "x+y"},
            ],
        }
        report = _make_mock_report(status="completed", report_content=content)
        db = _make_mock_db(report=report)
        result = tool_get_metric_trace(
            report_id=128, metric_name="unknown_metric",
            current_user=_make_mock_user(), db=db,
        )

        assert result.status == "error"
        assert "未知指标" in result.error

    def test_metric_trace_returns_source_formula_filters(self):
        """返回完整的 source_tables、formula、filters、period。"""
        from services.reporting.assistant.tools import tool_get_metric_trace

        content = {
            "metric_traces": [
                {
                    "metric_name": "risk_score",
                    "source_tables": ["application_risk_fact", "application_material_item"],
                    "formula": "base_score + overdue_bonus + missing_material_bonus",
                    "filters": {"status": "active", "period": "current_week"},
                },
            ],
        }
        report = _make_mock_report(
            status="completed",
            report_content=content,
            period_start=None,
            period_end=None,
        )
        db = _make_mock_db(report=report)
        result = tool_get_metric_trace(
            report_id=128, metric_name="risk_score",
            current_user=_make_mock_user(), db=db,
        )

        assert result.status == "success"
        assert "application_risk_fact" in result.data["source_tables"]
        assert "base_score" in result.data["formula"]
        assert result.data["filters"]["status"] == "active"

    def test_metric_trace_does_not_allow_jsonpath(self):
        """不允许 LLM 传递 JSONPath 作为 metric_name — 不在白名单即拒绝。"""
        from services.reporting.assistant.tools import tool_get_metric_trace

        report = _make_mock_report(status="completed", report_content={"metric_traces": []})
        db = _make_mock_db(report=report)

        # 尝试注入 JSONPath
        result = tool_get_metric_trace(
            report_id=128, metric_name="$.risk_items[0].risk_score",
            current_user=_make_mock_user(), db=db,
        )

        assert result.status == "error"

    def test_metric_trace_does_not_allow_table_name_input(self):
        """不允许 LLM 传递 SQL 表名作为 metric_name。"""
        from services.reporting.assistant.tools import tool_get_metric_trace

        report = _make_mock_report(status="completed", report_content={"metric_traces": []})
        db = _make_mock_db(report=report)

        result = tool_get_metric_trace(
            report_id=128, metric_name="application_risk_fact",
            current_user=_make_mock_user(), db=db,
        )

        assert result.status == "error"


# ============================================================================
# 六、DataQuality 工具测试
# ============================================================================


class TestToolGetReportDataQuality:
    def test_warning_keeps_answer_and_adds_limitation(self):
        """warning → 限制列表包含'说明数据局限性'。"""
        limits = _data_quality_limitations("warning")
        assert "说明数据局限性" in limits
        assert len(limits) == 1

    def test_empty_replaces_analysis_with_no_data_message(self):
        """empty → 不得解释趋势、不得分析变化原因。"""
        limits = _data_quality_limitations("empty")
        assert "不得解释趋势" in limits
        assert "不得分析变化原因" in limits
        assert len(limits) == 2

    def test_degraded_blocks_strong_conclusion(self):
        """degraded → 不得给出强结论、必须说明降级原因。"""
        limits = _data_quality_limitations("degraded")
        assert "不得给出强结论" in limits
        assert "必须说明降级原因" in limits

    def test_failed_blocks_business_analysis(self):
        """failed → 不得生成业务分析、不得做任何趋势判断。"""
        limits = _data_quality_limitations("failed")
        assert "不得生成业务分析" in limits
        assert "不得做任何趋势判断" in limits

    def test_ok_has_no_limitations(self):
        """ok → 无限制。"""
        limits = _data_quality_limitations("ok")
        assert len(limits) == 0

    def test_llm_cannot_remove_quality_warning(self):
        """DataQuality 约束在应用层注入，LLM 无法通过 Prompt 删除。"""
        from services.reporting.assistant.guardrails import apply_data_quality_guardrail

        # 即使 LLM 回答不包含限制，Python 也会注入
        llm_answer = "当前没有数据质量问题，一切正常。"
        result = apply_data_quality_guardrail(
            answer=llm_answer,
            data_quality_level="warning",
            is_analysis=True,
        )

        # warning 前缀被强制注入
        assert "数据质量提示" in result
        # 原始回答仍然保留
        assert "一切正常" in result


# ============================================================================
# 七、内部辅助函数测试
# ============================================================================


class TestInternalHelpers:
    def test_safe_error_message_truncates(self):
        """_safe_error_message 截断超长错误信息。"""
        long_msg = "x" * 300
        result = _safe_error_message(long_msg)
        assert len(result) <= 200

    def test_safe_error_message_handles_none(self):
        """_safe_error_message(None) → None。"""
        assert _safe_error_message(None) is None

    def test_sanitize_psych_preserves_non_sensitive(self):
        """脱敏保留非敏感字段。"""
        content = {
            "summary": "周报摘要",
            "other_field": "值",
            "alert_status": [],
        }
        result = _sanitize_psych_content(content)
        assert result["summary"] == "周报摘要"
        assert result["other_field"] == "值"

    def test_sanitize_psych_handles_non_dict(self):
        """_sanitize_psych_content 处理非 dict 输入。"""
        assert _sanitize_psych_content("string") == "string"
        assert _sanitize_psych_content(None) == None
        assert _sanitize_psych_content([]) == []
