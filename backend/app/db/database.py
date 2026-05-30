"""SQLAlchemy database engine and session management."""

from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from backend.app.core.config import get_settings


class Base(DeclarativeBase):
    """Declarative base for ORM models."""


@lru_cache
def get_engine() -> Engine:
    """Return a cached SQLAlchemy engine."""
    settings = get_settings()
    connect_args: dict[str, object] = {}
    if settings.database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    return create_engine(settings.database_url, connect_args=connect_args)


@lru_cache
def get_session_factory() -> sessionmaker[Session]:
    """Return a cached session factory."""
    return sessionmaker(autocommit=False, autoflush=False, bind=get_engine())


def init_db() -> None:
    """Create database tables if they do not exist."""
    from backend.app.models.seen_publication import SeenPublication  # noqa: F401

    Base.metadata.create_all(bind=get_engine())


def get_db() -> Generator[Session, None, None]:
    """Yield a database session."""
    db = get_session_factory()()
    try:
        yield db
    finally:
        db.close()


# Backward-compatible aliases used by jobs and tests.
engine = get_engine()
SessionLocal = get_session_factory()
