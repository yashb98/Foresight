# =============================================================================
# FORESIGHT API — Auth Router
# Authentication and user management endpoints
# =============================================================================

from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials

from api.dependencies import (
    get_current_user, require_admin, get_db_connection, 
    verify_password, get_password_hash, create_access_token, security
)
from api.models.schemas import (
    Token, UserLogin, UserCreate, UserResponse, 
    UserUpdate, TenantCreate, TenantResponse
)
from common.logging_config import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/auth", tags=["Authentication"])


# =============================================================================
# Authentication Endpoints
# =============================================================================

@router.post("/token", response_model=Token)
async def login(user_credentials: UserLogin):
    """
    Authenticate user and return JWT access token.
    
    - **email**: User's email address
    - **password**: User's password
    """
    import asyncpg
    
    # Get database connection
    from common.config import settings
    conn = await asyncpg.connect(dsn=settings.DATABASE_URL)
    
    try:
        # Find user by email
        user = await conn.fetchrow(
            "SELECT id, tenant_id, email, hashed_password, full_name, role, is_active FROM users WHERE email = $1",
            user_credentials.email
        )
        
        if not user:
            logger.warning(f"Login attempt for non-existent user: {user_credentials.email}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        if not user["is_active"]:
            logger.warning(f"Login attempt for inactive user: {user_credentials.email}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User account is disabled",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # Verify password
        if not verify_password(user_credentials.password, user["hashed_password"]):
            logger.warning(f"Failed login attempt for user: {user_credentials.email}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # Update last login
        await conn.execute(
            "UPDATE users SET last_login = NOW() WHERE id = $1",
            user["id"]
        )
        
        # Create JWT token
        access_token = create_access_token({
            "sub": str(user["id"]),
            "tenant_id": str(user["tenant_id"]),
            "email": user["email"],
            "role": user["role"]
        })
        
        logger.info(f"User {user_credentials.email} logged in successfully")
        
        return Token(
            access_token=access_token,
            token_type="bearer",
            tenant_id=user["tenant_id"],
            user_role=user["role"]
        )
    
    finally:
        await conn.close()


@router.post("/refresh", response_model=Token)
async def refresh_token(current_user: dict = Depends(get_current_user)):
    """Refresh access token before it expires."""
    access_token = create_access_token({
        "sub": str(current_user["user_id"]),
        "tenant_id": str(current_user["tenant_id"]),
        "email": current_user["email"],
        "role": current_user["role"]
    })
    
    return Token(
        access_token=access_token,
        token_type="bearer",
        tenant_id=current_user["tenant_id"],
        user_role=current_user["role"]
    )


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user: dict = Depends(get_current_user)):
    """Get current authenticated user's information."""
    import asyncpg
    from common.config import settings
    
    conn = await asyncpg.connect(dsn=settings.DATABASE_URL)
    try:
        user = await conn.fetchrow(
            """
            SELECT id, tenant_id, email, full_name, role, is_active, last_login, created_at, updated_at
            FROM users WHERE id = $1
            """,
            current_user["user_id"]
        )
        
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        return UserResponse(**dict(user))
    finally:
        await conn.close()


# =============================================================================
# User Management (Admin only)
# =============================================================================

@router.post("/tenants/{tenant_id}/users", response_model=UserResponse, status_code=201)
async def create_user(
    tenant_id: UUID,
    user_data: UserCreate,
    admin_user: dict = Depends(require_admin)
):
    """Create a new user in the tenant (admin only)."""
    import asyncpg
    from common.config import settings
    
    # Verify admin belongs to same tenant
    if admin_user["tenant_id"] != tenant_id:
        raise HTTPException(status_code=403, detail="Access denied for this tenant")
    
    conn = await asyncpg.connect(dsn=settings.DATABASE_URL)
    try:
        # Check if email already exists
        existing = await conn.fetchrow(
            "SELECT id FROM users WHERE tenant_id = $1 AND email = $2",
            tenant_id, user_data.email
        )
        if existing:
            raise HTTPException(status_code=409, detail="User with this email already exists")
        
        # Create user
        user_id = await conn.fetchval(
            """
            INSERT INTO users (tenant_id, email, hashed_password, full_name, role)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING id
            """,
            tenant_id,
            user_data.email,
            get_password_hash(user_data.password),
            user_data.full_name,
            user_data.role.value
        )
        
        # Fetch created user
        user = await conn.fetchrow(
            """
            SELECT id, tenant_id, email, full_name, role, is_active, last_login, created_at, updated_at
            FROM users WHERE id = $1
            """,
            user_id
        )
        
        logger.info(f"User {user_data.email} created by admin {admin_user['email']}")
        return UserResponse(**dict(user))
    
    finally:
        await conn.close()


@router.get("/tenants/{tenant_id}/users", response_model=list[UserResponse])
async def list_users(
    tenant_id: UUID,
    current_user: dict = Depends(get_current_user),
    skip: int = 0,
    limit: int = 100
):
    """List all users in the tenant."""
    import asyncpg
    from common.config import settings
    
    if current_user["tenant_id"] != tenant_id:
        raise HTTPException(status_code=403, detail="Access denied for this tenant")
    
    conn = await asyncpg.connect(dsn=settings.DATABASE_URL)
    try:
        users = await conn.fetch(
            """
            SELECT id, tenant_id, email, full_name, role, is_active, last_login, created_at, updated_at
            FROM users WHERE tenant_id = $1
            ORDER BY created_at DESC
            LIMIT $2 OFFSET $3
            """,
            tenant_id, limit, skip
        )
        
        return [UserResponse(**dict(u)) for u in users]
    finally:
        await conn.close()


@router.patch("/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: UUID,
    user_data: UserUpdate,
    current_user: dict = Depends(get_current_user)
):
    """Update user information."""
    import asyncpg
    from common.config import settings
    
    conn = await asyncpg.connect(dsn=settings.DATABASE_URL)
    try:
        # Verify user exists and belongs to same tenant
        user = await conn.fetchrow(
            "SELECT id, tenant_id FROM users WHERE id = $1",
            user_id
        )
        
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        if user["tenant_id"] != current_user["tenant_id"]:
            raise HTTPException(status_code=403, detail="Access denied")
        
        # Only admins can update other users
        if user_id != current_user["user_id"] and current_user["role"] != "admin":
            raise HTTPException(status_code=403, detail="Can only update your own profile")
        
        # Build update query
        updates = []
        params = []
        param_idx = 1
        
        if user_data.full_name is not None:
            updates.append(f"full_name = ${param_idx}")
            params.append(user_data.full_name)
            param_idx += 1
        
        if user_data.role is not None and current_user["role"] == "admin":
            updates.append(f"role = ${param_idx}")
            params.append(user_data.role.value)
            param_idx += 1
        
        if user_data.is_active is not None and current_user["role"] == "admin":
            updates.append(f"is_active = ${param_idx}")
            params.append(user_data.is_active)
            param_idx += 1
        
        if not updates:
            raise HTTPException(status_code=400, detail="No fields to update")
        
        updates.append("updated_at = NOW()")
        params.append(user_id)
        
        await conn.execute(
            f"UPDATE users SET {', '.join(updates)} WHERE id = ${param_idx}",
            *params
        )
        
        # Fetch updated user
        updated = await conn.fetchrow(
            """
            SELECT id, tenant_id, email, full_name, role, is_active, last_login, created_at, updated_at
            FROM users WHERE id = $1
            """,
            user_id
        )
        
        return UserResponse(**dict(updated))
    
    finally:
        await conn.close()


@router.delete("/users/{user_id}", status_code=204)
async def delete_user(
    user_id: UUID,
    admin_user: dict = Depends(require_admin)
):
    """Delete a user (admin only)."""
    import asyncpg
    from common.config import settings
    
    conn = await asyncpg.connect(dsn=settings.DATABASE_URL)
    try:
        # Prevent self-deletion
        if user_id == admin_user["user_id"]:
            raise HTTPException(status_code=400, detail="Cannot delete yourself")
        
        # Verify user exists in same tenant
        user = await conn.fetchrow(
            "SELECT id, tenant_id, email FROM users WHERE id = $1",
            user_id
        )
        
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        if user["tenant_id"] != admin_user["tenant_id"]:
            raise HTTPException(status_code=403, detail="Access denied for this tenant")
        
        await conn.execute("DELETE FROM users WHERE id = $1", user_id)
        
        logger.info(f"User {user['email']} deleted by admin {admin_user['email']}")
    
    finally:
        await conn.close()


# =============================================================================
# Tenant Management (Admin only)
# =============================================================================

@router.post("/tenants", response_model=TenantResponse, status_code=201)
async def create_tenant(tenant_data: TenantCreate, admin_user: dict = Depends(require_admin)):
    """Create a new tenant (super admin only - for now any admin can create)."""
    import asyncpg
    from common.config import settings
    
    conn = await asyncpg.connect(dsn=settings.DATABASE_URL)
    try:
        # Check if slug exists
        existing = await conn.fetchrow(
            "SELECT id FROM tenants WHERE slug = $1",
            tenant_data.slug
        )
        if existing:
            raise HTTPException(status_code=409, detail="Tenant with this slug already exists")
        
        tenant_id = await conn.fetchval(
            """
            INSERT INTO tenants (name, slug, description, contact_email, settings)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING id
            """,
            tenant_data.name,
            tenant_data.slug,
            tenant_data.description,
            tenant_data.contact_email,
            tenant_data.settings or {}
        )
        
        tenant = await conn.fetchrow(
            "SELECT * FROM tenants WHERE id = $1",
            tenant_id
        )
        
        logger.info(f"Tenant {tenant_data.name} created by {admin_user['email']}")
        return TenantResponse(**dict(tenant))
    
    finally:
        await conn.close()


@router.get("/tenants/{tenant_id}", response_model=TenantResponse)
async def get_tenant(
    tenant_id: UUID,
    current_user: dict = Depends(get_current_user)
):
    """Get tenant information."""
    import asyncpg
    from common.config import settings
    
    if current_user["tenant_id"] != tenant_id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    conn = await asyncpg.connect(dsn=settings.DATABASE_URL)
    try:
        tenant = await conn.fetchrow(
            "SELECT * FROM tenants WHERE id = $1",
            tenant_id
        )
        
        if not tenant:
            raise HTTPException(status_code=404, detail="Tenant not found")
        
        return TenantResponse(**dict(tenant))
    finally:
        await conn.close()
