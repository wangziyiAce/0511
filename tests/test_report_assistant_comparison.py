"""验证指标对比的 Decimal 计算规则与双周期数据质量门禁。"""

from decimal import Decimal

import pytest

from services.reporting.assistant.comparison import (
    calculate_values,
    evaluate_comparison_quality,
)


@pytest.mark.parametrize("current,previous", [(None, Decimal("1")), (Decimal("1"), None)])
def test_none_value_does_not_become_zero(current, previous):
    """任一期缺失时不应虚构差值、变化率或趋势方向。"""
    result = calculate_values(current, previous, value_type="integer")
    assert (result.delta, result.change_rate, result.direction) == (None, None, "unknown")


def test_previous_zero_returns_delta_without_rate():
    """零分母仍可展示差值，但不能计算变化率。"""
    result = calculate_values(Decimal("5"), Decimal("0"), value_type="integer")
    assert result.delta == Decimal("5")
    assert result.change_rate is None
    assert result.direction == "up"


def test_percentage_uses_percentage_point_delta_and_relative_rate():
    """百分比差值保持比例小数，代表百分点差；变化率仍为相对变化。"""
    result = calculate_values(Decimal("0.30"), Decimal("0.20"), value_type="percentage")
    assert result.delta == Decimal("0.10")
    assert result.change_rate == Decimal("0.5")


def test_negative_previous_uses_absolute_denominator():
    """负 ROI 的变化率分母取绝对值，避免方向被负号反转。"""
    result = calculate_values(Decimal("-0.10"), Decimal("-0.20"), value_type="decimal")
    assert result.delta == Decimal("0.10")
    assert result.change_rate == Decimal("0.5")
    assert result.direction == "up"


def test_decimal_precision_is_not_converted_through_float():
    """高精度输入必须保持 Decimal 的确定性精度。"""
    result = calculate_values(Decimal("0.3000000000000000001"), Decimal("0.2"), value_type="decimal")
    assert result.delta == Decimal("0.1000000000000000001")


def test_warning_retains_comparison_with_independent_quality():
    """单期 warning 不覆盖另一周期，并允许带限制地继续比较。"""
    current = {"level": "warning", "warnings": ["部分来源缺失"]}
    previous = {"level": "ok", "warnings": []}
    gate = evaluate_comparison_quality(current, previous)
    assert gate.current_quality == current
    assert gate.previous_quality == previous
    assert gate.allow_values is True
    assert gate.allow_trend is True
    assert gate.limited_trend is True
    assert gate.warnings


@pytest.mark.parametrize("blocked_level", ["empty", "failed"])
def test_empty_or_failed_blocks_trend(blocked_level):
    """任一期为空或失败时仅保留原值入口，不输出趋势。"""
    gate = evaluate_comparison_quality({"level": blocked_level}, {"level": "ok"})
    assert gate.allow_values is True
    assert gate.allow_trend is False
    assert gate.limited_trend is False
    blocked = gate.apply(calculate_values(Decimal("5"), Decimal("3"), value_type="integer"))
    assert (blocked.delta, blocked.change_rate, blocked.direction) == (None, None, "unknown")


def test_degraded_allows_only_limited_trend():
    """degraded 可展示原值及有限趋势，但必须携带限制标记。"""
    gate = evaluate_comparison_quality({"level": "ok"}, {"level": "degraded"})
    assert gate.allow_values is True
    assert gate.allow_trend is True
    assert gate.limited_trend is True


def test_explicit_incompatibility_rejects_comparison():
    """Schema、指标定义或周期口径不兼容时必须显式拒绝。"""
    with pytest.raises(ValueError, match="不兼容"):
        evaluate_comparison_quality({"level": "ok"}, {"level": "ok"}, compatible=False)


def test_unknown_quality_level_fails_closed():
    """未知质量等级不能被误判为正常数据。"""
    with pytest.raises(ValueError, match="数据质量等级"):
        evaluate_comparison_quality({"level": "invented"}, {"level": "ok"})
