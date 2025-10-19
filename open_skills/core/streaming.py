"""
Streaming support for real-time skill execution updates via SSE.
"""

import asyncio
import json
from typing import AsyncIterator, Dict, Any, Optional
from uuid import UUID
from enum import Enum

from open_skills.core.telemetry import get_logger

logger = get_logger(__name__)


class EventType(str, Enum):
    """Event types for streaming."""
    STATUS = "status"
    LOG = "log"
    OUTPUT = "output"
    ARTIFACT = "artifact"
    ERROR = "error"
    COMPLETE = "complete"


class ExecutionEventBus:
    """
    Simple in-memory event bus for execution events.

    In production, this could be replaced with Redis pub/sub or similar.
    """

    def __init__(self):
        self._listeners: Dict[UUID, asyncio.Queue] = {}

    def subscribe(self, run_id: UUID) -> asyncio.Queue:
        """
        Subscribe to events for a specific run.

        Args:
            run_id: Run UUID to subscribe to

        Returns:
            asyncio.Queue that will receive events
        """
        if run_id not in self._listeners:
            self._listeners[run_id] = asyncio.Queue()

        logger.info("event_bus_subscribed", run_id=str(run_id))
        return self._listeners[run_id]

    def unsubscribe(self, run_id: UUID) -> None:
        """
        Unsubscribe from events for a run.

        Args:
            run_id: Run UUID to unsubscribe from
        """
        if run_id in self._listeners:
            del self._listeners[run_id]
            logger.info("event_bus_unsubscribed", run_id=str(run_id))

    async def emit(self, run_id: UUID, event_type: EventType, data: Dict[str, Any]) -> None:
        """
        Emit an event for a specific run.

        Args:
            run_id: Run UUID
            event_type: Type of event
            data: Event data payload
        """
        if run_id in self._listeners:
            event = {
                "type": event_type.value,
                "data": data,
            }
            await self._listeners[run_id].put(event)
            logger.debug(
                "event_emitted",
                run_id=str(run_id),
                event_type=event_type.value,
            )

    async def stream_events(
        self,
        run_id: UUID,
        timeout: Optional[float] = None,
    ) -> AsyncIterator[Dict[str, Any]]:
        """
        Stream events for a run as an async iterator.

        Args:
            run_id: Run UUID
            timeout: Optional timeout in seconds for waiting for events

        Yields:
            Event dictionaries
        """
        queue = self.subscribe(run_id)

        try:
            while True:
                try:
                    if timeout:
                        event = await asyncio.wait_for(queue.get(), timeout=timeout)
                    else:
                        event = await queue.get()

                    yield event

                    # Stop streaming after complete/error event
                    if event["type"] in (EventType.COMPLETE.value, EventType.ERROR.value):
                        break

                except asyncio.TimeoutError:
                    # Send keepalive
                    yield {"type": "keepalive", "data": {}}

        finally:
            self.unsubscribe(run_id)


# Global event bus instance
_event_bus: Optional[ExecutionEventBus] = None


def get_event_bus() -> ExecutionEventBus:
    """Get the global event bus instance."""
    global _event_bus
    if _event_bus is None:
        _event_bus = ExecutionEventBus()
    return _event_bus


async def emit_status(run_id: UUID, status: str) -> None:
    """Emit a status change event."""
    bus = get_event_bus()
    await bus.emit(run_id, EventType.STATUS, {"status": status})


async def emit_log(run_id: UUID, line: str, stream: str = "stdout") -> None:
    """Emit a log line event."""
    bus = get_event_bus()
    await bus.emit(run_id, EventType.LOG, {"line": line, "stream": stream})


async def emit_output(run_id: UUID, key: str, value: Any) -> None:
    """Emit an output key-value event."""
    bus = get_event_bus()
    await bus.emit(run_id, EventType.OUTPUT, {"key": key, "value": value})


async def emit_artifact(
    run_id: UUID,
    filename: str,
    url: Optional[str] = None,
    size_bytes: Optional[int] = None,
) -> None:
    """Emit an artifact creation event."""
    bus = get_event_bus()
    await bus.emit(
        run_id,
        EventType.ARTIFACT,
        {
            "filename": filename,
            "url": url,
            "size_bytes": size_bytes,
        }
    )


async def emit_error(run_id: UUID, error: str, traceback: Optional[str] = None) -> None:
    """Emit an error event."""
    bus = get_event_bus()
    await bus.emit(
        run_id,
        EventType.ERROR,
        {
            "error": error,
            "traceback": traceback,
        }
    )


async def emit_complete(
    run_id: UUID,
    status: str,
    outputs: Dict[str, Any],
    duration_ms: int,
) -> None:
    """Emit a completion event."""
    bus = get_event_bus()
    await bus.emit(
        run_id,
        EventType.COMPLETE,
        {
            "status": status,
            "outputs": outputs,
            "duration_ms": duration_ms,
        }
    )


def format_sse_event(event: Dict[str, Any]) -> str:
    """
    Format an event as Server-Sent Events (SSE) format.

    Args:
        event: Event dictionary with 'type' and 'data'

    Returns:
        SSE formatted string
    """
    event_type = event.get("type", "message")
    data = event.get("data", {})

    # SSE format: event: type\ndata: json\n\n
    return f"event: {event_type}\ndata: {json.dumps(data)}\n\n"
