"""
教育服务系统 - 配置中心
基于 pydantic-settings，自动从 .env 文件和环境变量加载配置
"""
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # ==================== 应用基础配置 ====================
    APP_NAME: str = "教育服务系统 API"
    APP_VERSION: str = "1.1.0"
    DEBUG: bool = True
    SECRET_KEY: str = "change-me-in-production"

    # ==================== 数据库配置 ====================
    DB_HOST: str = "localhost"
    DB_PORT: int = 3306
    DB_USER: str = "root"
    DB_PASSWORD: str = ""
    DB_NAME: str = "education_service"

    # ==================== JWT 认证配置 ====================
    JWT_SECRET_KEY: str = "jwt-secret-change-me"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 1440  # 24 小时

    # ==================== Dify AI 平台配置 ====================
    DIFY_BASE_URL: str = "https://api.dify.ai/v1"
    DIFY_API_KEY: str = ""
    # Dify HTTP 节点调用 FastAPI 白名单接口时使用的服务令牌（独立于用户 JWT）
    DIFY_SERVICE_TOKEN: str = "dify-service-token-change-me"

    # ==================== 文件上传配置 ====================
    UPLOAD_DIR: str = "./uploads"
    MAX_UPLOAD_SIZE_MB: int = 10

    # ==================== CORS 配置 ====================
    CORS_ORIGINS: list[str] = ["*"]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

    @property
    def database_url(self) -> str:
        """构建异步 MySQL 连接字符串"""
        return (
            f"mysql+aiomysql://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
            f"?charset=utf8mb4"
        )

    @property
    def sync_database_url(self) -> str:
        """构建同步 MySQL 连接字符串（用于 alembic 等工具）"""
        return (
            f"mysql+pymysql://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
            f"?charset=utf8mb4"
        )


@lru_cache
def get_settings() -> Settings:
    """单例模式获取配置（带缓存）"""
    return Settings()
