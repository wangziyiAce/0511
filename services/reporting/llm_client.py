"""智能报告模块 — 大模型客户端封装。

本模块位于服务层：上游被 ``ai_generator`` 调用，下游依赖 ``openai`` SDK。
``ReportLLMClient`` 是业务代码与 LLM SDK 之间的隔离层，业务代码不直接 import openai。

设计要点：
1. **SDK 重试关闭**：``openai.OpenAI(max_retries=0)``，重试逻辑由本模块统一控制。
2. **指数退避**：网络/API 异常最多额外重试 2 次（1s → 2s → fail）。
3. **日志脱敏**：不输出 API Key；完整 Prompt 只记长度不记录内容。
4. **Token 与耗时统计**：调用方可通过返回值获取详情。
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from services.reporting.llm_config import settings

logger = logging.getLogger(__name__)


@dataclass
class LLMResponse:
    """LLM 调用结果。

    每次调用（包括网络重试）都会返回本对象。调用成功时 ``content`` 为模型输出文本；
    失败时 ``error`` 记录异常信息，``content`` 为 None。
    """

    content: Optional[str] = None
    model: str = ""
    provider: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: int = 0
    retry_count: int = 0  # 网络重试次数（不含首次）
    status: str = "success"  # success / api_error / timeout / unexpected
    error: Optional[str] = None

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


class ReportLLMClient:
    """智能报告专用 LLM 客户端。

    封装 ``openai.OpenAI``（同步客户端），提供统一的重试、超时、日志和脱敏能力。
    业务代码通过 ``chat_completion()`` 调用，不直接接触 openai SDK。

    使用示例::

        client = ReportLLMClient()
        response = client.chat_completion(
            messages=[{"role": "system", "content": "..."}, {"role": "user", "content": "..."}],
        )
        if response.status == "success":
            print(response.content)
    """

    def __init__(self) -> None:
        self._provider = settings.provider
        self._model = settings.model
        self._timeout = settings.timeout
        self._max_retries = settings.max_retries
        self._client = self._build_client()

    def _build_client(self):
        """创建 OpenAI 同步客户端。

        ``max_retries=0`` 关闭 SDK 内置重试，全部重试由本类的 ``_call_with_retry`` 控制。
        """
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise ImportError(
                "openai SDK 未安装。请执行: pip install openai>=1.50,<2.0"
            ) from exc

        if not settings.api_key:
            raise RuntimeError(
                "REPORT_LLM_API_KEY 未配置。请在 .env 中设置 REPORT_LLM_API_KEY"
            )

        return OpenAI(
            api_key=settings.api_key,
            base_url=settings.base_url,
            timeout=float(self._timeout),
            max_retries=0,  # SDK 不重试，由本类统一管理
        )

    # ------------------------------------------------------------------
    # 公开接口
    # ------------------------------------------------------------------

    def chat_completion(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.2,
        max_tokens: int = 1200,
        top_p: float = 0.9,
        json_mode: bool = True,
    ) -> LLMResponse:
        """调用 LLM Chat Completions API。

        带指数退避重试：首次 → 等 1s → 重试 1 → 等 2s → 重试 2 → 失败。

        Args:
            messages: [{"role": "system", "content": ...}, {"role": "user", "content": ...}]
            temperature: 温度参数，默认 0.2（低随机性，适合报告类任务）。
            max_tokens: 最大输出 Token，默认 1200。
            top_p: nucleus sampling，默认 0.9。
            json_mode: 是否要求供应商以 JSON object 模式返回。意图解析、报告生成使用
                JSON；面向用户的自然语言回答必须关闭，否则部分兼容接口会拒绝请求。

        Returns:
            ``LLMResponse``，成功时 ``content`` 为模型文本，失败时 ``error`` 有值。
        """
        total_start = time.perf_counter()
        retry_count = 0
        last_error: Optional[str] = None

        for attempt in range(self._max_retries + 1):
            retry_count = attempt  # 本轮之前已失败次数: 0, 1, 2
            try:
                return self._single_call(
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    top_p=top_p,
                    json_mode=json_mode,
                    total_start=total_start,
                    retry_count=retry_count,
                )
            except Exception as exc:
                last_error = f"{exc.__class__.__name__}: {exc}"

                if attempt < self._max_retries:
                    wait = 2 ** attempt  # 1s, 2s 指数退避
                    logger.warning(
                        "LLM 调用失败，第 %d 次重试，等待 %ds。错误: %s",
                        retry_count,
                        wait,
                        last_error,
                    )
                    time.sleep(wait)
                else:
                    logger.error(
                        "LLM 调用失败，已达最大重试次数 %d。错误: %s",
                        self._max_retries,
                        last_error,
                    )

        latency_ms = int((time.perf_counter() - total_start) * 1000)
        return LLMResponse(
            content=None,
            model=self._model,
            provider=self._provider,
            latency_ms=latency_ms,
            retry_count=retry_count,
            status="api_error",
            error=last_error,
        )

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _single_call(
        self,
        *,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int,
        top_p: float,
        json_mode: bool,
        total_start: float,
        retry_count: int,
    ) -> LLMResponse:
        """执行单次 API 调用（不含重试逻辑）。

        Returns:
            LLMResponse — 调用方通过 ``status`` 判断成功/失败。
        """
        msg_length = sum(len(m.get("content", "")) for m in messages)
        logger.info(
            "LLM 调用: provider=%s model=%s msg_count=%d total_chars=%d",
            self._provider,
            self._model,
            len(messages),
            msg_length,
        )

        call_start = time.perf_counter()

        request_kwargs = dict(
            model=self._model,
            messages=messages,  # type: ignore[arg-type]
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=top_p,
        )
        # 只有结构化输出场景才声明 JSON mode。普通回答若也携带该参数，DeepSeek 等
        # 兼容接口会要求提示词显式包含 json 并返回 400，最终误触发模板降级。
        if json_mode:
            request_kwargs["response_format"] = {"type": "json_object"}
        response = self._client.chat.completions.create(**request_kwargs)

        latency_ms = int((time.perf_counter() - total_start) * 1000)
        choice = response.choices[0]
        content = choice.message.content or ""
        usage = response.usage

        prompt_tokens = usage.prompt_tokens if usage else 0
        completion_tokens = usage.completion_tokens if usage else 0

        logger.info(
            "LLM 完成: latency_ms=%d prompt_tokens=%d completion_tokens=%d "
            "retry_count=%d finish_reason=%s",
            latency_ms,
            prompt_tokens,
            completion_tokens,
            retry_count,
            choice.finish_reason,
        )

        return LLMResponse(
            content=content,
            model=self._model,
            provider=self._provider,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            latency_ms=latency_ms,
            retry_count=retry_count,
            status="success",
        )
