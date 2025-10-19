"""
Example: Integrating open-skills into any FastAPI app (Library Mode)

This demonstrates how to embed open-skills as a library in your existing API.
"""

from fastapi import FastAPI
from open_skills.integrations.fastapi_integration import mount_open_skills

# Your existing FastAPI app
app = FastAPI(title="My Agent API")


# Your existing endpoints
@app.get("/")
async def root():
    return {"message": "My Agent API with Skills"}


@app.post("/chat")
async def chat(message: str):
    """Your chat endpoint - skills will be available here"""
    # Your agent logic here
    # Skills are auto-discovered via /.well-known/skills.json
    return {"response": "I can now use skills!"}


# Register open-skills on startup
@app.on_event("startup")
async def startup():
    # One-line integration!
    await mount_open_skills(
        app,
        prefix="/skills",              # API mounted at /skills/*
        skills_dir="./skills",         # Auto-register from folder
        auto_register=True,            # Register on startup
        auto_publish=True,             # Auto-publish versions
        database_url="postgresql+asyncpg://localhost/mydb",
    )
    # That's it! Skills are now:
    # - Auto-registered from ./skills folder
    # - Discoverable at /.well-known/skills.json
    # - Manageable via /skills/* API
    # - Executable via your agent


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
