"""企业工作台日报数据契约回归测试。

本文件覆盖开发种子数据与日报响应 Schema 的交界：种子值会进入
``EmployeeDailyReport``，再由日报列表接口交给 Pydantic 序列化。若 JSON 字段类型漂移，
前端真实联调会收到 500，因此在不连接真实 MySQL 的 SQLite 测试中提前拦截。
"""

from __future__ import annotations

from sqlalchemy import create_engine, inspect


def test_daily_report_seed_json_fields_are_string_lists():
    """日报的进展和风险字段应生成字符串数组，避免列表接口序列化为 500。"""
    from models import load_all_models
    from seed.seed_all_modules import _build_mock_rows
    from utils.database import Base

    load_all_models()
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    table = Base.metadata.tables["employee_daily_report"]

    rows = _build_mock_rows(table, inspect(engine).get_columns(table.name))

    for row in rows:
        assert isinstance(row["key_progress"], list)
        assert all(isinstance(item, str) for item in row["key_progress"])
        assert isinstance(row["risks"], list)
        assert all(isinstance(item, str) for item in row["risks"])
