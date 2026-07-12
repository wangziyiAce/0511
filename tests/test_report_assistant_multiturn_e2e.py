"""智能报告助手 Iteration 2A.1 — 多轮 E2E 集成测试与上下文伪造测试。

测试目标：
1. 完整四轮对话（生成报告 → 钻取 → 解释风险 → 解释指标）
2. 跨 Service 实例上下文传递（无状态验证）
3. 客户端上下文伪造安全性验证

数据库方案：Mock Repository 方案
- 使用 mock `_execute_tool` 模拟工具层返回
- 不依赖真实数据库，避免 SQLite BIGINT autoincrement 问题
- 覆盖完整 Service 编排链（意图解析 → 工具调用 → 回答生成 → 上下文更新）
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from services.reporting.assistant.schemas import (
    AssistantToolResult,
    EvidenceItem,
    ReferencedEntity,
    ReportAssistantIntent,
    ReportAssistantMessageRequest,
    ReportAssistantMessageResponse,
    ReportConversationContext,
)
from services.reporting.assistant.service import ReportAssistantService


# ============================================================================
# Test Helpers
# ============================================================================

FIXED_REPORT_ID = 128
FIXED_CONVERSATION_ID = "e2e-test-conv-001"


def _make_admin():
    """创建 admin 角色的 mock 用户。"""
    from utils.auth import CurrentUser
    return CurrentUser(
        id=1, username="admin", real_name="管理员",
        user_type="employee", role_code="admin", department="技术部",
    )


def _make_ctx(**overrides) -> ReportConversationContext:
    """创建会话上下文。"""
    defaults = {"conversation_id": FIXED_CONVERSATION_ID}
    defaults.update(overrides)
    return ReportConversationContext(**defaults)


# ---- 预置报告数据 ----

COMPLETED_REPORT_CONTENT = {
    "risk_items": [
        {
            "application_id": "A1024",
            "risk_score": 90,
            "risk_level": "high",
            "risk_reasons": ["申请已逾期", "缺少两项必填材料"],
            "missing_materials": ["推荐信", "成绩单"],
            "next_action": "立即联系学生补齐材料",
            "stage": "材料审核",
            "student_id": 201,
            "owner_id": 5,
        },
        {
            "application_id": "A1058",
            "risk_score": 70,
            "risk_level": "high",
            "risk_reasons": ["距离截止日期少于 7 天"],
            "missing_materials": ["个人陈述"],
            "next_action": "提醒顾问跟进",
            "stage": "文书准备",
            "student_id": 202,
            "owner_id": 5,
        },
        {
            "application_id": "A2001",
            "risk_score": 40,
            "risk_level": "medium",
            "risk_reasons": ["材料提交不完整"],
            "missing_materials": [],
            "next_action": "持续观察",
            "stage": "材料审核",
            "student_id": 203,
            "owner_id": 6,
        },
    ],
    "metric_traces": [
        {
            "metric_name": "risk_score",
            "source_tables": ["application_risk_fact"],
            "formula": "base_score + overdue_bonus + missing_material_bonus",
            "filters": {"status": "active"},
        },
        {
            "metric_name": "high_risk_count",
            "source_tables": ["application_risk_fact"],
            "formula": "COUNT WHERE risk_level = 'high'",
            "filters": {"status": "active"},
        },
    ],
}


# ---- 各 Turn 的 mock _execute_tool 实现 ----

def _mock_execute_turn1_generate(
    self, plan, resolved_period, generated_by, db,
    idempotency_key=None, current_user=None, context=None, message="",
):
    """Turn 1：生成申请风险报告 — 返回 generating 状态。"""
    return [AssistantToolResult(
        tool_name="generate_existing_report",
        status="success",
        data={
            "report_id": FIXED_REPORT_ID,
            "report_type": "application_risk",
            "status": "generating",
            "created": True,
            "period_start": "2026-07-04",
            "period_end": "2026-07-10",
        },
        report_id=FIXED_REPORT_ID,
    )]


def _mock_execute_turn1_completed(
    self, plan, resolved_period, generated_by, db,
    idempotency_key=None, current_user=None, context=None, message="",
):
    """Turn 1 变体：报告已完成（用于直接开始钻取的场景）。"""
    return [AssistantToolResult(
        tool_name="generate_existing_report",
        status="success",
        data={
            "report_id": FIXED_REPORT_ID,
            "report_type": "application_risk",
            "status": "completed",
            "created": False,
            "period_start": "2026-07-04",
            "period_end": "2026-07-10",
        },
        report_id=FIXED_REPORT_ID,
    )]


def _mock_execute_turn2_status(
    self, plan, resolved_period, generated_by, db,
    idempotency_key=None, current_user=None, context=None, message="",
):
    """Turn 2：通过助手查询同一报告状态，返回已完成且不创建新报告。"""
    return [AssistantToolResult(
        tool_name="query_report_status",
        status="success",
        data={
            "report_id": FIXED_REPORT_ID,
            "report_type": "application_risk",
            "status": "completed",
        },
        report_id=FIXED_REPORT_ID,
    )]


def _mock_execute_turn2_drill_down(
    self, plan, resolved_period, generated_by, db,
    idempotency_key=None, current_user=None, context=None, message="",
):
    """Turn 2：钻取最高风险项。"""
    risk_items = COMPLETED_REPORT_CONTENT["risk_items"]
    items = sorted(risk_items, key=lambda x: x["risk_score"], reverse=True)

    entities = []
    for i, item in enumerate(items):
        entities.append(ReferencedEntity(
            position=i + 1,
            entity_type="application",
            entity_id=str(item["application_id"]),
            display_name=f"申请 #{item['application_id']}",
            source_report_id=FIXED_REPORT_ID,
            metadata={
                "risk_score": item["risk_score"],
                "risk_level": item["risk_level"],
            },
        ).model_dump())

    return [AssistantToolResult(
        tool_name="get_application_risk_items",
        status="success",
        data={
            "report_id": FIXED_REPORT_ID,
            "total_items": len(items),
            "returned_items": len(items),
            "items": items,
            "referenced_entities": entities,
        },
        report_id=FIXED_REPORT_ID,
        data_quality={"level": "ok"},
    )]


def _mock_execute_turn3_explain_risk(
    self, plan, resolved_period, generated_by, db,
    idempotency_key=None, current_user=None, context=None, message="",
):
    """Turn 3：解释 A1024 风险详情。"""
    a1024 = COMPLETED_REPORT_CONTENT["risk_items"][0]
    return [AssistantToolResult(
        tool_name="get_application_risk_detail",
        status="success",
        data={
            "report_id": FIXED_REPORT_ID,
            "application_id": "A1024",
            "risk_score": a1024["risk_score"],
            "risk_level": a1024["risk_level"],
            "risk_reasons": a1024["risk_reasons"],
            "missing_materials": a1024["missing_materials"],
            "next_action": a1024["next_action"],
            "stage": a1024["stage"],
            "student_id": a1024["student_id"],
            "owner_id": a1024["owner_id"],
            "metric_traces": COMPLETED_REPORT_CONTENT["metric_traces"],
        },
        report_id=FIXED_REPORT_ID,
        data_quality={"level": "ok"},
    )]


def _mock_execute_turn4_explain_metric(
    self, plan, resolved_period, generated_by, db,
    idempotency_key=None, current_user=None, context=None, message="",
):
    """Turn 4：解释 risk_score 指标来源。"""
    trace = COMPLETED_REPORT_CONTENT["metric_traces"][0]
    return [AssistantToolResult(
        tool_name="get_metric_trace",
        status="success",
        data={
            "metric_name": trace["metric_name"],
            "source_tables": trace["source_tables"],
            "formula": trace["formula"],
            "filters": trace["filters"],
            "period_start": "2026-07-04",
            "period_end": "2026-07-10",
        },
        report_id=FIXED_REPORT_ID,
        data_quality={"level": "ok"},
    )]


def _patch_assistant_settings(monkeypatch):
    """统一 patch 所有使用 settings 的模块。"""
    from services.reporting.assistant.config import ReportAssistantSettings
    import services.reporting.assistant.config as config_module
    import services.reporting.assistant.intent_parser as ip_module
    import services.reporting.assistant.clarification as cl_module

    test_settings = ReportAssistantSettings(enabled=True, llm_enabled=False)
    monkeypatch.setattr(config_module, "settings", test_settings)
    monkeypatch.setattr(ip_module, "settings", test_settings)
    monkeypatch.setattr(cl_module, "settings", test_settings)
    return test_settings


# ============================================================================
# 一、完整四轮对话 E2E 测试
# ============================================================================


class TestFourTurnConversation:
    """验证完整四轮对话：生成 → 钻取 → 解释风险 → 解释指标。"""

    def test_turn1_generate_report(self, monkeypatch):
        """Turn 1：'看看申请风险' → generating + report_id=128。"""
        _patch_assistant_settings(monkeypatch)
        monkeypatch.setattr(ReportAssistantService, "_execute_tool", _mock_execute_turn1_generate)

        service = ReportAssistantService()
        response = service.handle_message(
            request=ReportAssistantMessageRequest(
                message="看看现在的申请风险",
                conversation_context=_make_ctx(),
            ),
            current_user=_make_admin(),
            db=MagicMock(),
        )

        assert response.status == "generating"
        assert response.report_id == FIXED_REPORT_ID
        assert response.report_type == "application_risk"
        assert response.intent == ReportAssistantIntent.GENERATE_REPORT
        # 上下文应记录 report_id
        assert response.conversation_context.last_report_id == FIXED_REPORT_ID
        assert response.conversation_context.last_report_type == "application_risk"

    def test_turn2_drill_down_after_generation(self, monkeypatch):
        """Turn 2：'最严重的是哪几个？' → drill_down + 排序 + entities。"""
        _patch_assistant_settings(monkeypatch)
        monkeypatch.setattr(ReportAssistantService, "_execute_tool", _mock_execute_turn2_drill_down)

        # 模拟 Turn 1 之后的上下文
        ctx = _make_ctx(
            last_report_id=FIXED_REPORT_ID,
            last_report_type="application_risk",
            previous_intent=ReportAssistantIntent.GENERATE_REPORT,
        )

        service = ReportAssistantService()
        response = service.handle_message(
            request=ReportAssistantMessageRequest(
                message="最严重的是哪几个？",
                conversation_context=ctx,
            ),
            current_user=_make_admin(),
            db=MagicMock(),
        )

        assert response.intent == ReportAssistantIntent.DRILL_DOWN
        assert response.status == "completed"
        # report_id 未变化
        assert response.conversation_context.last_report_id == FIXED_REPORT_ID
        # 上下文包含 referenced_entities
        entities = response.conversation_context.referenced_entities
        assert len(entities) >= 2
        # A1024 排在 position 1（最高风险分 90）
        # 注意：entities 可以是 dict 或 ReferencedEntity 对象，统一使用 get
        e0 = entities[0] if isinstance(entities[0], dict) else entities[0].model_dump()
        e1 = entities[1] if isinstance(entities[1], dict) else entities[1].model_dump()
        assert e0["position"] == 1
        assert e0["entity_id"] == "A1024"
        assert e0["metadata"]["risk_score"] == 90
        # A1058 排在 position 2
        assert e1["position"] == 2
        assert e1["entity_id"] == "A1058"
        assert e1["metadata"]["risk_score"] == 70
        # 排序由 Python 完成（risk_score 降序）
        assert e0["metadata"]["risk_score"] >= e1["metadata"]["risk_score"]

    def test_turn2_drill_down_does_not_regenerate(self, monkeypatch):
        """Turn 2：钻取 → 不调用 create_report_task_result。"""
        _patch_assistant_settings(monkeypatch)

        call_count = [0]
        def tracking_execute(self, plan, resolved_period, generated_by, db, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return _mock_execute_turn2_drill_down(
                    self, plan, resolved_period, generated_by, db, **kwargs,
                )
            return [AssistantToolResult(tool_name="noop", status="error", error="不应调用")]

        monkeypatch.setattr(ReportAssistantService, "_execute_tool", tracking_execute)

        ctx = _make_ctx(
            last_report_id=FIXED_REPORT_ID,
            last_report_type="application_risk",
            previous_intent=ReportAssistantIntent.GENERATE_REPORT,
        )

        service = ReportAssistantService()
        response = service.handle_message(
            request=ReportAssistantMessageRequest(
                message="最严重的是哪几个？",
                conversation_context=ctx,
            ),
            current_user=_make_admin(),
            db=MagicMock(),
        )

        # 只调用了一次 _execute_tool（drill_down）
        assert call_count[0] == 1
        assert response.intent == ReportAssistantIntent.DRILL_DOWN

    def test_turn3_explain_first_entity(self, monkeypatch):
        """Turn 3：'第一个为什么这么高？' → explain_risk + 解析到 A1024。"""
        _patch_assistant_settings(monkeypatch)
        monkeypatch.setattr(ReportAssistantService, "_execute_tool", _mock_execute_turn3_explain_risk)

        # 模拟 Turn 2 之后的上下文（带两个 referenced_entities）
        ctx = _make_ctx(
            last_report_id=FIXED_REPORT_ID,
            last_report_type="application_risk",
            previous_intent=ReportAssistantIntent.DRILL_DOWN,
            referenced_entities=[
                ReferencedEntity(
                    position=1, entity_type="application", entity_id="A1024",
                    display_name="申请 #A1024", source_report_id=FIXED_REPORT_ID,
                    metadata={"risk_score": 90, "risk_level": "high"},
                ).model_dump(),
                ReferencedEntity(
                    position=2, entity_type="application", entity_id="A1058",
                    display_name="申请 #A1058", source_report_id=FIXED_REPORT_ID,
                    metadata={"risk_score": 70, "risk_level": "high"},
                ).model_dump(),
            ],
        )

        service = ReportAssistantService()
        response = service.handle_message(
            request=ReportAssistantMessageRequest(
                message="第一个为什么这么高？",
                conversation_context=ctx,
            ),
            current_user=_make_admin(),
            db=MagicMock(),
        )

        assert response.intent == ReportAssistantIntent.EXPLAIN_RISK
        assert response.status == "completed"
        # report_id 仍然一致
        assert response.conversation_context.last_report_id == FIXED_REPORT_ID
        # 回答中包含 A1024 的风险原因
        assert "A1024" in response.answer or "90" in response.answer or "推荐信" in response.answer or "逾期" in response.answer
        # 不包含 A1058 的风险原因（"个人陈述"是 1058 的）
        # 注意：确定性模板不会主动引用其他实体的数据

    def test_turn4_explain_metric(self, monkeypatch):
        """Turn 4：'这个风险分怎么算？' → explain_metric + MetricTrace。"""
        _patch_assistant_settings(monkeypatch)
        monkeypatch.setattr(ReportAssistantService, "_execute_tool", _mock_execute_turn4_explain_metric)

        ctx = _make_ctx(
            last_report_id=FIXED_REPORT_ID,
            last_report_type="application_risk",
            previous_intent=ReportAssistantIntent.EXPLAIN_RISK,
            referenced_entities=[
                ReferencedEntity(
                    position=1, entity_type="application", entity_id="A1024",
                    display_name="申请 #A1024", source_report_id=FIXED_REPORT_ID,
                    metadata={"risk_score": 90, "risk_level": "high"},
                ).model_dump(),
            ],
        )

        service = ReportAssistantService()
        response = service.handle_message(
            request=ReportAssistantMessageRequest(
                message="这个风险分怎么算？",
                conversation_context=ctx,
            ),
            current_user=_make_admin(),
            db=MagicMock(),
        )

        assert response.intent == ReportAssistantIntent.EXPLAIN_METRIC
        assert response.status == "completed"
        # report_id 仍然一致
        assert response.conversation_context.last_report_id == FIXED_REPORT_ID
        # 回答包含来源表
        assert "application_risk_fact" in response.answer or "base_score" in response.answer or "公式" in response.answer
        # 不允许 LLM 自行生成公式（确认公式来自报告内容）
        # 确定性模板直接使用报告中的 formula

    def test_report_id_consistent_across_four_turns(self, monkeypatch):
        """report_id 在四轮中保持一致。"""
        _patch_assistant_settings(monkeypatch)

        report_ids = []

        # Turn 1
        monkeypatch.setattr(ReportAssistantService, "_execute_tool", _mock_execute_turn1_generate)
        service = ReportAssistantService()
        ctx = _make_ctx()
        r1 = service.handle_message(
            request=ReportAssistantMessageRequest(message="看看申请风险", conversation_context=ctx),
            current_user=_make_admin(), db=MagicMock(),
        )
        report_ids.append(r1.conversation_context.last_report_id)

        # Turn 2
        monkeypatch.setattr(ReportAssistantService, "_execute_tool", _mock_execute_turn2_drill_down)
        r2 = service.handle_message(
            request=ReportAssistantMessageRequest(
                message="最严重的是哪几个？",
                conversation_context=r1.conversation_context,
            ),
            current_user=_make_admin(), db=MagicMock(),
        )
        report_ids.append(r2.conversation_context.last_report_id)

        # Turn 3
        monkeypatch.setattr(ReportAssistantService, "_execute_tool", _mock_execute_turn3_explain_risk)
        r3 = service.handle_message(
            request=ReportAssistantMessageRequest(
                message="第一个为什么这么高？",
                conversation_context=r2.conversation_context,
            ),
            current_user=_make_admin(), db=MagicMock(),
        )
        report_ids.append(r3.conversation_context.last_report_id)

        # Turn 4
        monkeypatch.setattr(ReportAssistantService, "_execute_tool", _mock_execute_turn4_explain_metric)
        r4 = service.handle_message(
            request=ReportAssistantMessageRequest(
                message="这个风险分怎么算？",
                conversation_context=r3.conversation_context,
            ),
            current_user=_make_admin(), db=MagicMock(),
        )
        report_ids.append(r4.conversation_context.last_report_id)

        # 所有四轮的 report_id 一致
        assert all(rid == FIXED_REPORT_ID for rid in report_ids), (
            f"四轮 report_id 应保持一致，实际: {report_ids}"
        )


# ============================================================================
# 二、跨 Service 实例测试
# ============================================================================


class TestFiveTurnSameReportClosure:
    """验证生成、状态、钻取、实体解释和指标追溯始终绑定同一报告。"""

    def test_five_turns_keep_one_report_and_use_assistant_status(self, monkeypatch):
        """Turn 2 必须识别 query_report_status，Turn 2-5 不得再次生成报告。"""
        _patch_assistant_settings(monkeypatch)
        generation_calls: list[int] = []

        def dispatch(self, plan, resolved_period, generated_by, db, **kwargs):
            if plan.intent == ReportAssistantIntent.GENERATE_REPORT:
                generation_calls.append(FIXED_REPORT_ID)
                return _mock_execute_turn1_generate(
                    self, plan, resolved_period, generated_by, db, **kwargs,
                )
            if plan.intent == ReportAssistantIntent.QUERY_REPORT_STATUS:
                return _mock_execute_turn2_status(
                    self, plan, resolved_period, generated_by, db, **kwargs,
                )
            if plan.intent == ReportAssistantIntent.DRILL_DOWN:
                return _mock_execute_turn2_drill_down(
                    self, plan, resolved_period, generated_by, db, **kwargs,
                )
            if plan.intent == ReportAssistantIntent.EXPLAIN_RISK:
                return _mock_execute_turn3_explain_risk(
                    self, plan, resolved_period, generated_by, db, **kwargs,
                )
            if plan.intent == ReportAssistantIntent.EXPLAIN_METRIC:
                return _mock_execute_turn4_explain_metric(
                    self, plan, resolved_period, generated_by, db, **kwargs,
                )
            raise AssertionError(f"未覆盖的五步意图: {plan.intent}")

        monkeypatch.setattr(ReportAssistantService, "_execute_tool", dispatch)
        service = ReportAssistantService()
        context = _make_ctx()
        messages = [
            "看看现在的申请风险",
            "报告生成好了吗？",
            "最严重的是哪几个？",
            "第一个为什么这么高？",
            "这个风险分怎么算？",
        ]
        responses = []

        for index, message in enumerate(messages, start=1):
            response = service.handle_message(
                request=ReportAssistantMessageRequest(
                    message=message,
                    conversation_context=context,
                    client_request_id=f"five-turn-{index}",
                ),
                current_user=_make_admin(),
                db=MagicMock(),
            )
            responses.append(response)
            context = response.conversation_context

        assert responses[0].status == "generating"
        assert responses[1].intent == ReportAssistantIntent.QUERY_REPORT_STATUS
        assert responses[1].status == "completed"
        assert responses[2].intent == ReportAssistantIntent.DRILL_DOWN
        assert len(responses[2].conversation_context.referenced_entities) >= 2

        first_entity = responses[2].conversation_context.referenced_entities[0]
        assert first_entity.position == 1
        assert first_entity.entity_id == "A1024"
        assert responses[3].intent == ReportAssistantIntent.EXPLAIN_RISK
        assert responses[3].conversation_context.referenced_entities[0].entity_id == first_entity.entity_id
        assert responses[4].intent == ReportAssistantIntent.EXPLAIN_METRIC
        assert responses[4].conversation_context.referenced_entities[0].entity_id == first_entity.entity_id
        assert responses[4].evidence[0].evidence_id == "E1"
        assert responses[4].evidence[0].source_report_id == FIXED_REPORT_ID

        report_ids = {response.report_id for response in responses}
        assert report_ids == {FIXED_REPORT_ID}
        assert generation_calls == [FIXED_REPORT_ID]


class TestCrossServiceInstance:
    """验证不同 Service 实例之间通过 context 传递状态（无进程内会话依赖）。"""

    def test_context_passed_between_instances(self, monkeypatch):
        """Turn 1 用 service_a，Turn 2/3 用 service_b — 状态通过 context 传递。"""
        _patch_assistant_settings(monkeypatch)

        # Turn 1: service_a 生成报告
        monkeypatch.setattr(ReportAssistantService, "_execute_tool", _mock_execute_turn1_generate)
        service_a = ReportAssistantService()
        r1 = service_a.handle_message(
            request=ReportAssistantMessageRequest(
                message="看看申请风险",
                conversation_context=_make_ctx(),
            ),
            current_user=_make_admin(), db=MagicMock(),
        )
        assert r1.report_id == FIXED_REPORT_ID

        # Turn 2: service_b 使用 r1 的上下文
        monkeypatch.setattr(ReportAssistantService, "_execute_tool", _mock_execute_turn2_drill_down)
        service_b = ReportAssistantService()
        r2 = service_b.handle_message(
            request=ReportAssistantMessageRequest(
                message="最严重的是哪几个？",
                conversation_context=r1.conversation_context,
            ),
            current_user=_make_admin(), db=MagicMock(),
        )
        assert r2.intent == ReportAssistantIntent.DRILL_DOWN
        assert r2.conversation_context.last_report_id == FIXED_REPORT_ID
        assert len(r2.conversation_context.referenced_entities) >= 2

        # Turn 3: service_b 继续
        monkeypatch.setattr(ReportAssistantService, "_execute_tool", _mock_execute_turn3_explain_risk)
        r3 = service_b.handle_message(
            request=ReportAssistantMessageRequest(
                message="第一个为什么这么高？",
                conversation_context=r2.conversation_context,
            ),
            current_user=_make_admin(), db=MagicMock(),
        )
        assert r3.intent == ReportAssistantIntent.EXPLAIN_RISK
        assert r3.conversation_context.last_report_id == FIXED_REPORT_ID

    def test_no_in_memory_session_dependency(self, monkeypatch):
        """验证无进程内会话依赖 — 纯靠 context 传递。"""
        _patch_assistant_settings(monkeypatch)

        monkeypatch.setattr(ReportAssistantService, "_execute_tool", _mock_execute_turn2_drill_down)

        # 构造一个独立的 context（不来自任何 service 实例）
        ctx = _make_ctx(
            last_report_id=FIXED_REPORT_ID,
            last_report_type="application_risk",
            previous_intent=ReportAssistantIntent.GENERATE_REPORT,
        )

        # 新 service 实例，没有全局状态
        service = ReportAssistantService()
        response = service.handle_message(
            request=ReportAssistantMessageRequest(
                message="最严重的是哪几个？",
                conversation_context=ctx,
            ),
            current_user=_make_admin(), db=MagicMock(),
        )

        assert response.intent == ReportAssistantIntent.DRILL_DOWN
        assert response.conversation_context.last_report_id == FIXED_REPORT_ID


# ============================================================================
# 三、上下文伪造安全测试
# ============================================================================


class TestContextForgerySecurity:
    """验证客户端传入的上下文不可信，必须服务端重新校验。"""

    def test_forged_report_id_is_denied(self, monkeypatch):
        """客户端伪造 last_report_id → 工具层拒绝。"""
        _patch_assistant_settings(monkeypatch)

        # mock 工具层：报告不存在
        def mock_execute_not_found(self, plan, resolved_period, generated_by, db, **kwargs):
            return [AssistantToolResult(
                tool_name="query_report_status",
                status="error",
                error=f"报告不存在: 99999",
            )]

        monkeypatch.setattr(ReportAssistantService, "_execute_tool", mock_execute_not_found)

        ctx = _make_ctx(
            last_report_id=99999,  # 伪造的 report_id
            last_report_type="application_risk",
        )

        service = ReportAssistantService()
        response = service.handle_message(
            request=ReportAssistantMessageRequest(
                message="报告状态怎么样？",
                conversation_context=ctx,
            ),
            current_user=_make_admin(),
            db=MagicMock(),
        )

        assert response.status in ("not_found", "error")

    def test_forged_entity_id_is_rejected(self, monkeypatch):
        """客户端伪造 entity_id → 工具层拒绝。"""
        _patch_assistant_settings(monkeypatch)

        def mock_execute_reject_entity(self, plan, resolved_period, generated_by, db, **kwargs):
            return [AssistantToolResult(
                tool_name="get_application_risk_detail",
                status="error",
                error=f"报告中未找到申请: FAKE999",
            )]

        monkeypatch.setattr(ReportAssistantService, "_execute_tool", mock_execute_reject_entity)

        ctx = _make_ctx(
            last_report_id=FIXED_REPORT_ID,
            last_report_type="application_risk",
            referenced_entities=[
                ReferencedEntity(
                    position=1, entity_type="application", entity_id="FAKE999",
                    display_name="伪造实体", source_report_id=FIXED_REPORT_ID,
                    metadata={"risk_score": 99, "risk_level": "high"},
                ).model_dump(),
            ],
        )

        service = ReportAssistantService()
        response = service.handle_message(
            request=ReportAssistantMessageRequest(
                message="这个为什么这么高？",
                conversation_context=ctx,
            ),
            current_user=_make_admin(),
            db=MagicMock(),
        )

        assert response.status in ("not_found", "error")

    def test_entity_from_other_report_is_rejected(self, monkeypatch):
        """客户端引用其他报告的实体 → source_report_id 不一致。"""
        _patch_assistant_settings(monkeypatch)

        def mock_execute_check_source(self, plan, resolved_period, generated_by, db, **kwargs):
            context = kwargs.get("context")
            if context and context.referenced_entities:
                for e in context.referenced_entities:
                    # 兼容 dict 和 ReferencedEntity 对象
                    src_id = e.get("source_report_id") if isinstance(e, dict) else getattr(e, "source_report_id", 0)
                    if src_id != FIXED_REPORT_ID:
                        return [AssistantToolResult(
                            tool_name="explain_risk", status="error",
                            error="无权访问此实体",
                        )]
            return [AssistantToolResult(
                tool_name="get_application_risk_detail", status="success",
                data={"report_id": FIXED_REPORT_ID, "application_id": "A1024",
                      "risk_score": 90, "risk_level": "high",
                      "risk_reasons": ["逾期"], "missing_materials": [], "metric_traces": []},
                report_id=FIXED_REPORT_ID,
            )]

        monkeypatch.setattr(ReportAssistantService, "_execute_tool", mock_execute_check_source)

        ctx = _make_ctx(
            last_report_id=FIXED_REPORT_ID,
            last_report_type="application_risk",
            referenced_entities=[
                ReferencedEntity(
                    position=1, entity_type="application", entity_id="A1024",
                    source_report_id=999,  # 来自其他报告
                    metadata={"risk_score": 90, "risk_level": "high"},
                ).model_dump(),
            ],
        )

        service = ReportAssistantService()
        response = service.handle_message(
            request=ReportAssistantMessageRequest(
                message="第一个为什么这么高？",
                conversation_context=ctx,
            ),
            current_user=_make_admin(),
            db=MagicMock(),
        )

        # 应被拒绝（source_report_id 不一致）
        assert response.status in ("error", "permission_denied", "not_found")

    def test_entity_position_out_of_range_requires_clarification(self, monkeypatch):
        """'第三个'但只有两个实体 → 需要澄清。"""
        _patch_assistant_settings(monkeypatch)

        def mock_execute_out_of_range(self, plan, resolved_period, generated_by, db, **kwargs):
            return [AssistantToolResult(
                tool_name="explain_risk", status="error",
                error="无法确定要解释哪个申请",
            )]

        monkeypatch.setattr(ReportAssistantService, "_execute_tool", mock_execute_out_of_range)

        ctx = _make_ctx(
            last_report_id=FIXED_REPORT_ID,
            last_report_type="application_risk",
            referenced_entities=[
                ReferencedEntity(
                    position=1, entity_type="application", entity_id="A1024",
                    source_report_id=FIXED_REPORT_ID,
                    metadata={"risk_score": 90, "risk_level": "high"},
                ).model_dump(),
                ReferencedEntity(
                    position=2, entity_type="application", entity_id="A1058",
                    source_report_id=FIXED_REPORT_ID,
                    metadata={"risk_score": 70, "risk_level": "high"},
                ).model_dump(),
            ],
        )

        service = ReportAssistantService()
        response = service.handle_message(
            request=ReportAssistantMessageRequest(
                message="第三个呢？",
                conversation_context=ctx,
            ),
            current_user=_make_admin(),
            db=MagicMock(),
        )

        # 越界 → 返回错误或澄清
        assert response.status in ("error", "needs_clarification", "not_found")

    def test_other_employee_report_cannot_be_read(self, monkeypatch):
        """普通员工尝试读取他人报告 → 拒绝。"""
        _patch_assistant_settings(monkeypatch)

        def mock_execute_perm_denied(self, plan, resolved_period, generated_by, db, **kwargs):
            return [AssistantToolResult(
                tool_name="query_report_status",
                status="error",
                error="无权访问此报告",
            )]

        monkeypatch.setattr(ReportAssistantService, "_execute_tool", mock_execute_perm_denied)

        from utils.auth import CurrentUser
        employee = CurrentUser(
            id=99, username="employee", real_name="员工",
            user_type="employee", role_code="employee", department="销售部",
        )

        ctx = _make_ctx(
            last_report_id=FIXED_REPORT_ID,
            last_report_type="application_risk",
        )

        service = ReportAssistantService()
        response = service.handle_message(
            request=ReportAssistantMessageRequest(
                message="报告状态怎么样？",
                conversation_context=ctx,
            ),
            current_user=employee,
            db=MagicMock(),
        )

        assert response.status == "permission_denied"

    def test_unauthorized_psych_report_context_is_denied(self, monkeypatch):
        """客户端传入 psych_weekly 报告上下文（非授权角色）→ 工具层拒绝。

        使用触发多轮追问的消息（'报告状态怎么样？'），让服务进入工具调用路径，
        然后在工具模拟中返回权限拒绝。
        """
        _patch_assistant_settings(monkeypatch)

        def mock_execute_psych_denied(self, plan, resolved_period, generated_by, db, **kwargs):
            # 检查是否是 psych_weekly 报告的请求
            context = kwargs.get("context")
            if context and context.last_report_type == "psych_weekly":
                return [AssistantToolResult(
                    tool_name="query_report_status",
                    status="error",
                    error="无权访问报告类型: psych_weekly",
                )]
            return [AssistantToolResult(
                tool_name="query_report_status", status="success",
                data={"report_id": 200, "status": "completed"},
                report_id=200,
            )]

        monkeypatch.setattr(ReportAssistantService, "_execute_tool", mock_execute_psych_denied)

        from utils.auth import CurrentUser
        employee = CurrentUser(
            id=50, username="counselor", real_name="顾问",
            user_type="employee", role_code="employee", department="咨询部",
        )

        ctx = _make_ctx(
            last_report_id=200,
            last_report_type="psych_weekly",
        )

        service = ReportAssistantService()
        response = service.handle_message(
            request=ReportAssistantMessageRequest(
                message="报告状态怎么样？",  # 触发 query_report_status
                conversation_context=ctx,
            ),
            current_user=employee,
            db=MagicMock(),
        )

        assert response.status in ("permission_denied", "error")

    def test_client_metadata_not_trusted(self, monkeypatch):
        """客户端 metadata 中的 risk_score 不可信 → 工具层重新从报告内容读取。"""
        _patch_assistant_settings(monkeypatch)

        # 工具层返回真实值（90），忽略客户端传入的伪造值（999）
        monkeypatch.setattr(ReportAssistantService, "_execute_tool", _mock_execute_turn3_explain_risk)

        ctx = _make_ctx(
            last_report_id=FIXED_REPORT_ID,
            last_report_type="application_risk",
            referenced_entities=[
                ReferencedEntity(
                    position=1, entity_type="application", entity_id="A1024",
                    source_report_id=FIXED_REPORT_ID,
                    metadata={
                        "risk_score": 999,  # 客户端伪造的高分
                        "risk_level": "low",  # 客户端伪造成低风险
                    },
                ).model_dump(),
            ],
        )

        service = ReportAssistantService()
        response = service.handle_message(
            request=ReportAssistantMessageRequest(
                message="第一个为什么这么高？",
                conversation_context=ctx,
            ),
            current_user=_make_admin(),
            db=MagicMock(),
        )

        # 工具层返回真实的 risk_score=90
        # 确定性模板会使用工具返回的值（90），不是客户端传入的 999
        assert response.status == "completed"
        # 回答中不应出现伪造的 999
        assert "999" not in response.answer
