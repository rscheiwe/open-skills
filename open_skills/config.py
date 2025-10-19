"""
Configuration management using Pydantic Settings.
Loads environment variables with validation and type checking.
"""

from pathlib import Path
from typing import Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = "open-skills"
    app_version: str = "0.1.0"
    debug: bool = False
    environment: str = Field(default="development", pattern="^(development|staging|production)$")

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    workers: int = 1
    reload: bool = False

    # Database
    postgres_url: str = Field(
        ...,  # Required
        description="PostgreSQL connection URL with asyncpg driver",
    )
    db_echo: bool = False  # SQLAlchemy echo SQL statements
    db_pool_size: int = 5
    db_max_overflow: int = 10

    # OpenAI (for embeddings)
    openai_api_key: str = Field(
        ...,  # Required
        description="OpenAI API key for embeddings",
    )
    embedding_model: str = "text-embedding-3-large"
    embedding_dimensions: int = 1536

    # Security & Encryption
    jwt_secret: str = Field(
        ...,  # Required
        description="Secret key for JWT token signing and encryption",
    )
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24  # 24 hours

    # Storage
    storage_root: Path = Field(
        default=Path("./storage"),
        description="Root directory for skill bundle storage",
    )
    artifacts_root: Path = Field(
        default=Path("./artifacts"),
        description="Root directory for temporary artifacts before S3 upload",
    )

    # S3 (optional, stubbed)
    s3_endpoint: Optional[str] = None
    s3_bucket: Optional[str] = "open-skills-artifacts"
    s3_access_key: Optional[str] = None
    s3_secret_key: Optional[str] = None
    s3_region: str = "us-east-1"

    # Telemetry (Langfuse - stubbed)
    langfuse_enabled: bool = False
    langfuse_api_key: Optional[str] = None
    langfuse_host: str = "https://cloud.langfuse.com"
    langfuse_public_key: Optional[str] = None
    langfuse_secret_key: Optional[str] = None

    # Execution limits
    default_timeout_seconds: int = 60
    max_timeout_seconds: int = 300
    max_input_size_bytes: int = 10 * 1024 * 1024  # 10MB
    max_artifact_size_bytes: int = 100 * 1024 * 1024  # 100MB
    max_artifacts_per_run: int = 20

    # CORS
    cors_origins: list[str] = Field(
        default=["http://localhost:3000", "http://localhost:5173"],
        description="Allowed CORS origins",
    )

    # Logging
    log_level: str = Field(
        default="INFO",
        pattern="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$",
    )
    log_format: str = "json"  # or "text"

    @field_validator("storage_root", "artifacts_root")
    @classmethod
    def ensure_directories(cls, v: Path) -> Path:
        """Ensure storage directories exist."""
        v.mkdir(parents=True, exist_ok=True)
        return v.absolute()

    @field_validator("postgres_url")
    @classmethod
    def validate_postgres_url(cls, v: str) -> str:
        """Validate PostgreSQL URL uses asyncpg driver."""
        if not v.startswith("postgresql+asyncpg://"):
            raise ValueError(
                "POSTGRES_URL must use asyncpg driver (postgresql+asyncpg://...)"
            )
        return v

    @property
    def database_url(self) -> str:
        """Alias for postgres_url."""
        return self.postgres_url

    @property
    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self.environment == "production"

    @property
    def is_development(self) -> bool:
        """Check if running in development environment."""
        return self.environment == "development"


# Global settings instance
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """
    Get global settings instance (singleton pattern).

    Returns:
        Settings: Application settings
    """
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def reload_settings() -> Settings:
    """
    Reload settings from environment (useful for testing).

    Returns:
        Settings: Fresh settings instance
    """
    global _settings
    _settings = Settings()
    return _settings


# Convenience export
settings = get_settings()
