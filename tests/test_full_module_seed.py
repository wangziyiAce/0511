"""全模块模拟数据初始化的回归测试。

测试目标：验证种子脚本能从 ORM 元数据创建缺失表，并为每一张业务表写入可用于
接口联调的最小模拟数据；重复执行时不重复插入，保证开发环境可安全反复初始化。
"""

from __future__ import annotations

import os
import subprocess
import sys
from types import SimpleNamespace

import pytest
from sqlalchemy import Column, Integer, MetaData, Table, create_engine, inspect, text


def test_seed_all_module_tables_creates_and_keeps_one_or_more_rows_per_table(monkeypatch):
    """空 SQLite 库执行两次种子初始化后，每张 ORM 表均有数据且总数不增长。"""
    from models import load_all_models
    from utils.database import Base
    import seed.seed_all_modules as full_seed

    # 使用独立内存库验证脚本，不读取或修改开发 MySQL 的已有演示数据。
    test_engine = create_engine("sqlite:///:memory:")
    load_all_models()

    # 全局测试环境使用 APP_ENV=testing；此用例验证允许写入的开发分支，需显式模拟。
    monkeypatch.setattr(full_seed, "settings", SimpleNamespace(is_development=True))

    first_counts = full_seed.seed_all_module_tables(test_engine)
    second_counts = full_seed.seed_all_module_tables(test_engine)

    expected_tables = set(Base.metadata.tables)
    assert set(first_counts) == expected_tables
    assert all(count >= 1 for count in first_counts.values())
    assert second_counts == first_counts


def test_seed_all_module_tables_refuses_non_development_environment(monkeypatch):
    """非开发环境必须拒绝写入，防止初始化脚本误改生产数据库。"""
    import seed.seed_all_modules as full_seed

    # 即使传入独立 SQLite Engine，也应先检查运行环境，而不是尝试创建表或插入数据。
    monkeypatch.setattr(full_seed, "settings", SimpleNamespace(is_development=False), raising=False)

    with pytest.raises(RuntimeError, match="development"):
        full_seed.seed_all_module_tables(create_engine("sqlite:///:memory:"))


def test_seed_script_runs_directly_from_project_root_with_isolated_database(tmp_path):
    """命令行直接运行脚本时也应找到项目模块，并写入隔离 SQLite 文件库。"""
    test_database = tmp_path / "module_seed.db"
    environment = {
        **os.environ,
        "APP_ENV": "development",
        "DATABASE_URL": f"sqlite:///{test_database.as_posix()}",
    }

    result = subprocess.run(
        [sys.executable, "seed/seed_all_modules.py"],
        capture_output=True,
        text=True,
        env=environment,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "全模块模拟数据初始化完成" in result.stdout


def test_seed_adds_value_for_legacy_required_database_column_not_in_model():
    """旧表多出的非空列应获得模拟值，避免不迁移表结构时插入失败。"""
    from seed.seed_all_modules import required_database_only_values

    table = Table("report_schedule", MetaData(), Column("id", Integer, primary_key=True))
    database_columns = [
        {"name": "id", "nullable": False, "default": None, "type": Integer()},
        {"name": "status", "nullable": False, "default": None, "type": Integer()},
    ]

    assert required_database_only_values(table, database_columns, row_number=1) == {"status": 1}


def test_seed_uses_reflected_table_when_database_has_legacy_required_column():
    """模型外必填列存在时，INSERT 应使用反射表而非丢弃该列的 ORM 表对象。"""
    from seed.seed_all_modules import table_for_insert

    test_engine = create_engine("sqlite:///:memory:")
    with test_engine.begin() as connection:
        connection.execute(text("CREATE TABLE legacy_schedule (id INTEGER PRIMARY KEY, status INTEGER NOT NULL)"))

    model_table = Table("legacy_schedule", MetaData(), Column("id", Integer, primary_key=True))
    database_columns = inspect(test_engine).get_columns("legacy_schedule")

    assert "status" in table_for_insert(test_engine, model_table, database_columns).c
