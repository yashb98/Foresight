"""
FORESIGHT — FastAPI Dependencies

Provides reusable FastAPI dependency functions for:
  - Database session management (async SQLAlchemy)
  - JWT token validation and tenant extraction
  - Tenant isolation enforcement

Every endpoint that accesses tenant data MUST use get_current_tenant()
as a dependency to ensure cross-tenant access is impossible.
"""

from __future__ import annotations

import logging
import os
from typing import AsyncGenerator, Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

log = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Database
# ─────────────────────────────────────────────────────────────────────────────

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


class _EmptyResult:
    """Mock DB result that always returns no rows."""

    def fetchone(self):
        return None

    def fetchall(self):
        return []

    def scalars(self):
        return self

    def all(self):
        return []

    def first(self):
        return None

    def __iter__(self):
        return iter([])


class _NoOpSession:
    """
    Dummy session returned when the database is not configured (dev/demo mode).
    execute() returns an empty result so router code sees 'no rows found'
    instead of crashing with an unhandled RuntimeError.
    """

    async def execute(self, *args, **kwargs):  # noqa: ANN001
        log.debug("No-op DB execute (no DATABASE_URL configured)")
        return _EmptyResult()

    async def commit(self) -> None:
        pass

    async def rollback(self) -> None:
        pass

    async def close(self) -> None:
        pass

    def __aiter__(self):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency that yields an async database session.
    Falls back to a no-op session if DATABASE_URL is not set or the DB is unreachable
    (dev/demo mode — allows the API to run without Docker/PostgreSQL).

    Usage:
        @router.get("/example")
        async def example(db: AsyncSession = Depends(get_db)):
            ...
    """
    factory = get_session_factory()
    if factory is None:
        # No database configured — yield a no-op session (demo mode)
        yield _NoOpSession()  # type: ignore[misc]
        return

    try:
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
    except Exception as conn_exc:
        # DB is configured but unreachable (e.g. running outside Docker)
        log.debug("DB connection failed, using no-op session: %s", conn_exc)
        yield _NoOpSession()  # type: ignore[misc]


# ─────────────────────────────────────────────────────────────────────────────
# JWT Authentication
# ─────────────────────────────────────────────────────────────────────────────

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dev-secret-change-me-in-production-32ch")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")

CREDENTIALS_EXCEPTION = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Invalid or expired authentication credentials",
    headers={"WWW-Authenticate": "Bearer"},
)

FORBIDDEN_EXCEPTION = HTTPException(
    status_code=status.HTTP_403_FORBIDDEN,
    detail="Access denied: insufficient permissions for this tenant",
)


class TenantContext:
    """
    Holds the authenticated tenant context extracted from a JWT token.

    Injected into every route via Depends(get_current_tenant).
    All data access must be filtered by tenant_id.
    """

    def __init__(self, tenant_id: str, client_id: str) -> None:
        self.tenant_id = tenant_id
        self.client_id = client_id


async def get_current_tenant(
    token: str = Depends(oauth2_scheme),
) -> TenantContext:
    """
    FastAPI dependency that validates a JWT and returns the TenantContext.

    Raises:
        HTTPException 401: If the token is missing, invalid, or expired.

    Usage:
        @router.get("/assets/{tenant_id}")
        async def get_assets(
            tenant_id: str,
            current_tenant: TenantContext = Depends(get_current_tenant),
        ):
            if tenant_id != current_tenant.tenant_id:
                raise HTTPException(403)
    """
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        tenant_id: Optional[str] = payload.get("sub")
        client_id: Optional[str] = payload.get("client_id")

        if not tenant_id or not client_id:
            raise CREDENTIALS_EXCEPTION

        return TenantContext(tenant_id=tenant_id, client_id=client_id)

    except JWTError as exc:
        log.warning("JWT validation failed: %s", exc)
        raise CREDENTIALS_EXCEPTION


def verify_tenant_access(
    path_tenant_id: str,
    current_tenant: TenantContext,
) -> None:
    """
    Verify that the authenticated tenant matches the requested tenant_id path parameter.
    Call this at the start of every data endpoint.

    Args:
        path_tenant_id:  The tenant_id from the URL path.
        current_tenant:  The authenticated TenantContext.

    Raises:
        HTTPException 403: If the token's tenant_id doesn't match the path.
    """
    if path_tenant_id != current_tenant.tenant_id:
        log.warning(
            "TENANT ISOLATION BREACH ATTEMPT: token tenant=%s, requested tenant=%s",
            current_tenant.tenant_id,
            path_tenant_id,
        )
        raise FORBIDDEN_EXCEPTION
