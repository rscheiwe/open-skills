"""
Example: Using open-skills with OpenAI Agents SDK.

This demonstrates integration with OpenAI's agent framework (not Assistants API)
using the Swarm pattern or custom agent loops.

Requires: pip install openai
"""

import asyncio
import json
from typing import Any, Dict
from uuid import UUID

import openai

from open_skills import (
    configure,
    register_skills_from_folder,
    as_agent_tools,
    to_openai_tool,
    inject_skills_context,
    get_skills_session_metadata,
)
from open_skills.core.manager import SkillManager
from open_skills.core.executor import SkillExecutor
from open_skills.core.library import get_config


async def setup():
    """Setup open-skills in library mode."""
    configure(
        database_url="postgresql+asyncpg://localhost:5432/openskills",
        openai_api_key="sk-...",  # Your OpenAI API key
        storage_root="./skills",
    )

    # Auto-register skills from folder
    versions = await register_skills_from_folder(
        "./skills",
        auto_publish=True,
        visibility="org",
    )
    print(f"✓ Registered {len(versions)} skills")


async def execute_skill_from_tool_call(tool_call, db):
    """
    Execute a skill based on OpenAI tool call.

    Args:
        tool_call: OpenAI tool call object
        db: Database session

    Returns:
        Skill execution result
    """
    function_name = tool_call.function.name
    arguments = json.loads(tool_call.function.arguments)

    print(f"\n🔧 Executing skill: {function_name}")
    print(f"   Arguments: {arguments}")

    # Get skill version ID from arguments
    skill_version_id = UUID(arguments.pop("skill_version_id"))

    # Execute the skill
    manager = SkillManager(db)
    executor = SkillExecutor(db)

    version = await manager.get_skill_version(skill_version_id)
    result = await executor.execute_one(version, arguments)

    print(f"✓ Execution completed in {result['duration_ms']}ms")
    print(f"   Status: {result['status']}")
    print(f"   Outputs: {result['outputs']}")

    return result


async def run_agent_loop():
    """
    Run a simple agent loop with tool calling.

    This is a basic implementation of an agent pattern similar to OpenAI's
    Swarm framework or custom agent loops.
    """
    # Setup
    await setup()

    # Get tools
    tools = await as_agent_tools(published_only=True)
    openai_tools = [to_openai_tool(t) for t in tools]

    print(f"\n📋 Available tools: {len(openai_tools)}")
    for tool in tools:
        print(f"   • {tool['name']}: {tool['description'][:60]}...")

    # Log session metadata for observability
    metadata = await get_skills_session_metadata()
    print(f"\n📊 Session metadata: {metadata['skill_count']} skills, tags: {metadata['tags']}")

    # Create context-aware system prompt
    base_system_prompt = (
        "You are a helpful assistant with access to various skills. "
        "Use the available tools to help the user accomplish their tasks. "
        "Always explain what you're doing and show the results."
    )

    # Inject skills context into system prompt
    system_prompt = await inject_skills_context(
        base_system_prompt,
        format="compact"
    )

    print(f"\n📝 System prompt length: {len(system_prompt)} chars")

    # Initialize OpenAI client
    client = openai.AsyncOpenAI()

    # Agent conversation
    messages = [
        {
            "role": "system",
            "content": system_prompt
        },
        {
            "role": "user",
            "content": "Can you help me summarize this text: 'Open-skills is a framework-agnostic skills subsystem for Python agents...'"
        }
    ]

    print("\n" + "="*60)
    print("🤖 Agent Loop Starting")
    print("="*60)

    max_iterations = 5
    iteration = 0

    config = get_config()
    async for db in config.get_db():
        while iteration < max_iterations:
            iteration += 1
            print(f"\n📍 Iteration {iteration}")

            # Call OpenAI with tools
            response = await client.chat.completions.create(
                model="gpt-4",
                messages=messages,
                tools=openai_tools,
                tool_choice="auto",  # Let the model decide
            )

            message = response.choices[0].message
            messages.append(message)

            # Check if we're done
            if message.content and not message.tool_calls:
                print(f"\n💬 Assistant: {message.content}")
                break

            # Handle tool calls
            if message.tool_calls:
                print(f"\n🔨 Tool calls requested: {len(message.tool_calls)}")

                for tool_call in message.tool_calls:
                    # Execute the skill
                    result = await execute_skill_from_tool_call(tool_call, db)

                    # Add tool result to conversation
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": tool_call.function.name,
                        "content": json.dumps({
                            "status": result["status"],
                            "outputs": result["outputs"],
                            "duration_ms": result["duration_ms"],
                        })
                    })

            # Continue loop to get final response

        if iteration >= max_iterations:
            print("\n⚠️ Max iterations reached")

    print("\n" + "="*60)
    print("✅ Agent Loop Complete")
    print("="*60)


