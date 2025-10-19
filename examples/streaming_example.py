"""
Example: Real-time skill execution streaming with SSE.

This demonstrates:
1. Executing a skill
2. Streaming real-time updates via Server-Sent Events
3. Processing different event types (status, log, output, artifact, complete)
"""

import asyncio
import httpx
from uuid import UUID


async def execute_and_stream(skill_version_id: UUID, input_data: dict):
    """
    Execute a skill and stream real-time updates.

    Args:
        skill_version_id: Skill version UUID to execute
        input_data: Input payload for the skill
    """
    base_url = "http://localhost:8000/api"

    async with httpx.AsyncClient(timeout=300.0) as client:
        # 1. Start execution
        print(f"🚀 Starting execution of skill {skill_version_id}...")
        run_response = await client.post(
            f"{base_url}/runs",
            json={
                "skill_version_ids": [str(skill_version_id)],
                "input": input_data,
            }
        )
        run_response.raise_for_status()
        run_data = run_response.json()
        run_id = run_data["results"][0]["run_id"]
        print(f"✓ Run created: {run_id}")

        # 2. Stream execution events
        print(f"\n📡 Streaming events for run {run_id}...\n")

        async with client.stream("GET", f"{base_url}/runs/{run_id}/stream") as response:
            response.raise_for_status()

            async for line in response.aiter_lines():
                # SSE format: "event: type\ndata: json\n\n"
                if line.startswith("event:"):
                    event_type = line.split(":", 1)[1].strip()
                elif line.startswith("data:"):
                    import json
                    event_data = json.loads(line.split(":", 1)[1].strip())

                    # Handle different event types
                    if event_type == "status":
                        status = event_data.get("status")
                        print(f"📊 Status: {status}")

                    elif event_type == "log":
                        log_line = event_data.get("line")
                        stream = event_data.get("stream", "stdout")
                        print(f"📝 [{stream}] {log_line}")

                    elif event_type == "output":
                        key = event_data.get("key")
                        value = event_data.get("value")
                        print(f"📤 Output: {key} = {value}")

                    elif event_type == "artifact":
                        filename = event_data.get("filename")
                        size_bytes = event_data.get("size_bytes", 0)
                        size_kb = size_bytes / 1024
                        print(f"📎 Artifact: {filename} ({size_kb:.2f} KB)")

                    elif event_type == "error":
                        error = event_data.get("error")
                        print(f"❌ Error: {error}")
                        if "traceback" in event_data:
                            print(f"   Traceback: {event_data['traceback'][:200]}...")

                    elif event_type == "complete":
                        status = event_data.get("status")
                        duration_ms = event_data.get("duration_ms")
                        outputs = event_data.get("outputs", {})
                        print(f"\n✅ Complete!")
                        print(f"   Status: {status}")
                        print(f"   Duration: {duration_ms}ms")
                        print(f"   Outputs: {outputs}")
                        break  # Stop streaming

                    elif event_type == "keepalive":
                        # Keepalive ping (no action needed)
                        pass


async def main():
    """Run the streaming example."""
    # Example: Replace with your actual skill version ID
    skill_version_id = UUID("00000000-0000-0000-0000-000000000000")

    input_data = {
        "text": "Hello, world! This is a streaming test.",
    }

    try:
        await execute_and_stream(skill_version_id, input_data)
    except httpx.HTTPStatusError as e:
        print(f"HTTP error: {e.response.status_code} - {e.response.text}")
    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    print("=" * 60)
    print("Open-Skills Streaming Example")
    print("=" * 60)
    print()
    asyncio.run(main())
