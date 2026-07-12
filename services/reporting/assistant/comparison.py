"""提供智能报告双周期比较的确定性计算与数据质量门禁。

本文件位于助手业务层，上游由后续只读比较工具传入两个周期的指标值和
DataQuality 字典，下游向响应组装层提供差值、变化率、方向及展示限制。
所有数值运算只接受 ``Decimal``，避免浮点误差；本模块不读写数据库、
不调用外部服务，也不负责指标提取或报告聚合。
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal, Mapping, Any


Direction = Literal["up", "down", "flat", "unknown"]
QUALITY_LEVELS = frozenset({"ok", "warning", "degraded", "empty", "failed"})


@dataclass(frozen=True)
class CalculatedValues:
    """表示单个指标由 Python 计算出的对比结果。

    ``delta`` 和 ``change_rate`` 供响应层展示，``direction`` 供趋势文案使用。
    任一期原值缺失或质量门禁阻断趋势时，三个字段均不提供有效趋势结论。
    """

    delta: Decimal | None
    change_rate: Decimal | None
    direction: Direction


@dataclass(frozen=True)
class QualitySnapshot:
    """保存单周期不可变的数据质量快照，避免调用方后续修改嵌套列表。"""

    level: str
    warnings: tuple[str, ...]
    data_source: str | None


@dataclass(frozen=True)
class ComparisonQualityGate:
    """保存两期独立质量信息，并声明原值和趋势是否可展示。

    ``limited_trend`` 表示 warning/degraded 场景只能给出带限制的趋势；
    ``warnings`` 给后续接口或回答层提供可展示、可排错的质量说明。
    """

    current_quality: QualitySnapshot
    previous_quality: QualitySnapshot
    allow_values: bool
    allow_trend: bool
    limited_trend: bool
    warnings: tuple[str, ...]

    def apply(self, values: CalculatedValues) -> CalculatedValues:
        """把门禁应用到计算结果，阻断时清空派生值并把方向改为未知。

        参数 ``values`` 来自 :func:`calculate_values`。本方法不改变两期原值；
        后续工具仍可依据 ``allow_values`` 展示原始数据。若趋势被阻断而不清空，
        回答层可能把空数据或失败数据误说成上升、下降。
        """
        if self.allow_trend:
            return values
        return CalculatedValues(delta=None, change_rate=None, direction="unknown")


def calculate_values(
    current: Decimal | None,
    previous: Decimal | None,
    *,
    value_type: str,
) -> CalculatedValues:
    """计算两个周期的差值、相对变化率和方向。

    ``current``、``previous`` 来自受控指标 resolver；缺失值保持缺失。
    ``value_type`` 描述指标类型，当前各类型共享同一 Decimal 公式，其中
    percentage 的 delta 自然表示百分点差。函数无外部副作用；previous 为零时
    只返回差值，负 previous 则以绝对值作为变化率分母。
    """
    if not isinstance(value_type, str) or not value_type:
        raise ValueError("value_type 必须是非空字符串")
    if current is not None and not isinstance(current, Decimal):
        raise TypeError("current 必须是 Decimal 或 None")
    if previous is not None and not isinstance(previous, Decimal):
        raise TypeError("previous 必须是 Decimal 或 None")

    # 任一期缺失都无法形成同口径比较；不能把 None 当作零参与运算。
    if current is None or previous is None:
        return CalculatedValues(delta=None, change_rate=None, direction="unknown")

    delta = current - previous
    change_rate = None if previous == 0 else delta / abs(previous)
    direction: Direction = "up" if delta > 0 else "down" if delta < 0 else "flat"
    return CalculatedValues(delta=delta, change_rate=change_rate, direction=direction)


def evaluate_comparison_quality(
    current_quality: Mapping[str, Any],
    previous_quality: Mapping[str, Any],
    *,
    compatible: bool,
) -> ComparisonQualityGate:
    """根据两期独立 DataQuality 生成比较门禁。

    两个质量字典分别来自当前和上一周期报告。``compatible`` 必须由上游在检查
    Schema 版本、指标定义和周期口径后显式传入；不兼容时直接拒绝比较。
    warning/degraded 保留带限制趋势，empty/failed 仅允许保留原值入口并阻断
    delta、change_rate 和 direction。函数不修改调用方传入的字典。
    """
    if not compatible:
        raise ValueError("Schema、指标定义或周期口径不兼容，不能直接比较")

    current = _quality_snapshot(current_quality, "current")
    previous = _quality_snapshot(previous_quality, "previous")
    current_level = current.level
    previous_level = previous.level
    levels = {current_level, previous_level}

    # empty/failed 说明至少一期没有可用于推导趋势的数据，必须失败关闭。
    blocked = bool(levels & {"empty", "failed"})
    limited = not blocked and bool(levels & {"warning", "degraded"})
    warnings = _quality_warnings(current, previous, current_level, previous_level)
    return ComparisonQualityGate(
        current_quality=current,
        previous_quality=previous,
        allow_values=True,
        allow_trend=not blocked,
        limited_trend=limited,
        warnings=tuple(warnings),
    )


def _quality_level(quality: Mapping[str, Any], period_name: str) -> str:
    """读取并校验单个周期的质量等级，未知等级按失败关闭处理。"""
    level = quality.get("level", "ok")
    if level not in QUALITY_LEVELS:
        raise ValueError(f"{period_name} 数据质量等级无效: {level}")
    return str(level)


def _quality_snapshot(quality: Mapping[str, Any], period_name: str) -> QualitySnapshot:
    """把外部质量字典规范化为不共享嵌套可变对象的只读快照。"""
    level = _quality_level(quality, period_name)
    raw_warnings = quality.get("warnings", []) or []
    if isinstance(raw_warnings, (str, bytes)):
        raise ValueError(f"{period_name} warnings 必须是列表")
    return QualitySnapshot(
        level=level,
        warnings=tuple(str(warning) for warning in raw_warnings),
        data_source=(
            str(quality["data_source"]) if quality.get("data_source") is not None else None
        ),
    )


def _quality_warnings(
    current: QualitySnapshot,
    previous: QualitySnapshot,
    current_level: str,
    previous_level: str,
) -> list[str]:
    """按周期标记质量限制，避免两期 warning 在响应中混淆。"""
    warnings: list[str] = []
    for label, quality, level in (
        ("当前周期", current, current_level),
        ("上一周期", previous, previous_level),
    ):
        if level != "ok":
            warnings.append(f"{label}数据质量为 {level}")
        for warning in quality.warnings:
            warnings.append(f"{label}：{warning}")
    return warnings
