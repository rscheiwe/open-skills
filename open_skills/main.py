"""
Main entry point - delegates to service.main for backwards compatibility.

For library mode, import:
    from open_skills.integrations.fastapi_integration import mount_open_skills

For service mode, run:
    python -m open_skills.service.main
"""

# Re-export the service app for backwards compatibility
from open_skills.service.main import app

__all__ = ["app"]


if __name__ == "__main__":
    import uvicorn
    from open_skills.config import settings

    uvicorn.run(
        "open_skills.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.reload,
        workers=settings.workers if not settings.reload else 1,
        log_level=settings.log_level.lower(),
    )
