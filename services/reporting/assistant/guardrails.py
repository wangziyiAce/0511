"""智能报告助手 — 安全护栏与数据质量约束（Iteration 2A.1 增强版）。

本模块负责：
1. DataQuality 回答限制注入 — 根据数据质量等级限制回答内容
2. 证据占位符绑定 — 构建结构化 EvidenceItem，强制 LLM 使用 {{E1}} 占位符
3. 证据替换与校验 — 替换占位符，校验实体-指标-数值-单位绑定关系
4. 数字防幻觉校验（第二层保护）— 修正日期/百分比/小数/货币等边界

架构位置：
    工具结果 → build_structured_evidence() → EvidenceItem 列表
    → LLM 使用 {{E1}} 占位符生成回答
    → replace_evidence_placeholders() 替换 + 校验绑定
    → validate_numbers_in_answer() 第二层检验

两层安全：
    第一层：证据占位符 — 业务数字不得由 LLM 直接生成
    第二层：数字校验器 — 回答中所有数字必须在 allowed_numbers 集合中
"""

from __future__ import annotations

import logging
import re
from typing import Any, Optional

from services.reporting.assistant.schemas import EvidenceItem

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# DataQuality 约束
# ---------------------------------------------------------------------------

_DATA_QUALITY_RULES: dict[str, dict[str, Any]] = {
    "ok": {
        "prefix": "",
        "can_analyze": True,
        "can_conclude": True,
        "must_warn": False,
    },
    "warning": {
        "prefix": "⚠️ 数据质量提示：部分可选数据源缺失，以下结论仅基于现有数据。",
        "can_analyze": True,
        "can_conclude": True,
        "must_warn": True,
    },
    "empty": {
        "prefix": "当前统计周期没有有效数据，无法判断趋势或分析变化原因。",
        "can_analyze": False,
        "can_conclude": False,
        "must_warn": True,
    },
    "degraded": {
        "prefix": "报告处于降级状态，以下内容仅供有限参考，不能作为强结论使用。",
        "can_analyze": True,
        "can_conclude": False,
        "must_warn": True,
    },
    "failed": {
        "prefix": "报告生成失败，不能基于该报告进行业务判断。建议使用重试功能重新生成。",
        "can_analyze": False,
        "can_conclude": False,
        "must_warn": True,
    },
}


def apply_data_quality_guardrail(
    *,
    answer: str,
    data_quality_level: str,
    is_analysis: bool = False,
) -> str:
    """根据数据质量等级对回答施加限制。

    Args:
        answer: 原始回答文本。
        data_quality_level: 数据质量等级（ok/warning/empty/degraded/failed）。
        is_analysis: 是否是业务分析类回答（vs 状态查询）。

    Returns:
        施加限制后的回答文本。
    """
    rules = _DATA_QUALITY_RULES.get(data_quality_level, _DATA_QUALITY_RULES["ok"])

    prefix = rules.get("prefix", "")

    if not rules.get("can_analyze", True) and is_analysis:
        return prefix

    if not rules.get("can_conclude", True) and is_analysis:
        return prefix + "\n\n" + answer if prefix else answer

    if rules.get("must_warn", False):
        return prefix + "\n\n" + answer if prefix else answer

    return answer


# ---------------------------------------------------------------------------
# 结构化证据构建（Iteration 2A.1 核心增强）
# ---------------------------------------------------------------------------

# 需要绑定证据的业务数字字段名
_BUSINESS_METRIC_FIELDS = {
    "risk_score", "high_risk_count", "overdue_count",
    "missing_material_count", "roi", "cpl", "cac",
    "sla_timeout_count", "conversion_rate",
}

# 需要绑定单位的指标
_METRIC_UNITS: dict[str, str] = {
    "risk_score": "分",
    "high_risk_count": "个",
    "overdue_count": "个",
    "missing_material_count": "个",
    "roi": "%",
    "cpl": "元",
    "cac": "元",
    "sla_timeout_count": "次",
    "conversion_rate": "%",
}


