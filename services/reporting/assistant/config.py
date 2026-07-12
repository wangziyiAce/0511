"""智能报告助手 — 配置管理。

本模块管理智能报告助手的独立配置，使用 ``REPORT_ASSISTANT_`` 环境变量前缀。
遵循项目现有的环境变量读取模式（参考 ``services/reporting/llm_config.py``），
但不与 ``REPORT_LLM_*`` 或 ``DIFY_*`` 命名空间冲突。

配置读取顺序：进程环境变量优先，提供合理默认值兜底。
``REPORT_ASSISTANT_LLM_ENABLED=false`` 时意图解析使用本地关键词降级。
"""

from __future__ import annotations

import os
from dataclasses import dataclass


def _read_env(name: str, default: str = "") -> str:
    """读取环境变量；前后去空白，避免无意空格导致连接失败。"""
    return os.getenv(name, default).strip()


def _read_int_env(name: str, default: int) -> int:
    """读取整数环境变量；非法值时回退默认值。"""
    raw = _read_env(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _read_float_env(name: str, default: float) -> float:
    """读取浮点数环境变量；非法值时回退默认值。"""
    raw = _read_env(name)
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _read_bool_env(name: str, default: bool) -> bool:
    """读取布尔型环境变量。支持 true/false/1/0。"""
    raw = _read_env(name).lower()
    if not raw:
        return default
    return raw in ("true", "1", "yes", "on")


@dataclass(frozen=True)
class ReportAssistantSettings:
    """智能报告助手配置对象。

    字段全部从 ``REPORT_ASSISTANT_`` 前缀环境变量读取。
    """

    enabled: bool = False
    llm_enabled: bool = False
    provider: str = "deepseek"
    model: str = "deepseek-v4-pro"
    base_url: str = "https://api.deepseek.com"
    api_key: str = ""
    timeout_seconds: int = 180
    max_retries: int = 2
    confidence_high: float = 0.80
    confidence_low: float = 0.55

    @classmethod
    def from_environment(cls) -> "ReportAssistantSettings":
        """从环境变量构建配置对象。

        所有变量名以 ``REPORT_ASSISTANT_`` 为前缀，与 ``REPORT_LLM_*`` 隔离。
        """
        return cls(
            enabled=_read_bool_env("REPORT_ASSISTANT_ENABLED", False),
            llm_enabled=_read_bool_env("REPORT_ASSISTANT_LLM_ENABLED", False),
            provider=_read_env("REPORT_ASSISTANT_PROVIDER", "deepseek"),
            model=_read_env("REPORT_ASSISTANT_MODEL", "deepseek-v4-pro"),
            base_url=_read_env("REPORT_ASSISTANT_BASE_URL", "https://api.deepseek.com"),
            api_key=_read_env("REPORT_ASSISTANT_API_KEY", ""),
            timeout_seconds=_read_int_env("REPORT_ASSISTANT_TIMEOUT_SECONDS", 180),
            max_retries=_read_int_env("REPORT_ASSISTANT_MAX_RETRIES", 2),
            confidence_high=_read_float_env("REPORT_ASSISTANT_CONFIDENCE_HIGH", 0.80),
            confidence_low=_read_float_env("REPORT_ASSISTANT_CONFIDENCE_LOW", 0.55),
        )


# 模块级单例 — 其他模块 import 后直接使用。
settings = ReportAssistantSettings.from_environment()
