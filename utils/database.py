"""
教育服务系统 - 数据库连接管理
使用 SQLAlchemy 2.0 异步引擎 + aiomysql 驱动
采用惰性初始化模式：引擎和会话工厂在首次调用时才创建
"""
from typing import Optional
from sqlalchemy.ext.asyncio import (
    create_async_engine,
    async_sessionmaker,
    AsyncSession,
    AsyncEngine,
)
from sqlalchemy.orm import DeclarativeBase
from config import get_settings

settings = get_settings()

# ==================== 惰性初始化的全局实例 ====================
_engine: Optional[AsyncEngine] = None
_session_factory: Optional[async_sessionmaker] = None


def _get_engine() -> AsyncEngine:
    """惰性创建异步引擎（首次调用时才连接数据库）"""
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            settings.database_url,
            echo=settings.DEBUG,
            pool_size=10,
            max_overflow=20,
            pool_recycle=3600,
            pool_pre_ping=True,
        )
    return _engine


def _get_session_factory() -> async_sessionmaker:
    """惰性创建会话工厂"""
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            _get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _session_factory


# ==================== ORM 基类 ====================
class Base(DeclarativeBase):
    """所有 ORM Model 的基类"""
    pass


# ==================== 依赖注入 ====================
async def get_db() -> AsyncSession:
    """
    FastAPI 依赖注入：获取数据库会话。
    每次请求自动开启事务，结束时 commit/rollback。

    用法:
        @router.get("/users")
        async def get_users(db: AsyncSession = Depends(get_db)):
            ...
    """
    factory = _get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ==================== 数据库健康检查 ====================
async def check_db_connection() -> bool:
    """检测数据库连接是否正常"""
    try:
        factory = _get_session_factory()
        async with factory() as session:
            from sqlalchemy import text
            await session.execute(text("SELECT 1"))
            return True
    except Exception:
        return False


# ==================== 释放连接池 ====================
async def dispose_engine():
    """关闭引擎、释放连接池（应用关闭时调用）"""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
    _session_factory = None
