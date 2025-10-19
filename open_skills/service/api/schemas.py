"""
Pydantic schemas for API request/response models.
"""

from datetime import datetime
from typing import List, Optional, Dict, Any
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict


# ========== User & Org Schemas ==========


class UserBase(BaseModel):
    """Base user schema."""

    email: str


class UserCreate(UserBase):
    """User creation schema."""

    org_id: Optional[UUID] = None


class User(UserBase):
    """User response schema."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    org_id: Optional[UUID] = None
    created_at: datetime


# ========== Skill Schemas ==========


class SkillBase(BaseModel):
    """Base skill schema."""

    name: str = Field(..., min_length=1, max_length=255)
    visibility: str = Field(default="user", pattern="^(user|org)$")


class SkillCreate(SkillBase):
    """Skill creation schema."""

    org_id: Optional[UUID] = None


class SkillUpdate(BaseModel):
    """Skill update schema."""

    name: Optional[str] = Field(None, min_length=1, max_length=255)
    visibility: Optional[str] = Field(None, pattern="^(user|org)$")


class Skill(SkillBase):
    """Skill response schema."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    owner_id: Optional[UUID] = None
    org_id: Optional[UUID] = None
    created_at: datetime


class SkillDetail(Skill):
    """Detailed skill response with versions."""

    version_count: int = 0
    latest_version: Optional[str] = None


# ========== Skill Version Schemas ==========


class SkillVersionBase(BaseModel):
    """Base skill version schema."""

    version: str = Field(..., pattern=r"^\d+\.\d+\.\d+(-[a-zA-Z0-9\-\.]+)?$")
    description: Optional[str] = None


class SkillVersionCreate(SkillVersionBase):
    """Skill version creation schema (for direct API creation)."""

    entrypoint: str
    metadata_yaml: Dict[str, Any]


class SkillVersion(SkillVersionBase):
    """Skill version response schema."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    skill_id: UUID
    entrypoint: str
    metadata_yaml: Dict[str, Any]
    is_published: bool
    created_at: datetime


class SkillVersionDetail(SkillVersion):
    """Detailed skill version with metadata."""

    skill_name: Optional[str] = None
    bundle_path: Optional[str] = None
    has_embedding: bool = False


class SkillVersionSummary(BaseModel):
    """Summary for skill auto-selection."""

    skill_version_id: UUID
    skill_id: UUID
    skill_name: str
    version: str
    description: str
    summary: str
    tags: List[str]
    inputs: List[Dict[str, Any]]
    outputs: List[Dict[str, Any]]
    similarity: Optional[float] = None


# ========== Run Schemas ==========


class RunCreate(BaseModel):
    """Run creation schema."""

    skill_version_ids: List[UUID] = Field(..., min_length=1)
    input: Dict[str, Any] = Field(default_factory=dict)
    strategy: str = Field(default="parallel", pattern="^(parallel|chain)$")
    timeout_seconds: Optional[int] = Field(None, ge=1, le=600)


class RunResult(BaseModel):
    """Run result schema."""

    run_id: UUID
    skill_version_id: UUID
    status: str
    outputs: Dict[str, Any] = Field(default_factory=dict)
    artifacts: List[Dict[str, Any]] = Field(default_factory=list)
    duration_ms: Optional[int] = None
    error: Optional[str] = None


class Run(BaseModel):
    """Run response schema."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    skill_version_id: Optional[UUID] = None
    user_id: Optional[UUID] = None
    input_json: Optional[Dict[str, Any]] = None
    output_json: Optional[Dict[str, Any]] = None
    status: str
    duration_ms: Optional[int] = None
    logs: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None


class RunDetail(Run):
    """Detailed run with artifacts."""

    artifacts: List["Artifact"] = Field(default_factory=list)
    skill_name: Optional[str] = None
    version: Optional[str] = None


# ========== Artifact Schemas ==========


class Artifact(BaseModel):
    """Artifact response schema."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    run_id: UUID
    s3_url: Optional[str] = None
    local_path: Optional[str] = None
    filename: str
    mime_type: Optional[str] = None
    checksum: Optional[str] = None
    size_bytes: Optional[int] = None
    created_at: datetime


# ========== Search Schemas ==========


class SearchRequest(BaseModel):
    """Skill search request."""

    query: str = Field(..., min_length=1)
    io_hints: Optional[Dict[str, Any]] = None
    tags: Optional[List[str]] = None
    top_k: int = Field(default=5, ge=1, le=20)
    published_only: bool = True
    min_similarity: float = Field(default=0.0, ge=0.0, le=1.0)


class SearchResponse(BaseModel):
    """Skill search response."""

    results: List[SkillVersionSummary]
    total: int


# ========== Permission Schemas ==========


class PermissionCreate(BaseModel):
    """Permission creation schema."""

    user_id: UUID
    role: str = Field(..., pattern="^(viewer|author|publisher|admin)$")
    skill_id: Optional[UUID] = None
    org_id: Optional[UUID] = None


class Permission(BaseModel):
    """Permission response schema."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: Optional[UUID] = None
    org_id: Optional[UUID] = None
    skill_id: Optional[UUID] = None
    role: str
    created_at: datetime


# ========== Bulk Operation Schemas ==========


class BulkRunResponse(BaseModel):
    """Response for bulk/multi-skill runs."""

    results: List[RunResult]
    total: int
    successful: int
    failed: int


# ========== Health & Status Schemas ==========


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    version: str
    timestamp: datetime


class StatsResponse(BaseModel):
    """System statistics response."""

    total_skills: int
    total_versions: int
    total_runs: int
    successful_runs: int
    failed_runs: int
