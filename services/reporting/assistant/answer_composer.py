"""智能报告助手 — 证据化回答编排（Iteration 2A.1 增强版）。

本模块负责将工具结果和 LLM 能力结合，生成可信的自然语言回答。

Iteration 2A.1 策略（证据占位符方案 A）：
1. 从工具结果构建结构化 EvidenceItem 列表
2. LLM Prompt 要求使用 {{E1}} {{E2}} 占位符引用证据数字
3. Python 替换占位符为真实值 + 单位
4. 校验证据-实体绑定一致性
5. LLM 失败或输出裸数字 → 确定性模板降级

核心安全约束：
- LLM 不能直接输出业务数字（风险分、ROI、SLA 等）
- 所有业务数字通过 {{E1}} 占位符间接引用
- 数字与实体、指标的绑定关系不可交换
- LLM 失败时确定性模板可用
"""

from __future__ import annotations

import logging
import re
from typing import Any, Optional

from services.reporting.assistant.guardrails import (
    build_evidence_map_structured,
    build_structured_evidence,
    extract_allowed_numbers_from_tool_results,
    replace_evidence_placeholders,
    validate_evidence_binding,
    validate_numbers_in_answer,
)
from services.reporting.assistant.schemas import (
    AssistantToolResult,
    EvidenceItem,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 回答生成入口
# ---------------------------------------------------------------------------


def compose_answer(
    *,
    intent: str,
    tool_results: list[AssistantToolResult],
    data_quality_level: str = "ok",
    llm_enabled: bool = False,
) -> dict[str, Any]:
    """根据意图和工具结果生成证据绑定的回答。

    Args:
        intent: 用户意图。
        tool_results: 所有工具调用结果列表。
        data_quality_level: 数据质量等级。
        llm_enabled: LLM 是否可用。

    Returns:
        dict 包含 answer、evidence、suggested_follow_ups。
    """
    # 提取成功工具数据时保留工具名和 report_id。证据构建需要这两个字段判断
    # 数据来源并绑定原报告；只传 r.data 会让 MetricTrace 退化成空 evidence_id。
    tool_data_list = []
    for result in tool_results:
        if result.status != "success":
            continue
        data = dict(result.data) if isinstance(result.data, dict) else {"value": result.data}
        data.setdefault("tool_name", result.tool_name)
        data.setdefault("report_id", result.report_id)
        tool_data_list.append(data)

    # 获取主工具的 report_id
    primary = tool_results[0] if tool_results else None
    report_id = primary.report_id if primary else 0

    # 构建结构化证据映射（Iteration 2A.1 新版）
    evidence_map = build_evidence_map_structured(tool_data_list, report_id=report_id)
    allowed_numbers = extract_allowed_numbers_from_tool_results(tool_data_list)

    if llm_enabled:
        answer, evidence, used_template = _compose_with_llm(
            intent=intent,
            tool_data_list=tool_data_list,
            evidence_map=evidence_map,
            allowed_numbers=allowed_numbers,
        )
    else:
        answer, evidence = _compose_deterministic(
            intent=intent,
            tool_data_list=tool_data_list,
        )
        # 确定性模板不使用 {{E1}}，但前端仍需要完整证据卡片。优先返回
        # guardrails 生成的结构化证据，避免旧模板留下 evidence_id=""。
        if evidence_map:
            evidence = [item.model_dump() for item in evidence_map.values()]
        used_template = True

    # 注入数据质量限制
    from services.reporting.assistant.guardrails import apply_data_quality_guardrail
    is_analysis = intent in ("drill_down", "explain_risk", "explain_metric")
    answer = apply_data_quality_guardrail(
        answer=answer,
        data_quality_level=data_quality_level,
        is_analysis=is_analysis,
    )

    # 生成建议追问
    suggested_follow_ups = _generate_follow_ups(intent, tool_data_list)

    return {
        "answer": answer,
        "evidence": evidence,
        "suggested_follow_ups": suggested_follow_ups,
    }


# ---------------------------------------------------------------------------
# LLM 模式（证据占位符方案 A）
# ---------------------------------------------------------------------------


def _compose_with_llm(
    *,
    intent: str,
    tool_data_list: list[Any],
    evidence_map: dict[str, EvidenceItem],
    allowed_numbers: set[float | int],
) -> tuple[str, list[dict[str, Any]], bool]:
    """使用 LLM 生成自然语言回答，通过证据占位符绑定数字。

    流程：
    1. 构建含 {{E1}} 占位符约束的 Prompt
    2. LLM 生成使用占位符的回答
    3. Python 替换占位符为真实值
    4. 校验证据绑定 + 数字第二层校验
    5. 失败 → 一次修复 → 仍失败 → 确定性模板

    Returns:
        (answer, evidence_list, used_template) — 回答、证据列表、是否使用了模板。
    """
    try:
        from services.reporting.llm_client import ReportLLMClient

        system_prompt = _build_answer_system_prompt(intent, tool_data_list, evidence_map)
        available_ids = " ".join(f"{{{{{eid}}}}}" for eid in evidence_map)
        user_prompt = (
            "请根据上述数据生成用户友好的中文回答。所有业务数字必须使用证据占位符；"
            f"本轮只允许使用这些占位符：{available_ids or '无'}。"
        )

        client = ReportLLMClient()
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        response = client.chat_completion(
            messages, temperature=0.3, max_tokens=600, json_mode=False
        )

        if response.status != "success" or not response.content:
            logger.warning("LLM 回答生成失败，降级到确定性模板")
            answer, ev = _compose_deterministic(intent=intent, tool_data_list=tool_data_list)
            return answer, ev, True

        raw_answer = response.content.strip()

        # ---- 第一步：证据占位符替换（第一层保护） ----
        replaced_answer, e_warnings = replace_evidence_placeholders(
            answer=raw_answer,
            evidence_map=evidence_map,
        )

        if e_warnings:
            logger.warning("证据占位符替换警告: %s", e_warnings)

        # ---- 第二步：检查是否有裸业务数字（绕过了占位符） ----
        naked_check = _check_naked_business_numbers(
            answer=raw_answer,
            evidence_map=evidence_map,
        )

        if naked_check["has_naked"]:
            logger.warning("LLM 回答包含裸业务数字（未使用占位符）: %s", naked_check["naked_numbers"])
            # 尝试一次修复
            repair_prompt = (
                f"上述回答中包含未使用证据占位符的业务数字：{naked_check['naked_numbers']}。\n"
                "请修改回答，将所有业务数字替换为 {{E1}} {{E2}} 格式的占位符。\n"
                "例如：'风险分为 {{E1}}' 而不是 '风险分为 90'。"
            )
            repair_messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
                {"role": "assistant", "content": raw_answer},
                {"role": "user", "content": repair_prompt},
            ]
            repair_response = client.chat_completion(
                repair_messages, temperature=0.1, max_tokens=600, json_mode=False
            )

            if repair_response.status == "success" and repair_response.content:
                raw_answer = repair_response.content.strip()
                replaced_answer, e_warnings = replace_evidence_placeholders(
                    answer=raw_answer,
                    evidence_map=evidence_map,
                )
                naked_check = _check_naked_business_numbers(
                    answer=raw_answer,
                    evidence_map=evidence_map,
                )

            if naked_check["has_naked"]:
                logger.warning("修复后仍包含裸业务数字，使用确定性模板")
                answer, ev = _compose_deterministic(intent=intent, tool_data_list=tool_data_list)
                return answer, ev, True

        # ---- 第三步：证据绑定校验 ----
        is_valid_binding, binding_errors = validate_evidence_binding(
            answer=raw_answer,
            evidence_map=evidence_map,
        )

        if not is_valid_binding:
            logger.warning("证据绑定校验失败: %s", binding_errors)
            # 对绑定错误也尝试修复一次
            repair_prompt = (
                f"证据绑定错误：{'; '.join(binding_errors)}。\n"
                "请检查占位符与实体的对应关系，确保每个 {{E1}} 引用的实体与文本描述一致。"
            )
            repair_messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
                {"role": "assistant", "content": raw_answer},
                {"role": "user", "content": repair_prompt},
            ]
            repair_response = client.chat_completion(
                repair_messages, temperature=0.1, max_tokens=600, json_mode=False
            )

            if repair_response.status == "success" and repair_response.content:
                raw_answer = repair_response.content.strip()
                replaced_answer, e_warnings = replace_evidence_placeholders(
                    answer=raw_answer,
                    evidence_map=evidence_map,
                )
                is_valid_binding, binding_errors = validate_evidence_binding(
                    answer=raw_answer,
                    evidence_map=evidence_map,
                )

            if not is_valid_binding:
                logger.warning("修复后证据绑定仍失败，使用确定性模板")
                answer, ev = _compose_deterministic(intent=intent, tool_data_list=tool_data_list)
                return answer, ev, True

        # ---- 第四步：数字第二层校验（兜底保护） ----
        is_valid_nums, hallucinated = validate_numbers_in_answer(
            answer=replaced_answer,
            allowed_numbers=allowed_numbers,
        )

        if not is_valid_nums:
            logger.warning("LLM 回答包含幻觉数字: %s", hallucinated)
            # 尽力而为：如果占位符替换已正确完成，这些"幻觉"数字可能是
            # 日期/ID 的误报。只记录日志，不拒绝回答。
            # 但如果是明确的业务数字超出允许范围，则降级。
            business_hallucinated = [
                n for n in hallucinated
                if not _is_likely_identifier(n, replaced_answer)
            ]
            if business_hallucinated:
                logger.warning("确认的业务数字幻觉: %s，降级到模板", business_hallucinated)
                answer, ev = _compose_deterministic(intent=intent, tool_data_list=tool_data_list)
                return answer, ev, True

        # ---- 构建证据列表 ----
        evidence = _build_evidence_list(evidence_map, raw_answer)

        return replaced_answer, evidence, False

    except Exception as exc:
        logger.warning("LLM 回答生成异常: %s，降级到确定性模板", exc)
        answer, ev = _compose_deterministic(intent=intent, tool_data_list=tool_data_list)
        return answer, ev, True


