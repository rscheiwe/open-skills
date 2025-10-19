# Open-Skills Quickstart Guide

Get up and running with open-skills in minutes!

## Prerequisites

- Python 3.11+
- PostgreSQL 14+ with pgvector extension
- OpenAI API key (for embeddings)

## Installation

### 1. Install the Package

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install package with dependencies
pip install -e ".[dev]"
```

### 2. Set Up PostgreSQL with pgvector

```bash
# Using Docker (recommended for development)
docker run -d \
  --name openskills-postgres \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=openskills \
  -p 5432:5432 \
  pgvector/pgvector:pg16

# Or install PostgreSQL and pgvector extension manually
# See: https://github.com/pgvector/pgvector#installation
```

### 3. Configure Environment

```bash
# Copy example environment file
cp .env.example .env

# Edit .env with your configuration
# Required: POSTGRES_URL, OPENAI_API_KEY, JWT_SECRET
```

### 4. Run Database Migrations

```bash
# Run Alembic migrations
alembic upgrade head
```

## Quick Start

### Option A: Using Docker Compose (Easiest)

```bash
# Set your OpenAI API key
export OPENAI_API_KEY=sk-your-key-here

# Start all services
docker-compose up -d

# Check status
docker-compose ps

# View logs
docker-compose logs -f api

# API will be available at http://localhost:8000
# API docs at http://localhost:8000/docs
```

### Option B: Local Development

```bash
# Start the API server
uvicorn open_skills.main:app --reload --port 8000

# Or using the CLI
open-skills serve --reload
```

Visit:

- API: http://localhost:8000
- Docs: http://localhost:8000/docs
- Health: http://localhost:8000/api/health

## Create Your First Skill

### 1. Initialize a Skill Bundle

```bash
# Create a new skill
open-skills init my_first_skill

# Navigate to the skill directory
cd my_first_skill
```

### 2. Edit the Skill

Edit `SKILL.md` to customize metadata:

```yaml
---
name: my_first_skill
version: 1.0.0
entrypoint: scripts/main.py
description: My first skill
inputs:
  - type: text
outputs:
  - type: text
tags: [demo, example]
---
```

Edit `scripts/main.py` to implement your logic:

```python
async def run(input_payload):
    text = input_payload.get("text", "")
    result = text.upper()  # Simple transformation

    return {
        "outputs": {"result": result},
        "artifacts": []
    }
```

### 3. Test Locally

```bash
# Validate the skill bundle
open-skills validate .

# Test with sample input
open-skills run-local . tests/sample_input.json
```

### 4. Publish to Server

```bash
# Create a zip of the skill bundle
zip -r my_first_skill.zip . -x ".*" -x "__pycache__/*"

# Upload via API (requires authentication)
curl -X POST http://localhost:8000/api/skills/create \
  -H "Content-Type: application/json" \
  -H "X-User-Id: your-user-id" \
  -d '{"name": "my_first_skill", "visibility": "user"}'

# Note the skill_id from response, then upload the bundle
curl -X POST http://localhost:8000/api/skills/{skill_id}/versions \
  -H "X-User-Id: your-user-id" \
  -F "bundle=@my_first_skill.zip"
```

## Using the API

### Search for Skills

```python
import httpx
import asyncio

async def search_skills():
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost:8000/api/skills/search",
            json={
                "query": "summarize text",
                "top_k": 5,
                "published_only": True
            }
        )
        print(response.json())

asyncio.run(search_skills())
```

### Execute a Skill

```python
async def run_skill(skill_version_id: str):
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost:8000/api/runs",
            json={
                "skill_version_ids": [skill_version_id],
                "input": {"text": "Hello, world!"},
                "strategy": "parallel"
            }
        )
        result = response.json()
        print(f"Status: {result['results'][0]['status']}")
        print(f"Outputs: {result['results'][0]['outputs']}")

asyncio.run(run_skill("your-skill-version-id"))
```

## Example Skills

Try the included examples:

```bash
# Hello World - Simple greeting skill
cd examples/hello-world
open-skills validate .
open-skills run-local . tests/sample_input.json

# Text Summarizer - More complex example
cd ../text-summarizer
open-skills validate .
open-skills run-local . tests/sample_input.json
```

## Development Workflow

### 1. Run Tests

```bash
# Run all tests
pytest

# Run specific test types
pytest -m unit
pytest -m integration

# With coverage
pytest --cov=open_skills --cov-report=html
```

### 2. Code Quality

```bash
# Format code
black open_skills tests

# Lint
ruff check open_skills tests

# Type check
mypy open_skills
```

### 3. Database Migrations

```bash
# Create a new migration
alembic revision --autogenerate -m "description"

# Apply migrations
alembic upgrade head

# Rollback
alembic downgrade -1
```

## Integration with Agent Frameworks

### Generic Integration

```python
from open_skills.core.router import SkillRouter
from open_skills.core.executor import SkillExecutor
from open_skills.db.base import AsyncSessionLocal

async def use_skills():
    async with AsyncSessionLocal() as db:
        router = SkillRouter(db)
        executor = SkillExecutor(db)

        # Search for relevant skills
        results = await router.search("summarize text", top_k=3)

        # Execute the best match
        if results:
            version_id = results[0]["skill_version_id"]
            from uuid import UUID
            from open_skills.core.manager import SkillManager

            manager = SkillManager(db)
            version = await manager.get_skill_version(UUID(version_id))

            result = await executor.execute_one(
                version,
                {"text": "Your text here..."}
            )

            print(result["outputs"])
```

## Troubleshooting

### Database Connection Issues

```bash
# Check PostgreSQL is running
docker ps | grep postgres

# Test connection
psql postgresql://postgres:postgres@localhost:5432/openskills
```

### pgvector Extension

```sql
-- In psql, verify extension
\dx

-- If missing, install:
CREATE EXTENSION vector;
```

### API Not Starting

```bash
# Check logs
docker-compose logs api

# Verify environment variables
env | grep POSTGRES
env | grep OPENAI
```

## Next Steps

- Read the [API Reference](docs/api-reference.md)
- Learn about [Skill Authoring](docs/authoring.md)
- Explore [Deployment Options](docs/deployment.md)
- Check the [Integration Guide](docs/integration.md)

## Getting Help

- GitHub Issues: https://github.com/rscheiwe/open-skills/issues
- Documentation: See `docs/` directory
- Examples: See `examples/` directory

## Production Deployment

For production deployments:

1. **Use Kubernetes** (see `k8s/` directory)
2. **Set secure secrets** (JWT, database passwords)
3. **Enable HTTPS** (use an ingress controller)
4. **Configure S3** for artifact storage
5. **Set up monitoring** (Langfuse, metrics)
6. **Use managed PostgreSQL** with pgvector support

See `docs/deployment.md` for detailed production setup instructions.
