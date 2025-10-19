"""
Artifacts manager for handling file uploads and storage.
Includes S3-compatible storage stub.
"""

import hashlib
import mimetypes
from pathlib import Path
from typing import Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from open_skills.config import settings
from open_skills.core.exceptions import ArtifactError, ArtifactSizeExceededError, StorageError
from open_skills.core.telemetry import get_logger
from open_skills.db.models import SkillArtifact, SkillRun

logger = get_logger(__name__)


class ArtifactsManager:
    """Manages skill execution artifacts and storage."""

    def __init__(self, db: AsyncSession):
        """
        Initialize artifacts manager.

        Args:
            db: Database session
        """
        self.db = db
        self.artifacts_root = settings.artifacts_root

    def _compute_checksum(self, file_path: Path) -> str:
        """
        Compute SHA256 checksum of a file.

        Args:
            file_path: Path to file

        Returns:
            Hex string of SHA256 hash
        """
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            while chunk := f.read(8192):
                sha256.update(chunk)
        return sha256.hexdigest()

    def _guess_mime_type(self, file_path: Path) -> Optional[str]:
        """
        Guess MIME type from file extension.

        Args:
            file_path: Path to file

        Returns:
            MIME type string or None
        """
        mime_type, _ = mimetypes.guess_type(str(file_path))
        return mime_type

    async def _upload_to_s3_stub(self, file_path: Path, object_key: str) -> str:
        """
        Stub implementation of S3 upload.
        In production, replace with real boto3 upload.

        Args:
            file_path: Local file path
            object_key: S3 object key

        Returns:
            Signed URL (stubbed)
        """
        # STUB: Return fake URL
        checksum = self._compute_checksum(file_path)
        fake_url = (
            f"https://{settings.s3_bucket}.s3.{settings.s3_region}.amazonaws.com/"
            f"{object_key}?checksum={checksum}&stub=true"
        )

        logger.info(
            "artifact_upload_stubbed",
            file_path=str(file_path),
            object_key=object_key,
            url=fake_url,
        )

        # In production, use boto3:
        # import boto3
        # s3 = boto3.client('s3',
        #     endpoint_url=settings.s3_endpoint,
        #     aws_access_key_id=settings.s3_access_key,
        #     aws_secret_access_key=settings.s3_secret_key,
        #     region_name=settings.s3_region,
        # )
        # s3.upload_file(str(file_path), settings.s3_bucket, object_key)
        # url = s3.generate_presigned_url('get_object',
        #     Params={'Bucket': settings.s3_bucket, 'Key': object_key},
        #     ExpiresIn=3600)
        # return url

        return fake_url

    async def create_artifact(
        self,
        run_id: UUID,
        local_file_path: Path,
        upload_to_s3: bool = True,
    ) -> SkillArtifact:
        """
        Create an artifact record and optionally upload to S3.

        Args:
            run_id: Run UUID
            local_file_path: Path to local artifact file
            upload_to_s3: Whether to upload to S3 (stub)

        Returns:
            Created SkillArtifact instance

        Raises:
            ArtifactError: If artifact creation fails
            ArtifactSizeExceededError: If file is too large
        """
        if not local_file_path.exists():
            raise ArtifactError(f"Artifact file not found: {local_file_path}")

        # Check file size
        size_bytes = local_file_path.stat().st_size
        if size_bytes > settings.max_artifact_size_bytes:
            raise ArtifactSizeExceededError(
                f"Artifact size {size_bytes} exceeds limit "
                f"{settings.max_artifact_size_bytes}"
            )

        # Compute metadata
        filename = local_file_path.name
        mime_type = self._guess_mime_type(local_file_path)
        checksum = self._compute_checksum(local_file_path)

        # Upload to S3 (stubbed)
        s3_url = None
        if upload_to_s3:
            object_key = f"runs/{run_id}/{filename}"
            try:
                s3_url = await self._upload_to_s3_stub(local_file_path, object_key)
            except Exception as e:
                logger.error("artifact_upload_failed", error=str(e))
                # Continue without S3 URL

        # Create artifact record
        artifact = SkillArtifact(
            run_id=run_id,
            s3_url=s3_url,
            local_path=str(local_file_path),
            filename=filename,
            mime_type=mime_type,
            checksum=checksum,
            size_bytes=size_bytes,
        )

        self.db.add(artifact)
        await self.db.flush()
        await self.db.refresh(artifact)

        logger.info(
            "artifact_created",
            artifact_id=str(artifact.id),
            run_id=str(run_id),
            filename=filename,
            size_bytes=size_bytes,
        )

        return artifact

    async def get_artifact(self, artifact_id: UUID) -> Optional[SkillArtifact]:
        """
        Get artifact by ID.

        Args:
            artifact_id: Artifact UUID

        Returns:
            SkillArtifact instance or None
        """
        from sqlalchemy import select

        result = await self.db.execute(
            select(SkillArtifact).where(SkillArtifact.id == artifact_id)
        )
        return result.scalar_one_or_none()

    async def list_run_artifacts(self, run_id: UUID) -> list[SkillArtifact]:
        """
        List all artifacts for a run.

        Args:
            run_id: Run UUID

        Returns:
            List of SkillArtifact instances
        """
        from sqlalchemy import select

        result = await self.db.execute(
            select(SkillArtifact)
            .where(SkillArtifact.run_id == run_id)
            .order_by(SkillArtifact.created_at)
        )
        return list(result.scalars().all())

    async def delete_artifact(self, artifact_id: UUID) -> None:
        """
        Delete an artifact.

        Args:
            artifact_id: Artifact UUID

        Raises:
            ArtifactError: If artifact not found
        """
        artifact = await self.get_artifact(artifact_id)
        if not artifact:
            raise ArtifactError(f"Artifact not found: {artifact_id}")

        # TODO: Delete from S3 if s3_url exists

        await self.db.delete(artifact)
        await self.db.flush()

        logger.info("artifact_deleted", artifact_id=str(artifact_id))
