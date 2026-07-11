"""智能报告模块 — LLM 配置管理。

本模块位于服务层：上游被 ``ai_generator``、``llm_client`` 和 ``prompt_builder``
调用，下游依赖环境变量。它把 LLM 连接参数从业务代码中拆出来，避免硬编码。

配置读取顺序：进程环境变量优先，提供合理默认值兜底。
缺失 ``REPORT_LLM_API_KEY`` 时在 llm 模式会抛出 ConfigurationError，
但在 local 模式下允许应用正常启动。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


class ConfigurationError(RuntimeError):
    """LLM 配置错误。

    与 orchestrator 中的 ``RuntimeError`` 区分，方便调用方判断是配置问题
    还是运行时调用失败。
    """


def _read_env(name: str, default: str = "") -> str:
    """读取环境变量；前后去空白，避免无意空格导致连接失败。"""
    return os.getenv(name, default).strip()


def _read_int_env(name: str, default: int) -> int:
    """读取整数环境变量；非法值时回退默认值并记录差异。"""
    raw = _read_env(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class ReportLLMSettings:
    """智能报告模块 LLM 配置对象。

    字段全部从环境变量读取，默认值面向 DeepSeek 场景。
    调用 ``from_environment()`` 获取单例。
    """

    provider: str = "deepseek"
    model: str = "deepseek-v4-pro"
    base_url: str = "https://api.deepseek.com"
    api_key: str = ""
    timeout: int = 180
    max_retries: int = 2
    ai_mode: str = "local"  # local / llm / dify(废弃 → 报错)
    prompt_version: str = "v2-python-001"

    @classmethod
    def from_environment(cls) -> "ReportLLMSettings":
        """从环境变量构建配置对象。

        所有变量名以 ``REPORT_LLM_`` 为前缀，与 Dify 变量命名空间隔离。
        ``REPORT_AI_MODE`` 读取后由 ``resolve_ai_mode()`` 做合法性检查。
        """
        return cls(
            provider=_read_env("REPORT_LLM_PROVIDER", "deepseek"),
            model=_read_env("REPORT_LLM_MODEL", "deepseek-v4-pro"),
            base_url=_read_env("REPORT_LLM_BASE_URL", "https://api.deepseek.com"),
            api_key=_read_env("REPORT_LLM_API_KEY", ""),
            timeout=_read_int_env("REPORT_LLM_TIMEOUT", 180),
            max_retries=_read_int_env("REPORT_LLM_MAX_RETRIES", 2),
            ai_mode=resolve_ai_mode(),
        )


def resolve_ai_mode() -> str:
    """解析并校验 ``REPORT_AI_MODE``。

    Returns:
        ``"local"`` — 本地确定性解释，不调用任何 LLM。
        ``"llm"`` — 纯 Python LLM 调用。

    Raises:
        ConfigurationError: 设成了已废弃的 ``dify`` 或不支持的值。
    """
    mode = os.getenv("REPORT_AI_MODE", "local").lower().strip()
    if mode in ("local", "llm"):
        return mode
    if mode == "dify":
        raise ConfigurationError(
            "REPORT_AI_MODE=dify 已废弃。智能报告模块现已改为纯 Python 实现，"
            "不再依赖 Dify 服务。请将 REPORT_AI_MODE 改为 llm，并配置 "
            "REPORT_LLM_API_KEY、REPORT_LLM_MODEL 等环境变量。\n"
            "详情见 doc/智能报告模块_纯Python重构计划_v3.md"
        )
    raise ConfigurationError(
        f"不支持的 REPORT_AI_MODE: {mode}。支持的值: local / llm"
    )


# 模块级单例 — 其他模块 import 本模块后直接使用。
settings = ReportLLMSettings.from_environment()