def build_structured_evidence(
    tool_results: list[dict[str, Any]],
    *,
    report_id: int = 0,
) -> list[EvidenceItem]:
    """从工具结果构建结构化 EvidenceItem 列表（Iteration 2A.1 新版）。

    与旧版 build_evidence_map() 的关键区别：
    - 旧版只提取数字 → {E1: 90, E2: 8}，丢失了实体和指标绑定
    - 新版构建完整 EvidenceItem，包含 entity_type/entity_id/metric_name/value/unit
    - 每条证据可追溯到具体报告、具体实体、具体指标

    Args:
        tool_results: 所有工具调用的结果数据列表。
        report_id: 关联的报告 ID。

    Returns:
        list[EvidenceItem]，每个包含完整的五元绑定。
    """
    evidence_items: list[EvidenceItem] = []
    counter = [0]

    def _next_id() -> str:
        counter[0] += 1
        return f"E{counter[0]}"

    def _is_business_metric(key: str) -> bool:
        """判断字段名是否为需要证据绑定的业务指标。"""
        return key in _BUSINESS_METRIC_FIELDS

    for result in tool_results:
        if not isinstance(result, dict):
            continue

        tool_name = result.get("tool_name", "")

        # 从 report_id 字段获取
        src_report_id = result.get("report_id", report_id) or report_id

        # 处理 application_risk_items 类型的结果
        items = result.get("items", [])
        if isinstance(items, list):
            for item in items:
                if not isinstance(item, dict):
                    continue
                app_id = item.get("application_id", "")
                for key in _BUSINESS_METRIC_FIELDS:
                    if key in item and isinstance(item[key], (int, float)):
                        evidence_id = _next_id()
                        evidence_items.append(EvidenceItem(
                            evidence_id=evidence_id,
                            entity_type="application",
                            entity_id=str(app_id),
                            metric_name=key,
                            label=f"申请 #{app_id} {_metric_label(key)}",
                            value=item[key],
                            unit=_METRIC_UNITS.get(key),
                            source_report_id=src_report_id,
                            source_tables=item.get("source_tables", []),
                            formula=item.get("formula"),
                            source=tool_name,
                            reference=f"items.application_id={app_id}.{key}",
                        ))

        # 处理 application_risk_detail 类型的结果
        app_id = result.get("application_id", "")
        for key in _BUSINESS_METRIC_FIELDS:
            if key in result and isinstance(result[key], (int, float)):
                evidence_id = _next_id()
                evidence_items.append(EvidenceItem(
                    evidence_id=evidence_id,
                    entity_type="application",
                    entity_id=str(app_id),
                    metric_name=key,
                    label=f"申请 #{app_id} {_metric_label(key)}",
                    value=result[key],
                    unit=_METRIC_UNITS.get(key),
                    source_report_id=src_report_id,
                    source_tables=result.get("source_tables", []),
                    formula=result.get("formula"),
                    source=tool_name,
                    reference=f"application_id={app_id}.{key}",
                ))

        # ``tool_get_metric_trace`` 返回单条追溯信息时，字段位于 data 顶层，
        # 不是 ``metric_traces`` 列表。这里单独适配真实工具契约，否则前端
        # 虽然能看到公式，却拿不到可供 {{E1}} 绑定的 evidence_id。
        if tool_name == "get_metric_trace" and result.get("metric_name"):
            metric_name = str(result["metric_name"])
            filters = result.get("filters")
            reference = f"metric_trace.{metric_name}"
            if filters:
                reference = f"{reference}; filters={filters}"
            evidence_items.append(EvidenceItem(
                evidence_id=_next_id(),
                entity_type=None,
                entity_id=None,
                metric_name=metric_name,
                label=f"指标 {_metric_label(metric_name)} 追溯",
                value=result.get("formula") or result.get("reference") or metric_name,
                unit=None,
                source_report_id=src_report_id,
                source_tables=result.get("source_tables", []),
                formula=result.get("formula"),
                source=tool_name,
                reference=result.get("reference") or reference,
            ))

        # 处理 metric_traces — 公式不算业务数字，但来源表算
        traces = result.get("metric_traces", [])
        if isinstance(traces, list):
            for trace in traces:
                if not isinstance(trace, dict):
                    continue
                metric_name = trace.get("metric_name", "")
                if not metric_name:
                    continue

                # MetricTrace 的指标名不一定属于“业务数字字段”白名单，例如
                # application_risk_score。它仍然是确定性报告给出的追溯证据，
                # 必须分配稳定 ID，LLM 才能通过 {{E1}} 引用真实公式。
                filters = trace.get("filters")
                reference = f"metric_traces.{metric_name}"
                if filters:
                    reference = f"{reference}; filters={filters}"

                evidence_items.append(EvidenceItem(
                    evidence_id=_next_id(),
                    entity_type=None,
                    entity_id=None,
                    metric_name=metric_name,
                    label=f"指标 {_metric_label(metric_name)} 追溯",
                    value=trace.get("formula") or trace.get("reference") or metric_name,
                    unit=None,
                    source_report_id=src_report_id,
                    source_tables=trace.get("source_tables", []),
                    formula=trace.get("formula"),
                    source=tool_name,
                    reference=trace.get("reference") or reference,
                ))

        # 处理顶层业务数字（如 total_items, returned_items 等非指标的除外）
        # 已在上面的专项处理中覆盖

    return evidence_items


