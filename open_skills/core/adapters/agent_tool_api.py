"""
Universal tool manifest and agent integration API.
Provides standard tool contracts compatible with any LLM framework.
"""

from typing import Dict, Any, List, Optional
from uuid import UUID
from datetime import datetime, timezone

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from open_skills.core.telemetry import logger
from open_skills.core.library import get_config
from open_skills.db.models import SkillVersion, Skill, User


async def manifest_json(
    db: Optional[AsyncSession] = None,
    user_id: Optional[UUID] = None,
    org_id: Optional[UUID] = None,
    published_only: bool = True,
) -> Dict[str, Any]:
    """
    Generate the .well-known/skills.json manifest.

    This is the primary discovery mechanism for agents.

    Args:
        db: Database session (uses library config if None)
        user_id: Filter by user access
        org_id: Filter by organization access
        published_only: Only include published versions

    Returns:
        Tool manifest dictionary

    Example:
        ```python
        # In FastAPI endpoint
        @app.get("/.well-known/skills.json")
        async def skills_manifest():
            return await manifest_json(published_only=True)
        ```
    """
    # Get or create DB session
    if db is None:
        config = get_config()
        async for session in config.get_db():
            return await manifest_json(
                db=session,
                user_id=user_id,
                org_id=org_id,
                published_only=published_only,
            )

    tools = await as_agent_tools(
        db=db,
        user_id=user_id,
        org_id=org_id,
        published_only=published_only,
    )

    return {
        "version": "2025-10-01",
        "provider": "open-skills",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "tools": tools,
    }


async def as_agent_tools(
    db: Optional[AsyncSession] = None,
    user_id: Optional[UUID] = None,
    org_id: Optional[UUID] = None,
    published_only: bool = True,
    name_format: str = "versioned",  # "versioned" or "simple"
) -> List[Dict[str, Any]]:
    """
    Convert skill versions to agent tool definitions.

    Args:
        db: Database session (uses library config if None)
        user_id: Filter by user access
        org_id: Filter by organization access
        published_only: Only include published versions
        name_format: Tool naming format:
            - "versioned": skill:name@version (e.g., "skill:excel_to_pptx@1.0.0")
            - "simple": skill:name (e.g., "skill:excel_to_pptx")

    Returns:
        List of tool definitions compatible with most LLM frameworks

    Example:
        ```python
        # Get tools for agent registration
        tools = await as_agent_tools(published_only=True)

        # Register with your agent framework
        for tool in tools:
            agent.register_tool(
                name=tool["name"],
                description=tool["description"],
                args_schema=tool["args_schema"],
            )
        ```
    """
    # Get or create DB session
    if db is None:
        config = get_config()
        async for session in config.get_db():
            return await as_agent_tools(
                db=session,
                user_id=user_id,
                org_id=org_id,
                published_only=published_only,
                name_format=name_format,
            )

    # Build query
    query = select(SkillVersion, Skill).join(
        Skill, SkillVersion.skill_id == Skill.id
    )

    # Filter by published status
    if published_only:
        query = query.where(SkillVersion.is_published == True)  # noqa: E712

    # Filter by visibility (user/org access)
    if user_id or org_id:
        conditions = []
        if user_id:
            conditions.append(Skill.owner_id == user_id)
        if org_id:
            conditions.append(
                and_(
                    Skill.org_id == org_id,
                    Skill.visibility == "org",
                )
            )
        if conditions:
            from sqlalchemy import or_
            query = query.where(or_(*conditions))

    # Order by skill name and version (descending)
    query = query.order_by(Skill.name, SkillVersion.created_at.desc())

    result = await db.execute(query)
    rows = result.all()

    # Convert to tool definitions
    tools = []
    seen_skills = set()  # Track skills if using simple names

    for skill_version, skill in rows:
        metadata = skill_version.metadata_yaml or {}

        # Skip if we've already included this skill (simple name mode)
        if name_format == "simple" and skill.name in seen_skills:
            continue

        # Build tool name
        if name_format == "versioned":
            tool_name = f"skill:{skill.name}@{skill_version.version}"
        else:
            tool_name = f"skill:{skill.name}"
            seen_skills.add(skill.name)

        # Build args schema from metadata inputs
        properties = {}
        required = []

        # Always include skill_version_id (hidden from LLM but needed for execution)
        properties["skill_version_id"] = {
            "type": "string",
            "description": "Internal: skill version ID",
            "const": str(skill_version.id),
        }

        # Add inputs from metadata
        for input_spec in metadata.get("inputs", []):
            input_name = input_spec.get("name", input_spec.get("type", "input"))
            input_type = input_spec.get("type", "string")

            # Map skill types to JSON schema types
            json_type = _map_skill_type_to_json(input_type)

            properties[input_name] = {
                "type": json_type,
                "description": input_spec.get("description", f"{input_name} input"),
            }

            # Add to required if not optional
            if not input_spec.get("optional", False):
                required.append(input_name)

        # Build tool definition
        tool = {
            "name": tool_name,
            "title": metadata.get("name", skill.name).replace("_", " ").title(),
            "description": skill_version.description or metadata.get("description", ""),
            "args_schema": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
            "io": {
                "inputs": metadata.get("inputs", []),
                "outputs": metadata.get("outputs", []),
            },
            "skill_version_id": str(skill_version.id),
            "skill_id": str(skill.id),
            "version": skill_version.version,
            "visibility": skill.visibility,
            "tags": metadata.get("tags", []),
        }

        tools.append(tool)

    logger.info(
        "agent_tools_generated",
        count=len(tools),
        user_id=str(user_id) if user_id else None,
        org_id=str(org_id) if org_id else None,
    )

    return tools


