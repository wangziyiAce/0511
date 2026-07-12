"""全模块开发演示数据初始化脚本。

本文件位于数据初始化层，供开发人员在本地 MySQL 环境执行。它从 SQLAlchemy
``Base.metadata`` 读取当前 ORM 表定义：先创建缺失表，再仅为仍为空的表插入两条
类型匹配的模拟记录。上游是开发命令行或联调准备工作，下游是数据库 Engine 和
Session；脚本不提供 HTTP 接口，也不处理生产数据库迁移。

执行方式：
    .venv\\Scripts\\python.exe seed\\seed_all_modules.py
"""

from __future__ import annotations

import sys
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import Boolean, Date, DateTime, Enum, Float, Integer, JSON, MetaData, Numeric, String, Table, Text, func, inspect, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

# 直接执行 ``python seed/seed_all_modules.py`` 时，Python 默认只搜索 seed 目录。
# 把项目根目录加入模块搜索路径，才能复用根目录的 config、models 与 utils。
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import settings
from models import load_all_models
from utils.database import Base, engine


def _text_value(table_name: str, column_name: str, row_number: int, max_length: int | None) -> str:
    """生成长度受控的文本，避免短 VARCHAR 字段因模拟数据过长写入失败。"""
    value = f"mock_{table_name}_{column_name}_{row_number}"
    return value[:max_length] if max_length else value


def _mock_value_for_type(column_type: Any, table_name: str, column_name: str, row_number: int) -> Any:
    """根据 ORM 列类型生成最小合法值。

    模拟数据的目标是让接口、分页和关联查询有可用样本，而不是伪造真实用户信息。
    所有文本均使用 ``mock_`` 前缀，便于开发环境识别和后续人工清理。
    """
    if isinstance(column_type, Enum):
        return column_type.enums[0]
    if isinstance(column_type, DateTime):
        return datetime(2026, 7, 1, 9, 0, 0) + timedelta(days=row_number - 1)
    if isinstance(column_type, Date):
        return date(2026, 7, 1) + timedelta(days=row_number - 1)
    if isinstance(column_type, Boolean):
        return True
    if isinstance(column_type, Integer):
        # 状态型整数通常只接受 0/1；主键和逻辑关联 ID 才使用不同的行号。
        return 1 if column_name in {"status", "enabled"} else row_number
    if isinstance(column_type, (Numeric, Float)):
        return Decimal(f"{row_number}.00")
    if isinstance(column_type, JSON):
        # 日报响应 Schema 明确约定这两个字段是 string list。通用 JSON 对象虽然能入库，
        # 但会在日报列表的 Pydantic 序列化阶段触发 500，因此种子层必须遵守领域契约。
        if table_name == "employee_daily_report" and column_name in {"key_progress", "risks"}:
            return [f"mock_{column_name}_{row_number}"]
        return {"source": "mock_seed", "row": row_number}
    if isinstance(column_type, (String, Text)):
        return _text_value(table_name, column_name, row_number, getattr(column_type, "length", None))

    # 未显式覆盖的方言类型按文本处理；当前模型没有二进制必填业务字段。
    return _text_value(table_name, column_name, row_number, getattr(column_type, "length", None))


def _mock_value(column: Any, table_name: str, row_number: int) -> Any:
    """从 SQLAlchemy ORM 列读取类型信息，再生成对应的模拟值。"""
    return _mock_value_for_type(column.type, table_name, column.name, row_number)


def required_database_only_values(table: Any, database_columns: list[dict[str, Any]], row_number: int) -> dict[str, Any]:
    """为历史表中模型未声明但数据库要求非空的列提供兼容模拟值。

    该函数不迁移结构，只处理已存在表的插入兼容。例如旧版 ``report_schedule``
    仍要求 ``status``，当前 ORM 已改用 ``enabled``；不给该列赋值会使 MySQL 拒绝
    插入。数据库已有默认值或允许空值的列不需要额外处理。
    """
    model_column_names = {column.name for column in table.columns}
    values: dict[str, Any] = {}
    for database_column in database_columns:
        column_name = database_column["name"]
        if (
            column_name not in model_column_names
            and not database_column["nullable"]
            and database_column["default"] is None
        ):
            values[column_name] = _mock_value_for_type(
                database_column["type"], table.name, column_name, row_number
            )
    return values


