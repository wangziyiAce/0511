"""报告助手比较周期解析测试。

本文件用固定 ``now`` 验证自然周、月累计、滚动窗口、明确自然月和当前报告周期。
断言同时覆盖不重叠、不包含未来日期，以及解析假设可回传给前端。
"""

from datetime import date, datetime

import pytest

from services.reporting.assistant.comparison_period import resolve_comparison_period


NOW = datetime(2026, 7, 15, 10, 0)


def test_this_week_vs_last_week_uses_full_natural_weeks() -> None:
    """“本周和上周”应比较最近两个已完成的周一至周日自然周。"""
    period = resolve_comparison_period("本周和上周", now=NOW)

    assert (period.current_start, period.current_end) == (date(2026, 7, 6), date(2026, 7, 12))
    assert (period.previous_start, period.previous_end) == (date(2026, 6, 29), date(2026, 7, 5))
    assert period.assumptions


def test_this_month_uses_equal_elapsed_days() -> None:
    """本月累计应与上月相同已过天数比较，而不是与完整上月比较。"""
    period = resolve_comparison_period("本月和上月", now=NOW)

    assert (period.current_start, period.current_end) == (date(2026, 7, 1), date(2026, 7, 15))
    assert (period.previous_start, period.previous_end) == (date(2026, 6, 1), date(2026, 6, 15))


@pytest.mark.parametrize(
    ("message", "days", "current_start", "previous_start"),
    [
        ("最近7天和前7天", 7, date(2026, 7, 9), date(2026, 7, 2)),
        ("最近30天和前30天", 30, date(2026, 6, 16), date(2026, 5, 17)),
    ],
)
def test_rolling_periods_are_equal_and_non_overlapping(
    message: str, days: int, current_start: date, previous_start: date
) -> None:
    """滚动窗口包含今天，前一窗口应等长、紧邻且不重叠。"""
    period = resolve_comparison_period(message, now=NOW)

    assert period.current_start == current_start
    assert period.current_end == date(2026, 7, 15)
    assert period.previous_start == previous_start
    assert (period.current_end - period.current_start).days + 1 == days
    assert period.previous_end < period.current_start


def test_explicit_chinese_months_use_complete_calendar_months() -> None:
    """明确写出的中文月份应按各自完整自然月解析，允许月份天数不同。"""
    period = resolve_comparison_period("比较2026年5月和2026年4月", now=NOW)

    assert (period.current_start, period.current_end) == (date(2026, 5, 1), date(2026, 5, 31))
    assert (period.previous_start, period.previous_end) == (date(2026, 4, 1), date(2026, 4, 30))


def test_explicit_chinese_months_assign_later_month_as_current_regardless_of_order() -> None:
    """用户先说较早月份时，解析器仍应按时间顺序分配当前期和前一期。"""
    period = resolve_comparison_period("比较2026年4月和2026年5月", now=NOW)

    assert (period.current_start, period.current_end) == (date(2026, 5, 1), date(2026, 5, 31))
    assert (period.previous_start, period.previous_end) == (date(2026, 4, 1), date(2026, 4, 30))


def test_current_report_uses_preceding_equal_length_period() -> None:
    """当前报告周期应整体向前平移相同天数，供已有报告详情页发起比较。"""
    period = resolve_comparison_period(
        "当前报告和上一期",
        now=NOW,
        current_report_period=(date(2026, 7, 8), date(2026, 7, 14)),
    )

    assert (period.current_start, period.current_end) == (date(2026, 7, 8), date(2026, 7, 14))
    assert (period.previous_start, period.previous_end) == (date(2026, 7, 1), date(2026, 7, 7))


def test_future_explicit_month_is_rejected() -> None:
    """用户未明确要求预测时，比较周期不能包含未来日期。"""
    with pytest.raises(ValueError, match="未来"):
        resolve_comparison_period("比较2026年8月和2026年7月", now=NOW)


def test_unsupported_or_overlapping_request_is_rejected() -> None:
    """非白名单表达不能被猜测成可能重叠的比较周期。"""
    with pytest.raises(ValueError, match="不支持"):
        resolve_comparison_period("最近7天和本周", now=NOW)


def test_rolling_period_with_extra_period_intent_is_rejected() -> None:
    """匹配滚动窗口后仍有额外周期意图时必须拒绝，不能静默忽略歧义文本。"""
    with pytest.raises(ValueError, match="不支持"):
        resolve_comparison_period("最近7天和前7天再加本周", now=NOW)


@pytest.mark.parametrize(
    ("message", "current_report_period"),
    [
        ("本周和上周以及本月和上月", None),
        ("当前报告和上一期以及本月和上月", (date(2026, 7, 8), date(2026, 7, 14))),
    ],
)
def test_multiple_supported_period_families_are_rejected(
    message: str, current_report_period: tuple[date, date] | None
) -> None:
    """任意两个已支持周期族同时出现时都必须失败关闭，不能由分支顺序决定结果。"""
    with pytest.raises(ValueError, match="多个周期意图"):
        resolve_comparison_period(message, now=NOW, current_report_period=current_report_period)
