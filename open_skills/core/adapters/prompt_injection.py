"""
Prompt injection utilities for skill context awareness.

Provides functions to serialize skill manifests into formats suitable for
injection into agent system prompts or structured tool parameters.
"""

from typing import Dict, Any, List, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from open_skills.core.adapters.agent_tool_api import as_agent_tools
from open_skills.core.library import get_config
from open_skills.core.telemetry import get_logger

logger = get_logger(__name__)


async def manifest_to_prompt(
    db: Optional[AsyncSession] = None,
    user_id: Optional[UUID] = None,
    org_id: Optional[UUID] = None,
    published_only: bool = True,
    format: str = "detailed",  # "detailed", "compact", "numbered"
) -> str:
    """
    Convert skill manifest to human-readable text for system prompt injection.

    This allows agents to be context-aware of available skills before making
    tool calling decisions.

    Args:
        db: Database session (uses library config if None)
        user_id: Filter by user access
        org_id: Filter by organization access
        published_only: Only include published versions
        format: Output format:
            - "detailed": Full descriptions with inputs/outputs
            - "compact": Name and one-line description
            - "numbered": Numbered list with descriptions

    Returns:
        Formatted string describing available skills

    Example:
        ```python
        from open_skills.core.adapters.prompt_injection import manifest_to_prompt

        # Get skills context
        skills_context = await manifest_to_prompt(
            user_id=current_user.id,
            format="detailed"
        )

        # Inject into system prompt
        system_prompt = f'''
        You are an AI agent with access to the following skills:

        {skills_context}

        Use these skills to help the user accomplish their tasks.
        '''
        ```
    """
    # Get tools
    tools = await as_agent_tools(
        db=db,
        user_id=user_id,
        org_id=org_id,
        published_only=published_only,
        name_format="simple",  # Use simple names for readability
    )

    if not tools:
        return "No skills are currently available."

    # Format based on style
    if format == "compact":
        lines = []
        for tool in tools:
            lines.append(f"• **{tool['name']}** — {tool['description']}")
        result = "\n".join(lines)

    elif format == "numbered":
        lines = []
        for i, tool in enumerate(tools, 1):
            lines.append(f"{i}. **{tool['name']}** — {tool['description']}")
        result = "\n".join(lines)

    else:  # detailed
        lines = []
        for i, tool in enumerate(tools, 1):
            lines.append(f"{i}. **{tool['name']}**")
            lines.append(f"   Description: {tool['description']}")

            # Extract inputs
            inputs = tool.get("io", {}).get("inputs", [])
            if inputs:
                input_strs = []
                for inp in inputs:
                    inp_name = inp.get("name", inp.get("type", "input"))
                    inp_type = inp.get("type", "any")
                    inp_desc = inp.get("description", "")
                    if inp_desc:
                        input_strs.append(f"{inp_name} ({inp_type}): {inp_desc}")
                    else:
                        input_strs.append(f"{inp_name} ({inp_type})")
                lines.append(f"   Inputs: {', '.join(input_strs)}")

            # Extract outputs
            outputs = tool.get("io", {}).get("outputs", [])
            if outputs:
                output_strs = []
                for out in outputs:
                    out_name = out.get("name", out.get("type", "output"))
                    out_type = out.get("type", "any")
                    output_strs.append(f"{out_name} ({out_type})")
                lines.append(f"   Outputs: {', '.join(output_strs)}")

            # Add tags if available
            tags = tool.get("tags", [])
            if tags:
                lines.append(f"   Tags: {', '.join(tags)}")

            lines.append("")  # Blank line between skills

        result = "\n".join(lines)

    logger.info(
        "manifest_to_prompt_generated",
        tool_count=len(tools),
        format=format,
        user_id=str(user_id) if user_id else None,
        org_id=str(org_id) if org_id else None,
    )

    return result


async def manifest_to_tools(
    db: Optional[AsyncSession] = None,
    user_id: Optional[UUID] = None,
    org_id: Optional[UUID] = None,
    published_only: bool = True,
    framework: str = "generic",  # "generic", "openai", "anthropic", "langchain"
) -> List[Dict[str, Any]]:
    """
    Convert skill manifest to structured tools array for framework integration.

    This is an alias for as_agent_tools() with framework-specific conversion.

    Args:
        db: Database session
        user_id: Filter by user access
        org_id: Filter by organization access
        published_only: Only include published versions
        framework: Target framework format

    Returns:
        List of tool definitions in framework-specific format

    Example:
        ```python
        from open_skills.core.adapters.prompt_injection import manifest_to_tools

        # Get tools for OpenAI
        tools = await manifest_to_tools(framework="openai")

        # Use in chat completion
        response = await client.chat.completions.create(
            model="gpt-4",
            messages=[...],
            tools=tools,
        )
        ```
    """
    from open_skills.core.adapters.agent_tool_api import (
        to_openai_tool,
        to_anthropic_tool,
        to_langchain_tool,
    )

    # Get generic tools
    tools = await as_agent_tools(
        db=db,
        user_id=user_id,
        org_id=org_id,
        published_only=published_only,
    )

    # Convert to framework-specific format
    if framework == "openai":
        return [to_openai_tool(t) for t in tools]
    elif framework == "anthropic":
        return [to_anthropic_tool(t) for t in tools]
    elif framework == "langchain":
        return [to_langchain_tool(t) for t in tools]
    else:
        return tools


