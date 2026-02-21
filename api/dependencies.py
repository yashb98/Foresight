"""
FORESIGHT — FastAPI Dependencies

Provides reusable FastAPI dependency functions for:
  - Database session management (async SQLAlchemy)

Every endpoint that accesses tenant data should use get_db()
as a dependency.
"""

from __future__ import annotations

import logging
import os
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

log = logging.getLogger(__name__)

# -----------------------------------------------------------------------------
# Database
# -----------------------------------------------------------------------------

_engine = None
_session_factory = None


def get_engine():
    """Lazily initialise the async SQLAlchemy engine. Returns None if DATABASE_URL not set."""
    global _engine
    if _engine is None:
        db_url = os.environ.get("DATABASE_URL")
        if not db_url:
            return None
        _engine = create_async_engine(
            db_url,
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,
            echo=False,
        )
    return _engine


def get_session_factory():
    """Lazily initialise the async session factory. Returns None if no engine."""
    global _session_factory
    if _session_factory is None:
        engine = get_engine()
        if engine is None:
            return None
        _session_factory = async_sessionmaker(
            bind=engine,
            expire_on_commit=False,
            autoflush=False,
        )
    return _session_factory


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency that yields an async database session.

    Usage:
        @router.get("/example")
        async def example(db: AsyncSession = Depends(get_db)):
            ...
    """
    factory = get_session_factory()
    if factory is None:
        raise RuntimeError("Database not configured. Set DATABASE_URL environment variable.")

    async with factory() as session:
        try:
            yield session
        except Exception:
            try:
                await session.rollback()
            except Exception:
                pass
            raise
        finally:
            try:
                await session.close()
            except Exception:
                pass
