"""智能报告助手的声明式指标目录。

本模块位于报告 content 与比较服务之间，只登记当前聚合器能够稳定产出的指标路径、
类型、单位、质量规则和敏感性。上游比较工具只能按 ``report_type + metric_name`` 查询，
下游安全提取器按固定 resolver 读取；这里不保存可执行表达式，也不允许请求动态注册。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class MetricDefinition:
    """声明一个可比较指标及其安全提取契约。

    路径和 resolver 均由服务端维护；None、零分母、DataQuality 与敏感标记供后续比较、
    权限和 Evidence 层使用，避免各层自行猜测业务口径。
    """

    report_type: str
    metric_name: str
    label: str
    extraction_mode: Literal["direct", "derived", "dimensional"]
    value_path: tuple[str, ...] | None
    source_fields: tuple[tuple[str, ...], ...]
    resolver_name: str | None
    dimension_name: str | None
    dimension_key: str | None
    value_type: Literal["integer", "decimal", "percentage", "duration", "currency"]
    unit: str | None
    allow_delta: bool
    allow_change_rate: bool
    sensitive: bool
    none_semantics: str
    zero_denominator_rule: Literal["not_applicable", "return_none"]
    data_quality_rule: Literal["inherit", "warning_on_missing"]


def _direct(report_type: str, metric_name: str, label: str, root: str, **metadata: object) -> MetricDefinition:
    """生成固定直接路径定义，减少重复元数据但不开放动态注册。"""
    return MetricDefinition(
        report_type=report_type, metric_name=metric_name, label=label,
        extraction_mode="direct", value_path=(root, metric_name),
        source_fields=((root, metric_name),), resolver_name="direct_path",
        dimension_name=None, dimension_key=None,
        value_type=metadata.get("value_type", "integer"), unit=metadata.get("unit", "个"),
        allow_delta=True, allow_change_rate=True,
        sensitive=bool(metadata.get("sensitive", False)),
        none_semantics="源字段未知或缺失，不得转换为 0",
        zero_denominator_rule="return_none",
        data_quality_rule="warning_on_missing",
    )


_definitions = [
    *[
        _direct("application_risk", name, label, "metrics", sensitive=True)
        for name, label in (
            ("total_applications", "申请总数"), ("high_risk_count", "高风险申请数"),
            ("medium_risk_count", "中风险申请数"), ("low_risk_count", "低风险申请数"),
            ("overdue_count", "逾期申请数"), ("missing_material_count", "缺失材料申请数"),
        )
    ],
    MetricDefinition(
        report_type="sales_funnel", metric_name="signed_count", label="签约数",
        extraction_mode="derived", value_path=("funnel_counts", "signed"),
        source_fields=(("funnel_counts", "signed"),), resolver_name="funnel_stage_count",
        dimension_name=None, dimension_key=None, value_type="integer", unit="条",
        allow_delta=True, allow_change_rate=True, sensitive=False,
        none_semantics="漏斗阶段缺失表示未知，不得转换为 0",
        zero_denominator_rule="return_none", data_quality_rule="warning_on_missing",
    ),
    MetricDefinition(
        report_type="sales_funnel", metric_name="stagnant_lead_count", label="停滞线索数",
        extraction_mode="derived", value_path=None,
        source_fields=(("stalled_leads",),), resolver_name="list_length",
        dimension_name=None, dimension_key=None, value_type="integer", unit="条",
        allow_delta=True, allow_change_rate=True, sensitive=False,
        none_semantics="列表字段缺失表示未知；真实空列表才表示 0",
        zero_denominator_rule="return_none", data_quality_rule="warning_on_missing",
    ),
    *[
        MetricDefinition(
            report_type="channel_roi", metric_name=name, label=label,
            extraction_mode="dimensional", value_path=("channel_metrics", name),
            source_fields=(("channel_metrics", "channel"), ("channel_metrics", name)),
            resolver_name="dimension_list_value", dimension_name="channel", dimension_key="channel",
            value_type=value_type, unit=unit, allow_delta=True, allow_change_rate=True,
            sensitive=True, none_semantics="该渠道指标不可计算或缺失时保持 None",
            zero_denominator_rule="return_none", data_quality_rule="warning_on_missing",
        )
        for name, label, value_type, unit in (
            ("leads", "线索数", "integer", "条"), ("signed_count", "签约数", "integer", "个"),
            ("cost", "渠道成本", "currency", "元"), ("contract_amount", "合同金额", "currency", "元"),
            ("paid_amount", "回款金额", "currency", "元"), ("cpl", "单条线索成本", "currency", "元"),
            ("cac", "获客成本", "currency", "元"), ("roi", "投入产出率", "percentage", "%"),
        )
    ],
    *[
        _direct("service_sla", name, label, "sla_overview", value_type=value_type, unit=unit, sensitive=True)
        for name, label, value_type, unit in (
            ("total_complaints", "投诉总数", "integer", "件"),
            ("complaint_response_overdue_count", "首次响应超时数", "integer", "件"),
            ("complaint_resolve_overdue_count", "解决超时数", "integer", "件"),
            ("avg_first_response_hours", "平均首次响应时长", "duration", "小时"),
            ("psych_alert_count", "心理预警数", "integer", "条"),
            ("psych_high_risk_follow_overdue_count", "高风险心理跟进超时数", "integer", "条"),
        )
    ],
]

# 显式二元键保证调用者只能选择服务端审核过的报告与指标组合。
METRIC_CATALOG: dict[tuple[str, str], MetricDefinition] = {
    (item.report_type, item.metric_name): item for item in _definitions
}


def get_metric_definition(report_type: str, metric_name: str) -> MetricDefinition:
    """按报告类型和指标名返回定义；未知组合失败关闭。"""
    try:
        return METRIC_CATALOG[(report_type, metric_name)]
    except KeyError as exc:
        raise ValueError(f"未注册指标: {report_type}.{metric_name}") from exc


def list_metrics(report_type: str | None = None) -> list[MetricDefinition]:
    """列出全部或指定报告类型的稳定指标，按键排序以保证结果可复现。"""
    items = (
        item for (registered_type, _), item in METRIC_CATALOG.items()
        if report_type is None or registered_type == report_type
    )
    return sorted(items, key=lambda item: (item.report_type, item.metric_name))
