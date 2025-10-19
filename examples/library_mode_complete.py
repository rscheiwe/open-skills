"""
Complete example of using open-skills in library mode.

This shows:
1. Manual configuration
2. Skill registration
3. Tool discovery
4. Skill execution
5. Integration with a custom agent
"""

import asyncio
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# Import open-skills components
from open_skills.core.library import configure, get_config
from open_skills.core.adapters.discovery import register_skills_from_folder
from open_skills.core.adapters.agent_tool_api import as_agent_tools, to_openai_function
from open_skills.core.executor import SkillExecutor
from open_skills.core.manager import SkillManager


# Step 1: Configure open-skills
async def setup_open_skills():
    """Configure and initialize open-skills"""
    configure(
        database_url="postgresql+asyncpg://localhost:5432/myapp",
        storage_root="./my_skills_storage",
        openai_api_key="sk-...",
    )

    # Register skills from folder
    versions = await register_skills_from_folder(
        "./skills",
        auto_publish=True,
        visibility="org",
    )

    print(f"Registered {len(versions)} skill versions")
    return versions


# Step 2: Create FastAPI app
app = FastAPI(title="My Custom Agent")


class ChatRequest(BaseModel):
    message: str
    use_skills: bool = True


class ChatResponse(BaseModel):
    response: str
    skills_used: list[str] = []


# Step 3: Get available tools
@app.get("/.well-known/skills.json")
async def get_skills_manifest():
    """Tool discovery endpoint for agents"""
    from open_skills.core.adapters.agent_tool_api import manifest_json
    return await manifest_json(published_only=True)


# Step 4: Chat endpoint with skill execution
@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """
    Chat endpoint that can use skills.

    This demonstrates how to:
    1. Discover available skills
    2. Let LLM decide which skills to use
    3. Execute skills
    4. Return results
    """
    config = get_config()

    async for db in config.get_db():
        # Get available tools
        tools = await as_agent_tools(db=db, published_only=True)

        if not req.use_skills or not tools:
            # Simple response without skills
            return ChatResponse(
                response=f"Echo: {req.message}",
                skills_used=[],
            )

        # Example: Check if message asks for a skill
        # (In production, use LLM to decide which tool to call)
        message_lower = req.message.lower()

        # Simple keyword matching (replace with LLM tool calling)
        if "summarize" in message_lower:
            # Find summarizer skill
            summarizer = next(
                (t for t in tools if "summariz" in t["name"].lower()),
                None
            )

            if summarizer:
                # Execute the skill
                manager = SkillManager(db)
                executor = SkillExecutor(db)

                from uuid import UUID
                version_id = UUID(summarizer["skill_version_id"])
                version = await manager.get_skill_version(version_id)

                result = await executor.execute_one(
                    version,
                    {"text": req.message}
                )

                return ChatResponse(
                    response=result.get("outputs", {}).get("summary", ""),
                    skills_used=[summarizer["name"]],
                )

        # Default response
        return ChatResponse(
            response=f"I understand: {req.message}. "
                    f"I have {len(tools)} skills available.",
            skills_used=[],
        )


# Step 5: Advanced - Direct OpenAI integration
@app.post("/chat/openai")
async def chat_with_openai(req: ChatRequest):
    """
    Example using OpenAI function calling with skills.

    Requires: pip install openai
    """
    try:
        import openai
    except ImportError:
        raise HTTPException(
            status_code=500,
            detail="OpenAI package required. Install with: pip install openai"
        )

    config = get_config()

    async for db in config.get_db():
        # Get tools in OpenAI format
        tools = await as_agent_tools(db=db, published_only=True)
        openai_functions = [to_openai_function(t) for t in tools]

        # Call OpenAI with function calling
        client = openai.AsyncOpenAI()

        response = await client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "user", "content": req.message}
            ],
            functions=openai_functions if req.use_skills else None,
        )

        # Handle function calls
        message = response.choices[0].message

        if message.function_call:
            # Execute the skill
            function_name = message.function_call.name
            import json
            function_args = json.loads(message.function_call.arguments)

            # Find the tool
            tool = next(
                (t for t in tools if t["name"] == function_name),
                None
            )

            if tool:
                from uuid import UUID
                manager = SkillManager(db)
                executor = SkillExecutor(db)

                version_id = UUID(tool["skill_version_id"])
                version = await manager.get_skill_version(version_id)

                result = await executor.execute_one(version, function_args)

                return ChatResponse(
                    response=str(result.get("outputs", {})),
                    skills_used=[function_name],
                )

        return ChatResponse(
            response=message.content or "",
            skills_used=[],
        )


# Startup
@app.on_event("startup")
async def startup():
    """Initialize on startup"""
    await setup_open_skills()
    print("✓ Open-skills configured and skills registered")
    print("✓ Available endpoints:")
    print("  - GET  /.well-known/skills.json  (tool discovery)")
    print("  - POST /chat                      (simple chat)")
    print("  - POST /chat/openai               (OpenAI integration)")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