async def inject_skills_context(
    system_prompt: str,
    db: Optional[AsyncSession] = None,
    user_id: Optional[UUID] = None,
    org_id: Optional[UUID] = None,
    published_only: bool = True,
    format: str = "detailed",
    section_title: str = "Available Skills",
) -> str:
    """
    Inject skills context into an existing system prompt.

    Args:
        system_prompt: Base system prompt to augment
        db: Database session
        user_id: Filter by user access
        org_id: Filter by organization access
        published_only: Only include published versions
        format: Prompt format (detailed, compact, numbered)
        section_title: Title for the skills section

    Returns:
        Augmented system prompt with skills context

    Example:
        ```python
        from open_skills.core.adapters.prompt_injection import inject_skills_context

        base_prompt = "You are a helpful AI assistant."

        # Add skills context
        full_prompt = await inject_skills_context(
            base_prompt,
            user_id=current_user.id,
        )

        # Use with agent
        agent = Agent(system_prompt=full_prompt)
        ```
    """
    skills_context = await manifest_to_prompt(
        db=db,
        user_id=user_id,
        org_id=org_id,
        published_only=published_only,
        format=format,
    )

    if skills_context == "No skills are currently available.":
        # Don't modify prompt if no skills
        logger.warning("inject_skills_context_no_skills")
        return system_prompt

    # Inject skills section
    augmented_prompt = f"""{system_prompt}

## {section_title}

You have access to the following skills:

{skills_context}

When a task requires capabilities provided by these skills, use them by making tool calls.
Always explain what you're doing and show results to the user.
"""

    logger.info(
        "inject_skills_context_success",
        original_length=len(system_prompt),
        augmented_length=len(augmented_prompt),
        skills_added=skills_context.count("**"),  # Approximate skill count
    )

    return augmented_prompt


def format_skill_summary(tool: Dict[str, Any]) -> str:
    """
    Format a single skill as a compact summary.

    Args:
        tool: Tool definition from as_agent_tools()

    Returns:
        One-line summary of the skill

    Example:
        ```python
        tool = {"name": "summarize", "description": "Summarizes text"}
        summary = format_skill_summary(tool)
        # "summarize — Summarizes text"
        ```
    """
    return f"{tool['name']} — {tool['description']}"


def format_skill_detailed(tool: Dict[str, Any]) -> str:
    """
    Format a single skill with full details.

    Args:
        tool: Tool definition from as_agent_tools()

    Returns:
        Multi-line detailed description of the skill
    """
    lines = [f"**{tool['name']}**"]
    lines.append(f"Description: {tool['description']}")

    # Inputs
    inputs = tool.get("io", {}).get("inputs", [])
    if inputs:
        input_strs = [
            f"{inp.get('name', inp.get('type'))} ({inp.get('type')})"
            for inp in inputs
        ]
        lines.append(f"Inputs: {', '.join(input_strs)}")

    # Outputs
    outputs = tool.get("io", {}).get("outputs", [])
    if outputs:
        output_strs = [
            f"{out.get('name', out.get('type'))} ({out.get('type')})"
            for out in outputs
        ]
        lines.append(f"Outputs: {', '.join(output_strs)}")

    return "\n".join(lines)


async def get_skills_session_metadata(
    db: Optional[AsyncSession] = None,
    user_id: Optional[UUID] = None,
    org_id: Optional[UUID] = None,
    published_only: bool = True,
) -> Dict[str, Any]:
    """
    Get metadata about available skills for session logging.

    This is useful for observability — logging which skills were available
    when a session started.

    Args:
        db: Database session
        user_id: Filter by user access
        org_id: Filter by organization access
        published_only: Only include published versions

    Returns:
        Dictionary with session metadata

    Example:
        ```python
        metadata = await get_skills_session_metadata(user_id=user.id)
        logger.info("session_started", **metadata)
        # Logs: skill_count=5, skill_names=["skill1", "skill2", ...]
        ```
    """
    tools = await as_agent_tools(
        db=db,
        user_id=user_id,
        org_id=org_id,
        published_only=published_only,
    )

    return {
        "skill_count": len(tools),
        "skill_names": [t["name"] for t in tools],
        "skill_ids": [t["skill_version_id"] for t in tools],
        "tags": list(set(tag for t in tools for tag in t.get("tags", []))),
    }
