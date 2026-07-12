"""Unified runtime configuration for the education service API."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote_plus

from dotenv import load_dotenv


load_dotenv(Path(__file__).with_name(".env"), override=False)


def _read_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value in (None, ""):
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"Environment variable {name} must be an integer") from exc


def _read_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value in (None, ""):
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _first_non_empty(*names: str, default: str = "") -> str:
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return default


@dataclass(frozen=True)
class Settings:
    APP_NAME: str
    APP_VERSION: str
    APP_ENV: str
    APP_DEBUG: bool
    DATABASE_URL: str
    DB_ECHO: bool
    DB_POOL_SIZE: int
    DB_MAX_OVERFLOW: int
    DB_POOL_TIMEOUT: int
    DB_POOL_RECYCLE: int
    SECRET_KEY: str
    BCRYPT_COST: int
    ACCESS_TOKEN_EXPIRE_MINUTES: int
    DIFY_API_URL: str
    DIFY_API_KEY: str
    DIFY_SERVICE_TOKEN: str
    LLM_API_URL: str
    LLM_API_KEY: str
    LLM_MODEL: str
    LLM_TIMEOUT: int
    DASHSCOPE_API_KEY: str
    PRODUCT_RULES_PATH: str
    PRODUCT_CATALOG_PATH: str
    UPLOAD_DIR: str
    MAX_UPLOAD_SIZE: int

    @property
    def is_development(self) -> bool:
        return self.APP_ENV.lower() == "development"

    @classmethod
    def from_environment(cls) -> "Settings":
        db_host = _first_non_empty("DB_HOST", default="localhost")
        db_port = _read_int("DB_PORT", 3306)
        db_user = _first_non_empty("DB_USER", default="root")
        db_password = _first_non_empty("DB_PASSWORD")
        db_name = _first_non_empty("DB_NAME", default="education_service")
        db_charset = _first_non_empty("DB_CHARSET", default="utf8mb4")

        database_url = _first_non_empty("DATABASE_URL")
        if not database_url:
            database_url = (
                f"mysql+pymysql://{quote_plus(db_user)}:{quote_plus(db_password)}"
                f"@{db_host}:{db_port}/{db_name}?charset={db_charset}"
            )

        token_minutes = _read_int("ACCESS_TOKEN_EXPIRE_MINUTES", 0)
        if token_minutes <= 0:
            token_minutes = _read_int("JWT_EXPIRE_HOURS", 24) * 60

        return cls(
            APP_NAME=_first_non_empty("APP_NAME", default="教育服务系统 API"),
            APP_VERSION=_first_non_empty("APP_VERSION", default="1.0.0"),
            APP_ENV=_first_non_empty("APP_ENV", default="production"),
            APP_DEBUG=_read_bool("APP_DEBUG", False),
            DATABASE_URL=database_url,
            DB_ECHO=_read_bool("DB_ECHO", False),
            DB_POOL_SIZE=_read_int("DB_POOL_SIZE", 10),
            DB_MAX_OVERFLOW=_read_int("DB_MAX_OVERFLOW", 20),
            DB_POOL_TIMEOUT=_read_int("DB_POOL_TIMEOUT", 30),
            DB_POOL_RECYCLE=_read_int("DB_POOL_RECYCLE", 3600),
            SECRET_KEY=_first_non_empty("JWT_SECRET_KEY", "SECRET_KEY", default="change-me-in-production"),
            BCRYPT_COST=_read_int("BCRYPT_COST", 12),
            ACCESS_TOKEN_EXPIRE_MINUTES=token_minutes,
            DIFY_API_URL=_first_non_empty("DIFY_API_BASE_URL", "DIFY_API_URL", default="http://localhost:5001/v1"),
            DIFY_API_KEY=_first_non_empty("DIFY_API_KEY"),
            DIFY_SERVICE_TOKEN=_first_non_empty("DIFY_SERVICE_TOKEN"),
            LLM_API_URL=_first_non_empty("LLM_API_URL", default="https://api.deepseek.com/v1"),
            LLM_API_KEY=_first_non_empty("LLM_API_KEY"),
            LLM_MODEL=_first_non_empty("LLM_MODEL", default="qwen-plus"),
            LLM_TIMEOUT=_read_int("LLM_TIMEOUT", 120),
            DASHSCOPE_API_KEY=_first_non_empty("DASHSCOPE_API_KEY"),
            PRODUCT_RULES_PATH=_first_non_empty("PRODUCT_RULES_PATH", default="产品线匹配规则.md"),
            PRODUCT_CATALOG_PATH=_first_non_empty("PRODUCT_CATALOG_PATH", default="全产品线目录.md"),
            UPLOAD_DIR=_first_non_empty("UPLOAD_DIR", default="uploads/profiles"),
            MAX_UPLOAD_SIZE=_read_int("MAX_UPLOAD_SIZE", 10 * 1024 * 1024),
        )


settings = Settings.from_environment()

for _name in Settings.__dataclass_fields__:
    globals()[_name] = getattr(settings, _name)

