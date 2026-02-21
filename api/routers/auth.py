"""FORESIGHT — /auth router — JWT token issuance."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from jose import jwt
from passlib.context import CryptContext
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db
from api.models.schemas import TokenRequest, TokenResponse

log = logging.getLogger(__name__)
router = APIRouter()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def create_access_token(tenant_id: str, client_id: str) -> str:
    """
    Create a signed JWT access token for a tenant.

    Args:
        tenant_id: Tenant UUID embedded as 'sub' claim.
        client_id: Client identifier embedded as additional claim.

    Returns:
        Encoded JWT string.
    """
    secret = os.environ["JWT_SECRET_KEY"]
    algorithm = os.getenv("JWT_ALGORITHM", "HS256")
    expire_minutes = int(os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "60"))

    expire = datetime.now(tz=timezone.utc) + timedelta(minutes=expire_minutes)
    payload = {
        "sub": tenant_id,
        "client_id": client_id,
        "exp": expire,
        "iat": datetime.now(tz=timezone.utc),
        "type": "access",
    }
    return jwt.encode(payload, secret, algorithm=algorithm)


@router.post(
    "/token",
    response_model=TokenResponse,
    summary="Authenticate and receive JWT access token",
    description=(
        "Validates tenant credentials and returns a JWT token. "
        "Include the token in the Authorization header as 'Bearer <token>' for all other endpoints."
    ),
)
async def login(
    request: TokenRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """
    Authenticate a tenant and issue a JWT token.

    Args:
        request: TokenRequest with client_id and client_secret.
        db:      Database session (injected).

    Returns:
        TokenResponse with access_token and metadata.

    Raises:
        HTTPException 401: Invalid credentials.
    """
    result = await db.execute(
        text(
            "SELECT tenant_id, client_secret_hash FROM tenants WHERE client_id = :cid AND is_active = true"  # noqa: E501
        ),
        {"cid": request.client_id},
    )
    row = result.fetchone()

    if not row or not pwd_context.verify(request.client_secret, row[1]):
        log.warning("Failed auth attempt for client_id: %s", request.client_id)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid client_id or client_secret",
            headers={"WWW-Authenticate": "Bearer"},
        )

    tenant_id = str(row[0])
    token = create_access_token(tenant_id, request.client_id)
    expire_minutes = int(os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "60"))

    log.info("Token issued for tenant: %s", tenant_id)
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in=expire_minutes * 60,
        tenant_id=tenant_id,
    )
