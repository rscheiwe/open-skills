"""
FastAPI router with all API endpoints.
"""

import tempfile
import zipfile
from pathlib import Path
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Request
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from open_skills.service.api import schemas
from open_skills.service.api.deps import (
    get_db,
    require_user,
    require_author,
    require_publisher,
    get_optional_user,
    get_pagination,
    Pagination,
)
from open_skills.config import settings
from open_skills.core.manager import SkillManager
from open_skills.core.router import SkillRouter
from open_skills.core.executor import SkillExecutor
from open_skills.core.artifacts import ArtifactsManager
from open_skills.core.rbac import RBACManager, Permission, Role
from open_skills.core.streaming import get_event_bus, format_sse_event
from open_skills.core.exceptions import (
    SkillNotFoundError,
    SkillVersionNotFoundError,
    SkillValidationError,
    SkillExecutionError,
    RunNotFoundError,
)
from open_skills.db.models import Skill, SkillVersion, SkillRun, User

router = APIRouter(prefix="/api")


# ========== Health & Status ==========


@router.get("/health", response_model=schemas.HealthResponse)
async def health_check():
    """Health check endpoint."""
    from datetime import datetime, timezone
    return schemas.HealthResponse(
        status="healthy",
        version=settings.app_version,
        timestamp=datetime.now(timezone.utc),
    )


@router.get("/stats", response_model=schemas.StatsResponse)
async def get_stats(db: AsyncSession = Depends(get_db)):
    """Get system statistics."""
    # Count totals
    total_skills = await db.scalar(select(func.count()).select_from(Skill))
    total_versions = await db.scalar(select(func.count()).select_from(SkillVersion))
    total_runs = await db.scalar(select(func.count()).select_from(SkillRun))

    # Count successful/failed runs
    successful_runs = await db.scalar(
        select(func.count()).select_from(SkillRun).where(SkillRun.status == "success")
    )
    failed_runs = await db.scalar(
        select(func.count()).select_from(SkillRun).where(SkillRun.status == "error")
    )

    return schemas.StatsResponse(
        total_skills=total_skills or 0,
        total_versions=total_versions or 0,
        total_runs=total_runs or 0,
        successful_runs=successful_runs or 0,
        failed_runs=failed_runs or 0,
    )


# ========== Skills CRUD ==========


@router.post("/skills", response_model=schemas.Skill, status_code=status.HTTP_201_CREATED)
async def create_skill(
    payload: schemas.SkillCreate,
    current_user: User = Depends(require_author),
    db: AsyncSession = Depends(get_db),
):
    """Create a new skill."""
    manager = SkillManager(db)
    skill = await manager.create_skill(
        name=payload.name,
        owner_id=current_user.id,
        org_id=payload.org_id or current_user.org_id,
        visibility=payload.visibility,
    )
    await db.commit()
    return skill


@router.get("/skills", response_model=List[schemas.Skill])
async def list_skills(
    pagination: Pagination = Depends(get_pagination),
    current_user: Optional[User] = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
):
    """List skills (with optional user filtering)."""
    manager = SkillManager(db)
    skills = await manager.list_skills(
        owner_id=current_user.id if current_user else None,
        limit=pagination.limit,
        offset=pagination.skip,
    )
    return skills