def _check_naked_business_numbers(
    *,
    answer: str,
    evidence_map: dict[str, EvidenceItem],
) -> dict[str, Any]:
    """检查 LLM 回答中是否有绕过占位符的业务数字。

    业务数字的判断标准：
    1. 数字的值与某个 EvidenceItem.value 匹配
    2. 且该数字没有用 {{Ex}} 包裹

    Args:
        answer: LLM 原始回答（替换占位符前）。
        evidence_map: 证据映射。

    Returns:
        {"has_naked": bool, "naked_numbers": list}。
    """
    # 获取所有证据值
    evidence_values = set()
    for item in evidence_map.values():
        if isinstance(item.value, (int, float)):
            evidence_values.add(item.value)

    # 移除占位符文本后检查裸数字
    cleaned = re.sub(r'\{\{\w+\}\}', ' ', answer)

    # 提取所有数字
    numbers_in_text = re.findall(r'\b(\d+(?:\.\d+)?)\b', cleaned)

    naked = []
    for n_str in numbers_in_text:
        try:
            n = float(n_str)
            # 跳过日期/ID 类的大数字
            if n_str.isdigit() and len(n_str) >= 4:
                continue
            # 如果数字值在证据集合中，且以裸数字形式出现 → 违规
            for ev in evidence_values:
                if abs(n - float(ev)) < 0.001:
                    naked.append(n)
                    break
        except ValueError:
            continue

    return {
        "has_naked": len(naked) > 0,
        "naked_numbers": list(set(naked)),
    }


