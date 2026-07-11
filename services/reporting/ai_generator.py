"""纯 Python 大模型报告解释层。

本模块替代了原先的 Dify Chatflow 调用。V3 改为全同步方案，整个调用链为：

    聚合数据
    → sanitize_report_data()            Python 层面字段脱敏
    → build_chat_messages()             Prompt 构建
    → ReportLLMClient.chat_completion() 同步 LLM 调用
    → _parse_llm_json()                 JSON 提取
    → 合并（只覆盖 summary/explanation）
    → Pydantic content_model 校验
    → 失败 → 修复重试（1 次）
    → 报告内容返回

核心原则不变：业务数字由 SQL 与规则引擎计算，LLM 只负责 summary 和 explanation。
"""

from __future__ import annotations

import json
import logging
from copy import deepcopy
from typing import Any

from services.reporting.llm_client import LLMResponse, ReportLLMClient
from services.reporting.llm_config import settings
from services.reporting.prompt_builder import (
    build_chat_messages,
    build_repair_messages,
    sanitize_report_data,
)
from services.reporting.registry import ReportDefinition
from services.reporting.schemas import DataQuality

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 本地解释（保留不变）
# ---------------------------------------------------------------------------


def _local_explanation(
    report_type: str, content: dict[str, Any], data_quality: DataQuality
) -> dict[str, Any]:
    """未启用 LLM 时的本地确定性解释。

    这不是伪造 AI，而是明确标记的本地模板解释。保障开发环境在 LLM 未配置时
    仍可运行完整报告生成链路。
    """
    result = deepcopy(content)
    result["explanation"] = (
        result.get("explanation")
        or f"{report_type} 报告已由规则引擎生成指标；当前使用本地解释模式，"
        "配置 REPORT_LLM_API_KEY 并将 REPORT_AI_MODE 设为 llm 后可替换为 AI 解释。"
    )
    if data_quality.data_source == "database":
        data_quality.data_source = "local"
    data_quality.warnings.append(
        "REPORT_AI_MODE=local，使用本地确定性解释"
    )
    return result


# ---------------------------------------------------------------------------
# JSON 解析
# ---------------------------------------------------------------------------


def _parse_llm_json(raw_content: str) -> dict[str, Any]:
    """从 LLM 文本响应中提取 JSON 对象。

    兼容三种常见格式：
    1. 裸 JSON：``{"summary": "...", "explanation": "..."}``
    2. Markdown 代码块：`` ```json ... ``` ``
    3. 文本中内嵌 JSON（取第一个 { 到最后一个 }）

    Args:
        raw_content: LLM 返回的原始文本（来自 ``response.choices[0].message.content``）。

    Returns:
        解析后的 dict。

    Raises:
        json.JSONDecodeError: 所有解析策略均失败。
    """
    if not raw_content or not isinstance(raw_content, str):
        raise json.JSONDecodeError("LLM 响应为空或非文本", "", 0)

    text = raw_content.strip()

    # 策略 1：裸 JSON
    if text.startswith("{"):
        return json.loads(text)

    # 策略 2：Markdown 代码块
    if text.startswith("```"):
        text = (
            text.removeprefix("```json")
            .removeprefix("```")
            .removesuffix("```")
            .strip()
        )
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

    # 策略 3：文本中内嵌 JSON（取第一个 { 到最后一个 }）
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        return json.loads(text[start : end + 1])

    raise json.JSONDecodeError(
        f"无法从 LLM 响应中提取 JSON。响应前 200 字符: {text[:200]}",
        text,
        0,
    )


# ---------------------------------------------------------------------------
# 调用日志
# ---------------------------------------------------------------------------

_CALL_COUNTER = 0  # 模块级计数器，区分同一次报告生成中的多次 LLM 调用


def _log_llm_call(
    report_id: int | None,
    call_type: str,
    response: LLMResponse,
    *,
    prompt_version: str = "v2-python-001",
    repair_count: int = 0,
) -> None:
    """记录 LLM 调用详情到 Python logging。

    未来可选升级为写入 ``llm_call_log`` 数据库表。
    日志中不输出 API Key 或完整 Prompt。
    """
    global _CALL_COUNTER  # noqa: PLW0603
    _CALL_COUNTER += 1
    logger.info(
        "LLM_CALL_LOG | call_id=%d report_id=%s call_type=%s provider=%s model=%s "
        "status=%s latency_ms=%d prompt_tokens=%d completion_tokens=%d "
        "retry_count=%d repair_count=%d prompt_version=%s error=%s",
        _CALL_COUNTER,
        str(report_id) if report_id else "-",
        call_type,
        response.provider,
        response.model,
        response.status,
        response.latency_ms,
        response.prompt_tokens,
        response.completion_tokens,
        response.retry_count,
        repair_count,
        prompt_version,
        response.error or "",
    )


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------


