"""指标目录与安全提取器契约测试。

本文件验证报告真实 content 路径、派生指标白名单、渠道维度、敏感权限元数据和
失败关闭行为，确保后续比较工具不能执行 LLM 提供的路径或表达式。
"""

from decimal import Decimal
from pathlib import Path

import pytest

from services.reporting.assistant.metric_catalog import (
    get_metric_definition,
    list_metrics,
)
from services.reporting.assistant.metric_resolvers import (
    ExtractedMetric,
    extract_metric_values,
)


def test_direct_application_risk_metric_uses_real_content_path():
    """直接指标应从 application_risk 的真实 metrics 路径读取。"""
    definition = get_metric_definition("application_risk", "high_risk_count")

    assert definition.value_path == ("metrics", "high_risk_count")
    assert definition.sensitive is True
    assert extract_metric_values(definition, {"metrics": {"high_risk_count": 3}}) == [
        ExtractedMetric(value=Decimal("3"), dimension={})
    ]


def test_signed_count_uses_whitelisted_derived_resolver():
    """签约数只允许固定漏斗阶段 resolver 派生。"""
    definition = get_metric_definition("sales_funnel", "signed_count")

    assert definition.extraction_mode == "derived"
    assert definition.resolver_name == "funnel_stage_count"
    assert extract_metric_values(definition, {"funnel_counts": {"signed": 4}}) == [
        ExtractedMetric(value=Decimal("4"), dimension={})
    ]


def test_stagnant_lead_count_uses_list_length():
    """停滞线索数应取真实 stalled_leads 列表长度。"""
    definition = get_metric_definition("sales_funnel", "stagnant_lead_count")

    assert extract_metric_values(
        definition, {"stalled_leads": [{"lead_id": 1}, {"lead_id": 2}]}
    ) == [ExtractedMetric(value=Decimal("2"), dimension={})]


def test_channel_roi_metrics_are_extracted_per_channel():
    """渠道指标必须逐渠道返回，不能压缩成报告级 ROI。"""
    definition = get_metric_definition("channel_roi", "roi")
    values = extract_metric_values(
        definition,
        {
            "channel_metrics": [
                {"channel": "search", "roi": -0.2},
                {"channel": "social", "roi": None},
            ]
        },
    )

    assert values == [
        ExtractedMetric(value=Decimal("-0.2"), dimension={"channel": "search"}),
        ExtractedMetric(value=None, dimension={"channel": "social"}),
    ]


def test_none_is_preserved_for_direct_metric():
    """报告中的未知值必须保留 None，不能静默改成零。"""
    definition = get_metric_definition("service_sla", "avg_first_response_hours")

    assert extract_metric_values(
        definition, {"sla_overview": {"avg_first_response_hours": None}}
    ) == [ExtractedMetric(value=None, dimension={})]


def test_unknown_metric_is_rejected_and_catalog_is_filtered():
    """未注册指标应失败关闭，列表接口只返回指定报告类型。"""
    with pytest.raises(ValueError, match="未注册指标"):
        get_metric_definition("sales_funnel", "invented")

    assert list_metrics("sales_funnel")
    assert all(item.report_type == "sales_funnel" for item in list_metrics("sales_funnel"))


def test_catalog_has_no_expression_or_dynamic_execution_mechanism():
    """安全边界应能通过源码审计确认不存在表达式执行和动态导入。"""
    assistant_dir = Path(__file__).parents[1] / "services" / "reporting" / "assistant"
    source = "\n".join(
        (assistant_dir / name).read_text(encoding="utf-8")
        for name in ("metric_catalog.py", "metric_resolvers.py")
    )

    forbidden_fragments = ("eval(", "exec(", "__import__(", "importlib")
    assert not any(fragment in source for fragment in forbidden_fragments)
