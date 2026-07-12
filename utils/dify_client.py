"""
Dify Workflow API 客户端封装
===========================================
封装对 Dify Workflow 的 HTTP 调用，用于:
  - 客户研判 Workflow
  - 智能报告生成 Workflow
  - 其他场景的 Dify Workflow 调用

使用方式:
  from utils.dify_client import DifyClient
  client = DifyClient()
  result = client.run_workflow(report_type="daily_summary", inputs={...})

Dify API 参考:
  POST /v1/workflows/run  — 执行 Workflow（阻塞模式，等待结果）
  POST /v1/chat-messages   — 发送对话消息（Chatflow）

设计要点:
  1. 超时控制: Dify Workflow 默认 120s 超时（报告生成可能较慢）
  2. 错误处理: 网络异常、Dify 返回非 JSON 时抛出明确错误
  3. 日志摘要: 记录请求/响应的关键信息，不打印完整内容
"""

import json
import logging
import time
from typing import Any, Optional

import httpx

from config import DIFY_API_URL, DIFY_API_KEY

logger = logging.getLogger(__name__)


# ==================== Dify 客户端 ====================

class DifyClient:
    """
    Dify Workflow 阻塞模式客户端。

    使用 Dify 的 /v1/workflows/run 接口，以 blocking 模式调用 Workflow，
    等待 AI 处理完成后返回结果。

    适用场景:
      - 客户研判：传入客户资料，返回结构化研判结果
      - 报告生成：传入业务数据，返回结构化报告内容
    """

    def __init__(
        self,
        api_url: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout: int = 120,
    ):
        """
        初始化 Dify 客户端。

        Args:
            api_url: Dify API 基础地址，默认从 config 读取
            api_key: Dify 应用 API Key，默认从 config 读取
            timeout: HTTP 请求超时时间（秒），默认 120s
        """
        self.api_url = (api_url or DIFY_API_URL).rstrip("/")
        self.api_key = api_key or DIFY_API_KEY
        self.timeout = timeout

    def _headers(self) -> dict:
        """构建请求头"""
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def run_workflow(
        self,
        inputs: dict[str, Any],
        user: str = "system",
        response_mode: str = "blocking",
    ) -> dict[str, Any]:
        """
        以阻塞模式执行 Dify Workflow。

        Args:
            inputs: Workflow 输入变量（键值对，对应 Dify 工作流的输入节点）
            user: 用户标识，默认 "system"
            response_mode: 响应模式，"blocking"=等待结果, "streaming"=流式

        Returns:
            Dify Workflow 的完整响应体（包含 outputs 字段）。

        Raises:
            RuntimeError: Dify 调用失败、返回异常或超时
        """
        url = f"{self.api_url}/workflows/run"

        payload = {
            "inputs": inputs,
            "response_mode": response_mode,
            "user": user,
        }

        start_time = time.time()
        logger.info(
            "Dify 请求: url=%s, inputs_keys=%s",
            url,
            list(inputs.keys()),
        )

        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(url, json=payload, headers=self._headers())

            elapsed = time.time() - start_time
            logger.info(
                "Dify 响应: status=%d, elapsed=%.1fs",
                response.status_code,
                elapsed,
            )

        except httpx.TimeoutException:
            logger.error("Dify 调用超时: timeout=%ds", self.timeout)
            raise RuntimeError(f"Dify 调用超时（{self.timeout}秒）")
        except httpx.ConnectError as e:
            logger.error("Dify 连接失败: %s", e)
            raise RuntimeError(f"无法连接到 Dify 服务: {e}")
        except Exception as e:
            logger.error("Dify 网络异常: %s", e)
            raise RuntimeError(f"Dify 网络异常: {e}")

        if response.status_code != 200:
            logger.error(
                "Dify 返回非 200: status=%d, body=%s",
                response.status_code,
                response.text[:500],
            )
            raise RuntimeError(
                f"Dify 返回错误状态 {response.status_code}: {response.text[:200]}"
            )

        try:
            result = response.json()
        except json.JSONDecodeError:
            logger.error("Dify 响应非 JSON: %s", response.text[:500])
            raise RuntimeError("Dify 响应不是有效的 JSON 格式")

        # 检查 Dify 层面的错误
        if "error" in result:
            error_msg = result.get("error", "未知错误")
            logger.error("Dify 业务错误: %s", error_msg)
            raise RuntimeError(f"Dify 业务错误: {error_msg}")

        # 检查 Workflow 执行状态
        workflow_run_id = result.get("workflow_run_id", "unknown")
        logger.info(
            "Dify Workflow 完成: run_id=%s, outputs_keys=%s",
            workflow_run_id,
            list(result.get("data", {}).get("outputs", {}).keys()),
        )

        return result


# ==================== 便捷函数 ====================

