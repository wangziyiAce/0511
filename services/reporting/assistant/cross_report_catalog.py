"""声明受控跨报告分析白名单并在业务读取前完成安全预检。

本文件位于报告助手业务层，供后续 Service 在组合两类报告前查询固定定义。
它只依赖 Task 2 的指标目录，不执行 LLM 决策，也不开放动态指标、递归工具调用。
核心入口是 ``get_cross_report_definition`` 和 ``validate_cross_report_request``；
后者先完成角色、逐报告权限和调用预算检查，全部通过后才执行调用方给出的业务工具。
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Callable, Mapping, TypeVar

from services.reporting.assistant.metric_catalog import METRIC_CATALOG


_T = TypeVar("_T")
_FORBIDDEN_CLAIMS = ("导致", "证明", "必然", "根本原因是", "就是因为")
_OUTPUT_SECTIONS = ("已确认事实", "相关信号", "可能解释", "无法确认")
_PERIOD_MODES = ("same_period", "current_previous")


@dataclass(frozen=True)
class CrossReportDefinition:
    """表示一组服务端审核通过的跨报告分析契约。

    ``report_types`` 固定取数和输出顺序；``metric_bindings`` 只能引用 Task 2 目录。
    ``unsupported_gaps`` 明示尚无可靠指标的报告，避免用相似字段猜测或伪造结论。
    该对象不写库、不调用外部服务，冻结后可安全地作为全局只读配置复用。
    """

    report_types: tuple[str, str]
    allowed_roles: tuple[str, ...]
    metric_bindings: Mapping[str, tuple[str, ...]]
    allowed_period_modes: tuple[str, ...]
    max_business_tool_calls: int
    forbidden_claims: tuple[str, ...]
    output_sections: tuple[str, ...]
    unsupported_gaps: tuple[str, ...] = ()


def _definition(
    report_types: tuple[str, str],
    allowed_roles: tuple[str, ...],
    metric_bindings: dict[str, tuple[str, ...]],
    *,
    max_business_tool_calls: int = 2,
    unsupported_gaps: tuple[str, ...] = (),
) -> CrossReportDefinition:
    """构造只读定义，统一周期、因果保护、四段输出，并按组合控制工具预算。

    各组合必须显式声明 ``max_business_tool_calls`` 以体现审核结论；
    全局上限由 ``validate_cross_report_request`` 与 plan 约束共同保证，不在本函数内硬编码。
    """
    if max_business_tool_calls < 1 or max_business_tool_calls > 3:
        raise ValueError(f"max_business_tool_calls 必须在 1-3 之间，收到 {max_business_tool_calls}")
    return CrossReportDefinition(
        report_types=report_types,
        allowed_roles=allowed_roles,
        metric_bindings=MappingProxyType(metric_bindings),
        allowed_period_modes=_PERIOD_MODES,
        max_business_tool_calls=max_business_tool_calls,
        forbidden_claims=_FORBIDDEN_CLAIMS,
        output_sections=_OUTPUT_SECTIONS,
        unsupported_gaps=unsupported_gaps,
    )


# 无序键负责双向查找；定义中的 report_types 仍保留审核通过的固定输出顺序。
CROSS_REPORT_CATALOG: dict[frozenset[str], CrossReportDefinition] = {
    frozenset(("complaint_weekly", "service_sla")): _definition(
        ("complaint_weekly", "service_sla"), ("admin", "manager"),
        {"service_sla": ("total_complaints", "complaint_response_overdue_count", "complaint_resolve_overdue_count")},
        unsupported_gaps=("complaint_weekly 尚无 Task 2 注册指标",),
    ),
    frozenset(("sales_funnel", "customer_ops")): _definition(
        ("sales_funnel", "customer_ops"), ("admin", "manager", "team_leader", "employee"),
        {"sales_funnel": ("signed_count", "stagnant_lead_count")},
        unsupported_gaps=("customer_ops 尚无 Task 2 注册指标",),
    ),
    frozenset(("application_risk", "action_closure")): _definition(
        ("application_risk", "action_closure"), ("admin", "manager"),
        {"application_risk": ("high_risk_count", "overdue_count", "missing_material_count")},
        unsupported_gaps=("action_closure 尚无 Task 2 注册指标",),
    ),
    frozenset(("channel_roi", "sales_funnel")): _definition(
        ("channel_roi", "sales_funnel"), ("admin", "manager"),
        {
            "channel_roi": ("leads", "signed_count", "paid_amount", "roi"),
            "sales_funnel": ("signed_count", "stagnant_lead_count"),
        },
    ),
}


def validate_catalog_metric_bindings() -> None:
    """校验所有指标均来自 Task 2 目录；未知绑定立即阻止模块继续工作。"""
    for definition in CROSS_REPORT_CATALOG.values():
        for report_type, metric_names in definition.metric_bindings.items():
            for metric_name in metric_names:
                if (report_type, metric_name) not in METRIC_CATALOG:
                    raise RuntimeError(f"跨报告指标未在 Task 2 注册：{report_type}.{metric_name}")


def get_cross_report_definition(left_report_type: str, right_report_type: str) -> CrossReportDefinition:
    """按无序报告对查找定义；同类或未开放组合均失败关闭。"""
    if left_report_type == right_report_type:
        raise ValueError("跨报告类型不能相同")
    try:
        return CROSS_REPORT_CATALOG[frozenset((left_report_type, right_report_type))]
    except KeyError as exc:
        raise ValueError(f"跨报告组合未开放：{left_report_type} + {right_report_type}") from exc


def validate_cross_report_request(
    left_report_type: str,
    right_report_type: str,
    *,
    role_code: str,
    permission_check: Callable[[str], bool],
    tool_calls: tuple[Callable[[], _T], ...],
) -> tuple[_T, ...]:
    """预检整个请求后按固定列表执行工具，不允许 LLM 临时追加或递归选择。

    任一角色、报告权限或预算检查失败时，函数在首次业务调用前抛出异常，因此不会泄露
    部分数据。成功时返回与 ``tool_calls`` 相同顺序的结果，供后续四段回答组合使用。
    """
    definition = get_cross_report_definition(left_report_type, right_report_type)
    if role_code not in definition.allowed_roles:
        raise PermissionError("当前角色无权执行该跨报告分析")
    if len(tool_calls) > definition.max_business_tool_calls:
        raise ValueError(f"超过业务工具调用上限 {definition.max_business_tool_calls}")

    # 必须先检查两份报告，再读取其中任何一份；否则第二份拒绝时会留下第一份部分数据。
    denied = [report_type for report_type in definition.report_types if not permission_check(report_type)]
    if denied:
        raise PermissionError("无权访问跨报告分析所需的全部报告")

    return tuple(tool_call() for tool_call in tool_calls)


# 导入时即检查静态白名单，防止配置修改后直到真实请求才暴露错误。
validate_catalog_metric_bindings()
