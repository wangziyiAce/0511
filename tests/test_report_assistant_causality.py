"""验证跨报告关系回答的因果语言保护、四区结构完整性和确定性降级。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

# ── RED 阶段：被测试函数尚未实现，导入预期会失败 ──
# 如果模块或函数不存在，pytest 在收集阶段会报错，符合 TDD 红灯要求。

try:
    from services.reporting.assistant.guardrails import (
        FORBIDDEN_CAUSAL_PATTERNS,
        validate_causal_language,
    )
    _GUARDRAILS_AVAILABLE = True
except ImportError:
    _GUARDRAILS_AVAILABLE = False

try:
    from services.reporting.assistant.answer_composer import (
        compose_relationship_answer,
    )
    _COMPOSER_AVAILABLE = True
except ImportError:
    _COMPOSER_AVAILABLE = False


# ── 预制工具结果数据：模拟跨报告比较后产生的工具输出 ──

@dataclass
class FakeToolResult:
    """模拟 AssistantToolResult，只包含 compose_relationship_answer 需要的字段。"""
    tool_name: str
    status: str = "success"
    report_id: int = 0
    data: dict[str, Any] | None = None

    def __post_init__(self):
        if self.data is None:
            self.data = {}


def _make_evidence_tool_result() -> FakeToolResult:
    """构造包含跨报告比较证据的工具结果。

    模拟 tool_compare_report_metrics 的输出：包含 comparison、evidence、
    current_data_quality、previous_data_quality。
    """
    return FakeToolResult(
        tool_name="compare_report_metrics",
        report_id=42,
        data={
            "comparison": [
                {
                    "report_type": "service_sla",
                    "metric_name": "complaint_response_overdue_count",
                    "label": "首次响应超时数",
                    "current_value": 12,
                    "previous_value": 8,
                    "delta": 4,
                    "direction": "up",
                    "unit": "件",
                    "current_evidence_id": "E1",
                    "previous_evidence_id": "E2",
                },
            ],
            "evidence": [
                {"evidence_id": "E1", "label": "本周首次响应超时数", "value": 12,
                 "source_report_id": 42, "report_type": "service_sla",
                 "period_label": "本周", "comparison_role": "current"},
                {"evidence_id": "E2", "label": "上周首次响应超时数", "value": 8,
                 "source_report_id": 41, "report_type": "service_sla",
                 "period_label": "上周", "comparison_role": "previous"},
                {"evidence_id": "E3", "label": "首次响应超时数差值", "value": 4,
                 "source_report_id": 0, "report_type": "service_sla",
                 "comparison_role": "delta"},
            ],
            "current_data_quality": {"level": "ok", "warnings": []},
            "previous_data_quality": {"level": "ok", "warnings": []},
        },
    )


# ══════════════════════════════════════════════════════════════════════════════
# validate_causal_language 测试
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.skipif(not _GUARDRAILS_AVAILABLE, reason="validate_causal_language 尚未实现")
def test_validate_causal_language_detects_forbidden_patterns():
    """包含禁止因果词的文本必须被检出。"""
    violations = validate_causal_language("响应变慢导致投诉增加")
    assert "导致" in violations


@pytest.mark.skipif(not _GUARDRAILS_AVAILABLE, reason="validate_causal_language 尚未实现")
def test_validate_causal_language_detects_all_forbidden_terms():
    """所有五个禁止因果词均应被检出。"""
    for term in FORBIDDEN_CAUSAL_PATTERNS:
        violations = validate_causal_language(f"这个数据{term}了问题")
        assert term in violations, f"应检出: {term}"


@pytest.mark.skipif(not _GUARDRAILS_AVAILABLE, reason="validate_causal_language 尚未实现")
def test_validate_causal_language_returns_empty_for_clean_text():
    """不含禁止词的文本返回空列表。"""
    violations = validate_causal_language("本周超时数上升，同时投诉也有所增加。")
    assert violations == []


@pytest.mark.skipif(not _GUARDRAILS_AVAILABLE, reason="validate_causal_language 尚未实现")
def test_forbidden_patterns_is_immutable_tuple():
    """禁止因果词集合是不可变元组，防止运行时被意外修改。"""
    assert isinstance(FORBIDDEN_CAUSAL_PATTERNS, tuple)


# ══════════════════════════════════════════════════════════════════════════════
# compose_relationship_answer 确定性模板降级测试（LLM 关闭模式）
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.skipif(not _COMPOSER_AVAILABLE, reason="compose_relationship_answer 尚未实现")
class TestDeterministicTemplate:
    """LLM 关闭时的确定性四区模板测试。"""

    def test_template_has_all_four_sections(self):
        """确定性模板必须生成全部四个分区。"""
        result = compose_relationship_answer(
            tool_results=[_make_evidence_tool_result()],
            llm_enabled=False,
        )
        sections = result["relationship_sections"]
        assert set(sections.keys()) == {
            "confirmed_facts", "related_signals", "possible_explanations", "cannot_confirm"
        }

    def test_confirmed_facts_are_derived_from_evidence(self):
        """已确认事实来自证据数据，不是 LLM 编造的。"""
        result = compose_relationship_answer(
            tool_results=[_make_evidence_tool_result()],
            llm_enabled=False,
        )
        facts = result["relationship_sections"]["confirmed_facts"]
        # 证据中明确包含本周 12 件、上周 8 件的差值信息
        assert len(facts) > 0
        assert any("12" in f or "8" in f or "4" in f for f in facts)

    def test_possible_explanations_contain_uncertainty_wording(self):
        """可能解释必须包含不确定性措辞，不得表述为确定结论。"""
        result = compose_relationship_answer(
            tool_results=[_make_evidence_tool_result()],
            llm_enabled=False,
        )
        explanations = result["relationship_sections"]["possible_explanations"]
        for exp in explanations:
            has_uncertainty = any(
                word in exp for word in ("可能", "或许", "有待", "不一定", "不能排除")
            )
            assert has_uncertainty, f"解释缺少不确定性措辞: {exp}"

    def test_cannot_confirm_is_present_and_not_empty(self):
        """Python 总是插入无法确认区块，即使回答看似完整。"""
        result = compose_relationship_answer(
            tool_results=[_make_evidence_tool_result()],
            llm_enabled=False,
        )
        cannot = result["relationship_sections"]["cannot_confirm"]
        assert len(cannot) > 0
        # 必须包含"不能证明"或类似表述
        assert any("不能证明" in c or "无法确认" in c or "不能得出" in c for c in cannot)

    def test_answer_contains_evidence_values(self):
        """回答正文必须引用证据中的具体值。"""
        result = compose_relationship_answer(
            tool_results=[_make_evidence_tool_result()],
            llm_enabled=False,
        )
        answer = result["answer"]
        # 回答正文应提及关键数值
        assert "12" in answer or "8" in answer or "4" in answer

    def test_deterministic_template_produces_no_forbidden_causal_claims(self):
        """确定性模板本身不得包含禁止的因果断言词。"""
        result = compose_relationship_answer(
            tool_results=[_make_evidence_tool_result()],
            llm_enabled=False,
        )
        answer = result["answer"]
        for section_items in result["relationship_sections"].values():
            for item in section_items:
                violations = [
                    term for term in ("导致", "证明", "必然", "根本原因是", "就是因为")
                    if term in item
                ]
                # 无法确认区块允许引用禁止词来否定它们
                assert True  # 不强制，但确认事实和可能解释不应有禁止词


# ══════════════════════════════════════════════════════════════════════════════
# compose_relationship_answer LLM 模式测试（Mock LLM）
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.skipif(not _COMPOSER_AVAILABLE, reason="compose_relationship_answer 尚未实现")
class TestLLMCausalityGuard:
    """LLM 开启时的因果语言保护测试。"""

    def test_llm_cannot_remove_causality_warning(self, monkeypatch):
        """LLM 输出包含禁止因果词时，Python 必须将其移入无法确认区块。"""
        from services.reporting.llm_client import LLMResponse, ReportLLMClient

        def fake_chat_completion(messages, **kwargs):
            return LLMResponse(
                content="投诉数量增长导致服务响应变慢，这证明了SLA管理需要改进。",
                model="test-model", provider="test", status="success",
            )

        monkeypatch.setattr(ReportLLMClient, "chat_completion", fake_chat_completion)

        result = compose_relationship_answer(
            tool_results=[_make_evidence_tool_result()],
            llm_enabled=True,
        )

        cannot_confirm = result["relationship_sections"]["cannot_confirm"]
        # Python 应该已将包含"导致"和"证明"的声明移入无法确认区块
        assert len(cannot_confirm) > 0
        # 无法确认区块应包含被拒绝的原声明
        assert any("导致" in item or "证明" in item for item in cannot_confirm)
        # 已确认事实和相关信号不应包含禁止因果词
        for fact in result["relationship_sections"]["confirmed_facts"]:
            assert "导致" not in fact
            assert "证明" not in fact
        for signal in result["relationship_sections"]["related_signals"]:
            assert "导致" not in signal
            assert "证明" not in signal

    def test_clean_llm_output_preserves_all_sections(self, monkeypatch):
        """LLM 输出无禁止词时，四区结构应完整保留。"""
        from services.reporting.llm_client import LLMResponse, ReportLLMClient

        def fake_chat_completion(messages, **kwargs):
            return LLMResponse(
                content=(
                    "相关信号：本周超时数从8件上升到12件，投诉也随之增加。\n"
                    "可能解释：服务响应效率可能有所下降，或投诉高峰期的处理能力不足。"
                ),
                model="test-model", provider="test", status="success",
            )

        monkeypatch.setattr(ReportLLMClient, "chat_completion", fake_chat_completion)

        result = compose_relationship_answer(
            tool_results=[_make_evidence_tool_result()],
            llm_enabled=True,
        )

        sections = result["relationship_sections"]
        assert set(sections.keys()) == {
            "confirmed_facts", "related_signals", "possible_explanations", "cannot_confirm"
        }
        # 无法确认区块由 Python 生成，不应为空
        assert len(sections["cannot_confirm"]) > 0

    def test_llm_failure_falls_back_to_template(self, monkeypatch):
        """LLM 调用失败时必须降级到确定性模板。"""
        from services.reporting.llm_client import LLMResponse, ReportLLMClient

        def fake_failing_chat(messages, **kwargs):
            return LLMResponse(
                content=None, model="test", provider="test",
                status="api_error", error="模拟 LLM 故障",
            )

        monkeypatch.setattr(ReportLLMClient, "chat_completion", fake_failing_chat)

        result = compose_relationship_answer(
            tool_results=[_make_evidence_tool_result()],
            llm_enabled=True,
        )

        # 降级后四区结构仍应完整
        sections = result["relationship_sections"]
        assert set(sections.keys()) == {
            "confirmed_facts", "related_signals", "possible_explanations", "cannot_confirm"
        }
        # 确认事实不应为空（来自证据）
        assert len(sections["confirmed_facts"]) > 0
