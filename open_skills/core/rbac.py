"""
Role-Based Access Control (RBAC) system for skills.
"""

from enum import Enum
from typing import Optional
from uuid import UUID

from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from open_skills.core.exceptions import PermissionDeniedError
from open_skills.core.telemetry import get_logger
from open_skills.db.models import Skill, SkillPermission, User

logger = get_logger(__name__)


class Role(str, Enum):
    """Skill permission roles."""

    VIEWER = "viewer"
    AUTHOR = "author"
    PUBLISHER = "publisher"
    ADMIN = "admin"


# Role hierarchy (higher roles include permissions of lower roles)
ROLE_HIERARCHY = {
    Role.VIEWER: [],
    Role.AUTHOR: [Role.VIEWER],
    Role.PUBLISHER: [Role.VIEWER, Role.AUTHOR],
    Role.ADMIN: [Role.VIEWER, Role.AUTHOR, Role.PUBLISHER],
}


class Permission(str, Enum):
    """Specific permissions."""

    # Skill operations
    VIEW_SKILL = "view_skill"
    CREATE_SKILL = "create_skill"
    UPDATE_SKILL = "update_skill"
    DELETE_SKILL = "delete_skill"

    # Version operations
    VIEW_VERSION = "view_version"
    CREATE_VERSION = "create_version"
    PUBLISH_VERSION = "publish_version"
    UNPUBLISH_VERSION = "unpublish_version"

    # Run operations
    RUN_SKILL = "run_skill"
    VIEW_RUNS = "view_runs"

    # Permission management
    MANAGE_PERMISSIONS = "manage_permissions"


# Mapping of roles to permissions
ROLE_PERMISSIONS = {
    Role.VIEWER: [
        Permission.VIEW_SKILL,
        Permission.VIEW_VERSION,
        Permission.RUN_SKILL,
        Permission.VIEW_RUNS,
    ],
    Role.AUTHOR: [
        Permission.VIEW_SKILL,
        Permission.VIEW_VERSION,
        Permission.CREATE_SKILL,
        Permission.UPDATE_SKILL,
        Permission.CREATE_VERSION,
        Permission.RUN_SKILL,
        Permission.VIEW_RUNS,
    ],
    Role.PUBLISHER: [
        Permission.VIEW_SKILL,
        Permission.VIEW_VERSION,
        Permission.CREATE_SKILL,
        Permission.UPDATE_SKILL,
        Permission.CREATE_VERSION,
        Permission.PUBLISH_VERSION,
        Permission.UNPUBLISH_VERSION,
        Permission.RUN_SKILL,
        Permission.VIEW_RUNS,
    ],
    Role.ADMIN: [
        Permission.VIEW_SKILL,
        Permission.VIEW_VERSION,
        Permission.CREATE_SKILL,
        Permission.UPDATE_SKILL,
        Permission.DELETE_SKILL,
        Permission.CREATE_VERSION,
        Permission.PUBLISH_VERSION,
        Permission.UNPUBLISH_VERSION,
        Permission.RUN_SKILL,
        Permission.VIEW_RUNS,
        Permission.MANAGE_PERMISSIONS,
    ],
}


