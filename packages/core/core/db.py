"""Conexión a PostgreSQL (SQLAlchemy 2, psycopg 3)."""
from __future__ import annotations

from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from core.settings import get_settings


@lru_cache
def get_engine(url: str | None = None) -> Engine:
    settings = get_settings()
    dsn = url or (settings.DATABASE_URL_WORKER if settings.SERVICE_ROLE.startswith("worker") and settings.DATABASE_URL_WORKER else settings.DATABASE_URL)
    return create_engine(dsn, pool_pre_ping=True, pool_size=5, max_overflow=5, future=True)


@lru_cache
def get_sessionmaker() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False, future=True)


@contextmanager
def session_scope():
    session = get_sessionmaker()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def reset_caches() -> None:
    """Solo para pruebas: vuelve a leer la configuración de conexión."""
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()