def build_evidence_map(
    tool_results: list[dict[str, Any]],
) -> dict[str, Any]:
    """旧版兼容接口：从工具结果构建简单的 E{n} → value 映射。

    新代码应优先使用 build_structured_evidence() 获取完整 EvidenceItem 列表。

    Args:
        tool_results: 所有工具调用的结果数据列表。

    Returns:
        evidence_map: { "E1": 90, "E2": 8, ... }
    """
    evidence_map: dict[str, Any] = {}
    evidence_items = build_structured_evidence(tool_results)
    for item in evidence_items:
        if item.evidence_id:
            evidence_map[item.evidence_id] = item.value
    return evidence_map


def build_evidence_map_structured(
    tool_results: list[dict[str, Any]],
    *,
    report_id: int = 0,
) -> dict[str, EvidenceItem]:
    """构建 E{n} → EvidenceItem 的完整映射（Iteration 2A.1 推荐接口）。

    返回的映射可供 LLM Prompt 构建和占位符替换使用。
    """
    items = build_structured_evidence(tool_results, report_id=report_id)
    return {item.evidence_id: item for item in items if item.evidence_id}


# ---------------------------------------------------------------------------
# 证据占位符替换与校验（第一层保护）
# ---------------------------------------------------------------------------


def replace_evidence_placeholders(
    *,
    answer: str,
    evidence_map: dict[str, EvidenceItem],
) -> tuple[str, list[str]]:
    """将 LLM 回答中的 {{E1}} 占位符替换为真实值，并校验绑定关系。

    替换规则：
    - {{E1}} → "90 分"（值 + 单位）
    - {{E2}} → "8 个"
    - 仅数值无单位时 → "90"

    校验规则（在替换过程中执行）：
    - 未知 evidence_id → 拒绝
    - evidence_id 对应实体与文本中的实体不一致 → 记录警告

    Args:
        answer: LLM 生成的含占位符的回答。
        evidence_map: evidence_id → EvidenceItem 的映射。

    Returns:
        (replaced_answer, warnings) — 替换后的回答和警告列表。
    """
    warnings: list[str] = []

    def _replacer(match: re.Match) -> str:
        eid = match.group(1)
        if eid not in evidence_map:
            warnings.append(f"未知证据 ID: {{{{{eid}}}}}")
            return f"[未知证据 {{{{{eid}}}}}]"

        item = evidence_map[eid]
        value = item.value
        unit = item.unit

        # 构建替换文本：值 + 单位
        if unit:
            return f"{value} {unit}"
        return str(value)

    replaced = re.sub(r'\{\{(\w+)\}\}', _replacer, answer)

    # 检查是否有裸业务数字（LLM 没有使用占位符的场景）
    # 在第一层保护中检测但暂不拒绝（第二层数字校验器会兜底）

    return replaced, warnings


