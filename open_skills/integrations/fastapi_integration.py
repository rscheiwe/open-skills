"""
FastAPI integration helper for library mode.
Makes it easy to embed open-skills in any FastAPI application.
"""

from pathlib import Path
from typing import Optional
from uuid import UUID

from fastapi import FastAPI, APIRouter

from open_skills.core.telemetry import logger
from open_skills.core.library import configure, get_config
from open_skills.core.adapters.discovery import register_skills_from_folder
from open_skills.core.adapters.agent_tool_api import manifest_json


async def mount_open_skills(
    app: FastAPI,
    prefix: str = "/skills",
    skills_dir: Optional[str | Path] = None,
    auto_register: bool = True,
    auto_publish: bool = False,
    database_url: Optional[str] = None,
    **configure_kwargs
) -> None:
    """
    Mount open-skills into a FastAPI application (library mode).

    This is the primary integration point for embedding open-skills in your app.
    It does three things:
    1. Configures open-skills (if not already configured)
    2. Optionally auto-registers skills from a folder
    3. Mounts the API routes and .well-known/skills.json endpoint

    Args:
        app: FastAPI application instance
        prefix: URL prefix for skill routes (default: "/skills")
        skills_dir: Path to skills folder for auto-registration
        auto_register: Auto-register skills from skills_dir at startup
        auto_publish: Auto-publish registered skills
        database_url: Database URL (if not configured via configure())
        **configure_kwargs: Additional configuration options

    Example:
        ```python
        from fastapi import FastAPI
        from open_skills.integrations.fastapi_integration import mount_open_skills

        app = FastAPI()

        # Mount open-skills with auto-registration
        await mount_open_skills(
            app,
            prefix="/skills",
            skills_dir="./skills",
            database_url="postgresql+asyncpg://localhost/mydb",
            auto_publish=True
        )
        ```

    Minimal Example:
        ```python
        app = FastAPI()

        # Just mount the API (manual skill registration)
        await mount_open_skills(
            app,
            auto_register=False
        )
        ```
    """
    logger.info(
        "mounting_open_skills",
        prefix=prefix,
        skills_dir=str(skills_dir) if skills_dir else None,
        auto_register=auto_register,
    )

    # Configure library if needed
    config = get_config()
    if not config.initialized:
        if database_url:
            configure(database_url=database_url, **configure_kwargs)
        else:
            logger.warning(
                "open_skills_not_configured",
                message="Configure via configure() or pass database_url",
            )

    # Auto-register skills from folder
    if auto_register and skills_dir:
        skills_path = Path(skills_dir)
        if skills_path.exists():
            logger.info("auto_registering_skills", path=str(skills_path))

            versions = await register_skills_from_folder(
                skills_path,
                auto_publish=auto_publish,
                visibility="org",
            )

            logger.info(
                "skills_auto_registered",
                count=len(versions),
                path=str(skills_path),
            )
        else:
            logger.warning(
                "skills_dir_not_found",
                path=str(skills_path),
            )

    # Create router for skills endpoints
    router = APIRouter(prefix=prefix)

    # Import service router
    from open_skills.service.api.router import router as service_router

    # Include the full service API
    router.include_router(service_router)

    # Mount router to app
    app.include_router(router)

    # Add .well-known/skills.json endpoint at root level
    @app.get("/.well-known/skills.json")
    async def skills_manifest():
        """Tool manifest for agent discovery."""
        return await manifest_json(published_only=True)

    logger.info(
        "open_skills_mounted",
        prefix=prefix,
        manifest_endpoint="/.well-known/skills.json",
    )


async def mount_tools_only(
    app: FastAPI,
    skills_dir: Optional[str | Path] = None,
    auto_register: bool = True,
    auto_publish: bool = False,
    database_url: Optional[str] = None,
    **configure_kwargs
) -> None:
    """
    Mount only the tool manifest endpoint (no full API).

    Use this if you only want skill discovery/execution in your app
    without exposing the full management API.

    Args:
        app: FastAPI application instance
        skills_dir: Path to skills folder for auto-registration
        auto_register: Auto-register skills from skills_dir
        auto_publish: Auto-publish registered skills
        database_url: Database URL
        **configure_kwargs: Additional configuration options

    Example:
        ```python
        from fastapi import FastAPI
        from open_skills.integrations.fastapi_integration import mount_tools_only

        app = FastAPI()

        # Just expose tool manifest (minimal footprint)
        await mount_tools_only(
            app,
            skills_dir="./skills",
            database_url="postgresql+asyncpg://localhost/mydb",
        )
        ```
    """
    logger.info("mounting_tools_only", skills_dir=str(skills_dir) if skills_dir else None)

    # Configure library if needed
    config = get_config()
    if not config.initialized:
        if database_url:
            configure(database_url=database_url, **configure_kwargs)

    # Auto-register skills
    if auto_register and skills_dir:
        skills_path = Path(skills_dir)
        if skills_path.exists():
            await register_skills_from_folder(
                skills_path,
                auto_publish=auto_publish,
            )

    # Add .well-known/skills.json endpoint
    @app.get("/.well-known/skills.json")
    async def skills_manifest():
        """Tool manifest for agent discovery."""
        return await manifest_json(published_only=True)

    logger.info("tools_manifest_mounted", endpoint="/.well-known/skills.json")


def create_skill_execution_endpoint(
    router: APIRouter,
    skill_name: str,
    skill_version_id: UUID,
):
    """
    Create a custom endpoint for a specific skill.

    Useful for creating dedicated endpoints for frequently-used skills.

    Args:
        router: FastAPI router to add endpoint to
        skill_name: Name for the endpoint
        skill_version_id: Skill version to execute

    Example:
        ```python
        from fastapi import APIRouter
        from uuid import UUID

        router = APIRouter()

        create_skill_execution_endpoint(
            router,
            skill_name="summarize",
            skill_version_id=UUID("..."),
        )

        # Now available as POST /summarize
        ```
    """
    from fastapi import Depends
    from pydantic import BaseModel
    from open_skills.service.api.deps import get_db
    from open_skills.core.executor import SkillExecutor
    from open_skills.core.manager import SkillManager

    class ExecuteRequest(BaseModel):
        input: dict

    @router.post(f"/{skill_name}")
    async def execute_skill(
        req: ExecuteRequest,
        db=Depends(get_db),
    ):
        """Execute the skill."""
        manager = SkillManager(db)
        executor = SkillExecutor(db)

        version = await manager.get_skill_version(skill_version_id)
        result = await executor.execute_one(version, req.input)

        return result

    logger.info(
        "skill_endpoint_created",
        endpoint=f"/{skill_name}",
        skill_version_id=str(skill_version_id),
    )
