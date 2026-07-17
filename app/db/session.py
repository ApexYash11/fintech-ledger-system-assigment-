"""Database session management.

Provides a session factory and helper functions for dependency injection.
Uses SQLAlchemy 2.0 style sessions.
"""

from collections.abc import Generator
from typing import Any

from sqlalchemy import create_engine, Engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings


def create_db_engine(database_url: str | None = None) -> Engine:
    """Create a configured SQLAlchemy engine.

    For SQLite, enables WAL mode and foreign keys for correctness.
    For PostgreSQL, uses standard connection pooling.
    """
    db_url = database_url or settings.database_url
    connect_args: dict[str, Any] = {}

    if db_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False

        engine = create_engine(
            db_url,
            connect_args=connect_args,
            pool_pre_ping=True,
            echo=settings.debug,
        )

        @event.listens_for(engine, "connect")
        def _set_sqlite_pragma(dbapi_connection, connection_record):
            """Enable WAL mode for better concurrent read performance,
            and enforce foreign key constraints (off by default in SQLite)."""
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.close()
    else:
        engine = create_engine(
            db_url,
            pool_pre_ping=True,
            pool_size=10,
            max_overflow=20,
            echo=settings.debug,
        )

    return engine


engine = create_db_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that provides a database session.

    Ensures the session is always closed after the request completes.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
