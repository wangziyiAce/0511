"""
教育服务系统 — Dify AI 平台调用客户端
===========================================
封装对 Dify Workflow API 的 HTTP 调用。

Dify 在本系统中的角色（架构文档 1.3 节）:
  Dify = 大脑：负责意图识别、对话生成、RAG 检索、工作流编排

调用方向:
  FastAPI → Dify（本文件负责）: 触发 AI 客户研判、报告生成等工作流
  Dify → FastAPI（routers 处理）: Dify HTTP 节点回调我们的业务接口

使用场景:
  - 客户画像研判: POST /workflows/run {workflow: "customer_profiling", inputs: {...}}
  - 智能报告生成: POST /workflows/run {workflow: "report_generation", inputs: {...}}
  - 员工日报总结: POST /workflows/run {workflow: "daily_summary", inputs: {...}}

API 认证:
  使用 Dify 应用 API Key（Bearer Token），在 .env 中配置 DIFY_API_KEY。
  每个 Dify 应用有独立的 API Key，不同工作流可能需要不同的 Key。
  当前 MVP 阶段统一使用一个 Key。

超时策略:
  Dify HTTP 节点超时 15 秒，但 FastAPI 调用 Dify Workflow 属于后台异步任务，
  可以容忍更长的超时（60 秒）。AI 研判通常需要 10-30 秒。

降级策略:
  当 Dify 不可用（网络不通 / 超时 / 返回异常），调用方应 fallback 到
  mock 结果（MVP 阶段）或直接标记失败。

参考文档:
  《教育服务系统_API接口设计规范文档_V1.2》
  - 第 10 章  Dify 工具 API
  - 第 11 章  异步任务接口规范
  - 附录 C   Dify HTTP 节点配置参考
  《教育服务系统_Dify工作流设计规范文档_V1.1》
"""

import json
import logging
from typing import Any, Dict, Optional

import httpx

from config import DIFY_API_KEY, DIFY_API_URL
from models.common import BusinessError

logger = logging.getLogger(__name__)

# ============================================================
# 配置
# ============================================================

# Dify Workflow 执行接口（标准 API）
# 参考: https://docs.dify.ai/zh-hans/guides/application-publishing/developing-with-api
DIFY_WORKFLOW_URL = f"{DIFY_API_URL}/workflows/run"

# Dify API 超时时间（秒）
# 研判类工作流通常 10-30 秒，给 60 秒充足余量
DIFY_TIMEOUT = 60


# ============================================================
# 核心调用函数
# ============================================================


