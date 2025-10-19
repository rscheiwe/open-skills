"""
Pytest configuration and fixtures.
"""

import asyncio
import pytest
from pathlib import Path

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from open_skills.config import settings
from open_skills.db.base import Base


# Override settings for testing
settings.postgres_url = "postgresql+asyncpg://postgres:postgres@localhost:5432/openskills_test"
settings.storage_root = Path("./test_storage")
settings.artifacts_root = Path("./test_artifacts")


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def test_engine():
    """Create test database engine."""
    engine = create_async_engine(
        settings.postgres_url,
        echo=False,
    )

    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    # Drop all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest.fixture
async def db_session(test_engine):
    """Create database session for tests."""
    async_session = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session() as session:
        yield session
        await session.rollback()


@pytest.fixture
def sample_skill_bundle(tmp_path: Path) -> Path:
    """Create a sample skill bundle for testing."""
    bundle_dir = tmp_path / "test_skill"
    bundle_dir.mkdir()

    # Create SKILL.md
    skill_md = bundle_dir / "SKILL.md"
    skill_md.write_text("""---
name: test_skill
version: 1.0.0
entrypoint: scripts/main.py
description: A test skill
inputs:
  - type: text
outputs:
  - type: text
tags: [test]
allow_network: false
---

# Test Skill

This is a test skill.
""")

    # Create scripts directory and entrypoint
    scripts_dir = bundle_dir / "scripts"
    scripts_dir.mkdir()

    main_py = scripts_dir / "main.py"
    main_py.write_text("""
async def run(input_payload):
    return {
        "outputs": {"result": "test"},
        "artifacts": []
    }
""")

    return bundle_dir
