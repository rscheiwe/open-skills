"""
SQLAlchemy database models for open-skills.
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    String,
    Text,
    Integer,
    BigInteger,
    Boolean,
    TIMESTAMP,
    ForeignKey,
    CheckConstraint,
    Index,
    JSON,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from pgvector.sqlalchemy import Vector

from .base import Base


def utcnow() -> datetime:
    """Get current UTC datetime."""
    from datetime import timezone
    return datetime.now(timezone.utc)


class Org(Base):
    """Organization model."""

    __tablename__ = "orgs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=utcnow,
    )

    # Relationships
    users: Mapped[list["User"]] = relationship(
        "User",
        back_populates="org",
        cascade="all, delete-orphan",
    )
    skills: Mapped[list["Skill"]] = relationship(
        "Skill",
        back_populates="org",
    )

    def __repr__(self) -> str:
        return f"<Org(id={self.id}, name={self.name})>"


class User(Base):
    """User model."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    org_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("orgs.id", ondelete="SET NULL"),
        nullable=True,
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=utcnow,
    )

    # Relationships
    org: Mapped[Optional["Org"]] = relationship("Org", back_populates="users")
    owned_skills: Mapped[list["Skill"]] = relationship(
        "Skill",
        back_populates="owner",
        foreign_keys="Skill.owner_id",
    )
    runs: Mapped[list["SkillRun"]] = relationship(
        "SkillRun",
        back_populates="user",
    )

    def __repr__(self) -> str:
        return f"<User(id={self.id}, email={self.email})>"


class Skill(Base):
    """Top-level skill record."""

    __tablename__ = "skills"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    owner_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    org_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("orgs.id", ondelete="SET NULL"),
        nullable=True,
    )
    visibility: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="user",
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=utcnow,
    )

    # Relationships
    owner: Mapped[Optional["User"]] = relationship(
        "User",
        back_populates="owned_skills",
        foreign_keys=[owner_id],
    )
    org: Mapped[Optional["Org"]] = relationship("Org", back_populates="skills")
    versions: Mapped[list["SkillVersion"]] = relationship(
        "SkillVersion",
        back_populates="skill",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        CheckConstraint(
            "visibility IN ('user', 'org')",
            name="check_skill_visibility",
        ),
        Index("idx_skills_owner_id", "owner_id"),
        Index("idx_skills_org_id", "org_id"),
    )

    def __repr__(self) -> str:
        return f"<Skill(id={self.id}, name={self.name}, visibility={self.visibility})>"


class SkillVersion(Base):
    """Immutable skill version."""

    __tablename__ = "skill_versions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    skill_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("skills.id", ondelete="CASCADE"),
        nullable=False,
    )
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    entrypoint: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    metadata_yaml: Mapped[dict] = mapped_column(JSONB, nullable=False)
    embedding: Mapped[Optional[list[float]]] = mapped_column(
        Vector(1536),  # OpenAI text-embedding-3-large dimension
        nullable=True,
    )
    bundle_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_published: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=utcnow,
    )

    # Relationships
    skill: Mapped["Skill"] = relationship("Skill", back_populates="versions")
    runs: Mapped[list["SkillRun"]] = relationship(
        "SkillRun",
        back_populates="skill_version",
    )

    __table_args__ = (
        Index("idx_skill_versions_skill_id", "skill_id"),
        Index("idx_skill_versions_published", "is_published"),
        Index(
            "idx_skill_versions_embedding",
            "embedding",
            postgresql_using="ivfflat",  # pgvector index type
            postgresql_with={"lists": 100},  # clustering parameter
        ),
        # Unique constraint on skill_id + version
        Index(
            "idx_skill_versions_unique",
            "skill_id",
            "version",
            unique=True,
        ),
    )

    def __repr__(self) -> str:
        return f"<SkillVersion(id={self.id}, skill_id={self.skill_id}, version={self.version})>"


class SkillRun(Base):
    """Execution history for skills."""

    __tablename__ = "skill_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    skill_version_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("skill_versions.id", ondelete="SET NULL"),
        nullable=True,
    )
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    input_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    output_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    artifact_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="queued")
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    logs: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=utcnow,
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
    )

    # Relationships
    skill_version: Mapped[Optional["SkillVersion"]] = relationship(
        "SkillVersion",
        back_populates="runs",
    )
    user: Mapped[Optional["User"]] = relationship("User", back_populates="runs")
    artifacts: Mapped[list["SkillArtifact"]] = relationship(
        "SkillArtifact",
        back_populates="run",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'running', 'success', 'error', 'cancelled')",
            name="check_run_status",
        ),
        Index("idx_skill_runs_skill_version_id", "skill_version_id"),
        Index("idx_skill_runs_user_id", "user_id"),
        Index("idx_skill_runs_status", "status"),
        Index("idx_skill_runs_created_at", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<SkillRun(id={self.id}, status={self.status})>"


class SkillArtifact(Base):
    """File artifacts generated by skill runs."""

    __tablename__ = "skill_artifacts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("skill_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    s3_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    local_path: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    mime_type: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    checksum: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    size_bytes: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=utcnow,
    )

    # Relationships
    run: Mapped["SkillRun"] = relationship("SkillRun", back_populates="artifacts")

    __table_args__ = (Index("idx_skill_artifacts_run_id", "run_id"),)

    def __repr__(self) -> str:
        return f"<SkillArtifact(id={self.id}, filename={self.filename})>"


class SkillPermission(Base):
    """RBAC permissions for skills."""

    __tablename__ = "skill_permissions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
    )
    org_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("orgs.id", ondelete="CASCADE"),
        nullable=True,
    )
    skill_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("skills.id", ondelete="CASCADE"),
        nullable=True,
    )
    role: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=utcnow,
    )

    __table_args__ = (
        CheckConstraint(
            "role IN ('viewer', 'author', 'publisher', 'admin')",
            name="check_permission_role",
        ),
        Index("idx_skill_permissions_user_id", "user_id"),
        Index("idx_skill_permissions_org_id", "org_id"),
        Index("idx_skill_permissions_skill_id", "skill_id"),
    )

    def __repr__(self) -> str:
        return f"<SkillPermission(id={self.id}, role={self.role})>"