def call_dify_workflow(
    workflow_name: str,
    inputs: Dict[str, Any],
    user: str = "system",
) -> Dict[str, Any]:
    """
    调用 Dify Workflow API，同步等待 AI 返回结果。

    这是所有 Dify 调用的统一入口。调用方只需关心输入和输出，
    不需要处理 HTTP 细节。

    参数:
        workflow_name: Dify 工作流名称（如 "customer_profiling"）
        inputs:        工作流输入参数，格式由工作流定义决定
                       客户研判示例: {"customer_data": {...}, "rules": [...]}
        user:          用户标识（Dify 用于日志记录，默认 "system"）

    返回:
        Dify Workflow 的 outputs 字典，结构由工作流定义决定
        客户研判示例: {"match_result": "matched", "match_score": 85.5, ...}

    异常:
        BusinessError(50201): Dify 服务调用失败（超时/网络错误/HTTP 非 200）
        BusinessError(50202): AI 输出解析失败（返回的 JSON 结构异常）

    使用示例:
        try:
            result = call_dify_workflow("customer_profiling", {
                "customer_data": {"name": "张三", "education": "本科"},
                "rules": [{"product_line": "硕博连读", ...}],
            })
            print(result["match_result"])
        except BusinessError as e:
            # 降级处理
            fallback_result = mock_analysis(...)
    """
    # 1. 检查 API Key 是否已配置
    if not DIFY_API_KEY:
        raise BusinessError(
            code=50201,
            message="Dify API Key 未配置，请在 .env 中设置 DIFY_API_KEY",
            status_code=502,
        )

    # 2. 构造请求
    headers = {
        "Authorization": f"Bearer {DIFY_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "inputs": inputs,
        "response_mode": "blocking",  # 同步模式：等待工作流执行完毕再返回
        "user": user,
    }

    # 3. 发送请求
    logger.info(f"Dify 调用开始: workflow={workflow_name}")

    try:
        with httpx.Client(timeout=DIFY_TIMEOUT) as client:
            response = client.post(
                DIFY_WORKFLOW_URL,
                json=payload,
                headers=headers,
            )
    except httpx.TimeoutException:
        logger.error(f"Dify 调用超时: workflow={workflow_name}, timeout={DIFY_TIMEOUT}s")
        raise BusinessError(
            code=50201,
            message=f"Dify 服务调用超时（{DIFY_TIMEOUT}秒）",
            status_code=502,
        )
    except httpx.ConnectError as e:
        logger.error(f"Dify 连接失败: {str(e)}")
        raise BusinessError(
            code=50201,
            message=f"Dify 服务不可达: {DIFY_API_URL}",
            status_code=502,
        )

    # 4. 校验 HTTP 状态码
    if response.status_code != 200:
        logger.error(
            f"Dify 返回错误: status={response.status_code}, body={response.text[:200]}"
        )
        raise BusinessError(
            code=50201,
            message=f"Dify 服务返回错误: HTTP {response.status_code}",
            status_code=502,
        )

    # 5. 解析响应
    try:
        result = response.json()
    except Exception:
        logger.error(f"Dify 响应不是有效 JSON: {response.text[:200]}")
        raise BusinessError(
            code=50202,
            message="Dify 返回的数据格式异常（非 JSON）",
            status_code=502,
        )

    # Dify Workflow API 的返回结构:
    #   {"data": {"id": "...", "workflow_id": "...", "status": "succeeded",
    #    "outputs": {...}, "error": null, ...}}
    data = result.get("data", {})
    if data.get("status") != "succeeded":
        error_msg = data.get("error", "未知错误")
        logger.error(f"Dify 工作流执行失败: {error_msg}")
        raise BusinessError(
            code=50202,
            message=f"AI 研判失败: {error_msg}",
            status_code=502,
        )

    outputs = data.get("outputs", {})
    logger.info(f"Dify 调用成功: workflow={workflow_name}")

    # Dify Workflow 的 Answer 节点输出的是 JSON 字符串
    # 结构: outputs.answer_json = '{"success":true,"result":{...}}'
    # 解析并返回 result 部分，调用方直接使用 match_result/match_score 等字段
    answer_json = outputs.get("answer_json", "{}")
    if isinstance(answer_json, str):
        try:
            answer = json.loads(answer_json)
        except json.JSONDecodeError:
            raise BusinessError(
                code=50202,
                message="Dify 返回的 answer_json 无法解析",
                status_code=502,
            )
    else:
        answer = answer_json

    if not answer.get("success"):
        raise BusinessError(
            code=50202,
            message="AI 研判失败",
            status_code=502,
        )

    return answer.get("result", {})


def is_dify_available() -> bool:
    """
    快速检查 Dify 服务是否可用（不执行工作流，仅检查连通性）。

    返回:
        True  = Dify 服务可达
        False = Dify 不可用（可以放心使用 mock 降级）
    """
    if not DIFY_API_KEY:
        return False
    try:
        with httpx.Client(timeout=5) as client:
            # 尝试访问 Dify API，只要不报网络错误就算可达
            response = client.get(
                f"{DIFY_API_URL}/parameters",
                headers={"Authorization": f"Bearer {DIFY_API_KEY}"},
            )
            return response.status_code < 500
    except Exception:
        return False
