# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2025-10-19

### Added - Framework-Agnostic Release

#### Library Mode

- **Library mode** - Embed open-skills directly in Python applications without running a separate service
- `configure()` - Global configuration API for library mode
- `mount_open_skills()` - One-line FastAPI integration helper
- `mount_tools_only()` - Minimal integration (manifest only)

#### Auto-Discovery

- `register_skills_from_folder()` - Automatic skill registration from directory structure
- `watch_skills_folder()` - File-watching for development (requires `watchfiles`)
- Auto-create skill records if they don't exist
- Auto-increment versions on conflicts
- Automatic embedding generation on registration

#### Tool Discovery & Context Awareness

- `.well-known/skills.json` - Standard tool discovery manifest endpoint
- `as_agent_tools()` - Convert skills to tool definitions
- `manifest_json()` - Generate tool manifest
- **Context-aware prompts** - Prompt injection for agent skill awareness
  - `manifest_to_prompt()` - Convert skills to human-readable prompt text
  - `inject_skills_context()` - Auto-inject skills into system prompts
  - `get_skills_session_metadata()` - Session observability metadata
  - Format options: detailed, compact, numbered

#### Framework Integration

- `to_openai_tool()` - Convert to OpenAI tools format (modern API)
- `to_openai_function()` - Convert to OpenAI functions format (legacy, deprecated)
- `to_anthropic_tool()` - Convert to Anthropic tool format
- `to_langchain_tool()` - Convert to LangChain tool format
- Support for both versioned (`skill:name@version`) and simple (`skill:name`) naming

#### Real-Time Streaming

- **SSE streaming** - Server-Sent Events for real-time execution updates
- `GET /api/runs/{run_id}/stream` - SSE endpoint
- Event types: status, log, output, artifact, error, complete
- ExecutionEventBus for in-memory event management
- Browser-compatible EventSource support

#### Examples & Documentation

- `examples/integration_example.py` - Simple FastAPI integration
- `examples/prompt_injection_example.py` - Context-aware prompts with 7+ scenarios
- `examples/openai_agents_sdk_example.py` - OpenAI Agents SDK integration
- `examples/library_mode_complete.py` - Complete OpenAI example
- `examples/streaming_example.py` - SSE streaming client
- `examples/streaming_frontend_example.html` - Browser-based UI
- `INTEGRATION_GUIDE.md` - Comprehensive integration reference
- `MIGRATION_GUIDE.md` - Upgrade guide from v0.1.0
- `REFACTOR_SUMMARY.md` - Technical summary of changes

### Changed

#### Package Structure

- Moved `open_skills/api/` → `open_skills/service/api/` (breaking change for service-mode imports)
- Created `open_skills/core/adapters/` for discovery and tool conversion
- Created `open_skills/integrations/` for framework helpers
- Separated core library from service-specific code

#### Dependencies

- Added `sse-starlette>=2.0.0` for streaming support
- Made FastAPI optional for library-only usage (still required for service mode)

#### Backwards Compatibility

- `python -m open_skills.main` still works (delegates to `service.main`)
- Service mode unchanged for existing deployments
- All API endpoints remain the same
- Database schema unchanged

### Deprecated

- `to_openai_function()` - Use `to_openai_tool()` for modern OpenAI tools API

### Fixed

- Import paths updated throughout codebase
- Proper handling of async sessions in library mode
- Improved error handling in discovery module

## [0.1.0] - 2025-10-18

### Added - Initial Release

- **Core Features**

  - Skill management (CRUD operations)
  - Version control for skill bundles
  - Skill execution engine with timeout support
  - Embedding-based skill search using pgvector
  - Multi-skill composition (parallel and chain strategies)
  - Artifact generation and storage

- **API**

  - RESTful API with FastAPI
  - Health check endpoint
  - Skills CRUD endpoints
  - Version management endpoints
  - Search endpoint
  - Execution endpoint
  - Artifact retrieval

- **Database**

  - PostgreSQL with pgvector extension
  - Alembic migrations
  - SQLAlchemy async ORM
  - Support for skill metadata, versions, runs, and artifacts

- **Security**

  - JWT-based authentication (stubbed)
  - Role-based access control (RBAC)
  - Skill visibility levels (public, org, user)
  - Permission system (viewer, author, publisher, admin)

- **CLI**

  - `open-skills init` - Initialize new skill bundle
  - `open-skills validate` - Validate skill bundle
  - `open-skills run-local` - Test skill locally
  - `open-skills publish` - Publish skill to service
  - `open-skills serve` - Start API server

- **Deployment**

  - Docker support
  - Docker Compose configuration
  - Kubernetes manifests
  - S3-compatible artifact storage

- **Documentation**
  - README with quickstart
  - API documentation
  - Skill authoring guide
  - Example skill bundles (hello-world, text-summarizer)

[0.2.0]: https://github.com/rscheiwe/open-skills/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/rscheiwe/open-skills/releases/tag/v0.1.0
