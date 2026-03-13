from __future__ import annotations

import importlib.util
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.engine.url import make_url
from sqlalchemy.orm import sessionmaker

from app.core.config import settings


def _module_available(module_name: str) -> bool:
    return importlib.util.find_spec(module_name) is not None


def _normalize_database_url(database_url: str) -> str:
    normalized = str(database_url or '').strip()
    if not normalized:
        return normalized

    try:
        parsed = make_url(normalized)
    except Exception:
        return normalized

    backend = parsed.get_backend_name()
    driver = parsed.get_driver_name() or ''

    if backend != 'postgresql':
        return normalized

    has_psycopg2 = _module_available('psycopg2')
    has_psycopg = _module_available('psycopg')

    if driver in {'', 'psycopg2'}:
        if has_psycopg2:
            target_driver = 'postgresql+psycopg2'
        elif has_psycopg:
            target_driver = 'postgresql+psycopg'
        else:
            target_driver = 'postgresql+psycopg2'
        return parsed.set(drivername=target_driver).render_as_string(hide_password=False)

    if driver == 'psycopg' and not has_psycopg and has_psycopg2:
        return parsed.set(drivername='postgresql+psycopg2').render_as_string(hide_password=False)

    return normalized


def _engine_kwargs(database_url: str) -> dict:
    if database_url.startswith('sqlite'):
        return {'connect_args': {'check_same_thread': False}}
    return {'pool_pre_ping': True}


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    database_url = _normalize_database_url(settings.database_url)
    return create_engine(database_url, **_engine_kwargs(database_url))


SessionLocal = sessionmaker(autocommit=False, autoflush=False, expire_on_commit=False)


def create_session():
    SessionLocal.configure(bind=get_engine())
    return SessionLocal()


def get_db():
    db = create_session()
    try:
        yield db
    finally:
        db.close()