def _is_likely_identifier(num: float, answer: str) -> bool:
    """判断数字是否更可能是标识符而非业务数字。"""
    # Markdown/中文列表序号只承担排版作用，不是工具返回的业务量。若不排除，
    # 模型生成的“1. 原因、2. 建议”会被数字兜底误判为幻觉并强制降级。
    if num == int(num) and re.search(
        rf"(?m)^\s*{int(num)}\s*[.、)]\s*\S", answer
    ):
        return True
    # 整数且 >= 1000 → 可能是 ID
    if num == int(num) and num >= 1000:
        return True
    # 检查是否在日期上下文附近
    if re.search(rf'\b{int(num)}\b\s*[年/-]', answer):
        return True
    return False


def _build_answer_system_prompt(
    intent: str,
    tool_data_list: list[Any],
    evidence_map: dict[str, EvidenceItem],
) -> str:
    """构建 LLM 回答生成的 System Prompt（Iteration 2A.1 证据占位符版）。"""
    # 整理证据索引（带标签）
    evidence_lines = []
    for eid, item in evidence_map.items():
        unit_str = f" {item.unit}" if item.unit else ""
        evidence_lines.append(
            f"[{eid}] {item.label} = {item.value}{unit_str}"
            f"（来源: 报告 #{item.source_report_id}, 实体: {item.entity_id or 'N/A'}）"
        )

    evidence_text = "\n".join(evidence_lines) if evidence_lines else "（无额外数据）"
    allowed_placeholders = "、".join(f"{{{{{eid}}}}}" for eid in evidence_map) or "无"

    # 工具数据摘要
    data_summary = _summarize_tool_data(tool_data_list)

    return (
        "你是海外留学教育服务平台的智能报告助手。\n\n"
        "**回答规则（必须严格遵守）：**\n"
        "1. 所有业务数字（风险分、数量、金额、百分比等）必须使用证据占位符引用，禁止直接写出数字。\n"
        f"   本轮唯一允许的占位符是：{allowed_placeholders}；禁止引用未列出的 E 编号。\n"
        "2. 每个占位符有固定的含义（如 E1=申请 A1024 风险分=90），不能交换使用。\n"
        "3. 工具数据中的文字结论可以引用，但不能编造数据中不存在的风险原因。\n"
        "4. 行动建议必须标明是\"建议\"，不能表述为确定性事实。\n"
        "5. 回答使用中文，简洁、结构清晰。\n"
        "6. 如果数据包含多个实体，使用列表格式。\n"
        "7. 禁止在回答中直接写风险分、ROI、CPL、CAC、SLA超时数、转化率等业务数字的具体数值。\n\n"
        f"**当前意图**: {intent}\n\n"
        f"**可用证据**:\n{evidence_text}\n\n"
        f"**工具数据**:\n{data_summary}\n"
    )


