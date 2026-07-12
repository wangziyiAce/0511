"""数据库连接与初始化。

这个文件是 FastAPI 与 MySQL 的公共入口：

* ``engine``：数据库连接池；
* ``SessionLocal``：数据库会话工厂；
* ``Base``：所有 SQLAlchemy ORM 模型的基类；
* ``get_db``：FastAPI 依赖注入，每个请求自动获取/关闭 Session；
* ``init_db``：应用启动时注册模型、建表、写入最小种子数据。

启动期建表和种子写入只允许在 development 环境执行。生产和测试环境必须通过
版本化迁移准备数据库，避免应用导入或启动时隐式改变数据库结构。
"""

from __future__ import annotations

from typing import Generator

import bcrypt
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import QueuePool

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
    raise RuntimeError(
        "未配置 DATABASE_URL，也未提供完整的 DB_USER、DB_PASSWORD、DB_NAME；"
        "请在环境变量或 .env 中设置数据库连接。"
    )


engine = create_engine(
    DATABASE_URL,
    poolclass=QueuePool,
    pool_size=DB_POOL_SIZE,
    max_overflow=DB_MAX_OVERFLOW,
    pool_timeout=DB_POOL_TIMEOUT,
    pool_recycle=DB_POOL_RECYCLE,
    pool_pre_ping=True,
    echo=DB_ECHO,
)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


class Base(DeclarativeBase):
    """所有 ORM 模型的基类。"""


def get_db() -> Generator[Session, None, None]:
    """FastAPI 依赖：为每个请求提供一个数据库 Session。"""

    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _hash_seed_password(password: str) -> str:
    """生成开发种子用户的密码哈希，避免数据库层依赖认证模块。"""

    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def seed_basic_users(db: Session) -> None:
    """仅在开发库缺少基础角色或管理员时写入最小种子数据。"""

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
    """开发期兼容函数：补齐 ORM 新增列；当前启动流程不调用此函数。

    正式数据库变更必须使用版本化 migration。本函数只为历史调用方保留，不能在
    生产或测试启动阶段隐式执行。
    """

    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    db_table_names = set(inspector.get_table_names())
    type_map = {
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
        "ENUM": "VARCHAR(64)",
    }

    for table_name, table in Base.metadata.tables.items():
        if table_name not in db_table_names:
            continue
        db_columns = {column["name"] for column in inspector.get_columns(table_name)}
        for column in table.columns:
            if column.name in db_columns:
                continue
            base_type = str(column.type).split("(")[0].split()[0].upper()
            mysql_type = type_map.get(base_type)
            if mysql_type is None:
                continue
            nullable = "NULL" if column.nullable else "NOT NULL"
            default_clause = ""
            if column.server_default is not None:
                default_clause = f" DEFAULT {column.server_default.arg}"
            elif column.default is not None:
                default_clause = f" DEFAULT {column.default.arg}"
            comment = f" COMMENT '{column.comment}'" if column.comment else ""
            sql = (
                f"ALTER TABLE {table_name} ADD COLUMN {column.name} "
                f"{mysql_type} {nullable}{default_clause}{comment}"
            )
            try:
                with engine.connect() as connection:
                    connection.execute(text(sql))
                    connection.commit()
            except Exception:
                # 兼容函数不能阻断开发启动；正式迁移会显式报告错误。
                pass


def init_db() -> None:
    """仅在 development 环境加载全量模型、建表并写入基础种子。"""

    if not settings.is_development:
        return

    from models import load_all_models

    load_all_models()
    Base.metadata.create_all(bind=engine)

    # 不在启动期执行自动 ALTER；字段变更通过 migrations 目录的版本化 SQL 完成。
    db = SessionLocal()
    try:
        seed_basic_users(db)
    finally:
        db.close()
