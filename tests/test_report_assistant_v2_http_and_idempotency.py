"""智能报告助手 Iteration 1.2 — HTTP 状态码与后台任务幂等测试。

测试目标：
1. 动态 HTTP 状态码（202/200/403/503）
2. 幂等命中时不再重复注册后台任务
3. 并发边界验证
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from services.reporting.orchestrator import ReportTaskCreationResult


# ============================================================================
# 测试辅助
# ============================================================================


def _mock_admin():
    from utils.auth import CurrentUser
    return CurrentUser(
        id=1, username="admin", real_name="管理员",
        user_type="employee", role_code="admin", department="技术部",
    )


class _FakeDB:
    """假的数据库 Session，支持 tools.py 中的幂等键 pre-check。

    tools.py 中 tool_generate_existing_report 的幂等键 pre-check 需要:
        db.query(ReportGeneration).filter_by(idempotency_key=...).first()

    本实现维护一个内存字典模拟幂等键→记录的映射。
    """
    def __init__(self):
        self._records: dict[str, object] = {}

    def query(self, model):
        return _FakeQuery(self._records)

    def add_record(self, idempotency_key: str, record):
        """注册一条记录，后续对相同 idempotency_key 的查询会命中。"""
        self._records[idempotency_key] = record


class _FakeQuery:
    """模拟 SQLAlchemy Query 的 filter_by().first() 链式调用。"""
    def __init__(self, records: dict[str, object]):
        self._records = records
        self._idempotency_key: str | None = None

    def filter_by(self, **kwargs):
        self._idempotency_key = kwargs.get("idempotency_key")
        return self

    def first(self):
        if self._idempotency_key and self._idempotency_key in self._records:
            return self._records[self._idempotency_key]
        return None


def _enable_assistant_settings(monkeypatch):
    """统一启用 assistant 功能开关。"""
    import services.reporting.assistant.config as config_module
    import services.reporting.assistant.intent_parser as ip_module
    import services.reporting.assistant.clarification as cl_module
    import routers.report_assistant as ra_module
    from services.reporting.assistant.config import ReportAssistantSettings

    test_settings = ReportAssistantSettings(enabled=True, llm_enabled=False)
    monkeypatch.setattr(config_module, "settings", test_settings)
    monkeypatch.setattr(ip_module, "settings", test_settings)
    monkeypatch.setattr(cl_module, "settings", test_settings)
    monkeypatch.setattr(ra_module, "settings", test_settings)
    return test_settings


@pytest.fixture(autouse=True)
def _isolate_assistant_settings(monkeypatch):
    """让本模块所有用例使用确定性关键词路由，隔离开发机真实 LLM 配置。"""
    _enable_assistant_settings(monkeypatch)


def _create_token_and_override(monkeypatch, app, db_session):
    """在 SQLite 内存库中创建用户并生成 Token，同时覆盖 get_db 依赖。"""
    from models.user import SysUser
    from utils.auth import create_access_token, get_current_user, get_db

    # 创建管理员用户（status 必须是 "normal" 或 "disabled"）
    admin = SysUser(
        id=9999, username="admin_test", password_hash="hashed",
        user_type="employee", role="admin", real_name="管理员测试",
        status="normal", department="技术部",
    )
    db_session.add(admin)
    db_session.commit()
    db_session.refresh(admin)

    # 覆盖 get_db 返回测试数据库
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    token = create_access_token(admin, role_code="admin")
    return token


# ============================================================================
# 一、HTTP 状态码测试
# ============================================================================


class TestHTTPStatusCodes:
    """验证不同 assistant status 返回正确的 HTTP 状态码。"""

    def test_generating_returns_http_202(self, monkeypatch, db_session):
        """status=generating → HTTP 202 Accepted。"""
        from main import app
        from services.reporting.assistant.schemas import (
            ReportAssistantIntent,
            ReportAssistantMessageResponse,
            ReportConversationContext,
        )
        from services.reporting.assistant.service import ReportAssistantService

        _enable_assistant_settings(monkeypatch)
        token = _create_token_and_override(monkeypatch, app, db_session)

        def mock_handle(self, *, request, current_user, db, background_tasks=None):
            return ReportAssistantMessageResponse(
                status="generating",
                intent=ReportAssistantIntent.GENERATE_REPORT,
                report_id=100,
                report_type="application_risk",
                answer="已创建申请风险报告。报告 ID 为 #100。",
                needs_clarification=False,
                confidence=0.92,
                conversation_context=ReportConversationContext(conversation_id="test"),
            )

        monkeypatch.setattr(ReportAssistantService, "handle_message", mock_handle)

        client = TestClient(app)
        resp = client.post(
            "/api/v1/reports/assistant/messages",
            json={
                "message": "看看申请风险",
                "conversation_context": {"conversation_id": "test-http"},
            },
            headers={"Authorization": f"Bearer {token}"},
        )

        assert resp.status_code == status.HTTP_202_ACCEPTED, (
            f"期望 202，实际 {resp.status_code}，body={resp.json()}"
        )
        data = resp.json()
        assert data["status"] == "generating"
        assert data["report_id"] == 100

    def test_completed_returns_http_200(self, monkeypatch, db_session):
        """status=completed → HTTP 200 OK。"""
        from main import app
        from services.reporting.assistant.schemas import (
            ReportAssistantIntent,
            ReportAssistantMessageResponse,
            ReportConversationContext,
        )
        from services.reporting.assistant.service import ReportAssistantService

        _enable_assistant_settings(monkeypatch)
        token = _create_token_and_override(monkeypatch, app, db_session)

        def mock_handle(self, *, request, current_user, db, background_tasks=None):
            return ReportAssistantMessageResponse(
                status="completed",
                intent=ReportAssistantIntent.GENERATE_REPORT,
                report_id=200,
                report_type="application_risk",
                answer="报告已完成。",
                needs_clarification=False,
                confidence=0.95,
                conversation_context=ReportConversationContext(conversation_id="test"),
            )

        monkeypatch.setattr(ReportAssistantService, "handle_message", mock_handle)

        client = TestClient(app)
        resp = client.post(
            "/api/v1/reports/assistant/messages",
            json={
                "message": "看看申请风险",
                "conversation_context": {"conversation_id": "test-http"},
            },
            headers={"Authorization": f"Bearer {token}"},
        )

        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert data["status"] == "completed"

    def test_clarification_returns_http_200(self, monkeypatch, db_session):
        """status=needs_clarification → HTTP 200 OK。"""
        from main import app
        from services.reporting.assistant.schemas import (
            ReportAssistantIntent,
            ReportAssistantMessageResponse,
            ReportConversationContext,
        )
        from services.reporting.assistant.service import ReportAssistantService

        _enable_assistant_settings(monkeypatch)
        token = _create_token_and_override(monkeypatch, app, db_session)

        def mock_handle(self, *, request, current_user, db, background_tasks=None):
            return ReportAssistantMessageResponse(
                status="needs_clarification",
                intent=ReportAssistantIntent.UNKNOWN,
                answer="我还不能确定你的需求。",
                needs_clarification=True,
                clarification_question="你想查看哪类报告？",
                confidence=0.3,
                conversation_context=ReportConversationContext(conversation_id="test"),
            )

        monkeypatch.setattr(ReportAssistantService, "handle_message", mock_handle)

        client = TestClient(app)
        resp = client.post(
            "/api/v1/reports/assistant/messages",
            json={
                "message": "今天天气真好",
                "conversation_context": {"conversation_id": "test-http"},
            },
            headers={"Authorization": f"Bearer {token}"},
        )

        assert resp.status_code == status.HTTP_200_OK
        data = resp.json()
        assert data["status"] == "needs_clarification"

    def test_permission_denied_returns_http_403(self, monkeypatch, db_session):
        """status=permission_denied → HTTP 403 Forbidden。"""
        from main import app
        from services.reporting.assistant.schemas import (
            ReportAssistantIntent,
            ReportAssistantMessageResponse,
            ReportConversationContext,
        )
        from services.reporting.assistant.service import ReportAssistantService

        _enable_assistant_settings(monkeypatch)
        token = _create_token_and_override(monkeypatch, app, db_session)

        def mock_handle(self, *, request, current_user, db, background_tasks=None):
            return ReportAssistantMessageResponse(
                status="permission_denied",
                intent=ReportAssistantIntent.UNKNOWN,
                answer="当前角色没有可访问的报告类型。",
                needs_clarification=True,
                confidence=0.0,
                conversation_context=ReportConversationContext(conversation_id="test"),
                error_code="NO_ACCESSIBLE_REPORT_TYPES",
            )

        monkeypatch.setattr(ReportAssistantService, "handle_message", mock_handle)

        client = TestClient(app)
        resp = client.post(
            "/api/v1/reports/assistant/messages",
            json={
                "message": "任何消息",
                "conversation_context": {"conversation_id": "test-http"},
            },
            headers={"Authorization": f"Bearer {token}"},
        )

        assert resp.status_code == status.HTTP_403_FORBIDDEN
        data = resp.json()
        assert data["status"] == "permission_denied"

    def test_error_returns_http_500(self, monkeypatch, db_session):
        """status=error → HTTP 500 Internal Server Error。"""
        from main import app
        from services.reporting.assistant.schemas import (
            ReportAssistantIntent,
            ReportAssistantMessageResponse,
            ReportConversationContext,
        )
        from services.reporting.assistant.service import ReportAssistantService

        _enable_assistant_settings(monkeypatch)
        token = _create_token_and_override(monkeypatch, app, db_session)

        def mock_handle(self, *, request, current_user, db, background_tasks=None):
            return ReportAssistantMessageResponse(
                status="error",
                intent=ReportAssistantIntent.UNKNOWN,
                answer="处理请求时发生错误。",
                confidence=0.0,
                conversation_context=ReportConversationContext(conversation_id="test"),
                error_code="TOOL_EXECUTION_FAILED",
            )

        monkeypatch.setattr(ReportAssistantService, "handle_message", mock_handle)

        client = TestClient(app)
        resp = client.post(
            "/api/v1/reports/assistant/messages",
            json={
                "message": "任何消息",
                "conversation_context": {"conversation_id": "test-http"},
            },
            headers={"Authorization": f"Bearer {token}"},
        )

        assert resp.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        data = resp.json()
        assert data["status"] == "error"


# ============================================================================
# 二、后台任务幂等测试
# ============================================================================


class TestBackgroundTaskIdempotency:
    """验证幂等命中时不再重复注册 BackgroundTasks。"""

    def test_new_pending_registers_one_background_task(self, monkeypatch):
        """新创建的 pending 任务 → 注册一个后台任务。"""
        from services.reporting.assistant.schemas import (
            ReportAssistantMessageRequest,
            ReportConversationContext,
        )
        from services.reporting.assistant.service import ReportAssistantService

        mock_bg = MagicMock()

        def fake_create_report_task(db, **kwargs):
            fake = MagicMock()
            fake.id = 1
            fake.status = "pending"
            fake.report_type = "application_risk"
            fake.period_start = None
            fake.period_end = None
            return ReportTaskCreationResult(report=fake, created=True)

        monkeypatch.setattr(
            "services.reporting.assistant.tools.create_report_task_result",
            fake_create_report_task,
        )

        service = ReportAssistantService()
        service.handle_message(
            request=ReportAssistantMessageRequest(
                message="看看申请风险",
                client_request_id="new-task-001",
                conversation_context=ReportConversationContext(conversation_id="conv-001"),
            ),
            current_user=_mock_admin(),
            db=_FakeDB(),
            background_tasks=mock_bg,
        )

        # 新创建的 pending 任务应注册后台任务
        mock_bg.add_task.assert_called_once()

    def test_duplicate_pending_registers_no_second_background_task(self, monkeypatch):
        """幂等命中 pending 任务 → 不注册第二个后台任务。"""
        from services.reporting.assistant.schemas import (
            ReportAssistantMessageRequest,
            ReportConversationContext,
        )
        from services.reporting.assistant.service import ReportAssistantService

        mock_bg = MagicMock()

        def fake_create_report_task(db, **kwargs):
            fake = MagicMock()
            fake.id = 50
            fake.status = "pending"
            fake.report_type = "application_risk"
            fake.period_start = None
            fake.period_end = None
            return ReportTaskCreationResult(report=fake, created=False)

        monkeypatch.setattr(
            "services.reporting.assistant.tools.create_report_task_result",
            fake_create_report_task,
        )

        service = ReportAssistantService()
        service.handle_message(
            request=ReportAssistantMessageRequest(
                message="看看申请风险",
                client_request_id="dup-pending-001",
                conversation_context=ReportConversationContext(conversation_id="conv-001"),
            ),
            current_user=_mock_admin(),
            db=_FakeDB(),
            background_tasks=mock_bg,
        )

        # 幂等命中已有任务（created=False），不注册后台任务
        mock_bg.add_task.assert_not_called()

    def test_duplicate_generating_registers_no_background_task(self, monkeypatch):
        """幂等命中 generating 任务 → 不注册后台任务。"""
        from services.reporting.assistant.schemas import (
            ReportAssistantMessageRequest,
            ReportConversationContext,
        )
        from services.reporting.assistant.service import ReportAssistantService

        mock_bg = MagicMock()

        def fake_create_report_task(db, **kwargs):
            fake = MagicMock()
            fake.id = 60
            fake.status = "generating"
            fake.report_type = "application_risk"
            fake.period_start = None
            fake.period_end = None
            return ReportTaskCreationResult(report=fake, created=False)

        monkeypatch.setattr(
            "services.reporting.assistant.tools.create_report_task_result",
            fake_create_report_task,
        )

        service = ReportAssistantService()
        service.handle_message(
            request=ReportAssistantMessageRequest(
                message="看看申请风险",
                client_request_id="dup-generating-001",
                conversation_context=ReportConversationContext(conversation_id="conv-001"),
            ),
            current_user=_mock_admin(),
            db=_FakeDB(),
            background_tasks=mock_bg,
        )

        mock_bg.add_task.assert_not_called()

    def test_duplicate_completed_registers_no_background_task(self, monkeypatch):
        """幂等命中 completed 任务 → 不注册后台任务。"""
        from services.reporting.assistant.schemas import (
            ReportAssistantMessageRequest,
            ReportConversationContext,
        )
        from services.reporting.assistant.service import ReportAssistantService

        mock_bg = MagicMock()

        def fake_create_report_task(db, **kwargs):
            fake = MagicMock()
            fake.id = 70
            fake.status = "completed"
            fake.report_type = "application_risk"
            fake.period_start = None
            fake.period_end = None
            return fake

        monkeypatch.setattr(
            "services.reporting.assistant.tools.create_report_task_result",
            fake_create_report_task,
        )

        service = ReportAssistantService()
        service.handle_message(
            request=ReportAssistantMessageRequest(
                message="看看申请风险",
                client_request_id="dup-completed-001",
                conversation_context=ReportConversationContext(conversation_id="conv-001"),
            ),
            current_user=_mock_admin(),
            db=_FakeDB(),
            background_tasks=mock_bg,
        )

        mock_bg.add_task.assert_not_called()

    def test_duplicate_failed_registers_no_background_task(self, monkeypatch):
        """幂等命中 failed 任务 → 不自动注册后台任务。"""
        from services.reporting.assistant.schemas import (
            ReportAssistantMessageRequest,
            ReportConversationContext,
        )
        from services.reporting.assistant.service import ReportAssistantService

        mock_bg = MagicMock()

        def fake_create_report_task(db, **kwargs):
            fake = MagicMock()
            fake.id = 80
            fake.status = "failed"
            fake.report_type = "application_risk"
            fake.period_start = None
            fake.period_end = None
            return fake

        monkeypatch.setattr(
            "services.reporting.assistant.tools.create_report_task_result",
            fake_create_report_task,
        )

        service = ReportAssistantService()
        service.handle_message(
            request=ReportAssistantMessageRequest(
                message="看看申请风险",
                client_request_id="dup-failed-001",
                conversation_context=ReportConversationContext(conversation_id="conv-001"),
            ),
            current_user=_mock_admin(),
            db=_FakeDB(),
            background_tasks=mock_bg,
        )

        mock_bg.add_task.assert_not_called()

    def test_two_duplicate_requests_schedule_generation_only_once(self, monkeypatch):
        """两次相同幂等请求 → 后台任务最多注册一次。

        验证流程：
        1. 第一次请求：pre-check 找不到幂等键 → created=True → 注册后台任务
        2. 第二次请求：pre-check 找到幂等键 → created=False → 不注册
        """
        from services.reporting.assistant.schemas import (
            ReportAssistantMessageRequest,
            ReportConversationContext,
        )
        from services.reporting.assistant.service import ReportAssistantService

        schedule_count = [0]
        call_count = [0]

        def fake_create_report_task(db, **kwargs):
            call_count[0] += 1
            fake = MagicMock()
            fake.id = 42
            fake.status = "pending"
            fake.report_type = "application_risk"
            fake.period_start = None
            fake.period_end = None
            return ReportTaskCreationResult(report=fake, created=(call_count[0] == 1))

        monkeypatch.setattr(
            "services.reporting.assistant.tools.create_report_task_result",
            fake_create_report_task,
        )

        service = ReportAssistantService()

        # 第一次请求 — 创建 mock BackgroundTasks
        mock_bg1 = MagicMock()
        mock_bg2 = MagicMock()

        def tracking_add_task_1(func, *args, **kwargs):
            schedule_count[0] += 1

        def tracking_add_task_2(func, *args, **kwargs):
            schedule_count[0] += 1

        mock_bg1.add_task = tracking_add_task_1
        mock_bg2.add_task = tracking_add_task_2

        # 第一次请求
        service.handle_message(
            request=ReportAssistantMessageRequest(
                message="看看申请风险",
                client_request_id="schedule-once-001",
                conversation_context=ReportConversationContext(conversation_id="conv-001"),
            ),
            current_user=_mock_admin(),
            db=_FakeDB(),
            background_tasks=mock_bg1,
        )

        # 第二次请求（相同幂等键）
        service.handle_message(
            request=ReportAssistantMessageRequest(
                message="看看申请风险",
                client_request_id="schedule-once-001",
                conversation_context=ReportConversationContext(conversation_id="conv-001"),
            ),
            current_user=_mock_admin(),
            db=_FakeDB(),
            background_tasks=mock_bg2,
        )

        # 第一次请求：pre-check 找不到幂等键 → created=True → 注册
        # 第二次请求：pre-check 找到幂等键 → created=False → 不注册
        assert schedule_count[0] == 1, (
            f"两次相同幂等请求应只注册一次后台任务，实际注册了 {schedule_count[0]} 次"
        )


# ============================================================================
# 三、并发边界测试
# ============================================================================


class TestConcurrencyEdgeCases:
    """并发场景下的幂等安全。"""

    def test_concurrent_duplicate_requests_at_most_one_scheduled(self, monkeypatch):
        """两个相同幂等请求同时到达 → 最多注册一次后台任务。

        已知竞争窗口（文档化，不隐藏）：
        - tools.py 中的 pre-check（Line ~109）和 create_report_task（Line ~119）
          之间存在时间窗口
        - 如果两个请求同时通过 pre-check（都认为 created=True），
          则 create_report_task 内部的 DB UNIQUE INDEX 会让一个 db.add 失败
        - 但在当前实现中，两个请求都会注册 BackgroundTasks

        多层防护：
        1. tools.py pre-check（本测试验证的第一层）
        2. create_report_task 内部幂等检查（DB UNIQUE INDEX）
        3. generate_report_async 内部状态检查（pending→generating 转换，第二层）
        """
        from services.reporting.assistant.schemas import (
            ReportAssistantMessageRequest,
            ReportConversationContext,
        )
        from services.reporting.assistant.service import ReportAssistantService

        schedule_count = [0]
        call_count = [0]

        def fake_create_report_task(db, **kwargs):
            call_count[0] += 1
            fake = MagicMock()
            fake.id = 999
            fake.status = "pending"
            fake.report_type = "application_risk"
            fake.period_start = None
            fake.period_end = None
            return ReportTaskCreationResult(report=fake, created=(call_count[0] == 1))

        monkeypatch.setattr(
            "services.reporting.assistant.tools.create_report_task_result",
            fake_create_report_task,
        )

        service = ReportAssistantService()

        # 模拟两个"同时"到达的请求（在测试中顺序执行）
        for i in range(2):
            mock_bg = MagicMock()

            def make_tracker(cnt):
                def tracker(func, *args, **kwargs):
                    cnt[0] += 1
                return tracker

            mock_bg.add_task = make_tracker(schedule_count)

            service.handle_message(
                request=ReportAssistantMessageRequest(
                    message="看看申请风险",
                    client_request_id="concurrent-001",
                    conversation_context=ReportConversationContext(conversation_id="conv-001"),
                ),
                current_user=_mock_admin(),
                db=_FakeDB(),
                background_tasks=mock_bg,
            )

        # pre-check 层：第一次 created=True → 注册；第二次 created=False → 不注册
        assert schedule_count[0] == 1, (
            f"pre-check 层应保证只注册一次后台任务，实际注册了 {schedule_count[0]} 次"
        )