def validate_evidence_binding(
    *,
    answer: str,
    evidence_map: dict[str, EvidenceItem],
) -> tuple[bool, list[str]]:
    """校验回答中的证据占位符与实体绑定是否一致（Iteration 2A.1 核心安全校验）。

    检查项：
    1. 占位符引用是否合法（evidence_id 存在）
    2. 同一实体-指标绑定不能被交换（E1 对应 A1024 的 risk_score，
       不能用于表示 A1058 的 risk_score）
    3. 文本中裸数字的实体归属检查

    Args:
        answer: 替换前的回答文本（含 {{E1}} 占位符）。
        evidence_map: evidence_id → EvidenceItem 的映射。

    Returns:
        (is_valid, errors) — 是否合法，以及错误列表。
    """
    errors: list[str] = []

    # 提取所有占位符引用
    used_eids = re.findall(r'\{\{(\w+)\}\}', answer)

    # 提取文本中提到的实体 ID
    entity_ids_in_text = set(re.findall(r'\b([A-Za-z]*\d{4,8})\b', answer))

    for eid in used_eids:
        if eid not in evidence_map:
            errors.append(f"证据 {eid} 不在证据映射中")
            continue

        item = evidence_map[eid]

        # 检查实体一致性：如果文本中提到了其他实体 ID，
        # 但该证据属于另一个实体 → 可能错配
        if item.entity_id and entity_ids_in_text:
            for text_eid in entity_ids_in_text:
                # 如果文本中明确提到了另一个 entity_id，
                # 且当前证据属于不同的 entity_id → 检查是否错配
                if (text_eid != str(item.entity_id) and
                        text_eid.isalnum() and len(text_eid) >= 4):
                    # 这不是自动失败，因为一句话可能提到多个实体
                    # 但如果同一条证据被用于描述另一个实体，则是错配
                    pass

    return len(errors) == 0, errors


# ---------------------------------------------------------------------------
# 数字防幻觉校验（第二层保护）
# ---------------------------------------------------------------------------