def _map_skill_type_to_json(skill_type: str) -> str:
    """Map skill input/output types to JSON schema types."""
    type_map = {
        "text": "string",
        "number": "number",
        "integer": "integer",
        "boolean": "boolean",
        "file": "string",  # URL or path
        "object": "object",
        "array": "array",
    }
    return type_map.get(skill_type.lower(), "string")


def to_openai_function(tool: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert a tool definition to OpenAI function calling format (LEGACY).

    ⚠️ DEPRECATED: Use to_openai_tool() instead for the modern tools API.

    Args:
        tool: Tool definition from as_agent_tools()

    Returns:
        OpenAI function definition (legacy format)

    Example:
        ```python
        tools = await as_agent_tools()
        openai_functions = [to_openai_function(t) for t in tools]

        # Legacy format (deprecated)
        response = client.chat.completions.create(
            model="gpt-4",
            messages=messages,
            functions=openai_functions,  # Old parameter
        )
        ```
    """
    return {
        "name": tool["name"],
        "description": tool["description"],
        "parameters": tool["args_schema"],
    }


def to_openai_tool(tool: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert a tool definition to OpenAI tools format (current API).

    This is the modern format for OpenAI's chat completions API.

    Args:
        tool: Tool definition from as_agent_tools()

    Returns:
        OpenAI tool definition

    Example:
        ```python
        from open_skills import as_agent_tools, to_openai_tool
        import openai

        # Get tools
        tools = await as_agent_tools()
        openai_tools = [to_openai_tool(t) for t in tools]

        # Use with OpenAI (current API)
        client = openai.AsyncOpenAI()
        response = await client.chat.completions.create(
            model="gpt-4",
            messages=[{"role": "user", "content": "Help me..."}],
            tools=openai_tools,  # Modern parameter
        )

        # Check for tool calls
        if response.choices[0].message.tool_calls:
            for tool_call in response.choices[0].message.tool_calls:
                function_name = tool_call.function.name
                arguments = json.loads(tool_call.function.arguments)
                # Execute the skill...
        ```
    """
    return {
        "type": "function",
        "function": {
            "name": tool["name"],
            "description": tool["description"],
            "parameters": tool["args_schema"],
        }
    }


def to_anthropic_tool(tool: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert a tool definition to Anthropic tool format.

    Args:
        tool: Tool definition from as_agent_tools()

    Returns:
        Anthropic tool definition

    Example:
        ```python
        tools = await as_agent_tools()
        anthropic_tools = [to_anthropic_tool(t) for t in tools]

        # Use with Anthropic
        response = client.messages.create(
            model="claude-3-opus-20240229",
            messages=messages,
            tools=anthropic_tools,
        )
        ```
    """
    return {
        "name": tool["name"],
        "description": tool["description"],
        "input_schema": tool["args_schema"],
    }


def to_langchain_tool(tool: Dict[str, Any]):
    """
    Convert a tool definition to LangChain tool format.

    Args:
        tool: Tool definition from as_agent_tools()

    Returns:
        LangChain StructuredTool

    Example:
        ```python
        from open_skills.core.adapters.agent_tool_api import as_agent_tools, to_langchain_tool

        tools = await as_agent_tools()
        langchain_tools = [to_langchain_tool(t) for t in tools]

        # Use with LangChain
        agent = create_react_agent(llm, langchain_tools, prompt)
        ```

    Note:
        Requires langchain package: pip install langchain
    """
    try:
        from langchain.tools import StructuredTool
        from pydantic import BaseModel, create_model
    except ImportError:
        raise RuntimeError(
            "langchain package required. Install with: pip install langchain"
        )

    # Create Pydantic model from args schema
    fields = {}
    for prop_name, prop_spec in tool["args_schema"]["properties"].items():
        fields[prop_name] = (str, ...)  # Simplified - all strings for now

    ArgsModel = create_model(f"{tool['name']}_Args", **fields)

    # Create callable (will be implemented by executor integration)
    async def _run(**kwargs):
        from open_skills.core.executor import SkillExecutor
        from open_skills.core.library import get_config
        from open_skills.core.manager import SkillManager

        version_id = UUID(kwargs.get("skill_version_id"))

        config = get_config()
        async for db in config.get_db():
            manager = SkillManager(db)
            executor = SkillExecutor(db)

            version = await manager.get_skill_version(version_id)
            result = await executor.execute_one(version, kwargs)

            return result.get("outputs", {})

    return StructuredTool(
        name=tool["name"],
        description=tool["description"],
        args_schema=ArgsModel,
        coroutine=_run,
    )
