"""
Skill Executor for dynamic loading and execution of skill code.
"""

import asyncio
import importlib.util
import os
import sys
import tempfile
import time
import traceback
from pathlib import Path
from typing import Dict, Any, Optional, List
from uuid import UUID
import io
from contextlib import redirect_stdout, redirect_stderr

from sqlalchemy.ext.asyncio import AsyncSession

from open_skills.config import settings
from open_skills.core.exceptions import (
    SkillExecutionError,
    SkillTimeoutError,
    SkillVersionNotFoundError,
)
from open_skills.core.telemetry import get_logger, run_trace
from open_skills.core.streaming import (
    emit_status,
    emit_log,
    emit_output,
    emit_artifact,
    emit_error,
    emit_complete,
)
from open_skills.db.models import SkillRun, SkillVersion

logger = get_logger(__name__)


class SkillExecutor:
    """Executes skill code in isolated contexts with timeouts."""

    def __init__(self, db: AsyncSession):
        """
        Initialize skill executor.

        Args:
            db: Database session
        """
        self.db = db

    async def _load_callable(
        self,
        bundle_root: Path,
        entrypoint: str,
    ):
        """
        Dynamically load the skill entrypoint function.

        Args:
            bundle_root: Root directory of skill bundle
            entrypoint: Entrypoint path (e.g., "scripts/main.py" or "scripts/main.py:run")

        Returns:
            Callable function

        Raises:
            SkillExecutionError: If loading fails
        """
        try:
            # Parse entrypoint
            if ":" in entrypoint:
                mod_path, func_name = entrypoint.split(":", 1)
            else:
                mod_path, func_name = entrypoint, "run"

            # Get absolute path to module
            target_path = bundle_root / mod_path
            if not target_path.exists():
                raise SkillExecutionError(f"Entrypoint file not found: {target_path}")

            # Load module dynamically
            spec = importlib.util.spec_from_file_location(
                f"skill_module_{id(target_path)}",
                str(target_path),
            )
            if not spec or not spec.loader:
                raise SkillExecutionError(f"Failed to load module spec: {target_path}")

            module = importlib.util.module_from_spec(spec)

            # Add bundle root to sys.path temporarily
            old_sys_path = sys.path.copy()
            sys.path.insert(0, str(bundle_root))

            try:
                spec.loader.exec_module(module)
            finally:
                # Restore sys.path
                sys.path = old_sys_path

            # Get the function
            if not hasattr(module, func_name):
                raise SkillExecutionError(
                    f"Function '{func_name}' not found in module {mod_path}"
                )

            func = getattr(module, func_name)
            if not callable(func):
                raise SkillExecutionError(
                    f"'{func_name}' in {mod_path} is not callable"
                )

            logger.info(
                "skill_callable_loaded",
                module=mod_path,
                function=func_name,
            )

            return func

        except Exception as e:
            if isinstance(e, SkillExecutionError):
                raise
            raise SkillExecutionError(f"Failed to load skill callable: {e}")

    async def _create_run_record(
        self,
        skill_version_id: UUID,
        input_payload: Dict[str, Any],
        user_id: Optional[UUID] = None,
    ) -> SkillRun:
        """
        Create a new skill run record in the database.

        Args:
            skill_version_id: Skill version UUID
            input_payload: Input data
            user_id: Optional user ID

        Returns:
            Created SkillRun instance
        """
        run = SkillRun(
            skill_version_id=skill_version_id,
            user_id=user_id,
            input_json=input_payload,
            status="queued",
        )
        self.db.add(run)
        await self.db.flush()
        await self.db.refresh(run)

        logger.info("skill_run_created", run_id=str(run.id), status="queued")

        return run

    async def _update_run_status(
        self,
        run: SkillRun,
        status: str,
        output_json: Optional[Dict] = None,
        duration_ms: Optional[int] = None,
        logs: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> None:
        """
        Update skill run record.

        Args:
            run: SkillRun instance
            status: New status
            output_json: Output data
            duration_ms: Execution duration in milliseconds
            logs: Execution logs
            error_message: Error message if failed
        """
        run.status = status
        if output_json:
            run.output_json = output_json
        if duration_ms is not None:
            run.duration_ms = duration_ms
        if logs:
            run.logs = logs
        if error_message:
            run.error_message = error_message

        if status in ("success", "error", "cancelled"):
            from datetime import datetime, timezone
            run.completed_at = datetime.now(timezone.utc)

        await self.db.flush()
        await self.db.refresh(run)

        # Emit streaming event
        await emit_status(run.id, status)

        logger.info(
            "skill_run_updated",
            run_id=str(run.id),
            status=status,
            duration_ms=duration_ms,
        )

    async def execute_one(
        self,
        skill_version: SkillVersion,
        input_payload: Dict[str, Any],
        user_id: Optional[UUID] = None,
        timeout_seconds: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Execute a single skill version.

        Args:
            skill_version: SkillVersion instance to execute
            input_payload: Input data dictionary
            user_id: Optional user ID for tracking
            timeout_seconds: Optional timeout override

        Returns:
            Dictionary with run_id, status, outputs, and artifacts

        Raises:
            SkillExecutionError: If execution fails
            SkillTimeoutError: If execution times out
        """
        # Create run record
        run = await self._create_run_record(
            skill_version_id=skill_version.id,
            input_payload=input_payload,
            user_id=user_id,
        )

        # Get timeout
        metadata = skill_version.metadata_yaml or {}
        timeout = (
            timeout_seconds
            or metadata.get("timeout_seconds")
            or settings.default_timeout_seconds
        )
        timeout = min(timeout, settings.max_timeout_seconds)

        # Get bundle path
        bundle_path = Path(skill_version.bundle_path) if skill_version.bundle_path else None
        if not bundle_path or not bundle_path.exists():
            error_msg = f"Bundle path not found for version {skill_version.id}"
            await self._update_run_status(run, "error", error_message=error_msg)
            raise SkillExecutionError(error_msg)

        start_time = time.perf_counter()
        skill_name = metadata.get("name", "unknown")

        # Start tracing
        with run_trace(run.id, skill_name=skill_name, user_id=str(user_id) if user_id else None) as trace:
            try:
                # Update status to running
                await self._update_run_status(run, "running")

                # Load the callable
                func = await self._load_callable(bundle_path, skill_version.entrypoint)

                # Create temporary working directory for artifacts
                with tempfile.TemporaryDirectory(prefix="open-skills-") as workdir:
                    workdir_path = Path(workdir)

                    # Set up environment
                    old_cwd = os.getcwd()
                    os.chdir(workdir)
                    os.environ["OPEN_SKILLS_WORKDIR"] = str(workdir_path)
                    os.environ["OPEN_SKILLS_RUN_ID"] = str(run.id)

                    # Capture stdout/stderr
                    stdout_capture = io.StringIO()
                    stderr_capture = io.StringIO()

                    try:
                        with redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):
                            # Execute with timeout
                            if asyncio.iscoroutinefunction(func):
                                result = await asyncio.wait_for(
                                    func(input_payload),
                                    timeout=timeout,
                                )
                            else:
                                # Run sync function in executor
                                result = await asyncio.wait_for(
                                    asyncio.get_event_loop().run_in_executor(
                                        None, func, input_payload
                                    ),
                                    timeout=timeout,
                                )
                    finally:
                        # Restore environment
                        os.chdir(old_cwd)
                        os.environ.pop("OPEN_SKILLS_WORKDIR", None)
                        os.environ.pop("OPEN_SKILLS_RUN_ID", None)

                    # Collect outputs
                    outputs = result.get("outputs", {}) if isinstance(result, dict) else {}
                    artifact_files = result.get("artifacts", []) if isinstance(result, dict) else []

                    # Process artifacts (will be handled by artifacts manager)
                    artifact_records = []
                    for artifact_file in artifact_files:
                        artifact_path = workdir_path / artifact_file
                        if artifact_path.exists():
                            # For now, just record the file info
                            # In full implementation, upload to S3 here
                            size_bytes = artifact_path.stat().st_size
                            artifact_records.append({
                                "filename": artifact_path.name,
                                "local_path": str(artifact_path),
                                "size_bytes": size_bytes,
                            })
                            # Emit artifact event
                            await emit_artifact(
                                run.id,
                                artifact_path.name,
                                size_bytes=size_bytes,
                            )

                    # Collect logs
                    stdout_log = stdout_capture.getvalue()
                    stderr_log = stderr_capture.getvalue()
                    combined_logs = f"=== STDOUT ===\n{stdout_log}\n\n=== STDERR ===\n{stderr_log}"

                    # Calculate duration
                    duration_ms = int((time.perf_counter() - start_time) * 1000)

                    # Update run record
                    await self._update_run_status(
                        run,
                        "success",
                        output_json=outputs,
                        duration_ms=duration_ms,
                        logs=combined_logs,
                    )

                    trace.event("execution_completed", {
                        "duration_ms": duration_ms,
                        "artifact_count": len(artifact_records),
                    })

                    # Emit completion event
                    await emit_complete(run.id, "success", outputs, duration_ms)

                    return {
                        "run_id": str(run.id),
                        "status": "success",
                        "outputs": outputs,
                        "artifacts": artifact_records,
                        "duration_ms": duration_ms,
                        "logs": combined_logs,
                    }

            except asyncio.TimeoutError:
                duration_ms = int((time.perf_counter() - start_time) * 1000)
                error_msg = f"Execution timed out after {timeout}s"

                await self._update_run_status(
                    run,
                    "error",
                    duration_ms=duration_ms,
                    error_message=error_msg,
                )

                # Emit error event
                await emit_error(run.id, error_msg)

                logger.error(
                    "skill_execution_timeout",
                    run_id=str(run.id),
                    timeout=timeout,
                    duration_ms=duration_ms,
                )

                raise SkillTimeoutError(error_msg)

            except Exception as e:
                duration_ms = int((time.perf_counter() - start_time) * 1000)
                error_msg = str(e)
                tb = traceback.format_exc()

                await self._update_run_status(
                    run,
                    "error",
                    duration_ms=duration_ms,
                    error_message=error_msg,
                    logs=tb,
                )

                # Emit error event
                await emit_error(run.id, error_msg, tb)

                logger.exception(
                    "skill_execution_error",
                    run_id=str(run.id),
                    error=error_msg,
                    duration_ms=duration_ms,
                )

                raise SkillExecutionError(f"Execution failed: {error_msg}") from e

    async def execute_many(
        self,
        skill_versions: List[SkillVersion],
        input_payload: Dict[str, Any],
        user_id: Optional[UUID] = None,
        strategy: str = "parallel",
    ) -> List[Dict[str, Any]]:
        """
        Execute multiple skills.

        Args:
            skill_versions: List of SkillVersion instances
            input_payload: Input data (shared across all skills for parallel)
            user_id: Optional user ID
            strategy: "parallel" or "chain" (sequential with output passing)

        Returns:
            List of execution results

        Raises:
            SkillExecutionError: If any execution fails
        """
        if strategy == "parallel":
            # Execute all in parallel
            tasks = [
                self.execute_one(version, input_payload, user_id)
                for version in skill_versions
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Convert exceptions to error dicts
            formatted_results = []
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    formatted_results.append({
                        "run_id": None,
                        "status": "error",
                        "error": str(result),
                        "skill_version_id": str(skill_versions[i].id),
                    })
                else:
                    formatted_results.append(result)

            return formatted_results

        elif strategy == "chain":
            # Execute sequentially, passing output to next input
            results = []
            current_input = input_payload

            for version in skill_versions:
                result = await self.execute_one(version, current_input, user_id)
                results.append(result)

                # Pass outputs to next skill's input
                if result["status"] == "success":
                    current_input = result["outputs"]
                else:
                    # Stop chain on error
                    break

            return results

        else:
            raise ValueError(f"Unknown strategy: {strategy}")
