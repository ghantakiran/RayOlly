"""Database connection management for RayOlly metadata store.

Provides async SQLAlchemy session factory using asyncpg as the PostgreSQL driver.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

__all__ = ["Base", "init_db", "get_session"]


class Base(DeclarativeBase):
    """Declarative base for all SQLAlchemy ORM models."""

    pass


_engine: AsyncEngine | None = None
_async_session_factory: async_sessionmaker[AsyncSession] | None = None


async def init_db(
    postgres_url: str,
    *,
    pool_size: int = 10,
    max_overflow: int = 20,
    echo: bool = False,
) -> async_sessionmaker[AsyncSession]:
    """Initialise the async engine and session factory.

    Args:
        postgres_url: PostgreSQL connection URL
            (e.g. ``postgresql+asyncpg://user:pass@host:5432/rayolly``).
        pool_size: Number of persistent connections in the pool.
        max_overflow: Extra connections allowed beyond *pool_size*.
        echo: If ``True``, log all SQL statements.

    Returns:
        The configured ``async_sessionmaker`` instance.
    """
    global _engine, _async_session_factory

    _engine = create_async_engine(
        postgres_url,
        pool_size=pool_size,
        max_overflow=max_overflow,
        echo=echo,
        pool_pre_ping=True,
        pool_recycle=3600,
    )

    _async_session_factory = async_sessionmaker(
        bind=_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    return _async_session_factory


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an async database session.

    Usage::

        @app.get("/items")
        async def list_items(session: AsyncSession = Depends(get_session)):
            ...

    Raises:
        RuntimeError: If :func:`init_db` has not been called yet.
    """
    if _async_session_factory is None:
        raise RuntimeError(
            "Database not initialised. Call init_db() before requesting sessions."
        )

    async with _async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def close_db() -> None:
    """Dispose of the engine and release all pooled connections."""
    global _engine, _async_session_factory

    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _async_session_factory = None
