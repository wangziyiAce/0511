"""智能报告助手的确定性比较周期解析器。

本模块位于报告助手业务层，上游由比较意图编排逻辑调用，下游输出
``ComparisonPeriod`` 给只读指标比较工具。它只识别明确白名单表达，不调用 LLM，
并统一阻止未来日期和周期重叠；现有单周期 ``period_resolver.py`` 行为不受影响。
"""

from __future__ import annotations

import calendar
import re
from datetime import date, datetime, timedelta
from typing import Sequence

from services.reporting.assistant.schemas import ComparisonPeriod


_EXPLICIT_MONTH_PATTERN = re.compile(r"(\d{4})年(1[0-2]|[1-9])月")


def resolve_comparison_period(
    message: str,
    *,
    now: datetime,
    current_report_period: Sequence[date] | None = None,
) -> ComparisonPeriod:
    """把白名单中的中文比较表达解析为两段确定日期。

    Args:
        message: 用户原始问题，用于识别自然周、月累计、滚动窗口或明确月份。
        now: 固定参考时间；生产环境传当前时间，测试传固定时间保证可复现。
        current_report_period: 当前报告的 ``(开始日期, 结束日期)``，仅在用户要求
            “当前报告和上一期”时使用。

    Returns:
        两个带标签的非重叠周期，以及解释隐含口径的 assumptions。

    Raises:
        ValueError: 表达不在白名单、报告周期缺失或非法、周期包含未来日期或重叠。
    """
    today = now.date()
    normalized = "".join(message.split())
    rolling_match = re.search(r"最近(7|30)天(?:和|与|对比)前(?:面)?\1天", normalized)
    explicit_months = _EXPLICIT_MONTH_PATTERN.findall(normalized)

    # 先识别所有受支持周期族，再进入具体分支。这样结果不会由 if/elif 的先后顺序决定。
    period_families = [
        "current_report" if any(keyword in normalized for keyword in ("当前报告", "上一期", "前一期")) else None,
        "natural_week" if any(keyword in normalized for keyword in ("本周", "上周")) else None,
        "month_to_date" if any(keyword in normalized for keyword in ("本月", "上月")) else None,
        "rolling" if rolling_match else None,
        "explicit_months" if len(explicit_months) == 2 else None,
    ]
    if sum(family is not None for family in period_families) > 1:
        raise ValueError("不支持同时包含多个周期意图的比较请求")

    if "当前报告" in normalized and ("上一期" in normalized or "前一期" in normalized):
        period = _resolve_current_report(current_report_period)
    elif "本周" in normalized and "上周" in normalized:
        period = _resolve_completed_natural_weeks(today)
    elif "本月" in normalized and "上月" in normalized:
        period = _resolve_month_to_date(today)
    elif rolling_match:
        period = _resolve_rolling_days(today, int(rolling_match.group(1)))
    else:
        if len(explicit_months) == 2 and any(word in normalized for word in ("比较", "对比", "和", "与")):
            period = _resolve_explicit_months(explicit_months)
        else:
            raise ValueError("不支持的比较周期表达，请明确使用自然周、月份或最近 7/30 天")

    _validate_period_pair(period, today)
    return period


def _resolve_completed_natural_weeks(today: date) -> ComparisonPeriod:
    """返回今天之前最近两个完整自然周，避免当前未结束周包含未来日期。"""
    this_monday = today - timedelta(days=today.weekday())
    current_end = this_monday - timedelta(days=1)
    current_start = current_end - timedelta(days=6)
    return ComparisonPeriod(
        current_start=current_start,
        current_end=current_end,
        previous_start=current_start - timedelta(days=7),
        previous_end=current_start - timedelta(days=1),
        current_label="本周（最近完整自然周）",
        previous_label="上周",
        assumptions=["自然周按周一至周日计算；当前周未结束，因此使用最近完整自然周"],
    )


def _resolve_month_to_date(today: date) -> ComparisonPeriod:
    """返回本月累计与上月相同已过天数，保证比较口径一致。"""
    current_start = today.replace(day=1)
    previous_end_of_month = current_start - timedelta(days=1)
    elapsed_day = min(today.day, previous_end_of_month.day)
    previous_start = previous_end_of_month.replace(day=1)
    previous_end = previous_start.replace(day=elapsed_day)
    return ComparisonPeriod(
        current_start=current_start,
        current_end=today,
        previous_start=previous_start,
        previous_end=previous_end,
        current_label="本月截至今日",
        previous_label="上月同期",
        assumptions=["本月按截至今日的已过天数计算；上月取相同日序，短月按月末截断"],
    )


def _resolve_rolling_days(today: date, days: int) -> ComparisonPeriod:
    """返回包含今天的滚动窗口及紧邻的前一等长窗口。"""
    current_start = today - timedelta(days=days - 1)
    previous_end = current_start - timedelta(days=1)
    return ComparisonPeriod(
        current_start=current_start,
        current_end=today,
        previous_start=previous_end - timedelta(days=days - 1),
        previous_end=previous_end,
        current_label=f"最近{days}天",
        previous_label=f"前{days}天",
        assumptions=[f"最近{days}天包含今天；前一周期紧邻且不重叠"],
    )


def _resolve_explicit_months(months: list[tuple[str, str]]) -> ComparisonPeriod:
    """解析两个完整公历月，并固定把较晚月份分配为当前比较期。"""
    ordered_months = sorted(months, key=lambda item: (int(item[0]), int(item[1])), reverse=True)
    ranges = [_calendar_month(int(year), int(month)) for year, month in ordered_months]
    return ComparisonPeriod(
        current_start=ranges[0][0],
        current_end=ranges[0][1],
        previous_start=ranges[1][0],
        previous_end=ranges[1][1],
        current_label=f"{ordered_months[0][0]}年{int(ordered_months[0][1])}月",
        previous_label=f"{ordered_months[1][0]}年{int(ordered_months[1][1])}月",
        assumptions=["明确月份按完整公历月计算；较晚月份作为当前期，允许两个月份天数不同"],
    )


def _calendar_month(year: int, month: int) -> tuple[date, date]:
    """计算指定公历月的首日和末日。"""
    return date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])


def _resolve_current_report(current_report_period: Sequence[date] | None) -> ComparisonPeriod:
    """把当前报告周期按其包含天数整体向前平移，生成上一等长周期。"""
    if current_report_period is None or len(current_report_period) != 2:
        raise ValueError("比较当前报告时必须提供当前报告周期")
    current_start, current_end = current_report_period
    if current_start > current_end:
        raise ValueError("当前报告周期开始日期不能晚于结束日期")
    period_days = (current_end - current_start).days + 1
    previous_end = current_start - timedelta(days=1)
    return ComparisonPeriod(
        current_start=current_start,
        current_end=current_end,
        previous_start=previous_end - timedelta(days=period_days - 1),
        previous_end=previous_end,
        current_label="当前报告周期",
        previous_label="上一等长周期",
        assumptions=["上一期按当前报告包含天数向前平移，两个周期紧邻且不重叠"],
    )


def _validate_period_pair(period: ComparisonPeriod, today: date) -> None:
    """统一校验日期顺序、未来日期和非预期重叠，避免下游取错数据。"""
    if period.current_start > period.current_end or period.previous_start > period.previous_end:
        raise ValueError("比较周期开始日期不能晚于结束日期")
    if period.current_end > today or period.previous_end > today:
        raise ValueError("比较周期不能包含未来日期")
    if period.previous_end >= period.current_start:
        raise ValueError("比较周期不能重叠，且前一周期必须早于当前周期")
