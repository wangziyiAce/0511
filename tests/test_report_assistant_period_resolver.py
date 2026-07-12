"""智能报告助手 — 时间解析单元测试。

测试目标：验证自然语言相对时间表达到具体日期的映射规则。
所有测试使用固定 ``now``，保证结果可重现。

覆盖范围：
- 今天、昨天、本周、上周、本月、上月
- 最近7天、最近30天
- 现在、当前、最近 → 使用报告默认周期
- 显式起止日期
- 非法起止时间（start > end）
- 未来时间范围
"""

from __future__ import annotations

from datetime import date, datetime

import pytest

from services.reporting.assistant.period_resolver import (
    PERIOD_KEYWORD_MAP,
    ResolvedPeriod,
    resolve_assistant_period,
)
from services.reporting.registry import get_report_definition

# 固定测试时间：2026年7月15日周三
FIXED_NOW = datetime(2026, 7, 15, 10, 30, 0)

# 申请风险报告定义（default_period_rule = "previous_week"）
APP_RISK_DEF = get_report_definition("application_risk")


# ---------------------------------------------------------------------------
# 绝对日期映射
# ---------------------------------------------------------------------------


class TestExplicitDates:
    def test_explicit_dates_override_relative_period(self):
        """显式日期优先于相对时间。"""
        result = resolve_assistant_period(
            relative_period="last_week",
            period_start=date(2026, 7, 1),
            period_end=date(2026, 7, 5),
            report_definition=APP_RISK_DEF,
            now=FIXED_NOW,
        )
        assert result.start == date(2026, 7, 1)
        assert result.end == date(2026, 7, 5)
        assert result.source == "explicit"


class TestToday:
    def test_today(self):
        result = resolve_assistant_period(
            relative_period="today",
            period_start=None,
            period_end=None,
            report_definition=APP_RISK_DEF,
            now=FIXED_NOW,
        )
        assert result.start == date(2026, 7, 15)
        assert result.end == date(2026, 7, 15)
        assert result.source == "relative"


class TestYesterday:
    def test_yesterday(self):
        result = resolve_assistant_period(
            relative_period="yesterday",
            period_start=None,
            period_end=None,
            report_definition=APP_RISK_DEF,
            now=FIXED_NOW,
        )
        assert result.start == date(2026, 7, 14)
        assert result.end == date(2026, 7, 14)


class TestThisWeek:
    def test_this_week(self):
        result = resolve_assistant_period(
            relative_period="this_week",
            period_start=None,
            period_end=None,
            report_definition=APP_RISK_DEF,
            now=FIXED_NOW,
        )
        # 2026-07-15 周三 → 本周周一 = 2026-07-13，周日 = 2026-07-19
        assert result.start == date(2026, 7, 13)
        assert result.end == date(2026, 7, 19)


class TestLastWeek:
    def test_last_week(self):
        result = resolve_assistant_period(
            relative_period="last_week",
            period_start=None,
            period_end=None,
            report_definition=APP_RISK_DEF,
            now=FIXED_NOW,
        )
        # 上周周一 = 2026-07-06，周日 = 2026-07-12
        assert result.start == date(2026, 7, 6)
        assert result.end == date(2026, 7, 12)


class TestThisMonth:
    def test_this_month(self):
        result = resolve_assistant_period(
            relative_period="this_month",
            period_start=None,
            period_end=None,
            report_definition=APP_RISK_DEF,
            now=FIXED_NOW,
        )
        assert result.start == date(2026, 7, 1)
        assert result.end == date(2026, 7, 15)  # 截至今天


class TestLastMonth:
    def test_last_month(self):
        result = resolve_assistant_period(
            relative_period="last_month",
            period_start=None,
            period_end=None,
            report_definition=APP_RISK_DEF,
            now=FIXED_NOW,
        )
        assert result.start == date(2026, 6, 1)
        assert result.end == date(2026, 6, 30)