def enrich_content_with_ai(
    *,
    definition: ReportDefinition,
    title: str,
    period: dict[str, Any],
    content: dict[str, Any],
    data_quality: DataQuality,
) -> dict[str, Any]:
    """调用大模型补充报告 summary 和 explanation，并做一次 Schema 修复机会。

    本函数签名与 V2 Dify 版本完全兼容，外部调用方（orchestrator）无需修改。

    处理流程：
    1. ``REPORT_AI_MODE=local`` → 本地解释（不变）
    2. ``REPORT_AI_MODE=dify`` → 直接抛出 ConfigurationError
    3. ``REPORT_AI_MODE=llm`` → 纯 Python 流程：
       a) 数据脱敏
       b) Prompt 构建
       c) LLM 调用（含网络重试）
       d) JSON 解析（失败进入修复）
       e) 合并（只覆盖 summary/explanation）
       f) Pydantic 校验（失败进入修复，1 次）
       g) 修复失败 → 抛出异常

    Args:
        definition: 报告类型定义（来自 registry）。
        title: 报告标题。
        period: 统计周期 {"start": "2026-01-01", "end": "2026-01-07"}。
        content: 聚合器输出的完整内容（未经脱敏）。
        data_quality: 数据质量标记。

    Returns:
        包含 AI 生成的 summary/explanation 的完整内容 dict。

    Raises:
        ConfigurationError: REPORT_AI_MODE 设为已废弃的 dify。
        RuntimeError: LLM 调用失败、JSON 解析失败或 Schema 校验在修复后仍失败。
    """
    report_type = definition.report_type
    ai_mode = settings.ai_mode

    # ---- 本地模式 ----
    if ai_mode == "local":
        logger.info("REPORT_AI_MODE=local，使用本地确定性解释")
        return _local_explanation(report_type, content, data_quality)

    # ---- dify 模式已废弃 ----
    if ai_mode == "dify":
        # 本应在 llm_config.resolve_ai_mode() 中就报错，这里作为兜底检查。
        raise RuntimeError(
            "REPORT_AI_MODE=dify 已废弃，请改为 llm。详情见 doc/智能报告模块_纯Python重构计划_v3.md"
        )

    # ---- 纯 Python LLM 流程 ----
    logger.info(
        "LLM 报告解释开始: report_type=%s ai_mode=%s model=%s",
        report_type,
        ai_mode,
        settings.model,
    )

    client = ReportLLMClient()
    prompt_version = settings.prompt_version

    # 1) 数据脱敏
    safe_content = sanitize_report_data(report_type, content)

    # 2) 首次调用
    messages = build_chat_messages(
        definition=definition,
        title=title,
        period=period,
        content=safe_content,
        data_quality=data_quality,
    )
    primary_response = client.chat_completion(messages)
    _log_llm_call(None, "primary", primary_response, prompt_version=prompt_version)

    if primary_response.status != "success":
        raise RuntimeError(
            f"LLM 首次调用失败: {primary_response.error or '未知错误'}"
        )

    # 3) JSON 解析
    try:
        candidate = _parse_llm_json(primary_response.content or "")
    except json.JSONDecodeError as parse_error:
        # 非 JSON 输出 → 进入修复流程
        logger.warning("LLM 首次返回非 JSON，进入修复流程: %s", parse_error)
        return _repair(
            client=client,
            definition=definition,
            title=title,
            period=period,
            safe_content=safe_content,
            data_quality=data_quality,
            invalid_output=primary_response.content or "",
            validation_error=f"JSON 解析失败: {parse_error}",
        )

    # 4) 合并 + 首次校验
    merged = _merge_content(safe_content, candidate)

    try:
        definition.content_model.model_validate(merged)
        logger.info("LLM 报告解释完成（首次通过）: report_type=%s", report_type)
        return merged
    except Exception as first_error:
        logger.warning(
            "首次 Schema 校验失败，进入修复流程: %s", first_error
        )
        return _repair(
            client=client,
            definition=definition,
            title=title,
            period=period,
            safe_content=safe_content,
            data_quality=data_quality,
            invalid_output=candidate,
            validation_error=str(first_error),
        )


# ---------------------------------------------------------------------------
# 内部辅助
# ---------------------------------------------------------------------------


def _merge_content(
    original: dict[str, Any], candidate: dict[str, Any]
) -> dict[str, Any]:
    """合并 LLM 输出到业务内容。

    只允许 LLM 覆盖 summary 和 explanation，业务指标以聚合器原始值为准。
    这个设计保证即使 LLM 输出中包含 metrics/risk_items 等字段，
    也不会覆盖 Python 已计算完成的确定性指标。
    """
    merged = deepcopy(original)
    if not isinstance(candidate, dict):
        logger.warning("LLM 输出不是 dict，无法合并，使用原始内容。candidate_type=%s", type(candidate))
        return merged
    for key in ("summary", "explanation"):
        if candidate.get(key):
            merged[key] = candidate[key]
    return merged


def _repair(
    *,
    client: ReportLLMClient,
    definition: ReportDefinition,
    title: str,
    period: dict[str, Any],
    safe_content: dict[str, Any],
    data_quality: DataQuality,
    invalid_output: Any,
    validation_error: str,
) -> dict[str, Any]:
    """执行一次 Schema / JSON 修复调用。

    所有修复逻辑集中在此函数：
    - 构建修复 Prompt（含 invalid_output + validation_error）
    - LLM 调用
    - JSON 解析
    - 合并 + 校验
    - 仍失败 → 抛出 RuntimeError

    Raises:
        RuntimeError: 修复后 JSON 解析或 Schema 校验仍失败。
    """
    repair_messages = build_repair_messages(
        definition=definition,
        title=title,
        period=period,
        content=safe_content,
        data_quality=data_quality,
        invalid_output=invalid_output,
        validation_error=validation_error,
    )

    repair_response = client.chat_completion(repair_messages)
    _log_llm_call(
        None,
        "repair",
        repair_response,
        prompt_version=settings.prompt_version,
        repair_count=1,
    )

    if repair_response.status != "success":
        raise RuntimeError(
            f"LLM 修复调用失败: {repair_response.error or '未知错误'}"
        )

    try:
        repaired_candidate = _parse_llm_json(repair_response.content or "")
    except json.JSONDecodeError as parse_error:
        raise RuntimeError(
            f"LLM 修复后仍返回非 JSON: {parse_error}"
        ) from parse_error

    repaired = _merge_content(safe_content, repaired_candidate)
    definition.content_model.model_validate(repaired)
    logger.info("LLM 报告解释完成（修复后通过）: report_type=%s", definition.report_type)
    return repaired
