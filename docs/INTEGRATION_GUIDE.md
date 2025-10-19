## Open-Skills Integration Guide

Complete guide to integrating open-skills into any Python application.

## Table of Contents

1. [Overview](#overview)
2. [Library Mode vs Service Mode](#library-mode-vs-service-mode)
3. [Quick Start: Library Mode](#quick-start-library-mode)
4. [Quick Start: Service Mode](#quick-start-service-mode)
5. [Folder-Based Skill Registration](#folder-based-skill-registration)
6. [Tool Discovery](#tool-discovery)
7. [Skill Execution](#skill-execution)
8. [Framework-Specific Examples](#framework-specific-examples)
9. [Advanced Patterns](#advanced-patterns)

---

## Overview

Open-skills can be integrated into your application in two ways:

- **Library Mode**: Embedded directly in your Python app (in-process)
- **Service Mode**: Run as a separate microservice (out-of-process, REST API)

Both modes share the same skill format and execution engine.

---

## Library Mode vs Service Mode

### Library Mode (Recommended for Most Cases)

**Pros:**
- No network overhead
- Simpler deployment (single process)
- Direct Python API access
- Lower latency

**Cons:**
- Shares resources with your app
- Same Python process

**Use when:**
- Building a FastAPI/Flask app with agents
- Want minimal latency
- Prefer monolithic deployment

###  Mode (Sidecar)

**Pros:**
- Process isolation
- Language-agnostic clients (REST)
- Independent scaling
- Can serve multiple apps

**Cons:**
- Network overhead
- Additional deployment complexity

**Use when:**
- Multiple apps need to share skills
- Using non-Python agent frameworks
- Want independent scaling

---

## Quick Start: Library Mode

### 1. Install

```bash
pip install open-skills
```

### 2. Configure

```python
from open_skills.core.library import configure

configure(
    database_url="postgresql+asyncpg://localhost/mydb",
    storage_root="./skills_storage",
    openai_api_key="sk-...",
)
```

### 3. Register Skills

```python
from open_skills.core.adapters.discovery import register_skills_from_folder

# Auto-register all skills in ./skills folder
versions = await register_skills_from_folder(
    "./skills",
    auto_publish=True,
)
```

### 4. Mount to FastAPI (Optional)

```python
from fastapi import FastAPI
from open_skills.integrations.fastapi_integration import mount_open_skills

app = FastAPI()

await mount_open_skills(
    app,
    prefix="/skills",
    skills_dir="./skills",
    auto_register=True,
)
```

### 5. Discover & Execute

```python
from open_skills.core.adapters.agent_tool_api import as_agent_tools
from open_skills.core.executor import SkillExecutor

# Get available tools
tools = await as_agent_tools(published_only=True)

# Execute a skill
executor = SkillExecutor(db)
result = await executor.execute_one(
    skill_version,
    {"input_key": "value"}
)
```

---

## Quick Start: Service Mode

### 1. Run Service

```bash
# Using Docker Compose
docker-compose up -d

# Or directly
python -m open_skills.service.main
```

### 2. Discover Tools (from your app)

```python
import httpx

async with httpx.AsyncClient() as client:
    response = await client.get("http://localhost:8000/.well-known/skills.json")
    tools = response.json()["tools"]
```

### 3. Execute Skills (from your app)

```python
response = await client.post(
    "http://localhost:8000/api/runs",
    json={
        "skill_version_ids": ["skill-uuid"],
        "input": {"key": "value"}
    }
)
result = response.json()
```

---

## Folder-Based Skill Registration

### Convention

```
skills/
├── my_skill/
│   ├── SKILL.md
│   ├── scripts/main.py
│   └── resources/
├── another_skill/
│   ├── SKILL.md
│   └── scripts/main.py
```

### Auto-Register at Startup

```python
from open_skills.core.adapters.discovery import register_skills_from_folder

# In your app startup
@app.on_event("startup")
async def startup():
    await register_skills_from_folder(
        "./skills",
        auto_publish=True,      # Publish immediately
        visibility="org",        # Org-level visibility
        auto_create_skills=True, # Auto-create skill records
    )
```

### Watch for Changes (Development)

```python
from open_skills.core.adapters.discovery import watch_skills_folder

# Run in background
asyncio.create_task(watch_skills_folder(
    "./skills",
    auto_publish=True,
    callback=lambda v: print(f"Registered {len(v)} skills")
))
```

**Note:** Requires `watchfiles`: `pip install watchfiles`

---

## Tool Discovery

### Standard Manifest (`.well-known/skills.json`)

```python
from open_skills.core.adapters.agent_tool_api import manifest_json

# FastAPI endpoint
@app.get("/.well-known/skills.json")
async def skills_manifest():
    return await manifest_json(published_only=True)
```

### Get Tools Programmatically

```python
from open_skills.core.adapters.agent_tool_api import as_agent_tools

tools = await as_agent_tools(
    published_only=True,
    name_format="versioned",  # "skill:name@version" or "simple"
)

for tool in tools:
    print(f"{tool['name']}: {tool['description']}")
```

### Convert to Framework Formats

```python
from open_skills.core.adapters.agent_tool_api import (
    to_openai_function,
    to_anthropic_tool,
    to_langchain_tool,
)

# OpenAI
openai_functions = [to_openai_function(t) for t in tools]

# Anthropic
anthropic_tools = [to_anthropic_tool(t) for t in tools]

# LangChain
langchain_tools = [to_langchain_tool(t) for t in tools]
```

---

## Skill Execution

### Direct Execution

```python
from open_skills.core.executor import SkillExecutor
from open_skills.core.manager import SkillManager
from uuid import UUID

# Get skill version
manager = SkillManager(db)
version = await manager.get_skill_version(UUID("..."))

# Execute
executor = SkillExecutor(db)
result = await executor.execute_one(
    version,
    input_payload={"text": "Hello"},
    timeout_seconds=60,
)

print(result["outputs"])
print(result["artifacts"])
```

### Multi-Skill Execution

```python
# Parallel execution
results = await executor.execute_many(
    [version1, version2, version3],
    input_payload={"shared_input": "data"},
    strategy="parallel",
)

# Chained execution (output → input)
results = await executor.execute_many(
    [step1, step2, step3],
    input_payload={"initial": "data"},
    strategy="chain",
)
```

---

## Framework-Specific Examples

### OpenAI Tool Calling

```python
import openai
import json
from uuid import UUID
from open_skills.core.adapters.agent_tool_api import as_agent_tools, to_openai_tool
from open_skills.core.manager import SkillManager
from open_skills.core.executor import SkillExecutor

# Get tools
tools = await as_agent_tools()
openai_tools = [to_openai_tool(t) for t in tools]

# Call OpenAI (modern API)
client = openai.AsyncOpenAI()
response = await client.chat.completions.create(
    model="gpt-4",
    messages=[{"role": "user", "content": "Summarize this..."}],
    tools=openai_tools,
)

# Handle tool calls
message = response.choices[0].message
if message.tool_calls:
    for tool_call in message.tool_calls:
        function_name = tool_call.function.name
        function_args = json.loads(tool_call.function.arguments)

        # Execute skill
        tool = next(t for t in tools if t["name"] == function_name)
        version = await manager.get_skill_version(UUID(tool["skill_version_id"]))
        result = await executor.execute_one(version, function_args)

# See examples/openai_agents_sdk_example.py for a complete agent loop
```

### Anthropic Tool Use

```python
import anthropic
from open_skills.core.adapters.agent_tool_api import as_agent_tools, to_anthropic_tool

# Get tools
tools = await as_agent_tools()
anthropic_tools = [to_anthropic_tool(t) for t in tools]

# Call Claude
client = anthropic.AsyncAnthropic()
response = await client.messages.create(
    model="claude-3-opus-20240229",
    messages=[{"role": "user", "content": "Help me..."}],
    tools=anthropic_tools,
)

# Handle tool use
for block in response.content:
    if block.type == "tool_use":
        # Execute skill
        tool = next(t for t in tools if t["name"] == block.name)
        version = await manager.get_skill_version(UUID(tool["skill_version_id"]))
        result = await executor.execute_one(version, block.input)
```

### LangChain

```python
from langchain.agents import create_react_agent
from langchain_openai import ChatOpenAI
from open_skills.core.adapters.agent_tool_api import as_agent_tools, to_langchain_tool

# Get tools
tools = await as_agent_tools()
langchain_tools = [to_langchain_tool(t) for t in tools]

# Create agent
llm = ChatOpenAI(model="gpt-4")
agent = create_react_agent(llm, langchain_tools, prompt)

# Use agent
result = agent.invoke({"input": "Summarize this document"})
```

### Custom Agent Framework

```python
# Minimal integration
tools = await as_agent_tools()

async def handle_tool_call(tool_name: str, args: dict):
    """Route tool calls to open-skills executor"""
    if tool_name.startswith("skill:"):
        tool = next(t for t in tools if t["name"] == tool_name)
        version_id = UUID(tool["skill_version_id"])

        version = await manager.get_skill_version(version_id)
        result = await executor.execute_one(version, args)

        return result.get("outputs", {})

    # Handle other tools...
```

---

## Advanced Patterns

### Custom Skill Endpoints

Create dedicated endpoints for specific skills:

```python
from open_skills.integrations.fastapi_integration import create_skill_execution_endpoint

router = APIRouter()

create_skill_execution_endpoint(
    router,
    skill_name="summarize",
    skill_version_id=UUID("..."),
)

# Now available as POST /summarize
```

### Conditional Skill Loading

Load different skills based on user/tenant:

```python
async def get_tools_for_user(user_id: UUID):
    return await as_agent_tools(
        user_id=user_id,
        published_only=True,
    )

async def get_tools_for_org(org_id: UUID):
    return await as_agent_tools(
        org_id=org_id,
        published_only=True,
    )
```

### Skill Composition

Chain multiple skills:

```python
# Sequential processing
async def process_document(doc_url: str):
    # Step 1: Extract text
    extract_version = await manager.get_skill_version_by_number(
        skill_id, "extract_text"
    )
    text_result = await executor.execute_one(
        extract_version,
        {"url": doc_url}
    )

    # Step 2: Summarize
    summarize_version = await manager.get_skill_version_by_number(
        skill_id, "summarize"
    )
    summary = await executor.execute_one(
        summarize_version,
        {"text": text_result["outputs"]["text"]}
    )

    return summary
```

### Error Handling

```python
from open_skills.core.exceptions import (
    SkillExecutionError,
    SkillTimeoutError,
    SkillNotFoundError,
)

try:
    result = await executor.execute_one(version, input_data)
except SkillTimeoutError:
    # Handle timeout
    pass
except SkillExecutionError as e:
    # Handle execution error
    logging.error(f"Skill failed: {e}")
except SkillNotFoundError:
    # Handle missing skill
    pass
```

---

## Configuration Reference

### Library Configuration

```python
from open_skills.core.library import configure

configure(
    # Required
    database_url="postgresql+asyncpg://localhost/db",
    openai_api_key="sk-...",

    # Optional
    storage_root="./skills",
    artifacts_root="./artifacts",
    jwt_secret="your-secret",

    # Execution limits
    default_timeout_seconds=60,
    max_timeout_seconds=300,
    max_input_size_bytes=10*1024*1024,

    # S3 (optional)
    s3_endpoint="https://s3.amazonaws.com",
    s3_bucket="my-bucket",
    s3_access_key="...",
    s3_secret_key="...",
)
```

### Mount Options

```python
await mount_open_skills(
    app,
    prefix="/skills",              # API prefix
    skills_dir="./skills",         # Skill folder
    auto_register=True,            # Auto-register on startup
    auto_publish=False,            # Don't auto-publish
    database_url="...",            # DB URL
)
```

---

## Deployment

### Library Mode Deployment

```python
# main.py
from fastapi import FastAPI
from open_skills.integrations.fastapi_integration import mount_open_skills

app = FastAPI()

@app.on_event("startup")
async def startup():
    await mount_open_skills(
        app,
        skills_dir="./skills",
        database_url=os.getenv("DATABASE_URL"),
        openai_api_key=os.getenv("OPENAI_API_KEY"),
    )

# Deploy as normal FastAPI app
# uvicorn main:app --host 0.0.0.0 --port 8000
```

### Service Mode Deployment

```bash
# Using Docker
docker build -t my-skills-service .
docker run -p 8000:8000 my-skills-service

# Using Kubernetes
kubectl apply -f k8s/
```

---

## Best Practices

1. **Use Published Skills Only**: Set `published_only=True` in production
2. **Version Skills**: Use semantic versioning for skills
3. **Test Locally**: Use `open-skills run-local` before publishing
4. **Monitor Execution**: Check run logs and duration
5. **Set Timeouts**: Configure appropriate timeouts for long-running skills
6. **Handle Errors**: Wrap execution in try/except with specific error types
7. **Use RBAC**: Configure visibility and permissions appropriately

---

## Troubleshooting

### Skills Not Appearing

```python
# Check registration
from open_skills.core.manager import SkillManager

manager = SkillManager(db)
skills = await manager.list_skills()
print(f"Found {len(skills)} skills")
```

### Execution Failing

```python
# Check logs
result = await executor.execute_one(version, input_data)
if result["status"] == "error":
    print(result["logs"])
    print(result.get("error_message"))
```

### Database Issues

```python
# Verify connection
from open_skills.core.library import get_config

config = get_config()
async for db in config.get_db():
    # Test query
    from sqlalchemy import text
    result = await db.execute(text("SELECT 1"))
    print("DB connected!")
```

---

## Real-Time Streaming (SSE)

Open-skills supports Server-Sent Events (SSE) for real-time skill execution updates.

### Backend (Python)

```python
import httpx

async def stream_run(run_id: str):
    """Stream real-time execution events."""
    async with httpx.AsyncClient() as client:
        async with client.stream(
            "GET",
            f"http://localhost:8000/api/runs/{run_id}/stream"
        ) as response:
            async for line in response.aiter_lines():
                if line.startswith("event:"):
                    event_type = line.split(":", 1)[1].strip()
                elif line.startswith("data:"):
                    import json
                    event_data = json.loads(line.split(":", 1)[1].strip())

                    if event_type == "status":
                        print(f"Status: {event_data['status']}")
                    elif event_type == "complete":
                        print(f"Done: {event_data}")
                        break
```

### Frontend (JavaScript)

```javascript
const eventSource = new EventSource(`/api/runs/${runId}/stream`);

// Listen for status changes
eventSource.addEventListener('status', (e) => {
    const data = JSON.parse(e.data);
    console.log('Status:', data.status);
});

// Listen for log output
eventSource.addEventListener('log', (e) => {
    const data = JSON.parse(e.data);
    console.log(`[${data.stream}]`, data.line);
});

// Listen for artifacts
eventSource.addEventListener('artifact', (e) => {
    const data = JSON.parse(e.data);
    console.log('Artifact:', data.filename);
});

// Listen for completion
eventSource.addEventListener('complete', (e) => {
    const data = JSON.parse(e.data);
    console.log('Completed:', data);
    eventSource.close();
});

// Handle errors
eventSource.addEventListener('error', (e) => {
    const data = JSON.parse(e.data);
    console.error('Error:', data.error);
    eventSource.close();
});
```

### Event Types

| Event | Description | Data Fields |
|-------|-------------|-------------|
| `status` | Status change | `status`: queued, running, success, error |
| `log` | Log output | `line`: log text, `stream`: stdout/stderr |
| `output` | Individual output value | `key`: output key, `value`: output value |
| `artifact` | Artifact created | `filename`, `url`, `size_bytes` |
| `error` | Execution error | `error`: error message, `traceback`: stack trace |
| `complete` | Execution finished | `status`, `outputs`, `duration_ms` |

### Examples

See:
- `examples/streaming_example.py` - Python streaming client
- `examples/streaming_frontend_example.html` - Browser-based UI

---

## Context-Aware Prompts (Skill Injection)

Make your agent aware of available skills by injecting them into the system prompt.

### Basic Prompt Injection

```python
from open_skills import manifest_to_prompt, inject_skills_context

# Generate skills context
skills_context = await manifest_to_prompt(
    published_only=True,
    format="detailed"  # or "compact", "numbered"
)

# Use in your system prompt
system_prompt = f"""You are an AI assistant with access to:

{skills_context}

Use these skills to help users accomplish tasks."""
```

### Auto-Inject into Existing Prompt

```python
from open_skills import inject_skills_context

base_prompt = "You are a helpful AI assistant."

# Automatically augment with skills
full_prompt = await inject_skills_context(
    base_prompt,
    format="compact",
    section_title="Available Tools"
)

# Use with your agent
agent = Agent(system_prompt=full_prompt)
```

### Format Options

| Format | Description | Use Case |
|--------|-------------|----------|
| `detailed` | Full descriptions with inputs/outputs | Maximum context |
| `compact` | Name and one-line description | Token efficiency |
| `numbered` | Numbered list with descriptions | Structured prompts |

### Session Metadata for Observability

```python
from open_skills import get_skills_session_metadata

# Log which skills are available
metadata = await get_skills_session_metadata(
    user_id=current_user.id,
    published_only=True
)

logger.info(
    "agent_session_started",
    skill_count=metadata['skill_count'],
    skill_names=metadata['skill_names'],
    tags=metadata['tags']
)
```

### Example Output

**Detailed format:**
```
1. **text_summarizer**
   Description: Summarizes long text into key points
   Inputs: text (string): The text to summarize
   Outputs: summary (string)
   Tags: nlp, summarization

2. **generate_presentation**
   Description: Creates PowerPoint from structured data
   Inputs: data (object): Slide data
   Outputs: pptx_file (file)
   Tags: presentation, office
```

**Compact format:**
```
• text_summarizer — Summarizes long text into key points
• generate_presentation — Creates PowerPoint from structured data
```

### Multi-Tenant Context

```python
# Different skills per user/organization
user_context = await manifest_to_prompt(
    user_id=user.id,
    org_id=user.org_id,
    format="compact"
)
```

See `examples/prompt_injection_example.py` for complete examples.

---

## Next Steps

- See `examples/library_mode_complete.py` for full example
- See `examples/streaming_example.py` for streaming example
- Read the [API Reference](docs/api-reference.md)
- Check [Skill Authoring Guide](docs/authoring.md)
- Deploy with [Deployment Guide](docs/deployment.md)
