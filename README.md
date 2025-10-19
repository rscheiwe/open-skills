# open-skills

**A framework-agnostic Skills subsystem for Python agents.** Build, version, and execute reusable agent capabilities as code bundles — embed directly in your app or deploy as a service.

> Inspired by [Anthropic's Skills](https://www.anthropic.com/) feature for Claude.

## Overview

`open-skills` provides a complete system for managing executable code bundles (skills) that AI agents can discover and invoke. Think of it as a plugin system for LLM applications with version control, auto-discovery, and execution tracking.

**Version 0.2.0** introduces **library mode** — embed open-skills directly into any Python application without running a separate service.

### Key Features

✅ **Framework-Agnostic** — Works with OpenAI, Anthropic, LangChain, LlamaIndex, or custom agents

✅ **Two Deployment Modes** — Library (embedded) or Service (microservice)

✅ **Auto-Discovery** — Skills registered from folder structure at startup

✅ **Context-Aware Prompts** — Automatic skill injection into system prompts

✅ **Versioned Bundles** — Skills as folders with metadata, scripts, and resources

✅ **Embedding-Based Search** — Automatic skill selection via vector similarity

✅ **Tool Manifest** — Standard `.well-known/skills.json` for any LLM framework

✅ **Real-Time Streaming** — SSE for execution updates

✅ **Artifact Generation** — File outputs with S3-compatible storage

✅ **Multi-Skill Composition** — Chain or parallelize execution

## Quick Start

### Library Mode (Embed in Your App)

**Install:**

```bash
pip install open-skills
```

**Integrate into FastAPI:**

```python
from fastapi import FastAPI
from open_skills import mount_open_skills

app = FastAPI()

# One-line integration
await mount_open_skills(
    app,
    skills_dir="./skills",              # Auto-discover from this folder
    database_url="postgresql+asyncpg://localhost/mydb",
    openai_api_key="sk-...",
)

# Skills are now:
# - Auto-registered from ./skills folder
# - Discoverable at /.well-known/skills.json
# - Executable via /skills/api/runs
```

**Use with any agent framework:**

```python
from open_skills import as_agent_tools, to_openai_tool
import openai

# Get available tools
tools = await as_agent_tools(published_only=True)
openai_tools = [to_openai_tool(t) for t in tools]

# Use with OpenAI
client = openai.AsyncOpenAI()
response = await client.chat.completions.create(
    model="gpt-4",
    messages=[{"role": "user", "content": "Summarize this document..."}],
    tools=openai_tools,
)
```

### Service Mode (Microservice)

**Run as standalone service:**

```bash
# Using Docker Compose
docker-compose up -d

# Or directly
python -m open_skills.service.main
```

**Access from any language:**

```bash
curl http://localhost:8000/.well-known/skills.json  # Discover tools
curl -X POST http://localhost:8000/api/runs \
  -d '{"skill_version_ids": ["..."], "input": {...}}'
```

## Two Ways to Use

| Mode        | Best For                     | Pros                                 | Cons             |
| ----------- | ---------------------------- | ------------------------------------ | ---------------- |
| **Library** | Monolithic apps, low latency | In-process, zero network overhead    | Shares resources |
| **Service** | Microservices, polyglot apps | Process isolation, language-agnostic | Network overhead |

See [INTEGRATION_GUIDE.md](INTEGRATION_GUIDE.md) for complete integration patterns.

## Skill Bundle Format

A skill is a directory containing:

```
my-skill/
├── SKILL.md          # Metadata (YAML frontmatter + description)
├── scripts/
│   └── main.py       # Entrypoint function
├── resources/        # Optional: templates, data files
│   └── template.txt
└── tests/            # Optional: test inputs
    └── sample.json
```

**SKILL.md Example:**

```markdown
---
name: text_summarizer
version: 1.0.0
entrypoint: scripts/main.py
description: Summarizes long text into key points
inputs:
  - type: text
outputs:
  - type: text
tags: [nlp, summarization, text]
---

# Text Summarizer

This skill takes long text and produces a concise summary.
```

**scripts/main.py Example:**

```python
async def run(input_payload: dict) -> dict:
    text = input_payload.get("text", "")
    summary = text[:200] + "..."  # Simple truncation

    return {
        "outputs": {"summary": summary},
        "artifacts": []
    }
```

## Common Use Cases

### 1. Embed in Existing FastAPI App

```python
from fastapi import FastAPI
from open_skills import mount_open_skills

app = FastAPI()

# Your existing routes
@app.get("/")
async def root():
    return {"app": "my-app"}

# Add skills
@app.on_event("startup")
async def startup():
    await mount_open_skills(
        app,
        prefix="/skills",
        skills_dir="./skills",
        auto_register=True,
    )
```

### 2. Use with OpenAI Tool Calling

```python
from open_skills import configure, as_agent_tools, to_openai_tool
from open_skills.core.executor import SkillExecutor
from open_skills.core.manager import SkillManager
import openai

# Configure library
configure(database_url="postgresql+asyncpg://...", openai_api_key="sk-...")

# Get tools
tools = await as_agent_tools()
openai_tools = [to_openai_tool(t) for t in tools]

# Call OpenAI
client = openai.AsyncOpenAI()
response = await client.chat.completions.create(
    model="gpt-4",
    messages=[{"role": "user", "content": "Help me summarize this..."}],
    tools=openai_tools,
)

# Execute skill if tool called
if response.choices[0].message.tool_calls:
    for tool_call in response.choices[0].message.tool_calls:
        function_name = tool_call.function.name
        tool = next(t for t in tools if t["name"] == function_name)

        # Execute the skill
        # ... (see examples/openai_agents_sdk_example.py for full example)
```

### 3. Context-Aware Prompts (Skill Injection)

```python
from open_skills import configure, inject_skills_context

configure(database_url="postgresql+asyncpg://...", openai_api_key="sk-...")

# Create a context-aware system prompt
base_prompt = "You are a helpful AI assistant."

# Inject available skills into the prompt
system_prompt = await inject_skills_context(
    base_prompt,
    format="detailed"  # or "compact", "numbered"
)

# Now the agent knows what skills are available
agent = Agent(system_prompt=system_prompt)
```

### 4. Auto-Discovery from Folder

```python
from open_skills import configure, register_skills_from_folder

configure(database_url="postgresql+asyncpg://...", openai_api_key="sk-...")

# Auto-register all skills in ./skills folder
versions = await register_skills_from_folder(
    "./skills",
    auto_publish=True,
    visibility="org",
)

print(f"Registered {len(versions)} skills")
```

### 5. Real-Time Execution Streaming

```python
# Backend (Python)
import httpx

async with httpx.AsyncClient() as client:
    async with client.stream("GET", f"/api/runs/{run_id}/stream") as response:
        async for line in response.aiter_lines():
            # Process Server-Sent Events
            print(line)
```

```javascript
// Frontend (JavaScript)
const eventSource = new EventSource(`/api/runs/${runId}/stream`);

eventSource.addEventListener("status", (e) => {
  console.log("Status:", JSON.parse(e.data).status);
});

eventSource.addEventListener("complete", (e) => {
  console.log("Done:", JSON.parse(e.data));
  eventSource.close();
});
```

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Your Application                     │
├─────────────────────────────────────────────────────────┤
│  Library Mode                 │  Service Mode           │
│  ┌─────────────────────┐      │  ┌──────────────────┐  │
│  │ mount_open_skills() │      │  │ HTTP Client      │  │
│  │  • Auto-register    │      │  │  • REST API      │  │
│  │  • Tool discovery   │      │  │  • Language-     │  │
│  │  • In-process exec  │      │  │    agnostic      │  │
│  └─────────────────────┘      │  └──────────────────┘  │
└─────────────────────────────────────────────────────────┘
                      │
                      ▼
        ┌──────────────────────────┐
        │   open-skills Core       │
        ├──────────────────────────┤
        │  • Skill Manager         │
        │  • Skill Router          │
        │  • Skill Executor        │
        │  • Auto-Discovery        │
        │  • Tool Manifest         │
        └────┬─────────────────┬───┘
             │                 │
             ▼                 ▼
        ┌─────────┐      ┌──────────┐
        │Postgres │      │    S3    │
        │+pgvector│      │Artifacts │
        └─────────┘      └──────────┘
```

## Installation

### Prerequisites

- Python 3.11+
- PostgreSQL 14+ with pgvector extension
- OpenAI API key (for embeddings)

### Install Package

```bash
pip install open-skills

# Or for development
git clone https://github.com/rscheiwe/open-skills.git
cd open-skills
pip install -e ".[dev]"
```

### Database Setup

```bash
# Using Docker (recommended)
docker run -d \
  --name openskills-postgres \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=openskills \
  -p 5432:5432 \
  pgvector/pgvector:pg16

# Run migrations
alembic upgrade head
```

## Configuration

### Library Mode

```python
from open_skills import configure

configure(
    database_url="postgresql+asyncpg://localhost/mydb",
    openai_api_key="sk-...",
    storage_root="./skills",
    artifacts_root="./artifacts",
    # Optional S3 configuration
    s3_endpoint="https://s3.amazonaws.com",
    s3_bucket="my-bucket",
)
```

### Service Mode

Create `.env` file:

```env
POSTGRES_URL=postgresql+asyncpg://user:password@localhost:5432/openskills
OPENAI_API_KEY=sk-...
JWT_SECRET=your-secret-key-here
STORAGE_ROOT=./storage
ARTIFACTS_ROOT=./artifacts

# Optional
S3_ENDPOINT=https://s3.amazonaws.com
S3_BUCKET=open-skills-artifacts
LANGFUSE_API_KEY=  # Telemetry
```

## API Endpoints

When using `mount_open_skills()` or service mode:

| Endpoint                    | Method    | Description             |
| --------------------------- | --------- | ----------------------- |
| `/.well-known/skills.json`  | GET       | Tool discovery manifest |
| `/api/health`               | GET       | Health check            |
| `/api/skills`               | GET, POST | List/create skills      |
| `/api/skills/{id}/versions` | GET, POST | Manage versions         |
| `/api/skills/search`        | POST      | Embedding-based search  |
| `/api/runs`                 | POST      | Execute skills          |
| `/api/runs/{id}`            | GET       | Get run details         |
| `/api/runs/{id}/stream`     | GET       | Real-time SSE stream    |

See [INTEGRATION_GUIDE.md](INTEGRATION_GUIDE.md) for complete API reference.

## CLI Tools

```bash
# Create a new skill
open-skills init my-skill

# Validate skill bundle
open-skills validate ./my-skill

# Test locally
open-skills run-local ./my-skill input.json

# Publish to service
open-skills publish ./my-skill

# Start service
open-skills serve --port 8000
```

## Examples

- [`examples/integration_example.py`](examples/integration_example.py) - Simple FastAPI integration
- [`examples/prompt_injection_example.py`](examples/prompt_injection_example.py) - **Context-aware prompt injection**
- [`examples/openai_agents_sdk_example.py`](examples/openai_agents_sdk_example.py) - **OpenAI Agents SDK integration**
- [`examples/library_mode_complete.py`](examples/library_mode_complete.py) - Full example with OpenAI
- [`examples/streaming_example.py`](examples/streaming_example.py) - SSE streaming client
- [`examples/streaming_frontend_example.html`](examples/streaming_frontend_example.html) - Browser UI
- [`examples/hello-world/`](examples/hello-world/) - Sample skill bundle
- [`examples/text-summarizer/`](examples/text-summarizer/) - Advanced skill example

## Documentation

- **[QUICKSTART.md](QUICKSTART.md)** - Get started in 5 minutes
- **[INTEGRATION_GUIDE.md](INTEGRATION_GUIDE.md)** - Complete integration reference
- **[MIGRATION_GUIDE.md](MIGRATION_GUIDE.md)** - Upgrade from v0.1.0
- **[REFACTOR_SUMMARY.md](REFACTOR_SUMMARY.md)** - What's new in v0.2.0

## Framework Compatibility

Open-skills provides tool converters for:

- **OpenAI** - Function calling format
- **Anthropic** - Tool use format
- **LangChain** - Tool format
- **Custom** - Generic tool contract

```python
from open_skills import as_agent_tools, to_openai_tool, to_anthropic_tool, to_langchain_tool

tools = await as_agent_tools()

# Convert to framework-specific formats
openai_tools = [to_openai_tool(t) for t in tools]
anthropic_tools = [to_anthropic_tool(t) for t in tools]
langchain_tools = [to_langchain_tool(t) for t in tools]
```

## Development

### Run Tests

```bash
pytest                    # All tests
pytest -m unit            # Unit tests only
pytest -m integration     # Integration tests
pytest --cov=open_skills  # With coverage
```

### Code Quality

```bash
black open_skills tests   # Format
ruff check open_skills    # Lint
mypy open_skills          # Type check
```

### Database Migrations

```bash
alembic revision --autogenerate -m "description"  # Create migration
alembic upgrade head                              # Apply
alembic downgrade -1                              # Rollback
```

## Deployment

### Docker (Service Mode)

```bash
docker build -t open-skills:latest .
docker run -p 8000:8000 --env-file .env open-skills:latest
```

### Kubernetes

```bash
kubectl apply -f k8s/
```

### Library Mode (Embedded)

Deploy as part of your application — no separate deployment needed!

See [docs/deployment.md](docs/deployment.md) for production setup.

## Troubleshooting

### Skills not appearing in manifest

```python
from open_skills.core.manager import SkillManager

async with db_session() as db:
    manager = SkillManager(db)
    skills = await manager.list_skills()
    print(f"Found {len(skills)} skills")
```

### Database connection issues

```bash
# Verify pgvector extension
psql -d openskills -c "\dx"

# Test connection
psql postgresql://postgres:postgres@localhost:5432/openskills
```

See [INTEGRATION_GUIDE.md](INTEGRATION_GUIDE.md#troubleshooting) for more.

## Contributing

Contributions welcome! Please read [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

MIT License - see [LICENSE](LICENSE) file for details.

## Acknowledgments

Inspired by [Anthropic's Skills](https://www.anthropic.com/) feature for Claude, designed to work with any LLM framework.

---

**Current Version:** 0.2.0 (Framework-Agnostic Release)
**Status:** Production-ready for library mode, service mode, and hybrid deployments
