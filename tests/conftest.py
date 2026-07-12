"""测试公共 Fixture - SQLite 内存库 + FastAPI TestClient"""
import os
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

# 覆盖环境变量：测试模式下使用 SQLite 内存库
os.environ["APP_ENV"] = "testing"
os.environ["APP_DEBUG"] = "false"

# 必须在导入 config 前设置 DATABASE_URL
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
# 测试默认必须走确定性路径，不能因开发机 .env 中配置了真实密钥而访问外部模型。
# 需要验证 LLM 的用例会在自身 fixture 中显式开启并注入 Mock。
os.environ["REPORT_ASSISTANT_LLM_ENABLED"] = "false"

import config as settings  # config 模块以属性方式导出所有配置项（无 settings 对象）
from utils.database import Base, get_db
from main import app


def _normalize_sqlite_index_names() -> None:
    """把 MySQL 可接受的同名索引改为 SQLite 元数据内的全局唯一名称。

    生产库允许不同表使用相同索引名；SQLite 要求整个数据库唯一。这里只修改测试进程
    中的 SQLAlchemy 元数据，不修改业务模型和生产迁移，避免全量建表 fixture 互相污染。
    """
    indexes = [index for table in Base.metadata.tables.values() for index in table.indexes]
    name_counts: dict[str, int] = {}
    for index in indexes:
        if index.name:
            name_counts[index.name] = name_counts.get(index.name, 0) + 1
    for index in indexes:
        if index.name and name_counts[index.name] > 1:
            index.name = f"ix_{index.table.name}_{index.name}"


_normalize_sqlite_index_names()

# ---------------------------------------------------------------------------
# Engine & Session
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def engine():
    """会话级 SQLite 内存引擎。

    使用 StaticPool：让所有连接共享同一个内存库，
    否则 SQLite ':memory:' 每连接隔离，db_session 看不到 create_all 建的表。
    """
    from sqlalchemy.pool import StaticPool
    return create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False,
    )


# 测试只依赖以下表，避免 student 模块中跨表重名索引（idx_status 等）
# 在 SQLite 下建表失败（SQLite 索引名数据库级必须全局唯一，MySQL 表级允许重复）
NEEDED_TABLES = [
    "sys_role",
    "sys_user",
    "sys_organization",
    "crm_lead",
    "crm_follow_up",
    "employee_daily_report",
    "assistant_session",
    "assistant_message",
]


@pytest.fixture(scope="session")
def tables_created(engine):
    """会话级建表（只建测试所需表子集，只执行一次）"""
    tables = [Base.metadata.tables[name] for name in NEEDED_TABLES if name in Base.metadata.tables]
    Base.metadata.create_all(engine, tables=tables)
    yield
    Base.metadata.drop_all(engine, tables=tables)


@pytest.fixture
def db_session(engine, tables_created):
    """每个测试独立数据库会话（事务回滚隔离）"""
    connection = engine.connect()
    transaction = connection.begin()
    TestSession = sessionmaker(bind=connection)
    session = TestSession()

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def client(db_session, monkeypatch):
    """FastAPI TestClient，覆盖 get_db 依赖。

    禁用 lifespan 中的 init_db()：测试建表由 tables_created fixture 负责，
    避免 init_db 在独立内存库上建全部表（含 student 模块冲突索引）导致启动失败。
    """
    import main as _main
    monkeypatch.setattr(_main, "init_db", lambda: None)

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# 鉴权 Headers
# ---------------------------------------------------------------------------

@pytest.fixture
def auth_headers():
    """携带正确 Dify Service Token 的请求头"""
    return {"Authorization": f"Bearer {settings.DIFY_SERVICE_TOKEN}"}


@pytest.fixture
def invalid_auth_headers():
    """携带错误 Token 的请求头"""
    return {"Authorization": "Bearer wrong-token-xxxxx"}


# ---------------------------------------------------------------------------
# 种子数据
# ---------------------------------------------------------------------------

