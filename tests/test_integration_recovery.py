"""集成恢复公共基础设施回归测试。

本文件验证配置、ORM 模型注册和路由装配等公共层契约，避免成员模块再次
各自维护一套数据库或配置入口。测试使用进程内环境变量，不读取真实密钥。
"""

from __future__ import annotations

import importlib
import sys
import subprocess
from types import SimpleNamespace


def _load_config_with_env(monkeypatch, **values):
    """按测试给定的环境变量重新导入配置模块，隔离其他测试的模块缓存。"""

    for key in (
        "DATABASE_URL",
        "DB_HOST",
        "DB_PORT",
        "DB_USER",
        "DB_PASSWORD",
        "DB_NAME",
        "JWT_SECRET_KEY",
        "SECRET_KEY",
        "JWT_EXPIRE_HOURS",
        "ACCESS_TOKEN_EXPIRE_MINUTES",
        "DIFY_API_BASE_URL",
        "DIFY_API_URL",
        "DIFY_API_KEY",
        "DIFY_SERVICE_TOKEN",
        "APP_ENV",
    ):
        monkeypatch.delenv(key, raising=False)

    for key, value in values.items():
        monkeypatch.setenv(key, value)

    sys.modules.pop("config", None)
    return importlib.import_module("config")


def test_settings_prefers_database_url_and_keeps_legacy_constants(monkeypatch):
    """测试目标：统一配置既支持新 settings，也不破坏旧模块级常量导入。"""

    config = _load_config_with_env(
        monkeypatch,
        DATABASE_URL="sqlite+pysqlite:///:memory:",
        JWT_SECRET_KEY="test-jwt-secret",
        JWT_EXPIRE_HOURS="2",
        DIFY_API_BASE_URL="https://dify.example.test/v1",
        DIFY_API_KEY="test-dify-key",
        DIFY_SERVICE_TOKEN="test-service-token",
        APP_ENV="development",
    )

    assert config.settings.DATABASE_URL == "sqlite+pysqlite:///:memory:"
    assert config.DATABASE_URL == config.settings.DATABASE_URL
    assert config.settings.SECRET_KEY == "test-jwt-secret"
    assert config.ACCESS_TOKEN_EXPIRE_MINUTES == 120
    assert config.DIFY_API_URL == "https://dify.example.test/v1"
    assert config.settings.DIFY_SERVICE_TOKEN == "test-service-token"
    assert config.settings.is_development is True


def test_main_module_imports_after_public_orm_contract_is_restored():
    """测试目标：应用导入必须拿到聊天模型依赖的公共 ORM 类型，且不触发生命周期写库。"""

    result = subprocess.run(
        [sys.executable, "-c", "import main; print(main.app.title)"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip()


def test_model_registry_uses_student_models_for_shared_student_tables():
    """测试目标：报告与学生模块加载后，两张共享学生表只能有一个 ORM 映射。"""

    import models

    models.load_all_models()

    from models.report import StudentFeedbackTicket as ReportFeedbackTicket
    from models.report import StudentPsychAlert as ReportPsychAlert
    from models.student import StudentFeedbackTicket, StudentPsychAlert
    from utils.database import Base

    assert ReportFeedbackTicket is StudentFeedbackTicket
    assert ReportPsychAlert is StudentPsychAlert
    assert "student_feedback_ticket" in Base.metadata.tables
    assert "student_psych_alert" in Base.metadata.tables


def test_init_db_skips_all_writes_outside_development(monkeypatch):
    """测试目标：生产和测试环境启动时不能隐式改表或写入种子用户。"""

    import utils.database as database

    calls: list[str] = []
    monkeypatch.setattr(
        database,
        "settings",
        SimpleNamespace(is_development=False),
        raising=False,
    )
    monkeypatch.setattr(
        database.Base.metadata,
        "create_all",
        lambda **_: calls.append("create_all"),
    )
    monkeypatch.setattr(
        database,
        "_auto_migrate_missing_columns",
        lambda: calls.append("auto_migrate"),
    )
    monkeypatch.setattr(
        database,
        "seed_basic_users",
        lambda _: calls.append("seed_users"),
    )
    monkeypatch.setattr(
        database,
        "SessionLocal",
        lambda: SimpleNamespace(close=lambda: calls.append("close")),
    )

    database.init_db()

    assert calls == []


def test_router_registry_mounts_confirmed_modules_without_duplicate_operations():
    """统一路由入口应挂载确认模块，并避免同一请求方法与路径重复。

    本测试不启动数据库生命周期，只检查 FastAPI 最终暴露的接口清单。这样可以
    在服务启动前发现漏挂载或认证接口重复注册，避免 Swagger 文档与前端调用不一致。
    """
    from fastapi import FastAPI

    from routers import register_routers

    app = FastAPI()
    register_routers(app)

    # FastAPI 新版本会先保存嵌套路由对象；OpenAPI 是框架展开后的最终接口契约。
    operations = [
        (path, method.upper())
        for path, definition in app.openapi()["paths"].items()
        for method in definition
        if method.upper() not in {"HEAD", "OPTIONS"}
    ]
    paths = {path for path, _ in operations}

    assert {
        "/api/v1/auth/login",
        "/api/v1/crm/leads",
        "/api/v1/employee/daily-reports",
        "/api/v1/courses",
        "/api/v1/profile/upload",
        "/api/v1/reports/generate",
        "/api/v1/report-schedules",
        "/api/v1/report-actions/{action_id}",
        "/api/v1/report-data/application-materials",
        "/api/v1/student/feedback-tickets/{ticket_id}",
    }.issubset(paths)
    assert len(operations) == len(set(operations))