def table_for_insert(active_engine: Engine, model_table: Any, database_columns: list[dict[str, Any]]) -> Any:
    """选择实际可接收待写入字段的表对象。

    常规情况下直接使用 ORM 表定义；如果数据库含有模型未声明的必填列，则反射真实
    表结构。否则 SQLAlchemy 会在生成 INSERT 时忽略这些额外字段，导致 MySQL 对
    ``NOT NULL`` 列报错。该操作只读取元数据，不修改数据库结构。
    """
    model_column_names = {column.name for column in model_table.columns}
    has_required_legacy_column = any(
        column["name"] not in model_column_names
        and not column["nullable"]
        and column["default"] is None
        for column in database_columns
    )
    if has_required_legacy_column:
        return Table(model_table.name, MetaData(), autoload_with=active_engine)
    return model_table


def _build_mock_rows(table: Any, database_columns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """为一张空表构造两条记录，并给逻辑关联 ID 提供稳定的演示值。"""
    rows: list[dict[str, Any]] = []
    for row_number in (1, 2):
        row: dict[str, Any] = {}
        for column in table.columns:
            # 显式主键让 SQLite 与 MySQL 都能稳定插入，且每张表独立使用 1、2。
            if column.primary_key:
                row[column.name] = row_number
            else:
                row[column.name] = _mock_value(column, table.name, row_number)
        # 将旧表额外必填列合并到 ORM 行数据，保持既有数据库兼容而不执行 ALTER。
        row.update(required_database_only_values(table, database_columns, row_number))
        rows.append(row)
    return rows


def seed_all_module_tables(target_engine: Engine | None = None) -> dict[str, int]:
    """创建缺失表，并为每张空 ORM 表写入两条幂等模拟数据。

    参数:
        target_engine: 目标数据库 Engine；省略时使用项目当前配置的开发数据库。

    返回:
        ``{表名: 当前记录数}``，供命令行输出和测试断言使用。

    副作用:
        可能执行 ``CREATE TABLE`` 和 ``INSERT``。调用方必须确认目标是开发库；脚本
        从不执行 ``DELETE``、``UPDATE`` 或 ``ALTER TABLE``，已存在记录的表会跳过。
    """
    # 该脚本会创建表和插入数据；生产环境必须通过显式迁移与人工确认处理数据库变更。
    if not settings.is_development:
        raise RuntimeError("全模块模拟数据仅允许在 development 环境执行")

    load_all_models()
    active_engine = target_engine or engine

    # create_all 只补齐缺失表，不会改动已经存在的表结构。
    Base.metadata.create_all(bind=active_engine)
    session_factory = sessionmaker(bind=active_engine, autocommit=False, autoflush=False)
    db = session_factory()
    counts: dict[str, int] = {}

    try:
        for table_name, table in sorted(Base.metadata.tables.items()):
            existing_count = db.scalar(select(func.count()).select_from(table)) or 0
            if existing_count == 0:
                database_columns = inspect(active_engine).get_columns(table_name)
                insert_table = table_for_insert(active_engine, table, database_columns)
                # 每张空表一次性写入两行；失败时回滚当前表，避免半条数据残留。
                try:
                    db.execute(insert_table.insert(), _build_mock_rows(table, database_columns))
                    db.commit()
                except Exception:
                    db.rollback()
                    raise

            counts[table_name] = db.scalar(select(func.count()).select_from(table)) or 0
        return counts
    finally:
        db.close()


def main() -> None:
    """执行开发库全模块初始化并输出每张表的最终数据量。"""
    counts = seed_all_module_tables()
    for table_name, count in sorted(counts.items()):
        print(f"{table_name}: {count}")
    print(f"全模块模拟数据初始化完成，共 {len(counts)} 张表。")


if __name__ == "__main__":
    main()