def _summarize_tool_data(tool_data_list: list[Any]) -> str:
    """将工具数据转为 LLM 可读的摘要。"""
    parts = []
    for i, data in enumerate(tool_data_list):
        if not isinstance(data, dict):
            continue
        safe = dict(data)
        if "referenced_entities" in safe:
            safe["referenced_entities_count"] = len(safe.pop("referenced_entities", []))
        if "metric_traces" in safe:
            safe["metric_traces_count"] = len(safe.pop("metric_traces", []))
        if "items" in safe:
            # 对 items 中的每个 item 去掉嵌套对象
            safe_items = []
            for item in safe.get("items", []):
                if isinstance(item, dict):
                    si = dict(item)
                    si.pop("metric_traces", None)
                    safe_items.append(si)
            safe["items"] = safe_items
        safe_str = str(safe)
        if len(safe_str) > 800:
            safe_str = safe_str[:800] + "..."
        parts.append(f"[工具结果 {i+1}] {safe_str}")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# 确定性模板降级
# ---------------------------------------------------------------------------


def _compose_deterministic(
    *,
    intent: str,
    tool_data_list: list[Any],
) -> tuple[str, list[dict[str, Any]]]:
    """LLM 不可用时使用确定性模板生成回答。"""
    if intent == "query_report_status":
        return _template_status(tool_data_list)
    elif intent == "drill_down":
        return _template_drill_down(tool_data_list)
    elif intent == "explain_risk":
        return _template_explain_risk(tool_data_list)
    elif intent == "explain_metric":
        return _template_explain_metric(tool_data_list)
    elif intent == "query_data_quality":
        return _template_data_quality(tool_data_list)
    else:
        return _template_generic(tool_data_list)


def _template_status(tool_data_list: list[Any]) -> tuple[str, list[dict[str, Any]]]:
    data = tool_data_list[0] if tool_data_list else {}
    status = data.get("status", "unknown")
    status_text = {
        "pending": "排队等待生成",
        "generating": "正在生成中",
        "completed": "已完成",
        "failed": "生成失败",
    }.get(status, status)

    answer = f"报告 #{data.get('report_id')} 当前状态：{status_text}。"
    if data.get("suggest_retry"):
        answer += " 建议使用重试功能重新生成。"

    evidence = [{"source": "query_report_status", "reference": f"report_id={data.get('report_id')}", "value": status}]
    return answer, evidence


def _template_drill_down(tool_data_list: list[Any]) -> tuple[str, list[dict[str, Any]]]:
    data = tool_data_list[0] if tool_data_list else {}
    items = data.get("items", [])
    if not items:
        return "当前没有风险明细数据。", []

    lines = [f"当前风险最高的 {len(items)} 个申请："]
    evidence = []
    for i, item in enumerate(items):
        app_id = item.get("application_id", "?")
        score = item.get("risk_score", 0)
        level = item.get("risk_level", "?")
        reasons = item.get("risk_reasons", [])
        reasons_text = "、".join(reasons[:3]) if reasons else "无详细原因"
        lines.append(f"{i+1}. 申请 #{app_id}：风险分 {score}（{level}），{reasons_text}")
        evidence.append({
            "evidence_id": f"E{i+1}",
            "entity_type": "application",
            "entity_id": str(app_id),
            "metric_name": "risk_score",
            "label": f"申请 #{app_id} 风险分",
            "value": score,
            "unit": "分",
            "source": "get_application_risk_items",
        })

    answer = "\n".join(lines)
    return answer, evidence


