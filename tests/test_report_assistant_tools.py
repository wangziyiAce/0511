"""智能报告助手 — 受控工具单元测试。

测试目标：验证工具的输入/输出格式、错误处理和现有服务复用。
工具层不重新实现业务逻辑，只做参数校验和调用编排。
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from services.reporting.assistant.tools import (
    tool_generate_existing_report,
    tool_list_report_types,
    tool_query_report_status,
)

# 使用内存 SQLite 进行测试（不需要完整数据库）
TEST_DB_URL = "sqlite:///:memory:"


@pytest.fixture
def db_session() -> Session:
    """创建内存数据库会话。"""
    from utils.database import Base
    from models.report import ReportGeneration

    engine = create_engine(TEST_DB_URL)
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


# ---------------------------------------------------------------------------
# tool_list_report_types
# ---------------------------------------------------------------------------


class TestListReportTypes:
    def test_returns_all_types_for_admin(self):
        result = tool_list_report_types(user_role_code="admin")
        assert result.status == "success"
        assert result.data["total"] == 10

    def test_marks_restricted_types_for_employee(self):
        result = tool_list_report_types(user_role_code="employee")
        assert result.status == "success"
        allowed = [t for t in result.data["report_types"] if t["allowed"]]
        restricted = [t for t in result.data["report_types"] if not t["allowed"]]
        assert len(allowed) < 10
        assert any(t["report_type"] == "channel_roi" for t in restricted)

    def test_no_role_marks_all_disallowed(self):
        result = tool_list_report_types(user_role_code=None)
        assert all(not t["allowed"] for t in result.data["report_types"])


# ---------------------------------------------------------------------------
# tool_generate_existing_report
# ---------------------------------------------------------------------------


class TestGenerateExistingReport:
    def test_invalid_report_type_returns_error(self, db_session):
        result = tool_generate_existing_report(
            report_type="nonexistent_type",
            period_start=date(2026, 7, 1),
            period_end=date(2026, 7, 7),
            generated_by=1,
            title="测试报告",
            db=db_session,
        )
        assert result.status == "error"
        assert "不支持的报告类型" in (result.error or "")


# ---------------------------------------------------------------------------
# tool_query_report_status
# ---------------------------------------------------------------------------


class TestQueryReportStatus:
    def test_nonexistent_report_returns_error(self, db_session):
        result = tool_query_report_status(report_id=99999, db=db_session)
        assert result.status == "error"
        assert "不存在" in (result.error or "")
