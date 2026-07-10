"""Dify Chatflow / AI 报告解释层。

V2 的关键原则：业务数字先由 SQL 和规则引擎在后端算好，Dify Chatflow
只负责把这些数字解释成人能看懂的 summary 和 explanation。

所以这个文件的输入是：

* report_type
* schema_version
* report_title
* period
* aggregated_data
* expected_schema
* data_quality

输出只允许补充 ``summary``、``explanation`` 这类解释性字段。即使 Dify 不可用，
系统也会明确标记本地解释模式，避免“隐式 Mock”被当成正式 AI 结果。
"""

from __future__ import annotations

import json
import os
from copy import deepcopy
from typing import Any

import httpx

from config import DIFY_API_KEY, DIFY_API_URL
from services.reporting.registry import ReportDefinition
from services.reporting.schemas import DataQuality


def _local_explanation(report_type: str, content: dict[str, Any], data_quality: DataQuality) -> dict[str, Any]:
    """未启用 Dify 时的本地说明。

    这不是伪造 AI，而是明确标记的本地模板解释。它保证开发环境和课堂演示
    不因为外部 Dify 没配置而完全不可用。
    """

    result = deepcopy(content)
    result["explanation"] = (
        result.get("explanation")
        or f"{report_type} 报告已由规则引擎生成指标；当前使用本地解释模式，"
        "Dify Chatflow 配置后可替换为 AI 解释。"
    )
    if data_quality.data_source == "database":
        data_quality.data_source = "local"
    data_quality.warnings.append("REPORT_AI_MODE 未设置为 dify，使用本地确定性解释")
    return result


def _call_dify_chatflow(inputs: dict[str, Any], query: str, timeout: int = 180) -> dict[str, Any]:
    """报告 V2 专用 Dify Chatflow 调用。

    ``REPORT_AI_MODE=dify`` 在报告模块里代表“调用 Dify Chatflow”。这里固定
    使用 Chatflow 的 ``/chat-messages`` 接口，而不是旧的 Workflow 调用入口。
    后端把聚合数据放进 ``inputs``，把生成意图放进
    ``query``，从而让项目契约和当前实现保持一致。
    """

    url = f"{DIFY_API_URL.rstrip('/')}/chat-messages"
    payload = {
        "inputs": inputs,
        "query": query,
        "response_mode": "blocking",
        "user": "report-service",
    }
    headers = {"Authorization": f"Bearer {DIFY_API_KEY}", "Content-Type": "application/json"}
    with httpx.Client(timeout=timeout) as client:
        response = client.post(url, json=payload, headers=headers)
    response.raise_for_status()
    return response.json()


def _parse_dify_chatflow_content(response: dict[str, Any]) -> dict[str, Any]:
    """Parse report explanation content from a Dify Chatflow response.

    Chatflow blocking responses normally place model text in ``answer``. During
    real integration, the model may return either raw JSON or a JSON code block,
    so the parser accepts both forms and still lets Pydantic do the final schema
    validation later.
    """

    candidate = response.get("answer") or response.get("report_content") or response.get("content") or response
    if isinstance(candidate, dict):
        return candidate
    if not isinstance(candidate, str):
        return {}

    text = candidate.strip()
    if text.startswith("```"):
        text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start : end + 1])
        raise


def enrich_content_with_ai(
    *,
    definition: ReportDefinition,
    title: str,
    period: dict[str, Any],
    content: dict[str, Any],
    data_quality: DataQuality,
) -> dict[str, Any]:
    """调用 Dify Chatflow 补充报告解释，并做一次 Schema 修复机会。

    如果环境变量 ``REPORT_AI_MODE=dify`` 且配置了 ``DIFY_API_KEY``，才会调用
    报告 Chatflow。否则走明确标记的本地解释模式。
    """

    ai_mode = os.getenv("REPORT_AI_MODE", "local").lower()
    if ai_mode != "dify":
        return _local_explanation(definition.report_type, content, data_quality)
    if not DIFY_API_KEY:
        raise RuntimeError("REPORT_AI_MODE=dify 但 DIFY_API_KEY 未配置")

    expected_schema = definition.content_model.model_json_schema()
    chatflow_inputs = {
        "report_type": definition.report_type,
        "schema_version": definition.schema_version,
        "report_title": title,
        "period": period,
        "aggregated_data": content,
        "expected_schema": expected_schema,
        "data_quality": data_quality.model_dump(),
    }

    chatflow_query = (
        "请基于 inputs 中的后端聚合数据生成本报告的 summary 和 explanation。"
        "禁止改写 metrics、risk_items、action_checklist 等任何业务数字或明细。"
        "请只返回 JSON 对象。"
    )
    response = _call_dify_chatflow(inputs=chatflow_inputs, query=chatflow_query, timeout=180)
    candidate = _parse_dify_chatflow_content(response)

    merged = deepcopy(content)
    # 只允许 AI 修改解释性字段，业务指标仍以聚合器为准。
    for key in ("summary", "explanation"):
        if isinstance(candidate, dict) and candidate.get(key):
            merged[key] = candidate[key]

    try:
        definition.content_model.model_validate(merged)
        return merged
    except Exception as first_error:
        # 给 Dify 一次修复机会；仍失败就抛出，让任务进入 failed。
        repair_inputs = {
            **chatflow_inputs,
            "invalid_output": candidate,
            "validation_error": str(first_error),
        }
        repair_query = (
            "上一次输出没有通过后端 Schema 校验。请根据 inputs.validation_error 修复，"
            "仍然只能返回 JSON 对象，并且只能补充 summary 和 explanation。"
        )
        repair_response = _call_dify_chatflow(inputs=repair_inputs, query=repair_query, timeout=180)
        repaired = _parse_dify_chatflow_content(repair_response)
        for key in ("summary", "explanation"):
            if isinstance(repaired, dict) and repaired.get(key):
                merged[key] = repaired[key]
        definition.content_model.model_validate(merged)
        return merged
