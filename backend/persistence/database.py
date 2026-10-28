"""Database connection, session management, and configuration."""

from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Generator, Optional

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from persistence.models import Base

# Default SQLite database path in local backend directory
_DEFAULT_DB_FILE = Path(__file__).resolve().parent.parent / "qualloop.db"
_DEFAULT_URL = f"sqlite:///{_DEFAULT_DB_FILE}"

_current_url: Optional[str] = None
_engine: Optional[Engine] = None
_session_factory: Optional[sessionmaker[Session]] = None


def normalize_database_url(url: str) -> str:
    """
    Normalize legacy PostgreSQL database URLs.
    Rewrites 'postgres://' to 'postgresql://' without altering other URL components or credentials.
    Leaves SQLite and postgresql+... URLs unchanged.
    """
    if url.startswith("postgres://"):
        return "postgresql://" + url[len("postgres://"):]
    return url


def get_database_url() -> str:
    """Return active database URL from override, environment, or default, normalized."""
    raw = _current_url or os.getenv("DATABASE_URL", _DEFAULT_URL)
    return normalize_database_url(raw)


def set_database_url(url: Optional[str]) -> None:
    """Override database URL (primarily for test isolation)."""
    global _current_url, _engine, _session_factory
    _current_url = url
    _engine = None
    _session_factory = None


def get_engine() -> Engine:
    """Get or create the SQLAlchemy engine."""
    global _engine
    if _engine is None:
        url = get_database_url()
        is_sqlite = url.startswith("sqlite")
        connect_args = {"check_same_thread": False} if is_sqlite else {}

        _engine = create_engine(
            url,
            connect_args=connect_args,
            pool_pre_ping=True,
            future=True,
        )

        if is_sqlite:
            @event.listens_for(_engine, "connect")
            def _set_sqlite_pragma(dbapi_connection, connection_record):
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.close()

    return _engine


def get_session_factory() -> sessionmaker[Session]:
    """Get or create the session factory."""
    global _session_factory
    if _session_factory is None:
        engine = get_engine()
        _session_factory = sessionmaker(
            bind=engine,
            autocommit=False,
            autoflush=False,
            expire_on_commit=False,
        )
    return _session_factory


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    """Transactional context manager for database operations."""
    factory = get_session_factory()
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency for yielding database sessions."""
    with session_scope() as session:
        yield session


def verify_database_schema(engine: Optional[Engine] = None) -> None:
    """
    Verify that authoritative database schema and required tables exist.
    Does NOT mutate schema or call create_all().
    Raises RuntimeError with clear migration instructions if schema is missing or uninitialized.
    """
    from sqlalchemy import inspect

    target_engine = engine or get_engine()
    inspector = inspect(target_engine)
    existing_tables = set(inspector.get_table_names())
    required_tables = {"decisions", "audit_events"}
    missing = required_tables - existing_tables
    if missing:
        missing_str = ", ".join(sorted(missing))
        raise RuntimeError(
            f"Database schema is uninitialized or missing required tables: {missing_str}. "
            "Authoritative schema management requires applying migrations. "
            "Please run 'alembic upgrade head' (or 'python -m alembic upgrade head' "
            "from the backend directory) before starting the application."
        )


def init_db(engine: Optional[Engine] = None) -> None:
    """
    Explicit test/utility helper to create tables defined in metadata.
    NOTE: In production and standard local workflows, schema management is authoritatively
    handled by Alembic migrations ('alembic upgrade head'). This function must NOT be called
    during normal application startup.
    """
    target_engine = engine or get_engine()
    Base.metadata.create_all(bind=target_engine)


def reset_engine() -> None:
    """Reset active engine and session factory."""
    global _engine, _session_factory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None