class RBACManager:
    """Manages role-based access control."""

    def __init__(self, db: AsyncSession):
        """
        Initialize RBAC manager.

        Args:
            db: Database session
        """
        self.db = db

    async def get_user_role(
        self,
        user_id: UUID,
        skill_id: Optional[UUID] = None,
        org_id: Optional[UUID] = None,
    ) -> Optional[Role]:
        """
        Get user's role for a skill, org, or globally.

        Args:
            user_id: User UUID
            skill_id: Optional skill ID (specific skill permission)
            org_id: Optional org ID (org-level permission)

        Returns:
            Highest role the user has, or None
        """
        query = select(SkillPermission).where(
            SkillPermission.user_id == user_id
        )

        # Priority: skill-specific > org-level
        conditions = []
        if skill_id:
            conditions.append(SkillPermission.skill_id == skill_id)
        if org_id:
            conditions.append(SkillPermission.org_id == org_id)

        if conditions:
            query = query.where(or_(*conditions))

        result = await self.db.execute(query)
        permissions = list(result.scalars().all())

        if not permissions:
            return None

        # Return highest role in hierarchy
        roles = [Role(p.role) for p in permissions]
        for role in [Role.ADMIN, Role.PUBLISHER, Role.AUTHOR, Role.VIEWER]:
            if role in roles:
                return role

        return None

    async def has_permission(
        self,
        user_id: UUID,
        permission: Permission,
        skill_id: Optional[UUID] = None,
        org_id: Optional[UUID] = None,
    ) -> bool:
        """
        Check if user has a specific permission.

        Args:
            user_id: User UUID
            permission: Permission to check
            skill_id: Optional skill ID
            org_id: Optional org ID

        Returns:
            True if user has permission, False otherwise
        """
        role = await self.get_user_role(user_id, skill_id, org_id)
        if not role:
            return False

        # Check if role grants this permission
        allowed_permissions = ROLE_PERMISSIONS.get(role, [])
        return permission in allowed_permissions

    async def require_permission(
        self,
        user_id: UUID,
        permission: Permission,
        skill_id: Optional[UUID] = None,
        org_id: Optional[UUID] = None,
    ) -> None:
        """
        Require that user has a specific permission.

        Args:
            user_id: User UUID
            permission: Required permission
            skill_id: Optional skill ID
            org_id: Optional org ID

        Raises:
            PermissionDeniedError: If user lacks permission
        """
        has_perm = await self.has_permission(user_id, permission, skill_id, org_id)
        if not has_perm:
            raise PermissionDeniedError(
                f"User {user_id} lacks permission: {permission.value}"
            )

    async def grant_permission(
        self,
        user_id: UUID,
        role: Role,
        skill_id: Optional[UUID] = None,
        org_id: Optional[UUID] = None,
    ) -> SkillPermission:
        """
        Grant a role to a user.

        Args:
            user_id: User UUID
            role: Role to grant
            skill_id: Optional skill ID
            org_id: Optional org ID

        Returns:
            Created SkillPermission instance
        """
        permission = SkillPermission(
            user_id=user_id,
            org_id=org_id,
            skill_id=skill_id,
            role=role.value,
        )

        self.db.add(permission)
        await self.db.flush()
        await self.db.refresh(permission)

        logger.info(
            "permission_granted",
            user_id=str(user_id),
            role=role.value,
            skill_id=str(skill_id) if skill_id else None,
            org_id=str(org_id) if org_id else None,
        )

        return permission

    async def revoke_permission(
        self,
        permission_id: UUID,
    ) -> None:
        """
        Revoke a permission.

        Args:
            permission_id: Permission UUID
        """
        result = await self.db.execute(
            select(SkillPermission).where(SkillPermission.id == permission_id)
        )
        permission = result.scalar_one_or_none()

        if permission:
            await self.db.delete(permission)
            await self.db.flush()

            logger.info(
                "permission_revoked",
                permission_id=str(permission_id),
            )

    async def can_view_skill(
        self,
        user_id: UUID,
        skill: Skill,
    ) -> bool:
        """
        Check if user can view a skill based on visibility and permissions.

        Args:
            user_id: User UUID
            skill: Skill instance

        Returns:
            True if user can view, False otherwise
        """
        # Owner can always view
        if skill.owner_id == user_id:
            return True

        # Check visibility
        if skill.visibility == "user":
            # Only owner can view user-level skills
            return False

        if skill.visibility == "org":
            # Check if user is in the same org and has at least viewer role
            if skill.org_id:
                role = await self.get_user_role(user_id, org_id=skill.org_id)
                return role is not None

        return False

    async def can_modify_skill(
        self,
        user_id: UUID,
        skill: Skill,
    ) -> bool:
        """
        Check if user can modify a skill.

        Args:
            user_id: User UUID
            skill: Skill instance

        Returns:
            True if user can modify, False otherwise
        """
        # Owner can always modify
        if skill.owner_id == user_id:
            return True

        # Check for admin or author role
        role = await self.get_user_role(
            user_id,
            skill_id=skill.id,
            org_id=skill.org_id,
        )

        return role in [Role.ADMIN, Role.AUTHOR, Role.PUBLISHER]
