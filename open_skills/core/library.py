"""
Library mode configuration and initialization.
Provides a global configuration API for embedding open-skills in any application.
"""

from pathlib import Path
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from open_skills.config import settings
from open_skills.core.telemetry import logger
from open_skills.db.base import Base, engine as default_engine


class LibraryConfig:
    """Global configuration for library mode."""

    def __init__(self):
        self._database_url: Optional[str] = None
        self._engine = None
        self._session_factory = None
        self._initialized = False

    @property
    def initialized(self) -> bool:
        """Check if library has been configured."""
        return self._initialized

    @property
    def database_url(self) -> Optional[str]:
        """Get configured database URL."""
        return self._database_url or settings.database_url

    @property
    def engine(self):
        """Get database engine."""
        if self._engine is None:
            return default_engine
        return self._engine

    @property
    def session_factory(self):
        """Get session factory."""
        if self._session_factory is None:
            from open_skills.db.base import AsyncSessionLocal
            return AsyncSessionLocal
        return self._session_factory

    async def get_db(self) -> AsyncSession:
        """
        Get a database session.

        Yields:
            AsyncSession: Database session
        """
        async with self.session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()


# Global library config instance
_lib_config = LibraryConfig()


def configure(
    database_url: Optional[str] = None,
    storage_root: Optional[Path] = None,
    artifacts_root: Optional[Path] = None,
    openai_api_key: Optional[str] = None,
    **kwargs
) -> None:
    """
    Configure open-skills for library mode.

    This is the primary way to initialize open-skills when using it as a library
    embedded in your application.

    Args:
        database_url: PostgreSQL connection URL (postgresql+asyncpg://...)
        storage_root: Root directory for skill bundle storage
        artifacts_root: Root directory for artifacts
        openai_api_key: OpenAI API key for embeddings
        **kwargs: Additional settings to override

    Example:
        ```python
        from open_skills.core.library import configure

        configure(
            database_url="postgresql+asyncpg://localhost/mydb",
            storage_root="/app/skills",
            openai_api_key="sk-..."
        )
        ```
    """
    global _lib_config

    logger.info("configuring_library_mode")

    # Update database URL
    if database_url:
        _lib_config._database_url = database_url
        _lib_config._engine = create_async_engine(
            database_url,
            echo=settings.db_echo,
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_max_overflow,
            pool_pre_ping=True,
        )
        _lib_config._session_factory = async_sessionmaker(
            _lib_config._engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False,
        )

    # Update other settings
    if storage_root:
        settings.storage_root = Path(storage_root)
        settings.storage_root.mkdir(parents=True, exist_ok=True)

    if artifacts_root:
        settings.artifacts_root = Path(artifacts_root)
        settings.artifacts_root.mkdir(parents=True, exist_ok=True)

    if openai_api_key:
        settings.openai_api_key = openai_api_key

    # Apply additional settings
    for key, value in kwargs.items():
        if hasattr(settings, key):
            setattr(settings, key, value)

    _lib_config._initialized = True

    logger.info(
        "library_configured",
        database_url=bool(_lib_config._database_url),
        storage_root=str(settings.storage_root),
    )


def get_config() -> LibraryConfig:
    """
    Get the global library configuration.

    Returns:
        LibraryConfig: Global configuration instance

    Example:
        ```python
        from open_skills.core.library import get_config

        config = get_config()
        async for session in config.get_db():
            # Use session
            pass
        ```
    """
    return _lib_config


def is_configured() -> bool:
    """
    Check if library has been configured.

    Returns:
        bool: True if configured, False otherwise
    """
    return _lib_config.initialized


async def init_db() -> None:
    """
    Initialize database (create tables).
    Note: In production, use Alembic migrations instead.
    """
    if not _lib_config.initialized:
        logger.warning("init_db_called_before_configuration")

    async with _lib_config.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    logger.info("database_initialized")


async def dispose() -> None:
    """
    Dispose of database connections.
    Call this on application shutdown.
    """
    if _lib_config._engine:
        await _lib_config._engine.dispose()
        logger.info("library_disposed")