def call_dify_workflow(
    inputs: dict[str, Any],
    api_url: Optional[str] = None,
    api_key: Optional[str] = None,
    timeout: int = 120,
) -> dict[str, Any]:
    """
    快捷调用 Dify Workflow（不需要创建 DifyClient 实例）。

    使用场景:
      - 异步任务中调用（report_service.py）
      - 客户研判任务中调用（profile_service.py）

    Args:
        inputs: Workflow 输入变量
        api_url: Dify API 地址，默认从 config 读取
        api_key: Dify API Key，默认从 config 读取
        timeout: 超时时间（秒）

    Returns:
        Dify Workflow 响应体
    """
    client = DifyClient(api_url=api_url, api_key=api_key, timeout=timeout)
    return client.run_workflow(inputs=inputs)
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

from config import DIFY_API_KEY, DIFY_API_URL, LLM_API_URL, LLM_API_KEY, LLM_MODEL, LLM_TIMEOUT
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


# ============================================================
# LLM 直调函数（绕过 Dify，直接调用模型 API）
# ============================================================
# 使用 OpenAI 兼容的 /v1/chat/completions 格式。
# DeepSeek、通义千问、GLM 等国产模型均兼容。
#
# 为什么绕过 Dify？
#   - 客户研判需要灵活构造 prompt（动态加载 .md 规则文件全文）
#   - Dify Workflow 的 Start 节点变量类型有限，不适合传大段规则文本
#   - 直调 LLM 更简单，减少中间依赖


def call_llm_direct(
    system_prompt: str,
    user_message: str,
    model: Optional[str] = None,
    temperature: float = 0.2,
    response_format: str = "json_object",
    max_tokens: int = 4096,
) -> Dict[str, Any]:
    """
    直接调用 LLM API（OpenAI 兼容格式 /v1/chat/completions）。

    参数:
        system_prompt:   系统提示词（含产品线规则全文 + 输出格式约束）
        user_message:    用户消息（客户资料原文 + 结构化画像）
        model:           模型名，默认 config.LLM_MODEL
        temperature:     0.2（研判需严谨推理，低随机性）
        response_format: "json_object" 确保 LLM 返回合法 JSON
        max_tokens:      最大输出 4096

    返回:
        LLM 返回的 JSON dict

    异常:
        BusinessError(50201): API 调用失败（超时/401/429等）
        BusinessError(50202): 返回 JSON 解析失败
    """
    if not LLM_API_KEY:
        raise BusinessError(code=50201, message="LLM_API_KEY 未配置，请在 .env 中设置", status_code=502)
    if not LLM_API_URL:
        raise BusinessError(code=50201, message="LLM_API_URL 未配置，请在 .env 中设置", status_code=502)

    resolved_model = model or LLM_MODEL
    url = f"{LLM_API_URL.rstrip('/')}/chat/completions"

    payload: Dict[str, Any] = {
        "model": resolved_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if response_format:
        payload["response_format"] = {"type": response_format}

    logger.info(f"LLM直调: model={resolved_model}, prompt_len={len(system_prompt)}")

    try:
        # trust_env=False: 避免继承 Windows 系统代理(IE/WinHTTP)导致 HTTPS TLS 握手失败
        with httpx.Client(timeout=LLM_TIMEOUT, trust_env=False) as client:
            response = client.post(
                url,
                json=payload,
                headers={
                    "Authorization": f"Bearer {LLM_API_KEY}",
                    "Content-Type": "application/json",
                },
            )
    except httpx.TimeoutException:
        raise BusinessError(code=50201, message=f"LLM调用超时（{LLM_TIMEOUT}秒）", status_code=502)
    except httpx.ConnectError:
        raise BusinessError(code=50201, message=f"LLM服务不可达: {LLM_API_URL}", status_code=502)

    if response.status_code != 200:
        err = response.text[:300]
        logger.error(f"LLM返回错误: HTTP{response.status_code} {err}")
        if response.status_code == 401:
            raise BusinessError(code=50201, message="LLM API Key无效", status_code=502)
        if response.status_code == 429:
            raise BusinessError(code=50201, message="LLM调用频率超限", status_code=502)
        raise BusinessError(code=50201, message=f"LLM返回错误 HTTP{response.status_code}", status_code=502)

    try:
        result = response.json()
    except Exception:
        raise BusinessError(code=50202, message="LLM返回非JSON", status_code=502)

    choices = result.get("choices", [])
    if not choices:
        raise BusinessError(code=50202, message="LLM返回空结果", status_code=502)

    content = choices[0].get("message", {}).get("content", "")
    if not content:
        raise BusinessError(code=50202, message="LLM返回内容为空", status_code=502)

    # 去掉可能的 ```json ... ``` 包裹
    content = content.strip()
    if content.startswith("```"):
        lines = content.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        content = "\n".join(lines).strip()

    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        logger.error(f"LLM返回JSON解析失败: {str(e)} content={content[:300]}")
        raise BusinessError(code=50202, message=f"LLM返回JSON解析失败: {str(e)}", status_code=502)

    logger.info(f"LLM直调成功: model={resolved_model}")
    return data
