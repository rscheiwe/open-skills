"""
Example: Skill context awareness via prompt injection.

This demonstrates how to make agents aware of available skills by injecting
skill metadata into system prompts.
"""

import asyncio
from open_skills import (
    configure,
    register_skills_from_folder,
    manifest_to_prompt,
    inject_skills_context,
    get_skills_session_metadata,
)


async def basic_prompt_injection():
    """
    Basic example: Generate a skills-aware system prompt.
    """
    print("=" * 60)
    print("Basic Prompt Injection Example")
    print("=" * 60)

    # Setup
    configure(
        database_url="postgresql+asyncpg://localhost:5432/openskills",
        openai_api_key="sk-...",
        storage_root="./skills",
    )

    # Register skills
    await register_skills_from_folder("./skills", auto_publish=True)

    # Generate skills context
    skills_context = await manifest_to_prompt(
        published_only=True,
        format="detailed"  # or "compact", "numbered"
    )

    print("\n📋 Skills Context (detailed format):\n")
    print(skills_context)

    # Use in system prompt
    system_prompt = f"""You are a helpful AI assistant with access to specialized skills.

{skills_context}

When a user asks for help, consider which skills might be useful and use them appropriately.
"""

    print("\n" + "=" * 60)
    print("Complete System Prompt:")
    print("=" * 60)
    print(system_prompt)


async def compact_format_example():
    """
    Example: Use compact format for shorter prompts.
    """
    print("\n" + "=" * 60)
    print("Compact Format Example")
    print("=" * 60)

    configure(
        database_url="postgresql+asyncpg://localhost:5432/openskills",
        openai_api_key="sk-...",
    )

    # Compact format - good for saving tokens
    skills_context = await manifest_to_prompt(format="compact")

    print("\n📋 Skills Context (compact format):\n")
    print(skills_context)


async def inject_into_existing_prompt():
    """
    Example: Inject skills into an existing system prompt.
    """
    print("\n" + "=" * 60)
    print("Inject into Existing Prompt")
    print("=" * 60)

    configure(
        database_url="postgresql+asyncpg://localhost:5432/openskills",
        openai_api_key="sk-...",
    )

    # Your existing system prompt
    base_prompt = """You are a professional AI assistant.
You are helpful, harmless, and honest.
You follow instructions carefully and explain your reasoning."""

    # Augment with skills context
    full_prompt = await inject_skills_context(
        base_prompt,
        format="numbered",
        section_title="🛠️ Available Tools"
    )

    print("\n📝 Augmented System Prompt:\n")
    print(full_prompt)


async def session_metadata_example():
    """
    Example: Log session metadata for observability.
    """
    print("\n" + "=" * 60)
    print("Session Metadata for Observability")
    print("=" * 60)

    configure(
        database_url="postgresql+asyncpg://localhost:5432/openskills",
        openai_api_key="sk-...",
    )

    # Get metadata about available skills
    metadata = await get_skills_session_metadata(published_only=True)

    print("\n📊 Session Metadata:\n")
    print(f"Total skills: {metadata['skill_count']}")
    print(f"Skill names: {', '.join(metadata['skill_names'])}")
    print(f"Available tags: {', '.join(metadata['tags'])}")

    # This would typically be logged to Langfuse or similar
    # logger.info("agent_session_started", **metadata)


async def multi_tenant_example():
    """
    Example: Different skills per user/organization.
    """
    print("\n" + "=" * 60)
    print("Multi-Tenant Skill Context")
    print("=" * 60)

    configure(
        database_url="postgresql+asyncpg://localhost:5432/openskills",
        openai_api_key="sk-...",
    )

    from uuid import uuid4

    # Simulate different users
    user_1_id = uuid4()
    org_1_id = uuid4()

    # Get skills for specific user/org
    user_skills = await manifest_to_prompt(
        user_id=user_1_id,
        org_id=org_1_id,
        format="compact"
    )

    print(f"\n📋 Skills available to user {user_1_id}:\n")
    print(user_skills)


async def framework_integration_example():
    """
    Example: Get skills in framework-specific format.
    """
    print("\n" + "=" * 60)
    print("Framework-Specific Integration")
    print("=" * 60)

    configure(
        database_url="postgresql+asyncpg://localhost:5432/openskills",
        openai_api_key="sk-...",
    )

    from open_skills import manifest_to_tools

    # Get tools for OpenAI
    openai_tools = await manifest_to_tools(framework="openai")
    print(f"\n🤖 OpenAI format: {len(openai_tools)} tools")

    # Get tools for Anthropic
    anthropic_tools = await manifest_to_tools(framework="anthropic")
    print(f"🤖 Anthropic format: {len(anthropic_tools)} tools")

    # Generic format
    generic_tools = await manifest_to_tools(framework="generic")
    print(f"🤖 Generic format: {len(generic_tools)} tools")


async def real_world_agent_example():
    """
    Example: Complete agent setup with prompt injection.
    """
    print("\n" + "=" * 60)
    print("Real-World Agent Setup")
    print("=" * 60)

    configure(
        database_url="postgresql+asyncpg://localhost:5432/openskills",
        openai_api_key="sk-...",
    )

    # Register skills
    await register_skills_from_folder("./skills", auto_publish=True)

    # Log session metadata
    metadata = await get_skills_session_metadata()
    print(f"\n📊 Session started with {metadata['skill_count']} skills available")

    # Create context-aware system prompt
    base_prompt = """You are an AI assistant that helps users accomplish tasks.
You have access to specialized skills that extend your capabilities.
Think step-by-step about which skills to use."""

    system_prompt = await inject_skills_context(
        base_prompt,
        format="detailed"
    )

    # Get tools for framework
    from open_skills import manifest_to_tools
    tools = await manifest_to_tools(framework="openai")

    print(f"\n✅ Agent configured with:")
    print(f"   - System prompt: {len(system_prompt)} chars")
    print(f"   - Available tools: {len(tools)}")
    print(f"   - Skills: {', '.join(metadata['skill_names'])}")

    # Now use with your agent framework
    # agent = Agent(system_prompt=system_prompt, tools=tools)


if __name__ == "__main__":
    import sys

    examples = {
        "basic": basic_prompt_injection,
        "compact": compact_format_example,
        "inject": inject_into_existing_prompt,
        "metadata": session_metadata_example,
        "tenant": multi_tenant_example,
        "framework": framework_integration_example,
        "real": real_world_agent_example,
    }

    if len(sys.argv) > 1 and sys.argv[1] in examples:
        asyncio.run(examples[sys.argv[1]]())
    else:
        print("Available examples:")
        for name in examples.keys():
            print(f"  python prompt_injection_example.py {name}")
        print("\nRunning all examples...")
        asyncio.run(basic_prompt_injection())
        asyncio.run(compact_format_example())
        asyncio.run(inject_into_existing_prompt())
        asyncio.run(session_metadata_example())
        asyncio.run(real_world_agent_example())
