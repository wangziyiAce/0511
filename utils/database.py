"""Shared SQLAlchemy engine, session factory, and model initialization."""

from typing import Generator

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
    """Declarative base shared by every business module."""


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create registered tables and seed development data only."""

    if not settings.is_development:
        return

    from models import load_all_models

    load_all_models()
    Base.metadata.create_all(bind=engine)

    session = SessionLocal()
    try:
        from services.student_service import seed_data

        seed_data(session)
    finally:
        session.close()
