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
    """Lazily initialise the async SQLAlchemy engine."""
    global _engine
    if _engine is None:
        db_url = os.environ["DATABASE_URL"]
        _engine = create_async_engine(
            db_url,
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,
            echo=False,
        )
    return _engine


def get_session_factory():
    """Lazily initialise the async session factory."""
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=get_engine(),
            expire_on_commit=False,
            autoflush=False,
        )
    return _session_factory


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency that yields an async database session.
    Session is automatically closed after the request completes.

    Usage:
        @router.get("/example")
        async def example(db: AsyncSession = Depends(get_db)):
            ...
    """
    async with get_session_factory()() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ─────────────────────────────────────────────────────────────────────────────
# JWT Authentication
# ─────────────────────────────────────────────────────────────────────────────

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "")
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
    if not JWT_SECRET_KEY:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="JWT_SECRET_KEY is not configured",
        )
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
