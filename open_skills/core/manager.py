"""
Skill Manager for CRUD operations, versioning, and storage.
"""

import shutil
from pathlib import Path
from typing import Optional, List, Dict, Any
from uuid import UUID

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from open_skills.config import settings
from open_skills.core.exceptions import (
    SkillNotFoundError,
    SkillVersionNotFoundError,
    SkillValidationError,
    StorageError,
)
from open_skills.core.packing import parse_skill_bundle, SkillBundle
from open_skills.core.telemetry import get_logger, trace_operation
from open_skills.db.models import Skill, SkillVersion, User

logger = get_logger(__name__)


class SkillManager:
    """Manages skill CRUD operations, versioning, and storage."""

    def __init__(self, db: AsyncSession, storage_root: Optional[Path] = None):
        """
        Initialize skill manager.

        Args:
            db: Database session
            storage_root: Root directory for skill storage (defaults to settings)
        """
        self.db = db
        self.storage_root = storage_root or settings.storage_root

    async def create_skill(
        self,
        name: str,
        owner_id: UUID,
        org_id: Optional[UUID] = None,
        visibility: str = "user",
    ) -> Skill:
        """
        Create a new skill.

        Args:
            name: Skill name
            owner_id: Owner user ID
            org_id: Optional organization ID
            visibility: Visibility level ('user' or 'org')

        Returns:
            Created Skill instance
        """
        with trace_operation("create_skill", {"name": name}):
            skill = Skill(
                name=name,
                owner_id=owner_id,
                org_id=org_id,
                visibility=visibility,
            )
            self.db.add(skill)
            await self.db.flush()
            await self.db.refresh(skill)

            logger.info(
                "skill_created",
                skill_id=str(skill.id),
                name=name,
                owner_id=str(owner_id),
            )

            return skill

    async def get_skill(self, skill_id: UUID) -> Skill:
        """
        Get skill by ID.

        Args:
            skill_id: Skill UUID

        Returns:
            Skill instance

        Raises:
            SkillNotFoundError: If skill not found
        """
        result = await self.db.execute(
            select(Skill).where(Skill.id == skill_id)
        )
        skill = result.scalar_one_or_none()

        if not skill:
            raise SkillNotFoundError(f"Skill not found: {skill_id}")

        return skill

    async def list_skills(
        self,
        owner_id: Optional[UUID] = None,
        org_id: Optional[UUID] = None,
        visibility: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Skill]:
        """
        List skills with optional filters.

        Args:
            owner_id: Filter by owner
            org_id: Filter by organization
            visibility: Filter by visibility
            limit: Maximum results
            offset: Pagination offset

        Returns:
            List of Skill instances
        """
        query = select(Skill)

        conditions = []
        if owner_id:
            conditions.append(Skill.owner_id == owner_id)
        if org_id:
            conditions.append(Skill.org_id == org_id)
        if visibility:
            conditions.append(Skill.visibility == visibility)

        if conditions:
            query = query.where(and_(*conditions))

        query = query.limit(limit).offset(offset).order_by(Skill.created_at.desc())

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def delete_skill(self, skill_id: UUID) -> None:
        """
        Delete a skill and all its versions.

        Args:
            skill_id: Skill UUID

        Raises:
            SkillNotFoundError: If skill not found
        """
        skill = await self.get_skill(skill_id)

        # Delete storage directory
        skill_storage = self.storage_root / str(skill_id)
        if skill_storage.exists():
            try:
                shutil.rmtree(skill_storage)
                logger.info("skill_storage_deleted", path=str(skill_storage))
            except Exception as e:
                logger.error(
                    "skill_storage_delete_failed",
                    path=str(skill_storage),
                    error=str(e),
                )

        await self.db.delete(skill)
        await self.db.flush()

        logger.info("skill_deleted", skill_id=str(skill_id))

    async def create_version_from_bundle(
        self,
        skill_id: UUID,
        bundle_path: Path,
        embedding: Optional[List[float]] = None,
    ) -> SkillVersion:
        """
        Create a new skill version from a bundle directory.

        Args:
            skill_id: Parent skill ID
            bundle_path: Path to skill bundle directory
            embedding: Optional pre-generated embedding vector

        Returns:
            Created SkillVersion instance

        Raises:
            SkillNotFoundError: If skill not found
            SkillValidationError: If bundle is invalid
            StorageError: If storage operations fail
        """
        with trace_operation("create_version_from_bundle", {"skill_id": str(skill_id)}):
            # Validate skill exists
            skill = await self.get_skill(skill_id)

            # Parse and validate bundle
            try:
                bundle = parse_skill_bundle(bundle_path)
            except Exception as e:
                raise SkillValidationError(f"Bundle validation failed: {e}")

            version = bundle.metadata["version"]
            entrypoint = bundle.metadata["entrypoint"]
            description = bundle.metadata.get("description", "")

            # Check if version already exists
            existing = await self.get_skill_version_by_number(skill_id, version)
            if existing:
                raise SkillValidationError(
                    f"Version {version} already exists for skill {skill_id}"
                )

            # Copy bundle to storage
            target_path = self.storage_root / str(skill_id) / version
            try:
                target_path.mkdir(parents=True, exist_ok=True)
                shutil.copytree(
                    bundle_path,
                    target_path,
                    dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns(".*", "__pycache__", "*.pyc"),
                )
                logger.info(
                    "bundle_copied_to_storage",
                    source=str(bundle_path),
                    target=str(target_path),
                )
            except Exception as e:
                raise StorageError(f"Failed to copy bundle to storage: {e}")

            # Create version record
            skill_version = SkillVersion(
                skill_id=skill_id,
                version=version,
                entrypoint=entrypoint,
                description=description,
                metadata_yaml=bundle.metadata,
                embedding=embedding,
                bundle_path=str(target_path),
                is_published=False,
            )

            self.db.add(skill_version)
            await self.db.flush()
            await self.db.refresh(skill_version)

            logger.info(
                "skill_version_created",
                version_id=str(skill_version.id),
                skill_id=str(skill_id),
                version=version,
            )

            return skill_version

    async def get_skill_version(self, version_id: UUID) -> SkillVersion:
        """
        Get skill version by ID.

        Args:
            version_id: Version UUID

        Returns:
            SkillVersion instance

        Raises:
            SkillVersionNotFoundError: If version not found
        """
        result = await self.db.execute(
            select(SkillVersion).where(SkillVersion.id == version_id)
        )
        version = result.scalar_one_or_none()

        if not version:
            raise SkillVersionNotFoundError(f"Skill version not found: {version_id}")

        return version

    async def get_skill_version_by_number(
        self,
        skill_id: UUID,
        version: str,
    ) -> Optional[SkillVersion]:
        """
        Get skill version by skill ID and version number.

        Args:
            skill_id: Skill UUID
            version: Version string (e.g., "1.0.0")

        Returns:
            SkillVersion instance or None
        """
        result = await self.db.execute(
            select(SkillVersion).where(
                and_(
                    SkillVersion.skill_id == skill_id,
                    SkillVersion.version == version,
                )
            )
        )
        return result.scalar_one_or_none()

    async def list_skill_versions(
        self,
        skill_id: UUID,
        published_only: bool = False,
    ) -> List[SkillVersion]:
        """
        List all versions for a skill.

        Args:
            skill_id: Skill UUID
            published_only: Only return published versions

        Returns:
            List of SkillVersion instances
        """
        query = select(SkillVersion).where(SkillVersion.skill_id == skill_id)

        if published_only:
            query = query.where(SkillVersion.is_published == True)  # noqa: E712

        query = query.order_by(SkillVersion.created_at.desc())

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def publish_version(self, version_id: UUID) -> SkillVersion:
        """
        Publish a skill version.

        Args:
            version_id: Version UUID

        Returns:
            Updated SkillVersion instance

        Raises:
            SkillVersionNotFoundError: If version not found
        """
        version = await self.get_skill_version(version_id)
        version.is_published = True
        await self.db.flush()
        await self.db.refresh(version)

        logger.info(
            "skill_version_published",
            version_id=str(version_id),
            skill_id=str(version.skill_id),
            version=version.version,
        )

        return version

    async def unpublish_version(self, version_id: UUID) -> SkillVersion:
        """
        Unpublish a skill version.

        Args:
            version_id: Version UUID

        Returns:
            Updated SkillVersion instance

        Raises:
            SkillVersionNotFoundError: If version not found
        """
        version = await self.get_skill_version(version_id)
        version.is_published = False
        await self.db.flush()
        await self.db.refresh(version)

        logger.info(
            "skill_version_unpublished",
            version_id=str(version_id),
            skill_id=str(version.skill_id),
            version=version.version,
        )

        return version

    async def update_version_embedding(
        self,
        version_id: UUID,
        embedding: List[float],
    ) -> SkillVersion:
        """
        Update the embedding vector for a skill version.

        Args:
            version_id: Version UUID
            embedding: Embedding vector

        Returns:
            Updated SkillVersion instance

        Raises:
            SkillVersionNotFoundError: If version not found
        """
        version = await self.get_skill_version(version_id)
        version.embedding = embedding
        await self.db.flush()
        await self.db.refresh(version)

        logger.info(
            "skill_version_embedding_updated",
            version_id=str(version_id),
            embedding_dim=len(embedding),
        )

        return version

    def get_bundle_path(self, version: SkillVersion) -> Path:
        """
        Get the filesystem path for a skill version's bundle.

        Args:
            version: SkillVersion instance

        Returns:
            Path to bundle directory

        Raises:
            StorageError: If bundle path doesn't exist
        """
        if version.bundle_path:
            path = Path(version.bundle_path)
        else:
            path = self.storage_root / str(version.skill_id) / version.version

        if not path.exists():
            raise StorageError(f"Bundle path does not exist: {path}")

        return path
