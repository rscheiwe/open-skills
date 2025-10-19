"""
open-skills: A modular, Anthropic-style Skills subsystem for agent frameworks.

Framework-agnostic design supporting both library mode (embedded) and service mode (sidecar).
"""

__version__ = "0.2.0"

# Library mode - Core components
from .core.manager import SkillManager
from .core.router import SkillRouter
from .core.executor import SkillExecutor
from .core.library import configure, get_config, is_configured

# Library mode - Discovery and tools
from .core.adapters.discovery import register_skills_from_folder, watch_skills_folder
from .core.adapters.agent_tool_api import (
    as_agent_tools,
    manifest_json,
    to_openai_function,  # Legacy
    to_openai_tool,      # Modern
    to_anthropic_tool,
    to_langchain_tool,
)

# Prompt injection for context awareness
from .core.adapters.prompt_injection import (
    manifest_to_prompt,
    manifest_to_tools,
    inject_skills_context,
    get_skills_session_metadata,
)

# Streaming
from .core.streaming import (
    get_event_bus,
    emit_status,
    emit_log,
    emit_output,
    emit_artifact,
    emit_error,
    emit_complete,
)

# FastAPI integration
from .integrations.fastapi_integration import mount_open_skills, mount_tools_only

# Service mode - Re-export for backwards compatibility
from .service.main import app as service_app

__all__ = [
    # Version
    "__version__",
    # Core components
    "SkillManager",
    "SkillRouter",
    "SkillExecutor",
    # Library configuration
    "configure",
    "get_config",
    "is_configured",
    # Discovery
    "register_skills_from_folder",
    "watch_skills_folder",
    # Tool API
    "as_agent_tools",
    "manifest_json",
    "to_openai_function",  # Legacy
    "to_openai_tool",      # Modern
    "to_anthropic_tool",
    "to_langchain_tool",
    # Prompt injection
    "manifest_to_prompt",
    "manifest_to_tools",
    "inject_skills_context",
    "get_skills_session_metadata",
    # Streaming
    "get_event_bus",
    "emit_status",
    "emit_log",
    "emit_output",
    "emit_artifact",
    "emit_error",
    "emit_complete",
    # FastAPI integration
    "mount_open_skills",
    "mount_tools_only",
    # Service
    "service_app",
]
