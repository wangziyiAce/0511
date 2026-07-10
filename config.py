"""教育服务系统 - 全局配置"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Always load the project's .env file, even when Uvicorn is started from
# another working directory.
load_dotenv(dotenv_path=Path(__file__).with_name(".env"))


class Settings:
    APP_NAME: str = "教育服务系统"
    APP_VERSION: str = "1.0.0"
    APP_ENV: str = os.getenv("APP_ENV", "development")
    APP_DEBUG: bool = os.getenv("APP_DEBUG", "true").lower() == "true"

    # 数据库
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "mysql+pymysql://root:123456@127.0.0.1:3306/education_service?charset=utf8mb4&ssl_disabled=true"
    )
    DB_POOL_SIZE: int = int(os.getenv("DB_POOL_SIZE", "10"))
    DB_MAX_OVERFLOW: int = int(os.getenv("DB_MAX_OVERFLOW", "20"))

    # JWT
    JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", "change-me-in-production")
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_HOURS: int = int(os.getenv("JWT_EXPIRE_HOURS", "24"))

    ################################
    # Dify API
    ################################

    # FastAPI 调用 Dify
    DIFY_API_BASE_URL: str = os.getenv("DIFY_API_BASE_URL", "http://localhost/v1")
    DIFY_API_KEY: str = os.getenv("DIFY_API_KEY", "app-xxxxxxxxxxxxxxxx")

    ################################
    # Dify调用FastAPI
    ################################

    DIFY_SERVICE_TOKEN: str = os.getenv("DIFY_SERVICE_TOKEN", "service-edu-agent-20260709")

    ################################
    # Backend
    ################################

    BACKEND_API_BASE_URL: str = os.getenv(
        "BACKEND_API_BASE_URL",
        "http://host.docker.internal:8000"
    )
    # 文件上传
    UPLOAD_DIR: str = os.getenv("UPLOAD_DIR", "./uploads")
    MAX_UPLOAD_SIZE: int = int(os.getenv("MAX_UPLOAD_SIZE", "10485760"))


settings = Settings()
