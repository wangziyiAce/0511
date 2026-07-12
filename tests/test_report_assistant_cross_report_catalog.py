"""验证跨报告白名单、权限预检和确定性工具预算。"""

import pytest

from services.reporting.assistant.cross_report_catalog import (
    CROSS_REPORT_CATALOG,
    get_cross_report_definition,
    validate_catalog_metric_bindings,
    validate_cross_report_request,
)


def test_allowed_pair_has_fixed_order_and_registered_metrics():
    """验证合法组合返回固定输出顺序，且所有绑定的指标均在 Task 2 目录中可查。

    测试目标：确认 channel_roi+sales_funnel 组合的 report_types 顺序、metric_bindings
    内容与目录一致，validate_catalog_metric_bindings 不抛异常。
    """
    definition = get_cross_report_definition("channel_roi", "sales_funnel")
    assert definition.report_types == ("channel_roi", "sales_funnel")
    assert definition.metric_bindings == {
        "channel_roi": ("leads", "signed_count", "paid_amount", "roi"),
        "sales_funnel": ("signed_count", "stagnant_lead_count"),
    }
    assert validate_catalog_metric_bindings() is None
    assert definition.output_sections == ("已确认事实", "相关信号", "可能解释", "无法确认")


def test_reverse_lookup_preserves_registered_output_order():
    """反向输入报告类型时，返回的定义仍保持注册时的固定输出顺序。"""
    definition = get_cross_report_definition("sales_funnel", "channel_roi")
    assert definition.report_types == ("channel_roi", "sales_funnel")


@pytest.mark.parametrize("left,right", [("psych_weekly", "channel_roi"), ("service_sla", "service_sla")])
def test_unknown_or_same_type_pair_is_rejected(left, right):
    """未注册组合或同类报告组合必须在查找阶段被拒绝，不得返回任何定义。"""
    with pytest.raises(ValueError, match="未开放|不能相同"):
        get_cross_report_definition(left, right)


@pytest.mark.parametrize("denied_report", ["channel_roi", "sales_funnel"])
def test_each_report_permission_is_checked_before_any_tool(denied_report):
    """任一报告权限不通过时，所有业务工具均不得执行，且不产生部分调用。"""
    calls: list[str] = []

    def permission_check(report_type: str) -> bool:
        return report_type != denied_report

    with pytest.raises(PermissionError, match="无权访问"):
        validate_cross_report_request(
            "channel_roi", "sales_funnel", role_code="admin",
            permission_check=permission_check,
            tool_calls=(lambda: calls.append("first"), lambda: calls.append("second")),
        )
    assert calls == []


def test_role_failure_is_fail_closed_without_partial_calls():
    """角色不满足定义要求时立即失败，不产生任何工具调用。"""
    calls: list[str] = []
    with pytest.raises(PermissionError, match="角色"):
        validate_cross_report_request(
            "channel_roi", "sales_funnel", role_code="employee",
            permission_check=lambda _: True,
            tool_calls=(lambda: calls.append("called"),),
        )
    assert calls == []


def test_sensitive_metric_requires_privileged_role_even_if_definition_is_modified():
    """含敏感指标的组合即使权限检查被绕过，角色不匹配时也必须失败关闭。"""
    definition = get_cross_report_definition("application_risk", "action_closure")
    assert definition.allowed_roles == ("admin", "manager")
    with pytest.raises(PermissionError):
        validate_cross_report_request(
            "application_risk", "action_closure", role_code="team_leader",
            permission_check=lambda _: True, tool_calls=(),
        )


def test_tool_limit_is_rejected_before_execution():
    """工具数量超出该组合上限时，在执行任何工具前即被拒绝。"""
    calls: list[str] = []
    with pytest.raises(ValueError, match="工具调用上限"):
        validate_cross_report_request(
            "channel_roi", "sales_funnel", role_code="admin",
            permission_check=lambda _: True,
            tool_calls=tuple(lambda: calls.append("called") for _ in range(3)),
        )
    assert calls == []


def test_only_four_pairs_are_registered_and_gaps_are_explicit():
    """确认仅四组合法组合注册，且无指标的报告在 unsupported_gaps 中明确标记。"""
    assert len(CROSS_REPORT_CATALOG) == 4
    definition = get_cross_report_definition("complaint_weekly", "service_sla")
    assert "complaint_weekly 尚无 Task 2 注册指标" in definition.unsupported_gaps


