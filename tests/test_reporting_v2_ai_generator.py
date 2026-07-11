"""AI 生成器纯 Python 实现测试。

Mock ``ReportLLMClient.chat_completion()``，验证正常调用、JSON 解析、
合并保护、Schema 修复重试、非 JSON 修复和本地降级。
"""

from __future__ import annotations

import json

import pytest

from services.reporting.ai_generator import _merge_content, _parse_llm_json, enrich_content_with_ai
from services.reporting.llm_client import LLMResponse
from services.reporting.llm_config import ReportLLMSettings
from services.reporting.registry import get_report_definition
from services.reporting.schemas import DataQuality


# ---------------------------------------------------------------------------
# 数据工厂
# ---------------------------------------------------------------------------


def _application_risk_content() -> dict:
    return {
        "summary": "规则引擎初始总结",
        "explanation": "",
        "metrics": {
            "total_applications": 1,
            "high_risk_count": 1,
            "medium_risk_count": 0,
            "low_risk_count": 0,
            "overdue_count": 0,
            "missing_material_count": 1,
        },
        "risk_items": [
            {
                "application_id": 1001,
                "student_id": 2001,
                "owner_id": 1,
                "stage": "material_preparation",
                "risk_score": 80,
                "risk_level": "high",
                "risk_reasons": ["missing_required_materials"],
                "missing_materials": ["Personal Statement"],
                "next_action": "补齐文书初稿",
            }
        ],
        "action_checklist": [
            {
                "owner_id": 1,
                "action": "跟进 Personal Statement",
                "due_date": "2026-07-12",
                "priority": "high",
            }
        ],
    }


def _mock_llm_response(content: str) -> LLMResponse:
    return LLMResponse(
        content=content,
        model="deepseek-v4-pro",
        provider="deepseek",
        prompt_tokens=150,
        completion_tokens=60,
        latency_ms=800,
        status="success",
    )


def _make_llm_settings(**overrides) -> ReportLLMSettings:
    """创建可修改的 ReportLLMSettings 用于测试。"""
    defaults = {
        "provider": "deepseek",
        "model": "deepseek-v4-pro",
        "base_url": "https://api.deepseek.com",
        "api_key": "sk-test-key",
        "timeout": 10,
        "max_retries": 1,
        "ai_mode": "llm",
    }
    defaults.update(overrides)
    return ReportLLMSettings(**defaults)


def _patch_settings(monkeypatch, **overrides):
    """同时 patch ai_generator.settings 和 llm_client.settings。

    ai_generator 用 settings 判断 ai_mode，llm_client 用 settings 读取 api_key。
    """
    import services.reporting.ai_generator as ag_module
    import services.reporting.llm_client as lc_module

    test_settings = _make_llm_settings(**overrides)
    monkeypatch.setattr(ag_module, "settings", test_settings)
    monkeypatch.setattr(lc_module, "settings", test_settings)
    return test_settings


# ---------------------------------------------------------------------------
# JSON 解析
# ---------------------------------------------------------------------------


class TestParseLLMJson:
    def test_parse_plain_json(self):
        result = _parse_llm_json('{"summary": "ok", "explanation": "解释"}')
        assert result == {"summary": "ok", "explanation": "解释"}

    def test_parse_markdown_code_block(self):
        result = _parse_llm_json(
            '```json\n{"summary": "ok", "explanation": "代码块里的JSON"}\n```'
        )
        assert result == {"summary": "ok", "explanation": "代码块里的JSON"}

    def test_parse_without_lang_tag(self):
        result = _parse_llm_json(
            '```\n{"summary": "ok", "explanation": "裸代码块"}\n```'
        )
        assert result == {"summary": "ok", "explanation": "裸代码块"}

    def test_parse_embedded_json(self):
        result = _parse_llm_json(
            '这是一段说明文字 {"summary": "内嵌JSON", "explanation": "在文本中"} 后面还有字'
        )
        assert result == {"summary": "内嵌JSON", "explanation": "在文本中"}

    def test_parse_empty_string_raises(self):
        with pytest.raises(json.JSONDecodeError):
            _parse_llm_json("")

    def test_parse_plain_text_raises(self):
        with pytest.raises(json.JSONDecodeError):
            _parse_llm_json("这是一段普通自然语言，不是 JSON")


# ---------------------------------------------------------------------------
# 合并保护
# ---------------------------------------------------------------------------


class TestMergeContent:
    def test_only_allows_summary_and_explanation(self):
        original = {"summary": "原始摘要", "explanation": "", "metrics": {"total": 10}}
        candidate = {"summary": "AI 摘要", "explanation": "AI 解释", "metrics": {"total": 999}}
        merged = _merge_content(original, candidate)
        assert merged["summary"] == "AI 摘要"
        assert merged["metrics"]["total"] == 10

    def test_none_values_not_overwritten(self):
        original = {"summary": "original", "explanation": "old"}
        candidate = {"summary": "", "explanation": ""}
        merged = _merge_content(original, candidate)
        assert merged["summary"] == "original"

    def test_non_dict_candidate(self):
        original = {"summary": "original"}
        merged = _merge_content(original, "not a dict")
        assert merged["summary"] == "original"