async def simple_tool_calling_example():
    """
    Simple example of tool calling with OpenAI.

    This shows the basic pattern without the full agent loop.
    """
    await setup()

    # Get tools
    tools = await as_agent_tools(published_only=True)
    openai_tools = [to_openai_tool(t) for t in tools]

    # Call OpenAI
    client = openai.AsyncOpenAI()
    response = await client.chat.completions.create(
        model="gpt-4",
        messages=[
            {"role": "user", "content": "Summarize this: 'Hello world'"}
        ],
        tools=openai_tools,
    )

    # Check for tool calls
    message = response.choices[0].message

    if message.tool_calls:
        print(f"🔨 Model wants to call {len(message.tool_calls)} tool(s)")

        config = get_config()
        async for db in config.get_db():
            for tool_call in message.tool_calls:
                result = await execute_skill_from_tool_call(tool_call, db)
                print(f"✓ Result: {result['outputs']}")
    else:
        print(f"💬 Direct response: {message.content}")


async def swarm_pattern_example():
    """
    Example using a Swarm-like pattern with skill handoffs.

    This demonstrates a more advanced pattern where skills can hand off
    to other skills or return to the main agent.
    """
    await setup()

    # Define agent with tools
    class SkillAgent:
        def __init__(self, name: str, instructions: str, tools: list):
            self.name = name
            self.instructions = instructions
            self.tools = tools

    # Get all available skills as tools
    all_tools = await as_agent_tools(published_only=True)
    openai_tools = [to_openai_tool(t) for t in all_tools]

    # Create specialized agent
    summarization_agent = SkillAgent(
        name="Summarization Specialist",
        instructions="You specialize in summarizing text. Use available skills to help users.",
        tools=[t for t in openai_tools if "summar" in t["function"]["name"].lower()],
    )

    print(f"\n🤖 Agent: {summarization_agent.name}")
    print(f"   Tools available: {len(summarization_agent.tools)}")

    # Use the agent
    client = openai.AsyncOpenAI()

    messages = [
        {"role": "system", "content": summarization_agent.instructions},
        {"role": "user", "content": "Summarize this document for me..."}
    ]

    response = await client.chat.completions.create(
        model="gpt-4",
        messages=messages,
        tools=summarization_agent.tools,
    )

    print(f"   Response: {response.choices[0].message.content}")


if __name__ == "__main__":
    print("="*60)
    print("OpenAI Agents SDK + open-skills Integration")
    print("="*60)

    # Choose which example to run
    import sys

    if len(sys.argv) > 1:
        mode = sys.argv[1]
    else:
        mode = "agent"

    if mode == "simple":
        print("\n🔹 Running Simple Tool Calling Example")
        asyncio.run(simple_tool_calling_example())
    elif mode == "swarm":
        print("\n🔹 Running Swarm Pattern Example")
        asyncio.run(swarm_pattern_example())
    else:
        print("\n🔹 Running Full Agent Loop Example")
        asyncio.run(run_agent_loop())

    print("\n💡 Try other modes:")
    print("   python openai_agents_sdk_example.py simple")
    print("   python openai_agents_sdk_example.py swarm")
    print("   python openai_agents_sdk_example.py agent")
