"""
Integration tests for API endpoints.
"""

import pytest
from httpx import AsyncClient

from open_skills.main import app


@pytest.mark.asyncio
async def test_health_endpoint():
    """Test health check endpoint."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"


@pytest.mark.asyncio
async def test_root_endpoint():
    """Test root endpoint."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "name" in data
        assert "version" in data


@pytest.mark.asyncio
async def test_stats_endpoint():
    """Test stats endpoint."""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/api/stats")
        assert response.status_code == 200
        data = response.json()
        assert "total_skills" in data
        assert "total_runs" in data