def _template_explain_risk(tool_data_list: list[Any]) -> tuple[str, list[dict[str, Any]]]:
    data = tool_data_list[0] if tool_data_list else {}
    risk_reasons = data.get("risk_reasons", [])
    score = data.get("risk_score", 0)
    level = data.get("risk_level", "?")
    missing = data.get("missing_materials", [])
    next_action = data.get("next_action", "")
    app_id = data.get("application_id", "?")

    parts = [f"申请 #{app_id} 风险分为 {score}（{level}）。"]
    if risk_reasons:
        parts.append("风险原因：")
        for r in risk_reasons:
            parts.append(f"  - {r}")
    if missing:
        parts.append(f"缺失材料：{'、'.join(missing)}")
    if next_action:
        parts.append(f"建议：{next_action}")

    evidence = [{
        "evidence_id": "E1",
        "entity_type": "application",
        "entity_id": str(app_id),
        "metric_name": "risk_score",
        "label": f"申请 #{app_id} 风险分",
        "value": score,
        "unit": "分",
        "source": "get_application_risk_detail",
    }]
    return "\n".join(parts), evidence


def _template_explain_metric(tool_data_list: list[Any]) -> tuple[str, list[dict[str, Any]]]:
    data = tool_data_list[0] if tool_data_list else {}
    metric = data.get("metric_name", "?")
    formula = data.get("formula", "未提供")
    sources = data.get("source_tables", [])
    filters = data.get("filters", {})

    parts = [f"指标 '{metric}' 的追溯信息："]
    parts.append(f"  计算公式：{formula}")
    parts.append(f"  来源表：{', '.join(sources) if sources else '未指定'}")
    if filters:
        parts.append(f"  过滤条件：{filters}")

    evidence = [{"source": "get_metric_trace", "reference": f"metric={metric}", "value": formula}]
    return "\n".join(parts), evidence


def _template_data_quality(tool_data_list: list[Any]) -> tuple[str, list[dict[str, Any]]]:
    data = tool_data_list[0] if tool_data_list else {}
    level = data.get("level", "ok")
    desc = data.get("level_description", "未知")
    warnings = data.get("warnings", [])
    limitations = data.get("limitations", [])

    parts = [f"报告数据质量：{desc}"]
    if warnings:
        parts.append("注意事项：")
        for w in warnings:
            parts.append(f"  - {w}")
    if limitations:
        parts.append("当前限制：")
        for l in limitations:
            parts.append(f"  - {l}")

    evidence = [{"source": "get_report_data_quality", "reference": "level", "value": level}]
    return "\n".join(parts), evidence


def _template_generic(tool_data_list: list[Any]) -> tuple[str, list[dict[str, Any]]]:
    return "已处理你的请求。", []


# ---------------------------------------------------------------------------
# 内部辅助
# ---------------------------------------------------------------------------


def _build_evidence_list(
    evidence_map: dict[str, EvidenceItem],
    raw_answer: str,
) -> list[dict[str, Any]]:
    """从 evidence_map 和 LLM 回答构建最终证据列表。

    只包含回答中实际引用的证据。
    """
    used_eids = set(re.findall(r'\{\{(\w+)\}\}', raw_answer))
    evidence = []
    for eid in used_eids:
        if eid in evidence_map:
            item = evidence_map[eid]
            evidence.append({
                "evidence_id": item.evidence_id,
                "entity_type": item.entity_type,
                "entity_id": item.entity_id,
                "metric_name": item.metric_name,
                "label": item.label,
                "value": item.value,
                "unit": item.unit,
                "source_report_id": item.source_report_id,
                "source": item.source,
                "reference": item.reference,
            })
    # 如果没有占位符引用，返回所有证据
    if not evidence:
        for eid, item in evidence_map.items():
            evidence.append({
                "evidence_id": item.evidence_id,
                "entity_type": item.entity_type,
                "entity_id": item.entity_id,
                "metric_name": item.metric_name,
                "label": item.label,
                "value": item.value,
                "unit": item.unit,
                "source_report_id": item.source_report_id,
                "source": item.source,
                "reference": item.reference,
            })
    return evidence


# ══════════════════════════════════════════════════════════════════════════════
# 跨报告关系回答编排（Iteration 3 — Task 7）
# ══════════════════════════════════════════════════════════════════════════════