class TestLast7Days:
    def test_last_7_days(self):
        result = resolve_assistant_period(
            relative_period="last_7_days",
            period_start=None,
            period_end=None,
            report_definition=APP_RISK_DEF,
            now=FIXED_NOW,
        )
        assert result.start == date(2026, 7, 9)   # 15 - 6 = 9
        assert result.end == date(2026, 7, 15)


class TestLast30Days:
    def test_last_30_days(self):
        result = resolve_assistant_period(
            relative_period="last_30_days",
            period_start=None,
            period_end=None,
            report_definition=APP_RISK_DEF,
            now=FIXED_NOW,
        )
        assert result.start == date(2026, 6, 16)  # 15 - 29 = June 16
        assert result.end == date(2026, 7, 15)


# ---------------------------------------------------------------------------
# 模糊时间 → 使用报告默认周期
# ---------------------------------------------------------------------------


class TestFuzzyPeriods:
    def test_now_uses_default_period(self):
        """'现在' 使用报告的 default_period_rule。"""
        result = resolve_assistant_period(
            relative_period="now",
            period_start=None,
            period_end=None,
            report_definition=APP_RISK_DEF,
            now=FIXED_NOW,
        )
        # application_risk 默认 previous_week → 上周
        assert result.start == date(2026, 7, 6)
        assert result.end == date(2026, 7, 12)
        assert any("默认使用" in a for a in result.assumptions), f"assumptions: {result.assumptions}"

    def test_current_uses_default_period(self):
        result = resolve_assistant_period(
            relative_period="current",
            period_start=None,
            period_end=None,
            report_definition=APP_RISK_DEF,
            now=FIXED_NOW,
        )
        assert result.source == "default"

    def test_recent_uses_default_period(self):
        result = resolve_assistant_period(
            relative_period="recent",
            period_start=None,
            period_end=None,
            report_definition=APP_RISK_DEF,
            now=FIXED_NOW,
        )
        assert result.source == "default"

    def test_none_uses_default_period(self):
        result = resolve_assistant_period(
            relative_period=None,
            period_start=None,
            period_end=None,
            report_definition=APP_RISK_DEF,
            now=FIXED_NOW,
        )
        assert result.start == date(2026, 7, 6)
        assert result.end == date(2026, 7, 12)


# ---------------------------------------------------------------------------
# 不同报告类型的默认周期
# ---------------------------------------------------------------------------


class TestDailyReportDefaultPeriod:
    def test_daily_summary_uses_previous_day(self):
        """日报默认使用 previous_day。"""
        daily_def = get_report_definition("daily_summary")
        result = resolve_assistant_period(
            relative_period="now",
            period_start=None,
            period_end=None,
            report_definition=daily_def,
            now=FIXED_NOW,
        )
        assert result.start == date(2026, 7, 14)
        assert result.end == date(2026, 7, 14)


# ---------------------------------------------------------------------------
# 边界与异常
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_start_after_end_rejected(self):
        """开始日期晚于结束日期应抛出异常。"""
        with pytest.raises(ValueError, match="开始日期"):
            resolve_assistant_period(
                relative_period=None,
                period_start=date(2026, 7, 20),
                period_end=date(2026, 7, 10),
                report_definition=APP_RISK_DEF,
                now=FIXED_NOW,
            )

    def test_unknown_relative_period_raises(self):
        """非法相对时间表达应抛出异常。"""
        with pytest.raises(ValueError, match="不支持"):
            resolve_assistant_period(
                relative_period="next_century",
                period_start=None,
                period_end=None,
                report_definition=APP_RISK_DEF,
                now=FIXED_NOW,
            )


# ---------------------------------------------------------------------------
# 关键词映射完整性
# ---------------------------------------------------------------------------


class TestKeywordMap:
    def test_keyword_map_has_all_required_entries(self):
        """关键词映射必须包含计划要求的所有表达。"""
        required = {
            "today", "yesterday",
            "this_week", "last_week",
            "this_month", "last_month",
            "last_7_days", "last_30_days",
            "now", "current", "recent",
        }
        assert set(PERIOD_KEYWORD_MAP.keys()) >= required
