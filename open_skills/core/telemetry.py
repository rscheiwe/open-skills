"""
Telemetry and logging infrastructure.
Includes structured logging and Langfuse stub for tracing.
"""

import logging
import time
from contextlib import contextmanager
from typing import Any, Dict, Optional
from uuid import UUID
import json

import structlog

from open_skills.config import settings


# Configure structlog for structured logging
def add_log_level(logger: Any, method_name: str, event_dict: Dict) -> Dict:
    """Add log level to event dict."""
    event_dict["level"] = method_name.upper()
    return event_dict


def add_timestamp(logger: Any, method_name: str, event_dict: Dict) -> Dict:
    """Add timestamp to event dict."""
    import datetime
    event_dict["timestamp"] = datetime.datetime.utcnow().isoformat()
    return event_dict


# Configure structlog processors
processors = [
    structlog.contextvars.merge_contextvars,
    add_timestamp,
    add_log_level,
    structlog.processors.StackInfoRenderer(),
    structlog.processors.format_exc_info,
]

if settings.log_format == "json":
    processors.append(structlog.processors.JSONRenderer())
else:
    processors.append(structlog.dev.ConsoleRenderer())

structlog.configure(
    processors=processors,
    wrapper_class=structlog.make_filtering_bound_logger(
        logging.getLevelName(settings.log_level)
    ),
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
    cache_logger_on_first_use=True,
)

# Get logger instance
logger = structlog.get_logger("open-skills")


def get_logger(name: Optional[str] = None) -> Any:
    """
    Get a structured logger instance.

    Args:
        name: Optional logger name (defaults to "open-skills")

    Returns:
        Structured logger instance
    """
    return structlog.get_logger(name or "open-skills")


class LangfuseStub:
    """
    Stub implementation of Langfuse client for telemetry.
    In production, replace with real Langfuse client.
    """

    def __init__(self):
        self.enabled = settings.langfuse_enabled
        self.logger = get_logger("langfuse")

    def trace(
        self,
        name: str,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        metadata: Optional[Dict] = None,
    ):
        """Create a trace (stubbed)."""
        if self.enabled:
            self.logger.info(
                "trace_created",
                name=name,
                user_id=user_id,
                session_id=session_id,
                metadata=metadata,
            )
        return TraceStub(name, self.logger)

    def flush(self):
        """Flush pending traces (stubbed)."""
        if self.enabled:
            self.logger.debug("flush_called")


class TraceStub:
    """Stub for Langfuse trace."""

    def __init__(self, name: str, logger: Any):
        self.name = name
        self.logger = logger
        self.start_time = time.time()

    def span(self, name: str, metadata: Optional[Dict] = None):
        """Create a span within the trace (stubbed)."""
        self.logger.info("span_created", trace=self.name, span=name, metadata=metadata)
        return SpanStub(name, self.name, self.logger)

    def event(self, name: str, metadata: Optional[Dict] = None):
        """Log an event (stubbed)."""
        self.logger.info("event", trace=self.name, event=name, metadata=metadata)

    def end(self, metadata: Optional[Dict] = None):
        """End the trace (stubbed)."""
        duration = time.time() - self.start_time
        self.logger.info(
            "trace_ended",
            trace=self.name,
            duration_s=duration,
            metadata=metadata,
        )


class SpanStub:
    """Stub for Langfuse span."""

    def __init__(self, name: str, trace_name: str, logger: Any):
        self.name = name
        self.trace_name = trace_name
        self.logger = logger
        self.start_time = time.time()

    def end(self, metadata: Optional[Dict] = None):
        """End the span (stubbed)."""
        duration = time.time() - self.start_time
        self.logger.info(
            "span_ended",
            trace=self.trace_name,
            span=self.name,
            duration_s=duration,
            metadata=metadata,
        )


# Global Langfuse stub instance
langfuse = LangfuseStub()


@contextmanager
def run_trace(
    run_id: UUID,
    skill_name: Optional[str] = None,
    user_id: Optional[str] = None,
):
    """
    Context manager for tracing skill runs.

    Args:
        run_id: Run UUID
        skill_name: Optional skill name
        user_id: Optional user ID

    Yields:
        Trace instance

    Example:
        ```python
        with run_trace(run_id, "my_skill") as trace:
            # Do work
            trace.event("processing", {"step": 1})
            # More work
        ```
    """
    start_time = time.time()
    trace_name = f"skill_run_{run_id}"

    logger.info(
        "run_start",
        run_id=str(run_id),
        skill_name=skill_name,
        user_id=user_id,
    )

    trace = langfuse.trace(
        name=trace_name,
        user_id=user_id,
        metadata={"run_id": str(run_id), "skill_name": skill_name},
    )

    try:
        yield trace
        duration = time.time() - start_time
        logger.info(
            "run_end",
            run_id=str(run_id),
            skill_name=skill_name,
            duration_s=duration,
            status="success",
        )
        trace.end(metadata={"status": "success", "duration_s": duration})
    except Exception as e:
        duration = time.time() - start_time
        logger.exception(
            "run_error",
            run_id=str(run_id),
            skill_name=skill_name,
            duration_s=duration,
            error=str(e),
        )
        trace.end(metadata={"status": "error", "error": str(e), "duration_s": duration})
        raise
    finally:
        langfuse.flush()


@contextmanager
def trace_operation(operation: str, metadata: Optional[Dict] = None):
    """
    Context manager for tracing general operations.

    Args:
        operation: Operation name
        metadata: Optional metadata

    Example:
        ```python
        with trace_operation("embed_text", {"text_length": 100}):
            # Do work
            pass
        ```
    """
    start_time = time.time()
    logger.info("operation_start", operation=operation, metadata=metadata)

    try:
        yield
        duration = time.time() - start_time
        logger.info(
            "operation_end",
            operation=operation,
            duration_s=duration,
            metadata=metadata,
        )
    except Exception as e:
        duration = time.time() - start_time
        logger.exception(
            "operation_error",
            operation=operation,
            duration_s=duration,
            error=str(e),
            metadata=metadata,
        )
        raise


def log_event(event: str, **kwargs):
    """
    Log a structured event.

    Args:
        event: Event name
        **kwargs: Event data
    """
    logger.info(event, **kwargs)


def log_error(error: str, exception: Optional[Exception] = None, **kwargs):
    """
    Log an error event.

    Args:
        error: Error message
        exception: Optional exception
        **kwargs: Additional context
    """
    if exception:
        logger.exception(error, error_type=type(exception).__name__, **kwargs)
    else:
        logger.error(error, **kwargs)