@pytest.fixture
def seed_courses(db_session):
    """预置 10 条课程种子数据"""
    from models.chat import CourseProject
    courses = [
        CourseProject(project_name="雅思7分冲刺班", category="语言培训", description="雅思备考课程", target_audience="雅思基础5.5分以上", price=8800.00, duration="8周", tags='["名师授课"]', status=1),
        CourseProject(project_name="托福100分突破班", category="语言培训", description="托福备考课程", target_audience="托福基础70分以上", price=9800.00, duration="10周", tags='["真题题库"]', status=1),
        CourseProject(project_name="日语N2速成班", category="语言培训", description="日语速成课程", target_audience="零基础", price=6800.00, duration="24周", tags='["沉浸式教学"]', status=1),
        CourseProject(project_name="GRE/GMAT联报班", category="语言培训", description="GRE与GMAT联合备考", target_audience="大三及以上学生", price=12800.00, duration="16周", tags='["双线备考"]', status=1),
        CourseProject(project_name="科研背景提升项目", category="背景提升", description="科研课题参与", target_audience="本科在读学生", price=29800.00, duration="12周", tags='["名校教授"]', status=1),
        CourseProject(project_name="名企实习内推计划", category="背景提升", description="500强企业实习", target_audience="大三及以上学生", price=15800.00, duration="8-12周", tags='["500强企业"]', status=1),
        CourseProject(project_name="艺术作品集辅导", category="背景提升", description="作品集指导", target_audience="艺术/设计专业学生", price=25800.00, duration="16周", tags='["一对一辅导"]', status=1),
        CourseProject(project_name="英国硕士直通车", category="留学申请", description="英国TOP30申请", target_audience="本科毕业生", price=39800.00, duration="6-12个月", tags='["TOP30保录"]', status=1),
        CourseProject(project_name="美国名校申请套餐", category="留学申请", description="美国TOP50申请", target_audience="GPA 3.0以上", price=59800.00, duration="12-18个月", tags='["TOP50名校"]', status=1),
        CourseProject(project_name="澳大利亚移民+留学双规划", category="留学申请", description="移民+留学双路径", target_audience="有意向移民澳洲", price=35800.00, duration="8-14个月", tags='["移民规划"]', status=1),
    ]
    db_session.add_all(courses)
    db_session.commit()
    return courses


@pytest.fixture
def seed_events(db_session):
    """预置 5 条活动种子数据"""
    from models.chat import EventLecture
    from datetime import datetime
    events = [
        EventLecture(event_name="英国留学申请攻略讲座", event_type="online", description="详解英国硕士申请", start_time=datetime(2026, 7, 15, 14, 0, 0), end_time=datetime(2026, 7, 15, 16, 0, 0), location="线上-腾讯会议", max_participants=100, current_participants=0, status="upcoming"),
        EventLecture(event_name="美国TOP30名校申请经验分享", event_type="offline", description="名校申请经验分享", start_time=datetime(2026, 7, 20, 10, 0, 0), end_time=datetime(2026, 7, 20, 12, 0, 0), location="北京市朝阳区", max_participants=50, current_participants=0, status="upcoming"),
        EventLecture(event_name="雅思口语高分技巧公开课", event_type="online", description="雅思考官亲授", start_time=datetime(2026, 7, 18, 19, 0, 0), end_time=datetime(2026, 7, 18, 20, 30, 0), location="线上-Zoom", max_participants=200, current_participants=0, status="upcoming"),
        EventLecture(event_name="留学文书写作工作坊", event_type="hybrid", description="文书写作技巧", start_time=datetime(2026, 7, 25, 14, 0, 0), end_time=datetime(2026, 7, 25, 17, 0, 0), location="上海+线上同步", max_participants=30, current_participants=0, status="upcoming"),
        EventLecture(event_name="留学生海外生活指南分享会", event_type="online", description="海外生活经验", start_time=datetime(2026, 8, 1, 15, 0, 0), end_time=datetime(2026, 8, 1, 16, 30, 0), location="线上-腾讯会议", max_participants=150, current_participants=0, status="upcoming"),
    ]
    db_session.add_all(events)
    db_session.commit()
    return events


@pytest.fixture
def seed_user(db_session):
    """创建测试用户"""
    from models.user import SysUser
    user = SysUser(id=1001, username="testuser", password_hash="hashed_xxx", role="student", status=1)
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def seed_multiple_users(db_session):
    """创建多个测试用户（用于并发测试）"""
    from models.user import SysUser
    users = []
    for i in range(2001, 2011):
        user = SysUser(id=i, username=f"testuser_{i}", password_hash="hashed_xxx", role="student", status=1)
        users.append(user)
    db_session.add_all(users)
    db_session.commit()
    return users