# ---------------------------------------------------------------------------
# enrich_content_with_ai 集成测试
# ---------------------------------------------------------------------------


class TestEnrichContentWithAI:
    def test_local_mode(self, monkeypatch):
        """local 模式 → 本地解释。"""
        _patch_settings(monkeypatch, ai_mode="local")

        result = enrich_content_with_ai(
            definition=get_report_definition("application_risk"),
            title="测试报告",
            period={"start": "2026-07-01", "end": "2026-07-09"},
            content={"summary": "初始"},
            data_quality=DataQuality(),
        )
        assert "规则引擎" in result.get("explanation", "")

    def test_success_first_call(self, monkeypatch):
        """LLM 模式 — 首次通过。"""
        _patch_settings(monkeypatch, ai_mode="llm")

        def mock_chat_completion(self, messages):
            return _mock_llm_response(
                json.dumps({"summary": "AI摘要", "explanation": "AI解释"})
            )

        monkeypatch.setattr(
            "services.reporting.ai_generator.ReportLLMClient.chat_completion",
            mock_chat_completion,
        )

        result = enrich_content_with_ai(
            definition=get_report_definition("application_risk"),
            title="申请风险报告",
            period={"start": "2026-07-01", "end": "2026-07-09"},
            content=_application_risk_content(),
            data_quality=DataQuality(),
        )
        assert result["summary"] == "AI摘要"
        assert result["metrics"]["total_applications"] == 1

    def test_cannot_overwrite_business_metrics(self, monkeypatch):
        """LLM 输出中的额外字段不覆盖业务指标。"""
        _patch_settings(monkeypatch, ai_mode="llm")

        def mock_chat_completion(self, messages):
            return _mock_llm_response(
                json.dumps({
                    "summary": "AI解释",
                    "explanation": "只解释",
                    "metrics": {"total_applications": 999},
                })
            )

        monkeypatch.setattr(
            "services.reporting.ai_generator.ReportLLMClient.chat_completion",
            mock_chat_completion,
        )

        result = enrich_content_with_ai(
            definition=get_report_definition("application_risk"),
            title="申请风险报告",
            period={"start": "2026-07-01", "end": "2026-07-09"},
            content=_application_risk_content(),
            data_quality=DataQuality(),
        )
        assert result["metrics"]["total_applications"] == 1
        assert result["risk_items"][0]["risk_score"] == 80

    def test_schema_fail_then_repair_success(self, monkeypatch):
        """第一次 Schema 校验失败 → 修复成功。"""
        _patch_settings(monkeypatch, ai_mode="llm")

        call_count = [0]

        def mock_chat_completion(self, messages):
            call_count[0] += 1
            if call_count[0] == 1:
                return _mock_llm_response(
                    json.dumps({"summary": {"bad": "type"}, "explanation": "first"})
                )
            return _mock_llm_response(
                json.dumps({"summary": "修复后总结", "explanation": "修复后解释"})
            )

        monkeypatch.setattr(
            "services.reporting.ai_generator.ReportLLMClient.chat_completion",
            mock_chat_completion,
        )

        result = enrich_content_with_ai(
            definition=get_report_definition("application_risk"),
            title="申请风险报告",
            period={"start": "2026-07-01", "end": "2026-07-09"},
            content=_application_risk_content(),
            data_quality=DataQuality(),
        )
        assert call_count[0] == 2
        assert result["summary"] == "修复后总结"

    def test_non_json_enters_repair_then_succeeds(self, monkeypatch):
        """非 JSON 进入修复 → 修复成功。"""
        _patch_settings(monkeypatch, ai_mode="llm")

        call_count = [0]

        def mock_chat_completion(self, messages):
            call_count[0] += 1
            if call_count[0] == 1:
                return _mock_llm_response("纯自然语言，不是JSON")
            return _mock_llm_response(
                json.dumps({"summary": "修复后JSON", "explanation": "第二次正确"})
            )

        monkeypatch.setattr(
            "services.reporting.ai_generator.ReportLLMClient.chat_completion",
            mock_chat_completion,
        )

        result = enrich_content_with_ai(
            definition=get_report_definition("application_risk"),
            title="申请风险报告",
            period={"start": "2026-07-01", "end": "2026-07-09"},
            content=_application_risk_content(),
            data_quality=DataQuality(),
        )
        assert call_count[0] == 2
        assert result["summary"] == "修复后JSON"

    def test_both_calls_fail_raises_runtime_error(self, monkeypatch):
        """两次调用都失败 → RuntimeError。"""
        _patch_settings(monkeypatch, ai_mode="llm")

        def mock_chat_completion(self, messages):
            return _mock_llm_response("每次都是纯自然语言")

        monkeypatch.setattr(
            "services.reporting.ai_generator.ReportLLMClient.chat_completion",
            mock_chat_completion,
        )

        with pytest.raises(RuntimeError, match="非 JSON"):
            enrich_content_with_ai(
                definition=get_report_definition("application_risk"),
                title="申请风险报告",
                period={"start": "2026-07-01", "end": "2026-07-09"},
                content=_application_risk_content(),
                data_quality=DataQuality(),
            )
