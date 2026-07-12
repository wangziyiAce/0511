"""数据库连接与初始化。

这个文件是 FastAPI 与 MySQL / SQLite 的公共入口：

* ``engine``：数据库连接池；
* ``SessionLocal``：数据库会话工厂；
* ``Base``：所有 SQLAlchemy ORM 模型的基类；
* ``get_db``：FastAPI 依赖注入，每个请求自动获取/关闭 Session；
* ``init_db``：应用启动时注册模型、建表、写入最小种子数据。

SQLite 支持通过 ``_engine_options()`` 自动检测，用于本地测试与 CI。
"""

from __future__ import annotations

import os
from typing import Generator

import bcrypt
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import QueuePool, StaticPool

from config import (
    DATABASE_URL,
    DB_ECHO,
    DB_MAX_OVERFLOW,
    DB_POOL_RECYCLE,
    DB_POOL_SIZE,
    DB_POOL_TIMEOUT,
    settings,
)


if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not configured for education_service")


def _engine_options() -> dict:
    """根据数据库类型返回 engine 参数。

    SQLite 需要 ``check_same_thread=False``，内存库使用 ``StaticPool``。
    MySQL / PostgreSQL 使用 ``QueuePool`` 并启用 ``pool_pre_ping``。
    """
    common = {"echo": DB_ECHO}
    if DATABASE_URL.startswith("sqlite"):
        common["connect_args"] = {"check_same_thread": False}
        if ":memory:" in DATABASE_URL:
            common["poolclass"] = StaticPool
        return common
    return {
        **common,
        "poolclass": QueuePool,
        "pool_size": DB_POOL_SIZE,
        "max_overflow": DB_MAX_OVERFLOW,
        "pool_timeout": DB_POOL_TIMEOUT,
        "pool_recycle": DB_POOL_RECYCLE,
        "pool_pre_ping": True,
    }


engine = create_engine(DATABASE_URL, **_engine_options())
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


class Base(DeclarativeBase):
    """所有 ORM 模型的基类。"""


def get_db() -> Generator[Session, None, None]:
    """FastAPI 依赖：为每个请求提供一个数据库 Session。

    每次请求开始时通过 ``SessionLocal()`` 创建会话，
    请求结束后在 ``finally`` 中关闭，确保连接归还连接池。
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _hash_seed_password(password: str) -> str:
    """种子用户密码哈希。

    这里不从 ``utils.auth`` 导入，避免数据库层和认证层循环依赖。
    """
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def seed_basic_users(db: Session) -> None:
    """写入最小角色和管理员账号。

    种子数据只在表为空或用户不存在时写入，重复启动不会重复插入。
    """
    from models.user import SysRole, SysUser

    if db.query(SysRole).count() == 0:
        db.add_all(
            [
                SysRole(role_code="admin", role_name="系统管理员", description="拥有全部管理权限"),
                SysRole(role_code="manager", role_name="部门经理", description="查看部门管理报告"),
                SysRole(role_code="employee", role_name="员工/顾问", description="查看本人负责数据"),
                SysRole(role_code="team_leader", role_name="班主任", description="查看授权学生服务数据"),
                SysRole(role_code="student", role_name="学生", description="学生端角色，禁止管理报告"),
            ]
        )
        db.commit()

    if db.query(SysUser).filter_by(username="admin").count() == 0:
        admin_role = db.query(SysRole).filter_by(role_code="admin").first()
        admin = SysUser(
            username="admin",
            password_hash=_hash_seed_password("admin123"),
            real_name="系统管理员",
            user_type="admin",
            role_id=admin_role.id if admin_role else None,
            department="技术部",
            contact_info="admin@example.com",
            status="normal",
        )
        db.add(admin)
        db.commit()


def _auto_migrate_missing_columns() -> None:
    """为所有已存在的表自动补齐 ORM 模型中新增的列。

    ``Base.metadata.create_all()`` 对已存在的表只会跳过，不会执行 ALTER。
    开发期 ORM 字段频繁变更，这里自动对比 ORM 定义与数据库实际列，补齐缺失字段。

    生产环境应使用 Alembic 等正式迁移工具代替此函数。
    """
    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    db_table_names = set(inspector.get_table_names())

    # SQLAlchemy 类型 → MySQL DDL 的简单映射（只覆盖本项目用到的类型）
    _TYPE_MAP = {
        "BIGINT": "BIGINT",
        "INTEGER": "INT",
        "VARCHAR": "VARCHAR(255)",
        "TEXT": "TEXT",
        "MEDIUMTEXT": "MEDIUMTEXT",
        "DATETIME": "DATETIME",
        "DATE": "DATE",
        "JSON": "JSON",
        "DECIMAL": "DECIMAL(20,6)",
        "TINYINT": "TINYINT",
        "ENUM": "VARCHAR(64)",  # ENUM 新增列统一用 VARCHAR 兜底（添加新值不方便）
    }

    for table_name, table in Base.metadata.tables.items():
        if table_name not in db_table_names:
            continue  # 表还不存在，create_all 会处理

        db_columns = {col["name"]: col for col in inspector.get_columns(table_name)}

        for col in table.columns:
            if col.name in db_columns:
                continue

            # 推导 MySQL DDL 类型
            col_type_str = str(col.type)
            # 提取基础类型名（如 "VARCHAR(64)" → "VARCHAR"）
            base_type = col_type_str.split("(")[0].split()[0].upper()
            mysql_type = _TYPE_MAP.get(base_type)
            if mysql_type is None:
                # 不能识别的类型，跳过（避免错误迁移）
                continue

            # nullable
            nullable = "NULL" if col.nullable else "NOT NULL"

            # default
            default_clause = ""
            if col.server_default is not None:
                # server_default 是 SQL 表达式
                default_clause = f" DEFAULT {col.server_default.arg}"
            elif col.default is not None:
                default_clause = f" DEFAULT {col.default.arg}"

            # comment
            comment = f" COMMENT '{col.comment}'" if col.comment else ""

            sql = (
                f"ALTER TABLE {table_name} "
                f"ADD COLUMN {col.name} {mysql_type} {nullable}{default_clause}{comment}"
            )

            try:
                with engine.connect() as conn:
                    conn.execute(text(sql))
                    conn.commit()
            except Exception:
                pass  # 列可能已通过其他方式添加


def init_db() -> None:
    """注册全部 ORM 模型并创建表。

    ``create_all`` 只会创建不存在的表，不会自动 ALTER 已有表。
    开发环境额外执行自动列补齐和种子数据写入。
    """
    if not settings.is_development:
        return

    # 导入所有 Model 模块，触发类定义注册到 Base.metadata
    try:
        from models import load_all_models
        load_all_models()
    except ImportError:
        # 兼容旧版 models 包（无 load_all_models 时回退为显式导入）
        import models.chat  # noqa: F401
        import models.crm  # noqa: F401
        import models.knowledge  # noqa: F401
        import models.report  # noqa: F401
        import models.student  # noqa: F401
        import models.user  # noqa: F401

    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        seed_basic_users(db)
    finally:
        db.close()