@router.get("/skills/{skill_id}", response_model=schemas.Skill)
async def get_skill(
    skill_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get skill by ID."""
    manager = SkillManager(db)
    try:
        skill = await manager.get_skill(skill_id)
        return skill
    except SkillNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Skill not found: {skill_id}",
        )


@router.patch("/skills/{skill_id}", response_model=schemas.Skill)
async def update_skill(
    skill_id: UUID,
    payload: schemas.SkillUpdate,
    current_user: User = Depends(require_author),
    db: AsyncSession = Depends(get_db),
):
    """Update a skill."""
    manager = SkillManager(db)
    try:
        skill = await manager.get_skill(skill_id)

        # Check permissions
        rbac = RBACManager(db)
        if not await rbac.can_modify_skill(current_user.id, skill):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to modify this skill",
            )

        # Update fields
        if payload.name is not None:
            skill.name = payload.name
        if payload.visibility is not None:
            skill.visibility = payload.visibility

        await db.commit()
        await db.refresh(skill)
        return skill

    except SkillNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Skill not found: {skill_id}",
        )


@router.delete("/skills/{skill_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_skill(
    skill_id: UUID,
    current_user: User = Depends(require_author),
    db: AsyncSession = Depends(get_db),
):
    """Delete a skill."""
    manager = SkillManager(db)
    try:
        skill = await manager.get_skill(skill_id)

        # Check permissions
        rbac = RBACManager(db)
        if skill.owner_id != current_user.id:
            has_admin = await rbac.has_permission(
                current_user.id,
                Permission.DELETE_SKILL,
                skill_id=skill_id,
            )
            if not has_admin:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You don't have permission to delete this skill",
                )

        await manager.delete_skill(skill_id)
        await db.commit()

    except SkillNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Skill not found: {skill_id}",
        )


# ========== Skill Versions ==========


@router.post(
    "/skills/{skill_id}/versions",
    response_model=schemas.SkillVersion,
    status_code=status.HTTP_201_CREATED,
)
async def upload_skill_version(
    skill_id: UUID,
    bundle: UploadFile = File(...),
    current_user: User = Depends(require_author),
    db: AsyncSession = Depends(get_db),
):
    """Upload a skill bundle (zip file) and create a new version."""
    manager = SkillManager(db)
    skill_router = SkillRouter(db)

    try:
        # Verify skill exists
        skill = await manager.get_skill(skill_id)

        # Check permissions
        rbac = RBACManager(db)
        if not await rbac.can_modify_skill(current_user.id, skill):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to create versions for this skill",
            )

        # Save uploaded file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as tmp:
            content = await bundle.read()
            tmp.write(content)
            tmp_path = Path(tmp.name)

        # Extract zip
        extract_dir = Path(tempfile.mkdtemp(prefix="skill-bundle-"))
        try:
            with zipfile.ZipFile(tmp_path, "r") as zip_ref:
                zip_ref.extractall(extract_dir)

            # Find bundle root (may be nested in a single directory)
            bundle_path = extract_dir
            contents = list(extract_dir.iterdir())
            if len(contents) == 1 and contents[0].is_dir():
                bundle_path = contents[0]

            # Create version from bundle
            version = await manager.create_version_from_bundle(skill_id, bundle_path)

            # Generate embedding
            await skill_router.embed_skill_version(version)

            await db.commit()
            await db.refresh(version)

            return version

        finally:
            # Cleanup
            tmp_path.unlink(missing_ok=True)
            import shutil
            shutil.rmtree(extract_dir, ignore_errors=True)

    except SkillNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Skill not found: {skill_id}",
        )
    except SkillValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid skill bundle: {e}",
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upload skill version: {e}",
        )


@router.get("/skills/{skill_id}/versions", response_model=List[schemas.SkillVersion])
async def list_skill_versions(
    skill_id: UUID,
    published_only: bool = False,
    db: AsyncSession = Depends(get_db),
):
    """List all versions for a skill."""
    manager = SkillManager(db)
    try:
        versions = await manager.list_skill_versions(
            skill_id,
            published_only=published_only,
        )
        return versions
    except SkillNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Skill not found: {skill_id}",
        )


@router.get("/skill-versions/{version_id}", response_model=schemas.SkillVersion)
async def get_skill_version(
    version_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get skill version by ID."""
    manager = SkillManager(db)
    try:
        version = await manager.get_skill_version(version_id)
        return version
    except SkillVersionNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Skill version not found: {version_id}",
        )


@router.post(
    "/skill-versions/{version_id}/publish",
    response_model=schemas.SkillVersion,
)
async def publish_version(
    version_id: UUID,
    current_user: User = Depends(require_publisher),
    db: AsyncSession = Depends(get_db),
):
    """Publish a skill version."""
    manager = SkillManager(db)
    try:
        version = await manager.publish_version(version_id)
        await db.commit()
        await db.refresh(version)
        return version
    except SkillVersionNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Skill version not found: {version_id}",
        )


@router.post(
    "/skill-versions/{version_id}/unpublish",
    response_model=schemas.SkillVersion,
)
async def unpublish_version(
    version_id: UUID,
    current_user: User = Depends(require_publisher),
    db: AsyncSession = Depends(get_db),
):
    """Unpublish a skill version."""
    manager = SkillManager(db)
    try:
        version = await manager.unpublish_version(version_id)
        await db.commit()
        await db.refresh(version)
        return version
    except SkillVersionNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Skill version not found: {version_id}",
        )


# ========== Search & Routing ==========


@router.post("/skills/search", response_model=schemas.SearchResponse)
async def search_skills(
    payload: schemas.SearchRequest,
    db: AsyncSession = Depends(get_db),
):
    """Search for skills using embeddings and filters."""
    skill_router = SkillRouter(db)
    try:
        results = await skill_router.search(
            query=payload.query,
            io_hints=payload.io_hints,
            tags=payload.tags,
            top_k=payload.top_k,
            published_only=payload.published_only,
            min_similarity=payload.min_similarity,
        )

        summaries = [schemas.SkillVersionSummary(**r) for r in results]

        return schemas.SearchResponse(
            results=summaries,
            total=len(summaries),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Search failed: {e}",
        )


# ========== Runs ==========


