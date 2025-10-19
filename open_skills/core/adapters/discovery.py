"""
Skill discovery and auto-registration from folder conventions.
"""

import re
from pathlib import Path
from typing import Optional, List
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from open_skills.core.packing import parse_skill_bundle, SkillValidationError
from open_skills.core.manager import SkillManager
from open_skills.core.router import SkillRouter
from open_skills.core.telemetry import logger, trace_operation
from open_skills.core.library import get_config
from open_skills.db.models import Skill, SkillVersion, User


async def register_skills_from_folder(
    folder_path: str | Path,
    db: Optional[AsyncSession] = None,
    owner_id: Optional[UUID] = None,
    org_id: Optional[UUID] = None,
    visibility: str = "org",
    auto_publish: bool = False,
    auto_create_skills: bool = True,
) -> List[SkillVersion]:
    """
    Discover and register all skill bundles in a folder.

    This is the primary way to auto-register skills at application startup.

    Args:
        folder_path: Path to folder containing skill bundles
        db: Database session (uses library config if None)
        owner_id: Optional owner user ID (creates default if None)
        org_id: Optional organization ID
        visibility: Default visibility ('user' or 'org')
        auto_publish: Auto-publish new versions
        auto_create_skills: Auto-create skill records if they don't exist

    Returns:
        List of created/updated SkillVersion instances

    Example:
        ```python
        # At app startup
        from open_skills.core.adapters.discovery import register_skills_from_folder

        versions = await register_skills_from_folder(
            "./skills",
            auto_publish=True,
            visibility="org"
        )
        print(f"Registered {len(versions)} skill versions")
        ```
    """
    folder = Path(folder_path)
    if not folder.exists() or not folder.is_dir():
        raise ValueError(f"Folder not found or not a directory: {folder}")

    # Get or create DB session
    if db is None:
        config = get_config()
        if not config.initialized:
            raise RuntimeError(
                "Library not configured. Call configure() first or pass db session"
            )
        async for session in config.get_db():
            return await register_skills_from_folder(
                folder,
                db=session,
                owner_id=owner_id,
                org_id=org_id,
                visibility=visibility,
                auto_publish=auto_publish,
                auto_create_skills=auto_create_skills,
            )

    with trace_operation("register_skills_from_folder", {"folder": str(folder)}):
        manager = SkillManager(db)
        router = SkillRouter(db)
        registered_versions = []

        # Ensure owner exists
        if owner_id is None:
            owner_id = await _get_or_create_system_user(db)

        # Find all skill bundles (directories with SKILL.md)
        skill_dirs = []
        for item in folder.iterdir():
            if item.is_dir() and (item / "SKILL.md").exists():
                skill_dirs.append(item)

        logger.info(
            "discovered_skill_bundles",
            folder=str(folder),
            count=len(skill_dirs),
        )

        # Register each skill bundle
        for skill_dir in skill_dirs:
            try:
                # Parse bundle
                bundle = parse_skill_bundle(skill_dir)
                skill_name = bundle.metadata["name"]
                version_string = bundle.metadata["version"]

                # Find or create skill record
                skill = await _get_or_create_skill(
                    db,
                    manager,
                    skill_name,
                    owner_id,
                    org_id,
                    visibility,
                    auto_create=auto_create_skills,
                )

                if skill is None:
                    logger.warning(
                        "skill_not_found_skipping",
                        name=skill_name,
                        auto_create=auto_create_skills,
                    )
                    continue

                # Check if version already exists
                existing_version = await manager.get_skill_version_by_number(
                    skill.id, version_string
                )

                if existing_version:
                    # Version exists - check if we should update
                    version_id = existing_version.id
                    logger.info(
                        "skill_version_exists",
                        skill_id=str(skill.id),
                        version=version_string,
                        version_id=str(version_id),
                    )
                    # Could optionally update metadata/embedding here
                    registered_versions.append(existing_version)
                else:
                    # Create new version
                    version = await manager.create_version_from_bundle(
                        skill.id,
                        skill_dir,
                    )

                    # Generate embedding
                    await router.embed_skill_version(version)

                    # Auto-publish if requested
                    if auto_publish or bundle.metadata.get("published", False):
                        version.is_published = True
                        await db.flush()

                    await db.commit()
                    await db.refresh(version)

                    registered_versions.append(version)

                    logger.info(
                        "skill_version_registered",
                        skill_id=str(skill.id),
                        skill_name=skill_name,
                        version=version_string,
                        version_id=str(version.id),
                        published=version.is_published,
                    )

            except SkillValidationError as e:
                logger.error(
                    "skill_validation_failed",
                    directory=skill_dir.name,
                    error=str(e),
                )
                continue
            except Exception as e:
                logger.exception(
                    "skill_registration_failed",
                    directory=skill_dir.name,
                    error=str(e),
                )
                continue

        logger.info(
            "skill_registration_complete",
            folder=str(folder),
            total_registered=len(registered_versions),
        )

        return registered_versions


async def _get_or_create_system_user(db: AsyncSession) -> UUID:
    """Get or create a system user for skill ownership."""
    result = await db.execute(
        select(User).where(User.email == "system@open-skills.local")
    )
    user = result.scalar_one_or_none()

    if not user:
        user = User(email="system@open-skills.local")
        db.add(user)
        await db.flush()
        await db.refresh(user)
        logger.info("system_user_created", user_id=str(user.id))

    return user.id


async def _get_or_create_skill(
    db: AsyncSession,
    manager: SkillManager,
    name: str,
    owner_id: UUID,
    org_id: Optional[UUID],
    visibility: str,
    auto_create: bool = True,
) -> Optional[Skill]:
    """Get or create a skill record by name."""
    # Try to find existing skill by name
    result = await db.execute(
        select(Skill).where(Skill.name == name)
    )
    skill = result.scalar_one_or_none()

    if skill:
        return skill

    if not auto_create:
        return None

    # Create new skill
    skill = await manager.create_skill(
        name=name,
        owner_id=owner_id,
        org_id=org_id,
        visibility=visibility,
    )

    await db.flush()
    await db.refresh(skill)

    logger.info(
        "skill_auto_created",
        skill_id=str(skill.id),
        name=name,
    )

    return skill


async def watch_skills_folder(
    folder_path: str | Path,
    callback=None,
    **register_kwargs
):
    """
    Watch a skills folder for changes and auto-register (development mode).

    Args:
        folder_path: Path to skills folder
        callback: Optional callback(versions) called after registration
        **register_kwargs: Additional arguments for register_skills_from_folder

    Example:
        ```python
        # In development mode
        import asyncio

        async def on_skills_updated(versions):
            print(f"Updated {len(versions)} skills")

        # Run in background task
        asyncio.create_task(watch_skills_folder(
            "./skills",
            callback=on_skills_updated,
            auto_publish=True
        ))
        ```

    Note:
        This requires the watchfiles package: pip install watchfiles
    """
    try:
        from watchfiles import awatch
    except ImportError:
        raise RuntimeError(
            "watchfiles package required for folder watching. "
            "Install with: pip install watchfiles"
        )

    folder = Path(folder_path)
    logger.info("watching_skills_folder", folder=str(folder))

    async for changes in awatch(folder):
        logger.info("skills_folder_changed", changes=len(changes))

        try:
            versions = await register_skills_from_folder(
                folder,
                **register_kwargs
            )

            if callback:
                await callback(versions)

        except Exception as e:
            logger.exception("watch_registration_failed", error=str(e))
