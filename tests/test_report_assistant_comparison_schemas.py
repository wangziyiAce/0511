"""验证 Iteration 3 对比响应契约，并保护 Iteration 2 的既有字段。"""

from datetime import date
from decimal import Decimal

from services.reporting.assistant.schemas import (
    ComparisonDataQuality,
    ComparisonPeriod,
    EvidenceItem,
    MetricComparison,
    RelationshipSections,
    ReportAssistantMessageResponse,
    ReportConversationContext,
)
from services.reporting.assistant.service import _extract_comparison_response_fields


def test_metric_comparison_preserves_none_and_dimension():
    """缺失值必须保留为 None，维度信息必须原样传给前端。"""
    item = MetricComparison(
        report_type="channel_roi", metric_name="roi", label="ROI",
        dimension={"channel": "search"}, current_value=Decimal("-0.2"),
        previous_value=None, delta=None, change_rate=None, direction="unknown",
        unit="%", current_evidence_id="E1", previous_evidence_id="E2",
    )
    assert item.previous_value is None
    assert item.dimension == {"channel": "search"}


def test_evidence_accepts_comparison_binding():
    """对比证据需要绑定报告、周期和角色，供数字溯源。"""
    evidence = EvidenceItem(
        evidence_id="E1", label="本周高风险数", value=3, source_report_id=0,
        report_type="application_risk", period_label="本周",
        comparison_role="current", source_tables=["student_application"],
    )
    assert evidence.comparison_role == "current"


def test_response_accepts_all_comparison_sections():
    """响应在保留旧契约的同时，可以承载完整对比展示数据。"""
    period = ComparisonPeriod(
        current_start=date(2026, 7, 6), current_end=date(2026, 7, 12),
        previous_start=date(2026, 6, 29), previous_end=date(2026, 7, 5),
        current_label="本周", previous_label="上周",
    )
    quality = ComparisonDataQuality(allow_values=True, allow_trend=False)
    response = ReportAssistantMessageResponse(
        status="completed", answer="对比完成",
        conversation_context=ReportConversationContext(conversation_id="comparison-test"),
        comparison_period=period, metric_comparisons=[],
        comparison_data_quality=quality,
        relationship_sections=RelationshipSections(cannot_confirm=["不能确认因果关系"]),
    )
    assert response.comparison_period == period
    assert response.comparison_data_quality.allow_trend is False
    assert response.relationship_sections.cannot_confirm


def test_service_extracts_iteration3_fields_from_comparison_tool_data():
    """比较工具的确定性结果必须进入公开响应，不能只停留在回答文本内部。"""

    primary_data = {
        "periods": {
            "current_start": "2026-06-29",
            "current_end": "2026-07-05",
            "previous_start": "2026-06-22",
            "previous_end": "2026-06-28",
            "current_label": "本周",
            "previous_label": "上周",
            "assumptions": [],
        },
        "comparison": [
            {
                "report_type": "application_risk",
                "metric_name": "high_risk_count",
                "label": "高风险申请数",
                "dimension": {},
                "current_value": "2",
                "previous_value": "1",
                "delta": "1",
                "change_rate": "1",
                "direction": "up",
                "unit": "个",
                "current_evidence_id": "E1",
                "previous_evidence_id": "E2",
            }
        ],
        "current_data_quality": {"level": "ok", "warnings": []},
        "previous_data_quality": {"level": "ok", "warnings": []},
    }

    fields = _extract_comparison_response_fields(primary_data)

    assert fields["comparison_period"].current_label == "本周"
    assert fields["metric_comparisons"][0].metric_name == "high_risk_count"
    assert fields["comparison_data_quality"].allow_trend is True