def compose_relationship_answer(
    *,
    tool_results: list[Any],
    llm_enabled: bool = False,
) -> dict[str, Any]:
    """为跨报告分析生成四区结构化回答。

    回答分为四个区块（RelationshipSections）：
    - confirmed_facts：来自 Evidence 的确定性数值，不由 LLM 生成
    - related_signals：同一时间段内同时变化的指标信号
    - possible_explanations：可能解释，必须包含不确定性措辞
    - cannot_confirm：无法确认的事项——Python 强制插入，LLM 无法删除

    因果控制：
    - 禁止使用"导致""证明""必然""根本原因是""就是因为"等因果断言词
    - LLM 输出中包含禁止词的语句被移入 ``cannot_confirm`` 区块
    - 确定性模板自带不确定性措辞和无法确认说明

    Args:
        tool_results: 跨报告比较工具结果列表（包含 comparison、evidence、DataQuality）。
        llm_enabled: 是否启用 LLM 生成关系分析文本。

    Returns:
        dict 包含 answer（自然语言回答）、evidence（证据列表）、
        relationship_sections（四区结构化分析）。
    """
    # 提取工具数据及证据
    evidence_list: list[dict[str, Any]] = []
    comparison_items: list[dict[str, Any]] = []

    for result in tool_results:
        data = getattr(result, "data", result) if not isinstance(result, dict) else result
        if isinstance(data, dict):
            evidence_list.extend(data.get("evidence", []))
            comparison_items.extend(data.get("comparison", []))

    # ── 从证据确定性生成已确认事实 ──
    confirmed_facts = _build_confirmed_facts(comparison_items, evidence_list)

    if llm_enabled:
        try:
            from services.reporting.llm_client import ReportLLMClient

            system_prompt = _build_relationship_system_prompt(comparison_items, evidence_list)
            user_prompt = (
                "请根据上述跨报告比较数据，生成相关信号和可能解释两个区块的中文分析。"
                "相关信号：哪些指标在同一周期内同时变化（不声称因果）。"
                "可能解释：这些变化可能的业务含义（必须使用不确定措辞）。"
                '不要使用"导致""证明""必然""根本原因是""就是因为"等词。'
            )

            client = ReportLLMClient()
            response = client.chat_completion(
                [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.3, max_tokens=500, json_mode=False,
            )

            if response.status == "success" and response.content:
                raw_answer = response.content.strip()
                related_signals, possible_explanations = _parse_llm_sections(raw_answer)
            else:
                logger.warning("LLM 关系分析失败，降级到确定性模板")
                raw_answer = ""
                related_signals, possible_explanations = [], []

        except Exception as exc:
            logger.warning("LLM 关系分析异常: %s，降级到确定性模板", exc)
            raw_answer = ""
            related_signals, possible_explanations = [], []
    else:
        raw_answer = ""
        related_signals, possible_explanations = [], []

    # ── 确定性模板补齐：LLM 为空时必须用模板填充 ──
    if not related_signals:
        related_signals = _build_template_related_signals(comparison_items)
    if not possible_explanations:
        possible_explanations = _build_template_possible_explanations(comparison_items)

    # ── 因果语言校验与清理 ──
    from services.reporting.assistant.guardrails import (
        FORBIDDEN_CAUSAL_PATTERNS,
        validate_causal_language,
    )

    cannot_confirm: list[str] = []

    # 扫描 LLM 输出的相关信号和可能解释
    for section_items, section_name in [
        (related_signals, "相关信号"),
        (possible_explanations, "可能解释"),
    ]:
        cleaned: list[str] = []
        for item in section_items:
            violations = validate_causal_language(item)
            if violations:
                # 将原句移入无法确认区块，并说明原因
                terms_text = '、'.join(violations)
                cannot_confirm.append(
                    f"原{section_name}声明“{item}”"
                    f"使用了禁止的因果断言词（{terms_text}），不能作为确定性结论。"
                )
                # 尝试去除禁止词保留信号
                sanitized = item
                for term in violations:
                    sanitized = sanitized.replace(term, "与…相关")
                if sanitized != item:
                    cleaned.append(sanitized)
            else:
                cleaned.append(item)

        if section_name == "相关信号":
            related_signals = cleaned
        else:
            possible_explanations = cleaned

    # ── Python 强制插入无法确认说明 ──
    cannot_confirm.append(
        "跨报告分析只能识别同一周期内指标的共同变化，不能证明一个指标的变化"
        "导致了另一个指标的变化。以上相关信号和可能解释仅供业务参考，"
        "不应作为因果关系的确定性证据。"
    )

    # ── 构建自然语言回答 ──
    answer_parts: list[str] = []

    if confirmed_facts:
        answer_parts.append("📊 **已确认事实**")
        for fact in confirmed_facts:
            answer_parts.append(f"- {fact}")

    if related_signals:
        answer_parts.append("")
        answer_parts.append("📡 **相关信号**")
        for signal in related_signals:
            answer_parts.append(f"- {signal}")

    if possible_explanations:
        answer_parts.append("")
        answer_parts.append("💡 **可能解释**")
        for exp in possible_explanations:
            answer_parts.append(f"- {exp}")

    if cannot_confirm:
        answer_parts.append("")
        answer_parts.append("⚠️ **无法确认**")
        for item in cannot_confirm:
            answer_parts.append(f"- {item}")

    answer = "\n".join(answer_parts)

    relationship_sections = {
        "confirmed_facts": confirmed_facts,
        "related_signals": related_signals,
        "possible_explanations": possible_explanations,
        "cannot_confirm": cannot_confirm,
    }

    return {
        "answer": answer,
        "evidence": evidence_list,
        "relationship_sections": relationship_sections,
    }


# ══════════════════════════════════════════════════════════════════════════════
# 四区回答内部辅助
# ══════════════════════════════════════════════════════════════════════════════


def _build_confirmed_facts(
    comparison_items: list[dict[str, Any]],
    evidence_list: list[dict[str, Any]],
) -> list[str]:
    """从比较数据和证据中确定性提取已确认事实。

    已确认事实只包含可直接从数据中计算出的陈述，不包含推理或因果。
    """
    facts: list[str] = []
    for comp in comparison_items:
        label = comp.get("label", comp.get("metric_name", "指标"))
        unit = comp.get("unit", "")
        current = comp.get("current_value")
        previous = comp.get("previous_value")
        delta = comp.get("delta")
        direction = comp.get("direction", "unknown")
        dimension = comp.get("dimension", {})

        dim_str = f"（{'、'.join(f'{k}={v}' for k, v in dimension.items())}）" if dimension else ""

        fact_parts = [f"{label}{dim_str}："]
        if current is not None:
            fact_parts.append(f"当前周期为 {current}{unit}")
        if previous is not None:
            fact_parts.append(f"，上一周期为 {previous}{unit}")
        if delta is not None and direction != "unknown":
            direction_text = {"up": "上升", "down": "下降", "flat": "持平"}.get(direction, "变化")
            fact_parts.append(f"，{direction_text}了 {abs(delta)}{unit}")
        elif delta is not None:
            fact_parts.append(f"，变化量为 {delta}{unit}")

        facts.append("".join(fact_parts))

    # 如果比较数据中没有维度信息，补充证据层面的摘要
    if not facts and evidence_list:
        current_ev = [e for e in evidence_list if e.get("comparison_role") == "current"]
        previous_ev = [e for e in evidence_list if e.get("comparison_role") == "previous"]
        if current_ev:
            cur_val = current_ev[0]
            facts.append(
                f"{cur_val.get('label', '当前周期')}为 {cur_val.get('value')}{cur_val.get('unit', '')}"
            )
        if previous_ev:
            prev_val = previous_ev[0]
            facts.append(
                f"{prev_val.get('label', '上一周期')}为 {prev_val.get('value')}{prev_val.get('unit', '')}"
            )

    if not facts:
        facts.append("当前没有足够数据生成已确认事实。")

    return facts


def _build_template_related_signals(
    comparison_items: list[dict[str, Any]],
) -> list[str]:
    """从比较数据生成确定性相关信号（LLM 不可用时的模板）。"""
    signals: list[str] = []
    for comp in comparison_items:
        label = comp.get("label", comp.get("metric_name", "指标"))
        direction = comp.get("direction", "unknown")
        unit = comp.get("unit", "")
        delta = comp.get("delta")

        if direction == "up" and delta is not None:
            signals.append(f"{label}在本周期上升了 {abs(delta)}{unit}，建议关注是否与其他指标变化同步。")
        elif direction == "down" and delta is not None:
            signals.append(f"{label}在本周期下降了 {abs(delta)}{unit}，可结合其他报表分析原因。")
        elif direction == "flat":
            signals.append(f"{label}在本周期与上一周期基本持平，未见显著变化。")
        else:
            signals.append(f"{label}的变化方向不确定，可能因数据质量限制无法判定趋势。")

    if not signals:
        signals.append("当前比较数据不足以生成明确的相关信号。")

    return signals


def _build_template_possible_explanations(
    comparison_items: list[dict[str, Any]],
) -> list[str]:
    """从比较数据生成含不确定性措辞的可能解释（LLM 不可用时的模板）。"""
    explanations: list[str] = []
    for comp in comparison_items:
        label = comp.get("label", comp.get("metric_name", "指标"))
        dimension = comp.get("dimension", {})
        dim_str = f"（{'、'.join(f'{k}={v}' for k, v in dimension.items())}）" if dimension else ""
        explanations.append(
            f"{label}{dim_str}的变化可能与业务周期、资源分配或外部因素有关，"
            "有待结合更多数据进一步确认。"
        )

    if not explanations:
        explanations.append("可能受多种因素影响，有待获取更多周期数据后进一步分析。")

    # 每个解释必须包含不确定性措辞
    validated: list[str] = []
    for exp in explanations:
        has_uncertainty = any(
            word in exp for word in ("可能", "或许", "有待", "不一定", "不能排除", "建议关注")
        )
        if not has_uncertainty:
            exp = f"可能{exp}"
        validated.append(exp)

    return validated


def _build_relationship_system_prompt(
    comparison_items: list[dict[str, Any]],
    evidence_list: list[dict[str, Any]],
) -> str:
    """构建跨报告关系分析的 LLM System Prompt。"""
    comp_summary = "\n".join(
        f"- {c.get('label', c.get('metric_name', '?'))}: "
        f"当前={c.get('current_value', '?')}{c.get('unit', '')}, "
        f"上期={c.get('previous_value', '?')}{c.get('unit', '')}, "
        f"变化={c.get('delta', '?')}{c.get('unit', '')}, "
        f"方向={c.get('direction', '?')}"
        for c in comparison_items
    )

    return (
        '你是海外留学教育服务平台的智能报告助手，负责跨报告关系分析。\n\n'
        '**回答规则（必须严格遵守）：**\n'
        '1. 已确认事实由 Python 从证据中提取，你不需要重复生成。\n'
        '2. 你只需生成[相关信号]和[可能解释]两个区块。\n'
        '3. 相关信号：描述哪些指标在同一周期内同步变化（不声称因果）。\n'
        '4. 可能解释：推测变化的可能业务含义，必须使用[可能][或许][有待确认]等不确定措辞。\n'
        '5. 严禁使用以下词：导致、证明、必然、根本原因是、就是因为。\n'
        '6. 不要在回答中直接输出数字，使用定性描述即可。\n'
        '7. 回答使用中文，简洁、结构清晰。\n\n'
        f'**比较数据摘要**:\n{comp_summary}\n'
    )


def _parse_llm_sections(raw_answer: str) -> tuple[list[str], list[str]]:
    """解析 LLM 输出中的相关信号和可能解释区块。

    按段落级标记开拆分；如果 LLM 未按格式输出，则将全文按句号拆分后
    分配到相关信号落入，可能解释留空由模板补齐。
    """
    related_signals: list[str] = []
    possible_explanations: list[str] = []

    # 尝试按常见标记拆分
    import re
    # 匹配"相关信号"或"可能解释"标记后的内容
    patterns = [
        (r'相关信号[：:]\s*', 'signals'),
        (r'可能解释[：:]\s*', 'explanations'),
    ]

    # 简单策略：按段落拆分
    paragraphs = [p.strip() for p in raw_answer.split("\n\n") if p.strip()]
    if not paragraphs:
        paragraphs = [p.strip() for p in raw_answer.split("\n") if p.strip()]

    current_section = 'signals'  # 默认归入相关信号
    for para in paragraphs:
        lower = para.lower()
        if '相关信号' in lower or '关联信号' in lower or '同步信号' in lower:
            current_section = 'signals'
            # 提取标记后的内容
            cleaned = re.sub(r'^[#\-\*\s]*相关信号[：:]*\s*', '', para, flags=re.IGNORECASE)
            if cleaned:
                related_signals.append(cleaned)
            continue
        elif '可能解释' in lower or '可能原因' in lower or '分析解释' in lower:
            current_section = 'explanations'
            cleaned = re.sub(r'^[#\-\*\s]*可能解释[：:]*\s*', '', para, flags=re.IGNORECASE)
            if cleaned:
                possible_explanations.append(cleaned)
            continue
        else:
            if current_section == 'signals':
                related_signals.append(para)
            else:
                possible_explanations.append(para)

    return related_signals, possible_explanations


def _generate_follow_ups(intent: str, tool_data_list: list[Any]) -> list[str]:
    """根据意图和数据生成建议追问。"""
    data = tool_data_list[0] if tool_data_list else {}

    follow_ups_map = {
        "drill_down": ["第一个为什么这么高？", "这个风险分怎么计算的？", "这个报告的数据可靠吗？"],
        "explain_risk": ["这个风险分怎么计算的？", "有哪些缺失材料需要补充？"],
        "explain_metric": ["受影响的有哪些申请？", "这个报告的数据可靠吗？"],
        "query_data_quality": ["最严重的是哪几个？", "有哪些需要注意的数据问题？"],
        "query_report_status": ["报告完成后可以查看哪些内容？"],
    }

    return follow_ups_map.get(intent, [])[:3]