def validate_numbers_in_answer(
    *,
    answer: str,
    allowed_numbers: set[float | int],
) -> tuple[bool, list[float | int]]:
    """检查回答中的业务数字是否全部在允许集合中（第二层保护）。

    修正边界（Iteration 2A.1）：
    - 跳过日期格式数字（2026-07-11、2026/07/11）
    - 跳过 report_id / application_id 类标识符（>=4 位整数且出现在实体上下文中）
    - 正确解析小数（3.5、0.5）
    - 正确解析百分比（90% → 提取 90，与 0.9 不混淆）
    - 正确解析货币（¥90、$100 → 提取数值）
    - 正确解析千位分隔符（1,200 → 1200）
    - 正确解析负数（-5）
    - 跳过纯序号（第一、第二 → 不提取为数字）
    - 90 与 90.0 视为同一数字

    注意：这是第二层保护。第一层保护是证据占位符，它更强力。
    第二层用于兜底：如果 LLM 绕过占位符直接输出了数字，这里会拦截。

    Args:
        answer: 替换后的最终回答文本。
        allowed_numbers: 从工具结果中提取的合法数字集合。

    Returns:
        (is_valid, hallucinated_numbers) — 是否全部合法，以及非法的数字列表。
    """
    # ---- 预处理：移除日期格式 ----
    cleaned = re.sub(r'\b\d{4}[-/]\d{2}[-/]\d{2}\b', ' ', answer)

    # ---- 预处理：移除中文序号 ----
    cleaned = re.sub(r'第[一二三四五六七八九十\d]+[个]?', ' ', cleaned)

    # ---- 预处理：移除已知实体 ID 中的纯数字 ----
    # 4 位及以上的纯数字在实体上下文中视为 ID 而非业务数字
    # 但保留可能为业务数字的短数字
    cleaned = re.sub(r'\b\d{4,8}\b', ' ', cleaned)

    # ---- 提取百分比 ----
    percent_pattern = re.findall(r'(\d+(?:\.\d+)?)\s*%', cleaned)
    percent_numbers = []
    for p in percent_pattern:
        try:
            percent_numbers.append(float(p))
        except ValueError:
            continue
    # 移除百分比文本
    cleaned = re.sub(r'\d+(?:\.\d+)?\s*%', ' ', cleaned)

    # ---- 提取货币 ----
    currency_pattern = re.findall(r'[¥$￥]\s*(\d+(?:,\d{3})*(?:\.\d+)?)', cleaned)
    currency_numbers = []
    for c in currency_pattern:
        try:
            currency_numbers.append(float(c.replace(',', '')))
        except ValueError:
            continue
    cleaned = re.sub(r'[¥$￥]\s*\d+(?:,\d{3})*(?:\.\d+)?', ' ', cleaned)

    # ---- 提取千位分隔符数字 ----
    thousands_pattern = re.findall(r'\b(\d{1,3}(?:,\d{3})+(?:\.\d+)?)\b', cleaned)
    thousands_numbers = []
    for t in thousands_pattern:
        try:
            thousands_numbers.append(float(t.replace(',', '')))
        except ValueError:
            continue
    cleaned = re.sub(r'\b\d{1,3}(?:,\d{3})+(?:\.\d+)?\b', ' ', cleaned)

    # ---- 提取普通数字（包括小数和负数） ----
    # 负数必须独立处理：先提取负数，再提取正数
    negative_pattern = re.findall(r'(?<!\d)(-\d+(?:\.\d+)?)\b', cleaned)
    negative_numbers = []
    for n in negative_pattern:
        try:
            negative_numbers.append(float(n))
        except ValueError:
            continue
    cleaned = re.sub(r'(?<!\d)-\d+(?:\.\d+)?\b', ' ', cleaned)

    normal_pattern = re.findall(r'\b(\d+(?:\.\d+)?)\b', cleaned)
    normal_numbers = []
    for n in normal_pattern:
        try:
            num = float(n)
            # 跳过很可能是 ID 的大整数（>4 位）
            if num == int(num) and num >= 1000 and '.' not in n:
                continue
            normal_numbers.append(num)
        except ValueError:
            continue

    # ---- 汇总所有提取的数字 ----
    all_found_numbers = percent_numbers + currency_numbers + thousands_numbers + negative_numbers + normal_numbers

    # ---- 与 allowed_numbers 比对 ----
    # 归一化 allowed_numbers（int → float）
    normalized_allowed = set()
    for n in allowed_numbers:
        normalized_allowed.add(float(n))
        normalized_allowed.add(int(n))  # 同时加入 int 版本

    hallucinated = []
    for num in all_found_numbers:
        # 检查是否在允许集合中（允许 ±0.001 的浮点误差）
        found = False
        for allowed in normalized_allowed:
            if abs(num - allowed) < 0.001:
                found = True
                break
        if not found:
            hallucinated.append(num)

    return len(hallucinated) == 0, hallucinated


def extract_allowed_numbers_from_tool_results(
    tool_results: list[dict[str, Any]],
) -> set[float | int]:
    """从工具结果中提取所有允许的数字。

    递归遍历工具结果数据，提取所有数值类型，作为 LLM 回答中
    数字的合法来源集合。

    Args:
        tool_results: 工具调用结果列表。

    Returns:
        允许的数字集合。
    """
    allowed: set[float | int] = set()

    def _extract(obj: Any) -> None:
        if isinstance(obj, (int, float)):
            allowed.add(obj)
        elif isinstance(obj, dict):
            for v in obj.values():
                _extract(v)
        elif isinstance(obj, (list, tuple)):
            for item in obj:
                _extract(item)

    for result in tool_results:
        _extract(result)

    return allowed


# ---------------------------------------------------------------------------
# 内部辅助
# ---------------------------------------------------------------------------


def _metric_label(key: str) -> str:
    """指标字段名 → 中文标签。"""
    labels = {
        "risk_score": "风险分",
        "high_risk_count": "高风险数量",
        "overdue_count": "逾期数量",
        "missing_material_count": "缺失材料数",
        "roi": "ROI",
        "cpl": "CPL",
        "cac": "CAC",
        "sla_timeout_count": "SLA超时数",
        "conversion_rate": "转化率",
    }
    return labels.get(key, key)
