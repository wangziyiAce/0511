"""智能报告 V2 的确定性规则引擎。

为什么要单独建这个文件？
-------------------------
智能报告里最容易被面试官追问的一点是：“这些数字到底是谁算的？”

本项目采用的原则是：

* 风险分、转化率、ROI、SLA 是否超时等“业务数字”全部由 SQL/规则引擎计算；
* Dify / LLM 只能基于这些数字做解释、总结和建议；
* 所有规则函数都保持纯函数风格，方便单元测试和复盘。

这种设计能避免大模型幻觉，也能让每一个数字回溯到数据库事实表。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional


APPLICATION_RISK_LEVEL_HIGH = "high"
APPLICATION_RISK_LEVEL_MEDIUM = "medium"
APPLICATION_RISK_LEVEL_LOW = "low"


@dataclass(frozen=True)
class ApplicationRiskResult:
    """申请风险评分结果。

    ``score`` 是最终风险分；
    ``level`` 是面向管理者展示的风险等级；
    ``reasons`` 记录触发了哪些规则，方便报告里做指标追溯。
    """

    score: int
    level: str
    reasons: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ChannelROIMetrics:
    """渠道 ROI 指标。

    注意：当成本为 0、线索数为 0、签约数为 0 时，不能“估算”。
    企业分析报表宁愿返回 ``None`` 并给出数据质量警告，也不能除零或编数字。
    """

    cpl: Optional[float]
    cac: Optional[float]
    roi: Optional[float]
    data_quality_warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SLAEvaluation:
    """SLA 规则判断结果。

    ``response_hours`` 和 ``resolve_hours`` 是实际耗时；
    ``response_overdue`` 和 ``resolve_overdue`` 表示是否超过服务承诺。
    """

    response_hours: Optional[float]
    resolve_hours: Optional[float]
    response_overdue: bool
    resolve_overdue: bool
    thresholds: dict[str, int]


COMPLAINT_SLA_THRESHOLDS: dict[str, dict[str, int]] = {
    # 单位：小时。与用户给出的 V2 计划保持一致。
    "urgent": {"response_hours": 1, "resolve_hours": 24},
    "high": {"response_hours": 4, "resolve_hours": 48},
    "medium": {"response_hours": 24, "resolve_hours": 72},
    "low": {"response_hours": 48, "resolve_hours": 120},
}


def _round_money(value: Decimal) -> float:
    """把 Decimal 金额计算结果统一保留 2 位小数。

    报表金额类指标不要直接使用二进制浮点数做中间计算，否则容易出现
    ``0.30000000004`` 这类展示问题。这里用 Decimal 做计算，最后再转成
    JSON 友好的 float。
    """

    return float(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _round_rate(value: Decimal) -> float:
    """把比例类指标保留 4 位小数，既适合前端展示，也适合继续计算。"""

    return float(value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP))


def calculate_conversion_rate(numerator: int, denominator: int) -> Optional[float]:
    """计算转化率。

    Args:
        numerator: 分子，例如签约数。
        denominator: 分母，例如线索数。

    Returns:
        ``numerator / denominator``；当分母为 0 时返回 ``None``。

    面试表达：
    “我没有在分母为 0 时返回 0，因为 0 表示真实转化为 0，
    而 None 表示数据不足，两者业务含义不同。”
    """

    if denominator <= 0:
        return None
    return _round_rate(Decimal(numerator) / Decimal(denominator))


def calculate_application_risk(
    *,
    overdue: bool = False,
    days_to_deadline: Optional[int] = None,
    missing_required_materials: int = 0,
    days_since_update: Optional[int] = None,
    has_next_action: bool = True,
    score_override: Optional[int] = None,
) -> ApplicationRiskResult:
    """计算申请风险分。

    规则完全来自用户确认的 V2 计划：

    * 已逾期：+40
    * 7 天内截止：+30；8—30 天：+15
    * 缺必需材料：每项 +20，最多 +40
    * 7 天未更新：+20
    * 无下一步动作：+10
    * 高风险 ≥70，中风险 40—69，低风险 <40

    ``score_override`` 只给测试和历史数据兼容使用，真实业务调用不传。
    """

    reasons: list[str] = []

    if score_override is not None:
        score = score_override
    else:
        score = 0

        if overdue:
            score += 40
            reasons.append("overdue")

        if days_to_deadline is not None:
            if days_to_deadline <= 7:
                score += 30
                reasons.append("deadline_within_7_days")
            elif 8 <= days_to_deadline <= 30:
                score += 15
                reasons.append("deadline_within_30_days")

        material_score = min(max(missing_required_materials, 0) * 20, 40)
        if material_score:
            score += material_score
            reasons.append("missing_required_materials")

        if days_since_update is not None and days_since_update >= 7:
            score += 20
            reasons.append("not_updated_for_7_days")

        if not has_next_action:
            score += 10
            reasons.append("no_next_action")

    if score >= 70:
        level = APPLICATION_RISK_LEVEL_HIGH
    elif score >= 40:
        level = APPLICATION_RISK_LEVEL_MEDIUM
    else:
        level = APPLICATION_RISK_LEVEL_LOW

    return ApplicationRiskResult(score=score, level=level, reasons=reasons)


def calculate_channel_roi(
    *,
    channel_cost: float | int | Decimal,
    leads: int,
    signed_count: int,
    paid_amount: float | int | Decimal,
) -> ChannelROIMetrics:
    """计算渠道投放 ROI。

    公式：

    * ``CPL = 渠道成本 / 线索数``(Cost Per Lead 每条有效线索成本)
    * ``CAC = 渠道成本 / 签约数``(Customer Acquisition Cost 获取一个付费客户的成本)
    * ``ROI = (实际回款 - 渠道成本) / 渠道成本``(Return on Investment 投资回报率)

    成本为 0 或数据不完整时返回 ``None``，并在 ``data_quality_warnings``
    中说明原因，避免除零和大模型估算。
    """

    warnings: list[str] = []
    cost = Decimal(str(channel_cost or 0))
    paid = Decimal(str(paid_amount or 0))

    cpl: Optional[float] = None
    cac: Optional[float] = None
    roi: Optional[float] = None

    if leads > 0 and cost > 0:
        cpl = _round_money(cost / Decimal(leads))
    else:
        warnings.append("CPL 缺少有效成本或线索数，返回 null")

    if signed_count > 0 and cost > 0:
        cac = _round_money(cost / Decimal(signed_count))
    else:
        warnings.append("CAC 缺少有效成本或签约数，返回 null")

    if cost > 0:
        roi = _round_rate((paid - cost) / cost)
    else:
        warnings.append("ROI 成本为 0，返回 null")

    return ChannelROIMetrics(
        cpl=cpl,
        cac=cac,
        roi=roi,
        data_quality_warnings=warnings,
    )


def _hours_between(start: datetime, end: Optional[datetime]) -> Optional[float]:
    """计算两个时间点之间的小时数；结束时间缺失时返回 None。"""

    if end is None:
        return None
    return round((end - start).total_seconds() / 3600, 2)


def evaluate_complaint_sla(
    *,
    priority: str,
    created_at: datetime,
    first_response_at: Optional[datetime],
    resolved_at: Optional[datetime],
) -> SLAEvaluation:
    """按投诉优先级判断首次响应和解决时长是否超时。"""

    normalized_priority = (priority or "medium").lower()
    thresholds = COMPLAINT_SLA_THRESHOLDS.get(
        normalized_priority,
        COMPLAINT_SLA_THRESHOLDS["medium"],
    )

    response_hours = _hours_between(created_at, first_response_at)
    resolve_hours = _hours_between(created_at, resolved_at)

    response_overdue = (
        response_hours is None
        or response_hours > thresholds["response_hours"]
    )
    resolve_overdue = (
        resolve_hours is None
        or resolve_hours > thresholds["resolve_hours"]
    )

    return SLAEvaluation(
        response_hours=response_hours,
        resolve_hours=resolve_hours,
        response_overdue=response_overdue,
        resolve_overdue=resolve_overdue,
        thresholds=thresholds,
    )