@router.post("/runs", response_model=schemas.BulkRunResponse)
async def execute_skills(
    payload: schemas.RunCreate,
    current_user: Optional[User] = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
):
    """Execute one or more skills."""
    manager = SkillManager(db)
    executor = SkillExecutor(db)

    try:
        # Fetch skill versions
        versions = []
        for version_id in payload.skill_version_ids:
            version = await manager.get_skill_version(version_id)
            versions.append(version)

        # Execute
        if len(versions) == 1:
            result = await executor.execute_one(
                versions[0],
                payload.input,
                user_id=current_user.id if current_user else None,
                timeout_seconds=payload.timeout_seconds,
            )
            results = [result]
        else:
            results = await executor.execute_many(
                versions,
                payload.input,
                user_id=current_user.id if current_user else None,
                strategy=payload.strategy,
            )

        await db.commit()

        # Format response
        run_results = []
        successful = 0
        failed = 0

        for r in results:
            status = r.get("status", "error")
            if status == "success":
                successful += 1
            else:
                failed += 1

            run_results.append(
                schemas.RunResult(
                    run_id=UUID(r["run_id"]) if r.get("run_id") else UUID(int=0),
                    skill_version_id=UUID(r.get("skill_version_id", "00000000-0000-0000-0000-000000000000")),
                    status=status,
                    outputs=r.get("outputs", {}),
                    artifacts=r.get("artifacts", []),
                    duration_ms=r.get("duration_ms"),
                    error=r.get("error"),
                )
            )

        return schemas.BulkRunResponse(
            results=run_results,
            total=len(run_results),
            successful=successful,
            failed=failed,
        )

    except SkillVersionNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except SkillExecutionError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Execution failed: {e}",
        )


@router.get("/runs/{run_id}", response_model=schemas.Run)
async def get_run(
    run_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get run by ID."""
    result = await db.execute(
        select(SkillRun).where(SkillRun.id == run_id)
    )
    run = result.scalar_one_or_none()

    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run not found: {run_id}",
        )

    return run


@router.get("/skills/{skill_id}/runs", response_model=List[schemas.Run])
async def list_skill_runs(
    skill_id: UUID,
    pagination: Pagination = Depends(get_pagination),
    db: AsyncSession = Depends(get_db),
):
    """List all runs for a skill."""
    # Join to get runs for all versions of the skill
    result = await db.execute(
        select(SkillRun)
        .join(SkillVersion, SkillRun.skill_version_id == SkillVersion.id)
        .where(SkillVersion.skill_id == skill_id)
        .order_by(SkillRun.created_at.desc())
        .limit(pagination.limit)
        .offset(pagination.skip)
    )
    runs = list(result.scalars().all())
    return runs


@router.get("/runs/{run_id}/stream")
async def stream_run(
    run_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Stream real-time execution events for a run via Server-Sent Events (SSE).

    Events:
    - status: Status changes (queued, running, success, error)
    - log: Log output lines
    - output: Individual output values
    - artifact: Artifact creation
    - error: Error details
    - complete: Execution completion

    Example usage:
        const eventSource = new EventSource('/api/runs/{run_id}/stream');
        eventSource.addEventListener('status', (e) => {
            const data = JSON.parse(e.data);
            console.log('Status:', data.status);
        });
        eventSource.addEventListener('complete', (e) => {
            const data = JSON.parse(e.data);
            console.log('Completed:', data);
            eventSource.close();
        });
    """
    # Verify run exists
    result = await db.execute(
        select(SkillRun).where(SkillRun.id == run_id)
    )
    run = result.scalar_one_or_none()

    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run not found: {run_id}",
        )

    # Get event bus
    event_bus = get_event_bus()

    async def event_generator():
        """Generate SSE events from the event bus."""
        # Send initial status
        initial_event = {
            "type": "status",
            "data": {
                "status": run.status,
                "run_id": str(run.id),
            }
        }
        yield format_sse_event(initial_event)

        # If run is already completed, send complete event and stop
        if run.status in ("success", "error", "cancelled"):
            complete_event = {
                "type": "complete",
                "data": {
                    "status": run.status,
                    "outputs": run.output_json or {},
                    "duration_ms": run.duration_ms or 0,
                }
            }
            yield format_sse_event(complete_event)
            return

        # Stream events until completion
        async for event in event_bus.stream_events(run_id, timeout=30.0):
            # Check if client disconnected
            if await request.is_disconnected():
                break

            yield format_sse_event(event)

            # Stop after complete/error event
            if event["type"] in ("complete", "error"):
                break

    return EventSourceResponse(event_generator())


# ========== Artifacts ==========


@router.get("/artifacts/{artifact_id}", response_model=schemas.Artifact)
async def get_artifact(
    artifact_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get artifact by ID."""
    artifacts_manager = ArtifactsManager(db)
    artifact = await artifacts_manager.get_artifact(artifact_id)

    if not artifact:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Artifact not found: {artifact_id}",
        )

    return artifact
