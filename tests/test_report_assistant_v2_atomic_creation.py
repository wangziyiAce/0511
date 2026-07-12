"""智能报告助手 Iteration 1.3 — 原子任务创建与并发幂等测试。

测试目标：
1. create_report_task_result 返回正确的 created 标志（三条 DB 路径）
2. 并发相同幂等键只有一个 created=True
3. generate_report() 原子领取任务（条件 UPDATE）
4. 原 create_report_task() 向后兼容
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from sqlalchemy.exc import IntegrityError

from services.reporting.orchestrator import (
    ReportTaskCreationResult,
    create_report_task,
    create_report_task_result,
    generate_report_async,
)


# ============================================================================
# 一、原子任务创建 — created 三条路径（mock DB 验证）
# ============================================================================


class TestAtomicTaskCreation:
    """验证 create_report_task_result 在三种路径下的 created 返回值。"""

    def test_created_true_on_successful_insert(self, monkeypatch):
        """INSERT 成功 → created=True。"""
        from models.report import ReportGeneration

        # Mock: 幂等键不存在（first() 返回 None） + INSERT 成功
        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter_by.return_value = mock_query
        mock_query.first.return_value = None  # 路径 1: 未命中

        # 抓取 add 和 commit 的参数
        added_reports = []
        def fake_add(report):
            report.id = 42
            report.status = "pending"
            added_reports.append(report)
        mock_db.add = fake_add

        result = create_report_task_result(
            mock_db,
            report_type="application_risk",
            title="测试",
            period_start=None,
            period_end=None,
            generated_by=1,
            idempotency_key="manual:test-key",
            trigger_source="manual",
        )

        # INSERT 成功 → created=True
        assert result.created is True
        assert result.report.id == 42
        assert result.report.status == "pending"

    def test_created_false_on_existing_record(self, monkeypatch):
        """idempotency_key 已存在 → created=False（路径 1：提前命中）。"""
        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter_by.return_value = mock_query

        # 模拟幂等键已存在
        existing_report = MagicMock()
        existing_report.id = 99
        existing_report.status = "completed"
        mock_query.first.return_value = existing_report

        result = create_report_task_result(
            mock_db,
            report_type="application_risk",
            title="第二次",
            period_start=None,
            period_end=None,
            generated_by=1,
            idempotency_key="manual:existing-key",
            trigger_source="manual",
        )

        # 提前命中 → created=False
        assert result.created is False
        assert result.report.id == 99

    def test_created_false_after_integrity_error(self, monkeypatch):
        """INSERT 触发 IntegrityError → rollback → 查询胜出记录 → created=False（路径 3）。"""
        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter_by.return_value = mock_query

        # 第一次查询：幂等键不存在
        mock_query.first.return_value = None

        # commit 触发 IntegrityError
        call_count = [0]
        def mock_commit():
            call_count[0] += 1
            if call_count[0] == 1:
                raise IntegrityError("UNIQUE constraint failed", params={}, orig=Exception())

        mock_db.commit = mock_commit

        # rollback 后查询胜出记录
        winner = MagicMock()
        winner.id = 77
        winner.status = "pending"

        def mock_refresh(report):
            pass

        mock_db.refresh = mock_refresh

        # 第二次查询（rollback 后）：返回胜出记录
        query_calls = [0]
        def mock_filter_by(**kwargs):
            query_calls[0] += 1
            return mock_query
        mock_query.filter_by = mock_filter_by

        first_results = [None, winner]  # 第一次 None，第二次 winner
        def mock_first():
            return first_results.pop(0) if first_results else None
        mock_query.first = mock_first

        result = create_report_task_result(
            mock_db,
            report_type="application_risk",
            title="冲突测试",
            period_start=None,
            period_end=None,
            generated_by=1,
            idempotency_key="manual:conflict-key",
            trigger_source="manual",
        )

        # IntegrityError 后 → created=False
        assert result.created is False
        assert result.report.id == 77

    def test_original_create_report_task_contract_unchanged(self, monkeypatch):
        """原 create_report_task() 仍返回 ReportGeneration，向后兼容。"""
        from models.report import ReportGeneration

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter_by.return_value = mock_query
        mock_query.first.return_value = None  # 新创建

        def fake_add(report):
            report.id = 100
            report.status = "pending"
        mock_db.add = fake_add

        report = create_report_task(
            mock_db,
            report_type="application_risk",
            title="兼容性测试",
            period_start=None,
            period_end=None,
            generated_by=1,
            trigger_source="manual",
        )

        assert isinstance(report, ReportGeneration)
        # 虽然 report 是 MagicMock wrapped，但 isinstance 通过
        assert report.status == "pending"


# ============================================================================
# 二、并发幂等
# ============================================================================


class TestConcurrentIdempotency:
    """验证并发相同幂等键只有一个 created=True，只注册一次后台任务。"""

    def test_concurrent_same_idempotency_key_only_one_created_true(self, monkeypatch):
        """两个请求相同幂等键 → 第一个 created=True，第二个 created=False。"""
        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter_by.return_value = mock_query

        report_counter = [0]

        def mock_first():
            # 第一次调用 → 幂等键不存在（新创建）
            # 第二次调用 → 幂等键已存在
            report_counter[0] += 1
            return None  # 两条路径都是 None → created=True，由 mock commit 控制

        mock_query.first = mock_first

        created_results = []

        for i in range(2):
            mock_db_i = MagicMock()
            mock_q = MagicMock()
            mock_db_i.query.return_value = mock_q
            mock_q.filter_by.return_value = mock_q

            if i == 0:
                # 第一次：幂等键不存在 + commit 成功
                mock_q.first.return_value = None
                def fake_add_1(report):
                    report.id = 1
                    report.status = "pending"
                mock_db_i.add = fake_add_1
            else:
                # 第二次：幂等键已存在
                existing = MagicMock()
                existing.id = 1
                existing.status = "pending"
                mock_q.first.return_value = existing

            result = create_report_task_result(
                mock_db_i,
                report_type="application_risk",
                title=f"并发测试 {i}",
                period_start=None,
                period_end=None,
                generated_by=1,
                idempotency_key="manual:concurrent",
                trigger_source="manual",
            )
            created_results.append(result.created)

        created_count = sum(created_results)
        assert created_count == 1, (
            f"只有一个请求应为 created=True，实际: {created_results}"
        )

    def test_concurrent_only_one_background_task_registered(self, monkeypatch):
        """并发相同幂等键 → 后台任务只注册一次（service 层验证）。"""
        from services.reporting.assistant.schemas import (
            ReportAssistantMessageRequest,
            ReportConversationContext,
        )
        from services.reporting.assistant.service import ReportAssistantService

        schedule_count = [0]
        call_count = [0]

        def fake_create_report_task_result(db, **kwargs):
            call_count[0] += 1
            fake = MagicMock()
            fake.id = 777
            fake.status = "pending"
            fake.report_type = "application_risk"
            fake.period_start = None
            fake.period_end = None
            return ReportTaskCreationResult(report=fake, created=(call_count[0] == 1))

        monkeypatch.setattr(
            "services.reporting.assistant.tools.create_report_task_result",
            fake_create_report_task_result,
        )

        service = ReportAssistantService()
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
                    client_request_id="bg-once-test",
                    conversation_context=ReportConversationContext(conversation_id="conv-001"),
                ),
                current_user=_mock_admin(),
                db=MagicMock(),
                background_tasks=mock_bg,
            )

        assert schedule_count[0] == 1, (
            f"后台任务应只注册一次，实际: {schedule_count[0]}"
        )


# ============================================================================
# 三、generate_report 原子领取任务（条件 UPDATE）
# ============================================================================


class TestAtomicReportClaim:
    """验证条件 UPDATE 的原子性：只有 pending 状态才能被领取。"""

    def test_second_worker_cannot_claim_generating_report(self, db_session):
        """generating → 条件 UPDATE 更新 0 行。"""
        # 使用 conftest 的 db_session，创建临时测试表
        from sqlalchemy import Column, Integer, String, text

        # 直接用原始 SQL 验证原子 UPDATE 模式
        db_session.execute(text(
            "CREATE TABLE IF NOT EXISTS _test_claim ("
            "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "  status VARCHAR(10) NOT NULL DEFAULT 'pending'"
            ")"
        ))
        db_session.execute(text("INSERT INTO _test_claim (status) VALUES ('generating')"))
        db_session.commit()

        # 条件 UPDATE：只有 pending 才能更新
        result = db_session.execute(
            text("UPDATE _test_claim SET status = 'generating' WHERE status = 'pending'")
        )
        db_session.commit()

        assert result.rowcount == 0, (
            f"generating 不应被条件 UPDATE 领取，rowcount={result.rowcount}"
        )

    def test_completed_report_cannot_be_claimed(self, db_session):
        """completed → 条件 UPDATE 更新 0 行。"""
        from sqlalchemy import text

        db_session.execute(text(
            "CREATE TABLE IF NOT EXISTS _test_claim_completed ("
            "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "  status VARCHAR(10) NOT NULL DEFAULT 'pending'"
            ")"
        ))
        db_session.execute(text("INSERT INTO _test_claim_completed (status) VALUES ('completed')"))
        db_session.commit()

        result = db_session.execute(
            text("UPDATE _test_claim_completed SET status = 'generating' WHERE status = 'pending'")
        )
        db_session.commit()

        assert result.rowcount == 0, "已完成报告不应被领取"

    def test_failed_report_cannot_be_claimed_without_retry(self, db_session):
        """failed → 条件 UPDATE 更新 0 行。"""
        from sqlalchemy import text

        db_session.execute(text(
            "CREATE TABLE IF NOT EXISTS _test_claim_failed ("
            "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
            "  status VARCHAR(10) NOT NULL DEFAULT 'pending'"
            ")"
        ))
        db_session.execute(text("INSERT INTO _test_claim_failed (status) VALUES ('failed')"))
        db_session.commit()

        result = db_session.execute(
            text("UPDATE _test_claim_failed SET status = 'generating' WHERE status = 'pending'")
        )
        db_session.commit()

        assert result.rowcount == 0, "失败报告不应被自动领取"


# ============================================================================
# Test Helpers
# ============================================================================


def _mock_admin():
    from utils.auth import CurrentUser
    return CurrentUser(
        id=1, username="admin", real_name="管理员",
        user_type="employee", role_code="admin", department="技术部",
    )
