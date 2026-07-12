"""报告指标安全提取器。

本模块位于智能报告助手的指标提取层，上游由比较工具传入服务端注册的
``MetricDefinition``，下游只读取已经生成的报告 content。所有提取方式都通过固定
字典分发，不接受前端或 LLM 提供的路径、表达式和函数名；缺失值保留为 ``None``，
便于后续比较层正确应用 DataQuality 和零分母规则。
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from services.reporting.assistant.metric_catalog import MetricDefinition


@dataclass(frozen=True)
class ExtractedMetric:
    """表示从一份报告中提取出的单个指标值。

    ``value`` 使用 Decimal 保证比较计算精度，源值缺失时保持 None；``dimension``
    标识渠道等分组，直接指标和派生汇总指标使用空字典。
    """

    value: Decimal | None
    dimension: dict[str, str]


def _to_decimal(value: Any) -> Decimal | None:
    """把受控报告数值转换为 Decimal，且保留 None。

    非数值内容说明报告契约已经漂移，函数会明确报错，避免把坏数据当成零继续比较。
    """
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError("指标值不能是布尔值")
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"指标值不是有效数值: {value!r}") from exc


def _read_path(content: dict[str, Any], path: tuple[str, ...]) -> Any:
    """沿 Catalog 已注册的固定路径读取 content；任一层缺失时返回 None。"""
    current: Any = content
    for key in path:
        if not isinstance(current, dict) or key not in current:
            return None
        current = current[key]
    return current


def resolve_direct_path(
    definition: MetricDefinition, content: dict[str, Any]
) -> list[ExtractedMetric]:
    """提取固定直接路径，供 metrics 和 sla_overview 等真实字段使用。"""
    if definition.value_path is None:
        raise ValueError("直接指标缺少 value_path")
    return [ExtractedMetric(value=_to_decimal(_read_path(content, definition.value_path)), dimension={})]


def resolve_funnel_stage_count(
    definition: MetricDefinition, content: dict[str, Any]
) -> list[ExtractedMetric]:
    """从固定 funnel_counts 字段提取 Catalog 指定阶段的数量。"""
    if definition.value_path is None:
        raise ValueError("漏斗阶段指标缺少 value_path")
    return [ExtractedMetric(value=_to_decimal(_read_path(content, definition.value_path)), dimension={})]


def resolve_list_length(
    definition: MetricDefinition, content: dict[str, Any]
) -> list[ExtractedMetric]:
    """计算固定来源列表长度；字段缺失保留 None，类型错误则明确失败。"""
    if not definition.source_fields:
        raise ValueError("列表长度指标缺少 source_fields")
    items = _read_path(content, definition.source_fields[0])
    if items is None:
        value = None
    elif isinstance(items, list):
        value = Decimal(len(items))
    else:
        raise ValueError("列表长度指标的来源字段不是列表")
    return [ExtractedMetric(value=value, dimension={})]


def resolve_dimension_list_value(
    definition: MetricDefinition, content: dict[str, Any]
) -> list[ExtractedMetric]:
    """从固定列表逐维度提取数值，确保渠道 ROI 不被错误汇总。"""
    if definition.value_path is None or not definition.dimension_key or not definition.dimension_name:
        raise ValueError("维度指标定义不完整")
    list_path, value_key = definition.value_path[:-1], definition.value_path[-1]
    items = _read_path(content, list_path)
    if items is None:
        return []
    if not isinstance(items, list):
        raise ValueError("维度指标的来源字段不是列表")

    extracted: list[ExtractedMetric] = []
    for item in items:
        if not isinstance(item, dict) or definition.dimension_key not in item:
            raise ValueError("维度指标条目缺少维度字段")
        extracted.append(
            ExtractedMetric(
                value=_to_decimal(item.get(value_key)),
                dimension={definition.dimension_name: str(item[definition.dimension_key])},
            )
        )
    return extracted


Resolver = Callable[["MetricDefinition", dict[str, Any]], list[ExtractedMetric]]

# 固定分发表是安全边界：resolver 名只能来自服务端 Catalog，不能由请求动态扩展。
RESOLVERS: dict[str, Resolver] = {
    "direct_path": resolve_direct_path,
    "funnel_stage_count": resolve_funnel_stage_count,
    "list_length": resolve_list_length,
    "dimension_list_value": resolve_dimension_list_value,
}


def extract_metric_values(
    definition: MetricDefinition, content: dict[str, Any]
) -> list[ExtractedMetric]:
    """使用固定白名单 resolver 提取指标，未知 resolver 立即拒绝。"""
    resolver = RESOLVERS.get(definition.resolver_name or "")
    if resolver is None:
        raise ValueError(f"未注册 resolver: {definition.resolver_name}")
    return resolver(definition, content)
