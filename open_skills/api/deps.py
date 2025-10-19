"""
FastAPI dependencies for dependency injection.
Includes database sessions, authentication, and RBAC checks.
"""

from typing import Optional, AsyncGenerator
from uuid import UUID

from fastapi import Depends, HTTPException, status, Header
from sqlalchemy.ext.asyncio import AsyncSession

from open_skills.core.rbac import RBACManager, Permission
from open_skills.core.exceptions import PermissionDeniedError, AuthenticationError
from open_skills.db.base import get_db as get_db_session
from open_skills.db.models import User
from sqlalchemy import select


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Get database session dependency.

    Yields:
        AsyncSession: Database session
    """
    async for session in get_db_session():
        yield session


async def get_current_user(
    x_user_id: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
) -> Optional[User]:
    """
    Get current user from header (stub implementation).

    In production, this should validate JWT tokens and extract user info.

    Args:
        x_user_id: User ID from header
        db: Database session

    Returns:
        User instance or None

    Note:
        This is a stub. In production, implement proper JWT validation:
        - Extract token from Authorization header
        - Validate JWT signature
        - Extract user_id from claims
        - Load user from database
    """
    if not x_user_id:
        return None

    try:
        user_id = UUID(x_user_id)
        result = await db.execute(
            select(User).where(User.id == user_id)
        )
        return result.scalar_one_or_none()
    except (ValueError, Exception):
        return None


async def require_user(
    current_user: Optional[User] = Depends(get_current_user),
) -> User:
    """
    Require authenticated user.

    Args:
        current_user: Current user from dependency

    Returns:
        User instance

    Raises:
        HTTPException: 401 if not authenticated
    """
    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    return current_user


class RequireRole:
    """Dependency class for requiring specific roles."""

    def __init__(self, required_permission: Permission):
        """
        Initialize role requirement.

        Args:
            required_permission: Permission required
        """
        self.required_permission = required_permission

    async def __call__(
        self,
        current_user: User = Depends(require_user),
        db: AsyncSession = Depends(get_db),
    ) -> User:
        """
        Check if user has required permission.

        Args:
            current_user: Current user
            db: Database session

        Returns:
            User instance if authorized

        Raises:
            HTTPException: 403 if permission denied
        """
        rbac = RBACManager(db)

        try:
            await rbac.require_permission(
                user_id=current_user.id,
                permission=self.required_permission,
            )
            return current_user
        except PermissionDeniedError as e:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=str(e),
            )


# Convenience dependencies for common role checks
require_viewer = RequireRole(Permission.VIEW_SKILL)
require_author = RequireRole(Permission.CREATE_SKILL)
require_publisher = RequireRole(Permission.PUBLISH_VERSION)
require_admin = RequireRole(Permission.MANAGE_PERMISSIONS)


async def get_rbac(db: AsyncSession = Depends(get_db)) -> RBACManager:
    """
    Get RBAC manager dependency.

    Args:
        db: Database session

    Returns:
        RBACManager instance
    """
    return RBACManager(db)


# Optional user dependency (doesn't require authentication)
async def get_optional_user(
    x_user_id: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
) -> Optional[User]:
    """
    Get current user if available, but don't require authentication.

    Args:
        x_user_id: Optional user ID from header
        db: Database session

    Returns:
        User instance or None
    """
    return await get_current_user(x_user_id, db)


# Pagination dependencies
class Pagination:
    """Pagination parameters."""

    def __init__(
        self,
        skip: int = 0,
        limit: int = 100,
    ):
        """
        Initialize pagination.

        Args:
            skip: Number of records to skip
            limit: Maximum records to return
        """
        self.skip = max(0, skip)
        self.limit = min(max(1, limit), 100)  # Cap at 100


def get_pagination(skip: int = 0, limit: int = 100) -> Pagination:
    """
    Get pagination parameters dependency.

    Args:
        skip: Records to skip
        limit: Maximum records

    Returns:
        Pagination instance
    """
    return Pagination(skip=skip, limit=limit)
