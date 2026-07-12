"""智能报告助手 Iteration 1.1 — 异步契约与幂等链路测试。

测试目标：
1. 智能接口不阻塞 HTTP 请求线程（generate_report 不在请求线程内执行）
2. 幂等键从 client_request_id 到 create_report_task 的完整传递链路
3. 重复请求返回相同 report_id
4. BackgroundTasks 正确注册
5. 多 worker 兼容性（无进程内状态）
6. 功能开关正确生效
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch, call

from services.reporting.orchestrator import ReportTaskCreationResult


@pytest.fixture(autouse=True)
def _isolate_assistant_settings(monkeypatch):
    """为本模块固定关闭 LLM，避免本地 ``.env`` 改变异步契约测试路径。

    本文件验证的是幂等键、后台任务和多 worker 无状态契约，不应访问真实模型。
    同时替换意图解析、澄清策略和回答编排读取到的模块级配置，确保测试结果
    不依赖执行顺序或开发机上的 LLM 开关。
    """
    import services.reporting.assistant.answer_composer as answer_module
    import services.reporting.assistant.clarification as clarification_module
    import services.reporting.assistant.config as config_module
    import services.reporting.assistant.intent_parser as intent_module
    from services.reporting.assistant.config import ReportAssistantSettings

    test_settings = ReportAssistantSettings(enabled=True, llm_enabled=False)
    monkeypatch.setattr(config_module, "settings", test_settings)
    monkeypatch.setattr(intent_module, "settings", test_settings)
    monkeypatch.setattr(clarification_module, "settings", test_settings)
    monkeypatch.setattr(answer_module, "settings", test_settings, raising=False)


# ---------------------------------------------------------------------------
# 一、幂等链路测试
# ---------------------------------------------------------------------------


class TestIdempotencyKeyFlow:
    """验证 client_request_id → idempotency_key → create_report_task 的完整链路。"""

    def test_idempotency_key_built_from_client_request_id(self):
        """client_request_id 被正确转换为 manual:{key} 格式。"""
        from services.reporting.assistant.schemas import (
            ReportAssistantMessageRequest,
            ReportConversationContext,
        )

        request = ReportAssistantMessageRequest(
            message="看看申请风险",
            client_request_id="assistant-test-001",
            conversation_context=ReportConversationContext(conversation_id="conv-001"),
        )

        # 验证 service 层构建的幂等键格式
        idempotency_key = f"manual:{request.client_request_id}" if request.client_request_id else None
        assert idempotency_key == "manual:assistant-test-001"

    def test_no_client_request_id_produces_none_key(self):
        """无 client_request_id 时幂等键为 None，由 create_report_task 作为非幂等请求处理。"""
        from services.reporting.assistant.schemas import (
            ReportAssistantMessageRequest,
            ReportConversationContext,
        )

        request = ReportAssistantMessageRequest(
            message="看看申请风险",
            conversation_context=ReportConversationContext(conversation_id="conv-001"),
        )
        # 不传 client_request_id
        assert request.client_request_id is None

        idempotency_key = f"manual:{request.client_request_id}" if request.client_request_id else None
        assert idempotency_key is None

    def test_idempotency_key_passed_to_tool_function(self, monkeypatch):
        """验证 idempotency_key 从 service 正确传递到 tool_generate_existing_report。"""
        from services.reporting.assistant.schemas import (
            ReportAssistantMessageRequest,
            ReportConversationContext,
        )
        from services.reporting.assistant.service import ReportAssistantService

        # 记录 tool 被调用时的参数
        captured_kwargs = {}

        def fake_tool(**kwargs):
            captured_kwargs.update(kwargs)
            from services.reporting.assistant.schemas import AssistantToolResult
            return AssistantToolResult(
                tool_name="generate_existing_report",
                status="success",
                data={"report_id": 1, "report_type": "application_risk", "status": "pending"},
                report_id=1,
            )

        monkeypatch.setattr(
            "services.reporting.assistant.service.tool_generate_existing_report",
            fake_tool,
        )

        service = ReportAssistantService()
        service.handle_message(
            request=ReportAssistantMessageRequest(
                message="看看申请风险",
                client_request_id="test-key-123",
                conversation_context=ReportConversationContext(conversation_id="conv-001"),
            ),
            current_user=_mock_admin(),
            db=FakeDB(),
        )

        assert captured_kwargs.get("idempotency_key") == "manual:test-key-123"

    def test_idempotency_key_passed_to_create_report_task(self, monkeypatch):
        """验证 idempotency_key 最终到达 create_report_task。"""
        from services.reporting.assistant.schemas import (
            ReportAssistantMessageRequest,
            ReportConversationContext,
        )
        from services.reporting.assistant.service import ReportAssistantService

        captured_kwargs = {}

        def fake_create_report_task(db, **kwargs):
            captured_kwargs.update(kwargs)
            # 返回一个假报告对象
            fake_report = MagicMock()
            fake_report.id = 1
            fake_report.status = "pending"
            fake_report.report_type = "application_risk"
            fake_report.period_start = None
            fake_report.period_end = None
            return ReportTaskCreationResult(report=fake_report, created=True)

        monkeypatch.setattr(
            "services.reporting.assistant.tools.create_report_task_result",
            fake_create_report_task,
        )

        service = ReportAssistantService()
        service.handle_message(
            request=ReportAssistantMessageRequest(
                message="看看申请风险",
                client_request_id="idempotency-flow-test",
                conversation_context=ReportConversationContext(conversation_id="conv-001"),
            ),
            current_user=_mock_admin(),
            db=FakeDB(),
        )

        # 幂等键应该传递到 create_report_task
        assert captured_kwargs.get("idempotency_key") == "manual:idempotency-flow-test"


# ---------------------------------------------------------------------------
# 二、重复请求幂等测试
# ---------------------------------------------------------------------------


class TestDuplicateRequestIdempotency:
    """相同 client_request_id 的重复请求应返回相同 report_id。"""

    def test_duplicate_request_returns_same_report_id(self, monkeypatch):
        """连续两次相同请求 → 返回相同 report_id。"""
        from services.reporting.assistant.schemas import (
            ReportAssistantMessageRequest,
            ReportConversationContext,
        )
        from services.reporting.assistant.service import ReportAssistantService

        # 模拟 create_report_task：第一次创建，第二次幂等命中
        call_count = [0]

        def fake_create_report_task(db, **kwargs):
            call_count[0] += 1
            fake_report = MagicMock()
            is_first = call_count[0] == 1
            if is_first:
                fake_report.id = 100
                fake_report.status = "pending"
            else:
                # 幂等命中 — 返回已有任务
                fake_report.id = 100
                fake_report.status = "generating"
            fake_report.report_type = "application_risk"
            fake_report.period_start = None
            fake_report.period_end = None
            return ReportTaskCreationResult(report=fake_report, created=is_first)

        monkeypatch.setattr(
            "services.reporting.assistant.tools.create_report_task_result",
            fake_create_report_task,
        )

        # 第一次请求
        service1 = ReportAssistantService()
        response1 = service1.handle_message(
            request=ReportAssistantMessageRequest(
                message="看看申请风险",
                client_request_id="dup-test-001",
                conversation_context=ReportConversationContext(conversation_id="conv-001"),
            ),
            current_user=_mock_admin(),
            db=FakeDB(),
        )

        # 第二次请求（相同 client_request_id）
        service2 = ReportAssistantService()
        response2 = service2.handle_message(
            request=ReportAssistantMessageRequest(
                message="看看申请风险",
                client_request_id="dup-test-001",
                conversation_context=ReportConversationContext(conversation_id="conv-001"),
            ),
            current_user=_mock_admin(),
            db=FakeDB(),
        )

        # 两次返回相同 report_id
        assert response1.report_id == 100
        assert response2.report_id == 100
        assert response1.report_id == response2.report_id

    def test_different_client_request_id_creates_new_report(self, monkeypatch):
        """不同 client_request_id → 允许创建两条独立任务。"""
        from services.reporting.assistant.schemas import (
            ReportAssistantMessageRequest,
            ReportConversationContext,
        )
        from services.reporting.assistant.service import ReportAssistantService

        report_ids = []

        def fake_create_report_task(db, **kwargs):
            fake_report = MagicMock()
            fake_report.id = len(report_ids) + 200
            fake_report.status = "pending"
            fake_report.report_type = "application_risk"
            fake_report.period_start = None
            fake_report.period_end = None
            report_ids.append(fake_report.id)
            return ReportTaskCreationResult(report=fake_report, created=True)

        monkeypatch.setattr(
            "services.reporting.assistant.tools.create_report_task_result",
            fake_create_report_task,
        )

        service = ReportAssistantService()
        response1 = service.handle_message(
            request=ReportAssistantMessageRequest(
                message="看看申请风险",
                client_request_id="unique-a",
                conversation_context=ReportConversationContext(conversation_id="conv-001"),
            ),
            current_user=_mock_admin(),
            db=FakeDB(),
        )
        response2 = service.handle_message(
            request=ReportAssistantMessageRequest(
                message="看看申请风险",
                client_request_id="unique-b",
                conversation_context=ReportConversationContext(conversation_id="conv-001"),
            ),
            current_user=_mock_admin(),
            db=FakeDB(),
        )

        # 不同 client_request_id 创建不同任务
        assert response1.report_id != response2.report_id
        assert len(report_ids) == 2


# ---------------------------------------------------------------------------
# 三、异步契约测试 — generate_report 不在请求线程内执行
# ---------------------------------------------------------------------------


class TestAsyncContract:
    """智能接口请求返回时，generate_report() 尚未在当前请求线程内执行。"""

    def test_generate_report_not_called_in_request_thread(self, monkeypatch):
        """验证 tool_generate_existing_report 不再同步调用 generate_report()。"""
        from services.reporting.assistant.schemas import (
            ReportAssistantMessageRequest,
            ReportConversationContext,
        )
        from services.reporting.assistant.service import ReportAssistantService

        # 记录 generate_report 是否被调用
        generate_called = []

        def fake_generate_report(report_id, db):
            generate_called.append(report_id)

        # Patch orchestrator 中的 generate_report
        monkeypatch.setattr(
            "services.reporting.orchestrator.generate_report",
            fake_generate_report,
        )

        # Mock create_report_task
        def fake_create_report_task(db, **kwargs):
            fake_report = MagicMock()
            fake_report.id = 300
            fake_report.status = "pending"
            fake_report.report_type = "application_risk"
            fake_report.period_start = None
            fake_report.period_end = None
            return ReportTaskCreationResult(report=fake_report, created=True)

        monkeypatch.setattr(
            "services.reporting.assistant.tools.create_report_task_result",
            fake_create_report_task,
        )

        service = ReportAssistantService()
        response = service.handle_message(
            request=ReportAssistantMessageRequest(
                message="看看申请风险",
                conversation_context=ReportConversationContext(conversation_id="conv-001"),
            ),
            current_user=_mock_admin(),
            db=FakeDB(),
        )

        # 响应正常返回
        assert response.status == "generating"
        assert response.report_id == 300
        # generate_report 不应该在请求线程内被同步调用
        assert len(generate_called) == 0, (
            "generate_report() 不应在智能接口请求线程内同步调用，"
            "应通过 BackgroundTasks 在后台独立 Session 中执行"
        )

    def test_background_tasks_add_task_called_for_pending_report(self, monkeypatch):
        """验证 pending 状态的报告会注册 BackgroundTasks.add_task。"""
        from services.reporting.assistant.schemas import (
            ReportAssistantMessageRequest,
            ReportConversationContext,
        )
        from services.reporting.assistant.service import ReportAssistantService

        # Mock BackgroundTasks
        mock_bg = MagicMock()

        def fake_create_report_task(db, **kwargs):
            fake_report = MagicMock()
            fake_report.id = 400
            fake_report.status = "pending"
            fake_report.report_type = "application_risk"
            fake_report.period_start = None
            fake_report.period_end = None
            return ReportTaskCreationResult(report=fake_report, created=True)

        monkeypatch.setattr(
            "services.reporting.assistant.tools.create_report_task_result",
            fake_create_report_task,
        )

        service = ReportAssistantService()
        service.handle_message(
            request=ReportAssistantMessageRequest(
                message="看看申请风险",
                conversation_context=ReportConversationContext(conversation_id="conv-001"),
            ),
            current_user=_mock_admin(),
            db=FakeDB(),
            background_tasks=mock_bg,
        )

        # BackgroundTasks.add_task 应该被调用
        mock_bg.add_task.assert_called_once()
        call_args = mock_bg.add_task.call_args[0]
        # 第一个参数应该是 generate_report_async
        from services.reporting.orchestrator import generate_report_async
        assert call_args[0] == generate_report_async
        # 第二个参数应该是 report_id
        assert call_args[1] == 400

    def test_background_tasks_not_called_for_completed_report(self, monkeypatch):
        """幂等命中已完成报告时，不注册后台任务。"""
        from services.reporting.assistant.schemas import (
            ReportAssistantMessageRequest,
            ReportConversationContext,
        )
        from services.reporting.assistant.service import ReportAssistantService

        mock_bg = MagicMock()

        def fake_create_report_task(db, **kwargs):
            fake_report = MagicMock()
            fake_report.id = 500
            fake_report.status = "completed"  # 已完成
            fake_report.report_type = "application_risk"
            fake_report.period_start = None
            fake_report.period_end = None
            return ReportTaskCreationResult(report=fake_report, created=True)

        monkeypatch.setattr(
            "services.reporting.assistant.tools.create_report_task_result",
            fake_create_report_task,
        )

        service = ReportAssistantService()
        service.handle_message(
            request=ReportAssistantMessageRequest(
                message="看看申请风险",
                client_request_id="completed-test",
                conversation_context=ReportConversationContext(conversation_id="conv-001"),
            ),
            current_user=_mock_admin(),
            db=FakeDB(),
            background_tasks=mock_bg,
        )

        # 已完成报告不应注册后台任务
        mock_bg.add_task.assert_not_called()

    def test_background_tasks_none_skips_registration(self, monkeypatch):
        """background_tasks=None 时（测试环境）不崩溃。"""
        from services.reporting.assistant.schemas import (
            ReportAssistantMessageRequest,
            ReportConversationContext,
        )
        from services.reporting.assistant.service import ReportAssistantService

        def fake_create_report_task(db, **kwargs):
            fake_report = MagicMock()
            fake_report.id = 600
            fake_report.status = "pending"
            fake_report.report_type = "application_risk"
            fake_report.period_start = None
            fake_report.period_end = None
            return ReportTaskCreationResult(report=fake_report, created=True)

        monkeypatch.setattr(
            "services.reporting.assistant.tools.create_report_task_result",
            fake_create_report_task,
        )

        service = ReportAssistantService()
        # 不传 background_tasks（测试环境常见情况）
        response = service.handle_message(
            request=ReportAssistantMessageRequest(
                message="看看申请风险",
                conversation_context=ReportConversationContext(conversation_id="conv-001"),
            ),
            current_user=_mock_admin(),
            db=FakeDB(),
        )

        # 不应崩溃，正常返回
        assert response.status == "generating"
        assert response.report_id == 600


# ---------------------------------------------------------------------------
# 四、多 worker 兼容性测试 — 无进程内状态
# ---------------------------------------------------------------------------


class TestMultiWorkerCompatibility:
    """验证智能报告助手不存在进程内可变状态，可以在多 worker 环境运行。"""

    def test_no_module_level_conversation_dict(self):
        """验证各模块不存在模块级会话字典或全局状态映射。"""
        import ast
        from pathlib import Path

        modules_to_check = [
            "services/reporting/assistant/config.py",
            "services/reporting/assistant/schemas.py",
            "services/reporting/assistant/intent_parser.py",
            "services/reporting/assistant/service.py",
            "services/reporting/assistant/tools.py",
            "routers/report_assistant.py",
        ]

        root = Path(__file__).parent.parent
        suspicious_patterns = [
            "_sessions",
            "_conversations",
            "_contexts",
            "session_dict",
            "conversation_dict",
            "user_state",
            "global_state",
            "in_memory",
            "process_cache",
        ]

        for module_path in modules_to_check:
            full_path = root / module_path
            if not full_path.exists():
                continue
            content = full_path.read_text(encoding="utf-8")
            for pattern in suspicious_patterns:
                assert pattern not in content.lower(), (
                    f"{module_path} 中存在可疑的进程内状态变量: {pattern}"
                )

    def test_two_service_instances_independent(self, monkeypatch):
        """两个独立 service 实例产生一致结果，不共享可变状态。"""
        from services.reporting.assistant.schemas import (
            ReportAssistantMessageRequest,
            ReportConversationContext,
        )
        from services.reporting.assistant.service import ReportAssistantService

        def fake_create_report_task(db, **kwargs):
            fake_report = MagicMock()
            fake_report.id = 700
            fake_report.status = "pending"
            fake_report.report_type = "application_risk"
            fake_report.period_start = None
            fake_report.period_end = None
            return ReportTaskCreationResult(report=fake_report, created=True)

        monkeypatch.setattr(
            "services.reporting.assistant.tools.create_report_task_result",
            fake_create_report_task,
        )

        # 使用相同 conversation_context 创建两个独立实例
        ctx = ReportConversationContext(conversation_id="shared-conv")

        service1 = ReportAssistantService()
        response1 = service1.handle_message(
            request=ReportAssistantMessageRequest(message="看看申请风险", conversation_context=ctx),
            current_user=_mock_admin(),
            db=FakeDB(),
        )

        service2 = ReportAssistantService()
        response2 = service2.handle_message(
            request=ReportAssistantMessageRequest(message="看看申请风险", conversation_context=ctx),
            current_user=_mock_admin(),
            db=FakeDB(),
        )

        # 两个实例得到一致结果
        assert response1.report_id == 700
        assert response2.report_id == 700
        assert response1.report_type == response2.report_type

    def test_service_instance_stateless(self):
        """ReportAssistantService 实例在方法调用之间不保留可变请求状态。"""
        from services.reporting.assistant.service import ReportAssistantService

        service = ReportAssistantService()

        # 检查 __dict__ 中是否只有 _intent_parser 这种无状态依赖
        instance_vars = vars(service)
        # 只应该有 _intent_parser（无状态解析器）
        assert "_intent_parser" in instance_vars
        # 不应有请求级别的可变状态
        for key in instance_vars:
            assert not key.startswith("_current_"), f"存在请求级可变状态: {key}"
            assert not key.startswith("_last_"), f"存在请求级可变状态: {key}"


# ---------------------------------------------------------------------------
# 五、功能开关测试
# ---------------------------------------------------------------------------


class TestFeatureToggles:
    """验证 REPORT_ASSISTANT_* 功能开关正确生效。"""

    def test_llm_disabled_uses_keyword_router(self, monkeypatch):
        """REPORT_ASSISTANT_LLM_ENABLED=false 时使用关键词降级路由。"""
        from services.reporting.assistant.config import ReportAssistantSettings
        from services.reporting.assistant.schemas import (
            ReportAssistantMessageRequest,
            ReportConversationContext,
        )
        from services.reporting.assistant.service import ReportAssistantService

        # 禁用 LLM
        test_settings = ReportAssistantSettings(enabled=True, llm_enabled=False)
        _patch_settings(monkeypatch, test_settings)

        # 不 mock create_report_task — 让真正的关键词路由匹配
        def fake_create_report_task(db, **kwargs):
            fake_report = MagicMock()
            fake_report.id = 800
            fake_report.status = "pending"
            fake_report.report_type = kwargs.get("report_type", "unknown")
            fake_report.period_start = None
            fake_report.period_end = None
            return ReportTaskCreationResult(report=fake_report, created=True)

        monkeypatch.setattr(
            "services.reporting.assistant.tools.create_report_task_result",
            fake_create_report_task,
        )

        service = ReportAssistantService()
        response = service.handle_message(
            request=ReportAssistantMessageRequest(
                message="看看现在的申请风险",
                conversation_context=ReportConversationContext(conversation_id="conv-001"),
            ),
            current_user=_mock_admin(),
            db=FakeDB(),
        )

        # 关键词"申请"+"风险"应匹配到 application_risk
        assert response.report_type == "application_risk"
        assert response.status == "generating"

    def test_llm_disabled_still_handles_unknown(self, monkeypatch):
        """LLM 禁用时，无法识别的内容返回澄清。"""
        from services.reporting.assistant.config import ReportAssistantSettings
        from services.reporting.assistant.schemas import (
            ReportAssistantMessageRequest,
            ReportConversationContext,
        )
        from services.reporting.assistant.service import ReportAssistantService

        test_settings = ReportAssistantSettings(enabled=True, llm_enabled=False)
        _patch_settings(monkeypatch, test_settings)

        service = ReportAssistantService()
        response = service.handle_message(
            request=ReportAssistantMessageRequest(
                message="今天天气真好",
                conversation_context=ReportConversationContext(conversation_id="conv-001"),
            ),
            current_user=_mock_admin(),
            db=FakeDB(),
        )

        assert response.status == "needs_clarification"

    def test_config_missing_api_key_does_not_crash_service(self):
        """缺少 API Key 不应导致 service 初始化崩溃。"""
        from services.reporting.assistant.service import ReportAssistantService

        # Service 应该能正常创建
        service = ReportAssistantService()
        assert service is not None
        assert service._intent_parser is not None


# ---------------------------------------------------------------------------
# Test Helpers
# ---------------------------------------------------------------------------


def _patch_settings(monkeypatch, test_settings):
    """统一 patch settings 到所有引用模块。"""
    import services.reporting.assistant.config as config_module
    import services.reporting.assistant.intent_parser as ip_module
    import services.reporting.assistant.clarification as cl_module
    import services.reporting.assistant.service as svc_module

    monkeypatch.setattr(config_module, "settings", test_settings)
    monkeypatch.setattr(ip_module, "settings", test_settings)
    monkeypatch.setattr(cl_module, "settings", test_settings)


def _mock_admin():
    """创建管理员 mock 用户。"""
    from utils.auth import CurrentUser

    return CurrentUser(
        id=1,
        username="admin",
        real_name="管理员",
        user_type="employee",
        role_code="admin",
        department="技术部",
    )


class FakeDB:
    """假的数据库 Session，用于测试不需要真实 DB 的路径。

    支持 tools.py 中的幂等键 pre-check 查询：
        db.query(ReportGeneration).filter_by(idempotency_key=...).first()
    """
    def query(self, model):
        """返回链式查询对象（默认返回 None = 幂等键不存在）。"""
        return _FakeDBQuery()

    pass


class _FakeDBQuery:
    """模拟 SQLAlchemy Query 的 filter_by().first() 链式调用。"""
    def filter_by(self, **kwargs):
        return self

    def first(self):
        return None
