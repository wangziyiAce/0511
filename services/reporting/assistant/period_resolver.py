"""智能报告助手 — 确定性时间解析。

本模块把自然语言中的相对时间表达（"上周"、"本月"、"最近7天"）转换成具体
的起止日期。所有计算基于固定的 ``now`` 参数，保证测试可重现。

职责：
- 接收 relative_period（LLM 提取的相对时间关键词）或显式 period_start/period_end
- 返回包含具体日期、计算来源和假设说明的 ``ResolvedPeriod``

不负责：
- 理解"春节前"、"Q4" 等需推理的复杂时间表达（不在 Iteration 1 范围内）
- 时区转换（默认使用服务端本地时间）

设计原则：
1. 相对时间表达严格白名单，不支持的直接报错
2. 模糊表达（"现在"、"最近"）使用报告注册表的 default_period_rule
3. 显式日期优先于相对时间
4. 所有计算使用固定 now，便于测试

面试表达：
"我没有把时间解析交给 LLM 自由发挥，因为 LLM 可能把'本周'理解成周日开始。
我用了确定性 Python 函数，根据已知的 now 和白名单关键词计算具体日期范围，
并且对模糊表达使用报告注册表中预定义的默认周期。"
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Literal, Optional

from services.reporting.registry import ReportDefinition


# ---------------------------------------------------------------------------
# 绝对日期 → 相对关键词映射表
# Iteration 1 支持的关键词
# ---------------------------------------------------------------------------

PERIOD_KEYWORD_MAP: dict[str, str] = {
    # 精确日期
    "today": "today",
    "yesterday": "yesterday",
    # 周
    "this_week": "this_week",
    "last_week": "last_week",
    # 月
    "this_month": "this_month",
    "last_month": "last_month",
    # 天数
    "last_7_days": "last_7_days",
    "last_30_days": "last_30_days",
    # 模糊表达 → 使用报告默认周期
    "now": "default",
    "current": "default",
    "recent": "default",
}


# ---------------------------------------------------------------------------
# 解析结果
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ResolvedPeriod:
    """时间解析结果。

    Attributes:
        start: 统计周期开始日期。
        end: 统计周期结束日期。
        source: 周期来源 — explicit（用户显式指定）/ relative（相对关键词）/
                default（使用报告默认周期）。
        assumptions: 解析过程中所做的假设，用于前端展示和用户确认。
    """

    start: date
    end: date
    source: Literal["explicit", "relative", "default"] = "relative"
    assumptions: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# 公开接口
# ---------------------------------------------------------------------------


def resolve_assistant_period(
    *,
    relative_period: str | None,
    period_start: date | None,
    period_end: date | None,
    report_definition: ReportDefinition,
    now: datetime,
) -> ResolvedPeriod:
    """把 LLM 提取的相对时间关键词解析为具体起止日期。

    处理优先级：
    1. 显式起止日期（period_start + period_end）→ 直接使用
    2. 已知相对关键词（today/yesterday/this_week/last_week 等）→ 计算
    3. 模糊关键词（now/current/recent）→ 使用报告 default_period_rule
    4. 无关键词 → 使用报告 default_period_rule

    Args:
        relative_period: LLM 从自然语言中提取的相对时间关键词。
        period_start: 显式指定的开始日期。
        period_end: 显式指定的结束日期。
        report_definition: 报告类型定义，用于获取默认周期规则。
        now: 参考时间点（测试中固定，生产中传 datetime.now()）。

    Returns:
        ResolvedPeriod，包含具体起止日期、来源和假设。

    Raises:
        ValueError: relative_period 不在白名单中，或 period_start > period_end。
    """
    # 1) 显式日期优先
    if period_start is not None and period_end is not None:
        if period_start > period_end:
            raise ValueError(f"开始日期 {period_start} 不能晚于结束日期 {period_end}")
        return ResolvedPeriod(
            start=period_start,
            end=period_end,
            source="explicit",
            assumptions=[f"使用指定周期：{period_start} ~ {period_end}"],
        )

    today = now.date()

    # 2) 没有相对关键词 → 使用默认周期
    if relative_period is None:
        return _resolve_default_period(report_definition, today)

    normalized = relative_period.strip().lower()

    # 3) 检查白名单
    if normalized not in PERIOD_KEYWORD_MAP:
        raise ValueError(
            f"不支持的时间表达: {relative_period}。"
            f"支持的关键词: {', '.join(sorted(PERIOD_KEYWORD_MAP.keys()))}"
        )

    mapped = PERIOD_KEYWORD_MAP[normalized]

    # 4) 模糊表达 → 使用默认周期
    if mapped == "default":
        return _resolve_default_period(report_definition, today)

    # 5) 按映射计算
    return _compute_relative_period(mapped, today)


# ---------------------------------------------------------------------------
# 内部计算函数
# ---------------------------------------------------------------------------


def _resolve_default_period(definition: ReportDefinition, today: date) -> ResolvedPeriod:
    """使用报告注册表中的 default_period_rule 解析周期。

    Args:
        definition: 报告类型定义。
        today: 参考日期。

    Returns:
        ResolvedPeriod，来源为 "default"。
    """
    rule = definition.default_period_rule
    period_label = {
        "previous_week": "上周",
        "previous_day": "昨天",
        "previous_month": "上月",
    }.get(rule, rule)

    if rule == "previous_day":
        target = today - timedelta(days=1)
        return ResolvedPeriod(
            start=target,
            end=target,
            source="default",
            assumptions=[f"未指定具体时间范围，默认使用{period_label}"],
        )

    if rule == "previous_month":
        first_this_month = today.replace(day=1)
        last_prev_month = first_this_month - timedelta(days=1)
        first_prev_month = last_prev_month.replace(day=1)
        return ResolvedPeriod(
            start=first_prev_month,
            end=last_prev_month,
            source="default",
            assumptions=[f"未指定具体时间范围，默认使用{period_label}"],
        )

    # 默认 previous_week：上一个自然周（周一到周日）
    this_monday = today - timedelta(days=today.weekday())
    last_monday = this_monday - timedelta(days=7)
    last_sunday = this_monday - timedelta(days=1)
    return ResolvedPeriod(
        start=last_monday,
        end=last_sunday,
        source="default",
        assumptions=[f"未指定具体时间范围，默认使用{period_label}"],
    )


def _compute_relative_period(mapped: str, today: date) -> ResolvedPeriod:
    """根据映射后的关键词计算具体日期范围。

    所有计算基于 today，不对 now 的时、分、秒做处理。

    Args:
        mapped: 映射后的关键词（today/yesterday/this_week/last_week 等）。
        today: 参考日期。

    Returns:
        ResolvedPeriod，来源为 "relative"。
    """
    if mapped == "today":
        return ResolvedPeriod(
            start=today,
            end=today,
            source="relative",
            assumptions=["“今天”指当前日期"],
        )

    if mapped == "yesterday":
        yesterday = today - timedelta(days=1)
        return ResolvedPeriod(
            start=yesterday,
            end=yesterday,
            source="relative",
            assumptions=["“昨天”指当前日期的前一天"],
        )

    if mapped == "this_week":
        # 周一开始
        monday = today - timedelta(days=today.weekday())
        sunday = monday + timedelta(days=6)
        return ResolvedPeriod(
            start=monday,
            end=sunday,
            source="relative",
            assumptions=["“本周”按周一至周日计算"],
        )

    if mapped == "last_week":
        # 上周一到上周日
        this_monday = today - timedelta(days=today.weekday())
        last_monday = this_monday - timedelta(days=7)
        last_sunday = this_monday - timedelta(days=1)
        return ResolvedPeriod(
            start=last_monday,
            end=last_sunday,
            source="relative",
            assumptions=["“上周”按上一个周一至周日计算"],
        )

    if mapped == "this_month":
        # 本月第一天到今天
        first_day = today.replace(day=1)
        return ResolvedPeriod(
            start=first_day,
            end=today,
            source="relative",
            assumptions=["“本月”从月初截至当前日期"],
        )

    if mapped == "last_month":
        # 上月完整月
        first_this_month = today.replace(day=1)
        last_prev_month = first_this_month - timedelta(days=1)
        first_prev_month = last_prev_month.replace(day=1)
        return ResolvedPeriod(
            start=first_prev_month,
            end=last_prev_month,
            source="relative",
            assumptions=["“上月”指上一个完整自然月"],
        )

    if mapped == "last_7_days":
        # 包含今天在内的最近 7 天
        return ResolvedPeriod(
            start=today - timedelta(days=6),
            end=today,
            source="relative",
            assumptions=["“最近7天”包含今天在内的过去 7 天"],
        )

    if mapped == "last_30_days":
        # 包含今天在内的最近 30 天
        return ResolvedPeriod(
            start=today - timedelta(days=29),
            end=today,
            source="relative",
            assumptions=["“最近30天”包含今天在内的过去 30 天"],
        )

    # 不会到这里，因为 resolve_assistant_period 已经做了白名单检查
    raise ValueError(f"内部错误：未处理的时间关键词 '{mapped}'")