# ── 正向路径：全部权限通过时按顺序执行业务工具 ──
def test_successful_validation_executes_tools_in_order():
    """两份报告权限均通过时，按 tool_calls 顺序返回结果且无部分调用遗漏。"""
    call_log: list[str] = []

    def tool_a() -> str:
        call_log.append("a")
        return "result_a"

    def tool_b() -> str:
        call_log.append("b")
        return "result_b"

    results = validate_cross_report_request(
        "channel_roi", "sales_funnel", role_code="admin",
        permission_check=lambda _: True,
        tool_calls=(tool_a, tool_b),
    )
    # 调用顺序必须与传入顺序一致
    assert call_log == ["a", "b"]
    # 返回值按相同顺序打包
    assert results == ("result_a", "result_b")


# ── 空工具计划：允许不调用任何工具 ──
def test_empty_tool_plan_is_allowed():
    """0 个工具调用不触发预算或权限异常，返回空元组。"""
    results = validate_cross_report_request(
        "channel_roi", "sales_funnel", role_code="admin",
        permission_check=lambda _: True,
        tool_calls=(),
    )
    assert results == ()


# ── 工具执行顺序稳定性：多次相同输入产生相同输出顺序 ──
def test_tool_results_preserve_input_order():
    """无论工具内部耗时如何，结果元组顺序始终与 tool_calls 传入顺序一致。"""
    results = validate_cross_report_request(
        "channel_roi", "sales_funnel", role_code="admin",
        permission_check=lambda _: True,
        tool_calls=(
            lambda: "first",
            lambda: "second",
        ),
    )
    assert results == ("first", "second")


# ── 重复工具调用：允许传入相同函数多次 ──
def test_duplicate_tool_calls_are_executed_normally():
    """同一函数传入两次时各自独立调用，不因引用相同而跳过或合并。"""
    counter = {"value": 0}

    def increment() -> int:
        counter["value"] += 1
        return counter["value"]

    results = validate_cross_report_request(
        "channel_roi", "sales_funnel", role_code="admin",
        permission_check=lambda _: True,
        tool_calls=(increment, increment),
    )
    # 两次调用分别执行，返回各自结果
    assert results == (1, 2)
    assert counter["value"] == 2


# ── Catalog 不可变性：调用方不得修改定义中的 metric_bindings ──
def test_definition_metric_bindings_is_immutable_to_callers():
    """获取到的定义中 metric_bindings 为只读映射，写入操作必须在运行时失败。"""
    definition = get_cross_report_definition("channel_roi", "sales_funnel")
    with pytest.raises(TypeError):
        definition.metric_bindings["channel_roi"] = ("forged",)  # type: ignore[index]


# ── 隐私保护：权限失败时错误消息不泄露报告是否存在 ──
def test_permission_denial_message_does_not_leak_report_existence():
    """权限拒绝时只说明"无权访问"而不暴露被拒绝的报告列表或数据量。"""
    def permission_check(report_type: str) -> bool:
        return report_type == "channel_roi"  # sales_funnel 无权限

    with pytest.raises(PermissionError) as exc_info:
        validate_cross_report_request(
            "channel_roi", "sales_funnel", role_code="admin",
            permission_check=permission_check,
            tool_calls=(),
        )
    message = str(exc_info.value)
    # 不应在错误消息中列出具体被拒报告名
    assert "sales_funnel" not in message
    # 不应暴露数据量、行数等统计信息
    assert "条" not in message and "行" not in message and "count" not in message.lower()


# ── max_business_tool_calls 范围校验：构造期即阻止非法配置 ──
@pytest.mark.parametrize("bad_value", [0, 4, 100])
def test_max_business_tool_calls_must_be_between_1_and_3(bad_value: int):
    """无效的工具预算在定义构造阶段即被拒绝，不允许进入运行时。"""
    from services.reporting.assistant.cross_report_catalog import _definition

    with pytest.raises(ValueError, match="max_business_tool_calls"):
        _definition(
            ("application_risk", "action_closure"),
            ("admin", "manager"),
            {"application_risk": ("high_risk_count",)},
            max_business_tool_calls=bad_value,
        )


# ── 四组 Catalog 入口均显式声明 max_business_tool_calls ──
def test_every_catalog_entry_declares_explicit_tool_budget():
    """每个跨报告定义必须在 1-3 范围内显式声明工具预算，不得依赖默认值。"""
    for definition in CROSS_REPORT_CATALOG.values():
        assert 1 <= definition.max_business_tool_calls <= 3
    # 四组均应为审核过的值
    budgets = {
        frozenset(defn.report_types): defn.max_business_tool_calls
        for defn in CROSS_REPORT_CATALOG.values()
    }
    assert budgets[frozenset(("complaint_weekly", "service_sla"))] == 2
    assert budgets[frozenset(("sales_funnel", "customer_ops"))] == 2
    assert budgets[frozenset(("application_risk", "action_closure"))] == 2
    assert budgets[frozenset(("channel_roi", "sales_funnel"))] == 2
