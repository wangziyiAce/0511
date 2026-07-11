"""ReportLLMClient 单元测试。

Mock ``openai.OpenAI``，验证重试逻辑、超时处理、Token 统计和日志脱敏。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from unittest.mock import MagicMock, patch

import pytest

from services.reporting.llm_client import LLMResponse, ReportLLMClient


# ---------------------------------------------------------------------------
# Mock 工厂
# ---------------------------------------------------------------------------

@dataclass
class _MockMessage:
    content: str = ""


@dataclass
class _MockChoice:
    message: _MockMessage = field(default_factory=_MockMessage)
    finish_reason: str = "stop"


@dataclass
class _MockUsage:
    prompt_tokens: int = 100
    completion_tokens: int = 50


@dataclass
class _MockCompletion:
    choices: list[_MockChoice] = field(default_factory=lambda: [_MockChoice()])
    usage: _MockUsage = field(default_factory=_MockUsage)


def _success_response(content: str) -> _MockCompletion:
    return _MockCompletion(
        choices=[_MockChoice(message=_MockMessage(content=content))],
        usage=_MockUsage(prompt_tokens=200, completion_tokens=80),
    )


def _make_mock_openai(create_side_effect):
    """构建 mock openai 模块对象。"""
    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = create_side_effect
    mock_openai_cls = MagicMock(return_value=mock_client)
    return mock_openai_cls, mock_client


# ---------------------------------------------------------------------------
# 测试
# ---------------------------------------------------------------------------


class TestLLMResponse:
    def test_success_response_fields(self):
        resp = LLMResponse(
            content='{"summary": "ok", "explanation": "解释"}',
            model="deepseek-v4-pro",
            provider="deepseek",
            prompt_tokens=150,
            completion_tokens=60,
            latency_ms=1200,
            status="success",
        )
        assert resp.total_tokens == 210
        assert resp.status == "success"
        assert resp.error is None

    def test_error_response_fields(self):
        resp = LLMResponse(
            content=None,
            status="api_error",
            error="ConnectionError: 连接被拒绝",
            retry_count=2,
            latency_ms=5000,
        )
        assert resp.error is not None


class TestReportLLMClient:
    def test_chat_completion_success(self, monkeypatch):
        """正常调用返回 LLMResponse。"""
        monkeypatch.setenv("REPORT_LLM_API_KEY", "sk-test-key")

        from services.reporting.llm_config import ReportLLMSettings
        import services.reporting.llm_client as lc_module

        # 用可修改的新 Settings 实例替换模块级 settings
        test_settings = ReportLLMSettings(
            provider="deepseek",
            model="deepseek-v4-pro",
            base_url="https://api.deepseek.com",
            api_key="sk-test-key",
            timeout=10,
            max_retries=2,
            ai_mode="llm",
        )
        monkeypatch.setattr(lc_module, "settings", test_settings)

        mock_cls, mock_client = _make_mock_openai(
            [_success_response('{"summary": "AI生成", "explanation": "AI解释"}')]
        )
        with patch("openai.OpenAI", mock_cls):
            client = ReportLLMClient()
            response = client.chat_completion(
                messages=[
                    {"role": "system", "content": "你是报告分析助手"},
                    {"role": "user", "content": "请生成报告解释"},
                ],
            )

        assert response.status == "success"
        assert response.content == '{"summary": "AI生成", "explanation": "AI解释"}'
        assert response.model == "deepseek-v4-pro"
        assert response.prompt_tokens == 200
        assert response.completion_tokens == 80
        assert response.retry_count == 0

    def test_chat_completion_retry_then_success(self, monkeypatch):
        """第一次失败、第二次成功——验证重试逻辑。"""
        monkeypatch.setenv("REPORT_LLM_API_KEY", "sk-test-key")
        monkeypatch.setenv("REPORT_LLM_MAX_RETRIES", "2")

        from services.reporting.llm_config import ReportLLMSettings
        import services.reporting.llm_client as lc_module

        test_settings = ReportLLMSettings(
            provider="deepseek",
            model="deepseek-v4-pro",
            base_url="https://api.deepseek.com",
            api_key="sk-test-key",
            timeout=10,
            max_retries=2,
            ai_mode="llm",
        )
        monkeypatch.setattr(lc_module, "settings", test_settings)

        mock_cls, mock_client = _make_mock_openai([
            ConnectionError("第一次网络错误"),
            ConnectionError("第二次网络错误"),
            _success_response('{"summary": "重试后OK", "explanation": "经过2次重试"}'),
        ])

        with patch("openai.OpenAI", mock_cls):
            client = ReportLLMClient()
            response = client.chat_completion(
                messages=[{"role": "user", "content": "test"}],
            )

        assert response.status == "success"
        assert response.retry_count == 2
        assert "重试后OK" in (response.content or "")

    def test_chat_completion_all_retries_exhausted(self, monkeypatch):
        """所有重试都失败——返回错误响应。"""
        monkeypatch.setenv("REPORT_LLM_API_KEY", "sk-test-key")
        monkeypatch.setenv("REPORT_LLM_MAX_RETRIES", "2")

        from services.reporting.llm_config import ReportLLMSettings
        import services.reporting.llm_client as lc_module

        test_settings = ReportLLMSettings(
            provider="deepseek",
            model="deepseek-v4-pro",
            base_url="https://api.deepseek.com",
            api_key="sk-test-key",
            timeout=10,
            max_retries=2,
            ai_mode="llm",
        )
        monkeypatch.setattr(lc_module, "settings", test_settings)

        # side_effect=Exception 时每次调用都抛出该异常
        mock_cls, mock_client = _make_mock_openai(
            ConnectionError("持续网络错误")
        )
        with patch("openai.OpenAI", mock_cls):
            client = ReportLLMClient()
            response = client.chat_completion(
                messages=[{"role": "user", "content": "test"}],
            )

        assert response.status == "api_error"
        assert response.content is None
        assert response.retry_count == 2
        assert "ConnectionError" in (response.error or "")

    def test_client_raises_without_api_key(self, monkeypatch):
        """未配置 API Key 时抛出明确 RuntimeError。"""
        from services.reporting.llm_config import ReportLLMSettings
        import services.reporting.llm_client as lc_module

        test_settings = ReportLLMSettings(
            api_key="",
            timeout=10,
            max_retries=2,
            ai_mode="llm",
        )
        monkeypatch.setattr(lc_module, "settings", test_settings)

        with pytest.raises(RuntimeError, match="REPORT_LLM_API_KEY"):
            ReportLLMClient()

    def test_client_disables_sdk_retry(self, monkeypatch):
        """验证 SDK max_retries=0。"""
        monkeypatch.setenv("REPORT_LLM_API_KEY", "sk-test-key")

        from services.reporting.llm_config import ReportLLMSettings
        import services.reporting.llm_client as lc_module

        test_settings = ReportLLMSettings(
            api_key="sk-test-key",
            timeout=10,
            max_retries=2,
            ai_mode="llm",
        )
        monkeypatch.setattr(lc_module, "settings", test_settings)

        mock_cls = MagicMock()
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.chat.completions.create.return_value = _success_response('{}')

        with patch("openai.OpenAI", mock_cls) as mock_openai_patch:
            ReportLLMClient()
            mock_openai_patch.assert_called_once()
            kwargs = mock_openai_patch.call_args.kwargs
            assert kwargs.get("max_retries") == 0, (
                "SDK max_retries 必须为 0，避免与自定义重试叠加"
            )
