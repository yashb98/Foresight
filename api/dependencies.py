# =============================================================================
# FORESIGHT API — Dependencies
# JWT authentication, database sessions, tenant isolation
# =============================================================================

from typing import AsyncGenerator, Optional
from uuid import UUID

from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from passlib.context import CryptContext
import asyncpg
from motor.motor_asyncio import AsyncIOMotorClient
import psycopg2
from psycopg2.extras import RealDictCursor

from common.config import settings
from common.logging_config import get_logger

logger = get_logger(__name__)

# =============================================================================
# Password Hashing
# =============================================================================

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


# =============================================================================
# JWT Authentication
# =============================================================================

security = HTTPBearer(auto_error=False)


def create_access_token(data: dict) -> str:
    """Create a JWT access token."""
    to_encode = data.copy()
    import time
    to_encode.update({"exp": int(time.time()) + settings.JWT_EXPIRATION_SECONDS})
    return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    """Decode and validate a JWT token."""
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        return payload
    except JWTError as e:
        logger.warning(f"JWT decode error: {e}")
        return None


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> dict:
    """Dependency to get current authenticated user from JWT."""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    payload = decode_token(credentials.credentials)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    user_id = payload.get("sub")
    tenant_id = payload.get("tenant_id")
    email = payload.get("email")
    role = payload.get("role")
    
    if not user_id or not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token claims",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return {
        "user_id": UUID(user_id),
        "tenant_id": UUID(tenant_id),
        "email": email,
        "role": role,
    }


async def require_admin(current_user: dict = Depends(get_current_user)) -> dict:
    """Dependency to require admin role."""
    if current_user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return current_user


# =============================================================================
# Tenant Isolation
# =============================================================================

async def verify_tenant_access(
    tenant_id: UUID,
    current_user: dict = Depends(get_current_user)
) -> dict:
    """Verify user has access to the specified tenant."""
    if current_user["tenant_id"] != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied for this tenant"
        )
    return current_user


class TenantContext:
    """Context manager for tenant isolation in database queries."""
    
    def __init__(self, tenant_id: UUID):
        self.tenant_id = tenant_id
    
    def filter_query(self, query: str, params: dict = None) -> tuple[str, dict]:
        """Add tenant filter to a query."""
        params = params or {}
        params["tenant_id"] = str(self.tenant_id)
        
        # Simple approach: add WHERE clause
        # In production, consider using row-level security (RLS) policies
        if "WHERE" in query.upper():
            query = query.replace("WHERE", "WHERE tenant_id = :tenant_id AND")
        else:
            query += " WHERE tenant_id = :tenant_id"
        
        return query, params


# =============================================================================
# Database Connections
# =============================================================================

# PostgreSQL async connection pool
_pg_pool: Optional[asyncpg.Pool] = None


async def get_postgres_pool() -> asyncpg.Pool:
    """Get or create PostgreSQL connection pool."""
    global _pg_pool
    if _pg_pool is None:
        _pg_pool = await asyncpg.create_pool(
            dsn=settings.DATABASE_URL,
            min_size=5,
            max_size=20,
            command_timeout=60,
        )
        logger.info("PostgreSQL connection pool created")
    return _pg_pool


async def close_postgres_pool():
    """Close PostgreSQL connection pool."""
    global _pg_pool
    if _pg_pool:
        await _pg_pool.close()
        _pg_pool = None
        logger.info("PostgreSQL connection pool closed")


async def get_db_connection() -> AsyncGenerator[asyncpg.Connection, None]:
    """Dependency to get a database connection."""
    pool = await get_postgres_pool()
    async with pool.acquire() as conn:
        yield conn


# MongoDB client
_mongo_client: Optional[AsyncIOMotorClient] = None


async def get_mongo_client() -> AsyncIOMotorClient:
    """Get or create MongoDB client."""
    global _mongo_client
    if _mongo_client is None:
        _mongo_client = AsyncIOMotorClient(
            settings.MONGO_URI,
            maxPoolSize=50,
            minPoolSize=10,
        )
        logger.info("MongoDB client created")
    return _mongo_client


async def get_mongo_db():
    """Get MongoDB database instance."""
    client = await get_mongo_client()
    return client[settings.MONGO_DB]


async def close_mongo_client():
    """Close MongoDB client."""
    global _mongo_client
    if _mongo_client:
        _mongo_client.close()
        _mongo_client = None
        logger.info("MongoDB client closed")


# Sync PostgreSQL connection for batch operations
def get_postgres_sync_conn():
    """Get synchronous PostgreSQL connection (for batch/background tasks)."""
    return psycopg2.connect(
        dsn=settings.DATABASE_URL_SYNC,
        cursor_factory=RealDictCursor
    )


# =============================================================================
# Request Context
# =============================================================================

async def get_tenant_from_path(
    tenant_id: UUID,
    current_user: dict = Depends(get_current_user)
) -> UUID:
    """Extract and validate tenant_id from path parameter."""
    if current_user["tenant_id"] != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied for this tenant"
        )
    return tenant_id


class PaginationParams:
    """Common pagination parameters."""
    
    def __init__(
        self,
        page: int = 1,
        page_size: int = 20,
        sort_by: Optional[str] = None,
        sort_order: str = "desc"
    ):
        self.page = max(1, page)
        self.page_size = min(max(1, page_size), 100)
        self.sort_by = sort_by
        self.sort_order = sort_order.lower() if sort_order.lower() in ["asc", "desc"] else "desc"
        self.offset = (self.page - 1) * self.page_size


def get_pagination(
    page: int = 1,
    page_size: int = 20,
    sort_by: Optional[str] = None,
    sort_order: str = "desc"
) -> PaginationParams:
    """Dependency for pagination parameters."""
    return PaginationParams(page, page_size, sort_by, sort_order)
