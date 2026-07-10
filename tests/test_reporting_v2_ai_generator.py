import json

import pytest

from services.reporting import ai_generator
from services.reporting.registry import get_report_definition
from services.reporting.schemas import DataQuality


class _FakeResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return {"answer": "{\"summary\": \"ok\", \"explanation\": \"chatflow解释\"}"}


class _FakeClient:
    def __init__(self, recorder: list[dict]):
        self.recorder = recorder

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def post(self, url, json, headers):
        self.recorder.append({"url": url, "json": json, "headers": headers})
        return _FakeResponse()


def test_dify_chatflow_call_uses_chat_messages_contract(monkeypatch):
    """报告模块对接的是 Dify Chatflow，不能再走 Workflow 风格调用。

    这个测试保护的是项目讲解和真实联调都会遇到的契约点：
    文档说 Chatflow，代码也必须打 `/chat-messages`，并使用 Chatflow 的
    `inputs + query + response_mode + user` 请求体。
    """

    calls: list[dict] = []

    monkeypatch.setattr(ai_generator, "DIFY_API_URL", "https://dify.example/v1")
    monkeypatch.setattr(ai_generator, "DIFY_API_KEY", "test-key")
    monkeypatch.setattr(ai_generator.httpx, "Client", lambda timeout: _FakeClient(calls))

    response = ai_generator._call_dify_chatflow(
        inputs={"report_type": "application_risk"},
        query="请生成报告解释",
        timeout=3,
    )

    assert calls[0]["url"] == "https://dify.example/v1/chat-messages"
    assert calls[0]["json"] == {
        "inputs": {"report_type": "application_risk"},
        "query": "请生成报告解释",
        "response_mode": "blocking",
        "user": "report-service",
    }
    assert calls[0]["headers"]["Authorization"] == "Bearer test-key"
    assert response["answer"].startswith("{")


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


def test_parse_dify_chatflow_answer_accepts_markdown_json_block():
    response = {
        "answer": """```json
{"summary": "ok", "explanation": "代码块里的 Chatflow JSON"}
```"""
    }

    parsed = ai_generator._parse_dify_chatflow_content(response)

    assert parsed == {"summary": "ok", "explanation": "代码块里的 Chatflow JSON"}


def test_parse_dify_chatflow_answer_rejects_non_json_text():
    with pytest.raises(json.JSONDecodeError):
        ai_generator._parse_dify_chatflow_content({"answer": "这是一段普通自然语言，不是 JSON"})


def test_chatflow_non_json_response_propagates_to_failed_task_chain(monkeypatch):
    monkeypatch.setenv("REPORT_AI_MODE", "dify")
    monkeypatch.setattr(ai_generator, "DIFY_API_KEY", "test-key")
    monkeypatch.setattr(
        ai_generator,
        "_call_dify_chatflow",
        lambda **kwargs: {"answer": "这是一段普通自然语言，不是 JSON"},
    )

    with pytest.raises(json.JSONDecodeError):
        ai_generator.enrich_content_with_ai(
            definition=get_report_definition("application_risk"),
            title="申请风险报告",
            period={"start": "2026-07-01", "end": "2026-07-09"},
            content=_application_risk_content(),
            data_quality=DataQuality(),
        )


def test_chatflow_explanation_cannot_overwrite_business_metrics(monkeypatch):
    monkeypatch.setenv("REPORT_AI_MODE", "dify")
    monkeypatch.setattr(ai_generator, "DIFY_API_KEY", "test-key")
    monkeypatch.setattr(
        ai_generator,
        "_call_dify_chatflow",
        lambda **kwargs: {
            "answer": json.dumps(
                {
                    "summary": "AI 解释",
                    "explanation": "只解释，不改数字",
                    "metrics": {"total_applications": 999},
                },
                ensure_ascii=False,
            )
        },
    )

    result = ai_generator.enrich_content_with_ai(
        definition=get_report_definition("application_risk"),
        title="申请风险报告",
        period={"start": "2026-07-01", "end": "2026-07-09"},
        content=_application_risk_content(),
        data_quality=DataQuality(),
    )

    assert result["summary"] == "AI 解释"
    assert result["explanation"] == "只解释，不改数字"
    assert result["metrics"]["total_applications"] == 1
    assert result["risk_items"][0]["risk_score"] == 80


def test_chatflow_first_invalid_schema_then_repair_success(monkeypatch):
    calls: list[dict] = []

    def fake_chatflow(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            return {"answer": '{"summary": {"bad": "type"}}'}
        return {"answer": '{"summary": "修复后总结", "explanation": "修复后解释"}'}

    monkeypatch.setenv("REPORT_AI_MODE", "dify")
    monkeypatch.setattr(ai_generator, "DIFY_API_KEY", "test-key")
    monkeypatch.setattr(ai_generator, "_call_dify_chatflow", fake_chatflow)

    result = ai_generator.enrich_content_with_ai(
        definition=get_report_definition("application_risk"),
        title="申请风险报告",
        period={"start": "2026-07-01", "end": "2026-07-09"},
        content=_application_risk_content(),
        data_quality=DataQuality(),
    )

    assert len(calls) == 2
    assert "validation_error" in calls[1]["inputs"]
    assert result["summary"] == "修复后总结"
    assert result["explanation"] == "修复后解释"
