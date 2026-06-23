"""Data Plane runtime: the shared Blackboard and event-driven message bus.

Adapted from the reference implementation (blueprint_builder_v1.py) and aligned
with the architecture docs:
  * Blackboard pattern — docs/02-multi-agent-ecosystem.md (2.4.2)
  * Event-driven bus  — docs/02-multi-agent-ecosystem.md (2.4.1)

The Blackboard writes entries that conform to docs/schemas/blackboard.schema.json
and persists them via the Control Plane's BlackboardStore so crew output is
inspectable and consumable by other crews without custom parsing.
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any, Callable

from ..models import (
    BlackboardEntry,
    BlackboardStatus,
    CrewName,
)
from ..store import BlackboardStore


class Blackboard:
    """Schema-aware shared memory backed by the BlackboardStore."""

    def __init__(self, store: BlackboardStore) -> None:
        self._store = store
        self._lock = threading.Lock()

    def write_entry(
        self,
        *,
        crew: CrewName,
        producer_agent: str,
        artifact_type: str,
        payload: dict,
        status: BlackboardStatus = BlackboardStatus.COMPLETE,
        parent_task_id: str | None = None,
        metadata: dict | None = None,
    ) -> BlackboardEntry:
        entry = BlackboardEntry(
            crew=crew,
            producer_agent=producer_agent,
            artifact_type=artifact_type,
            payload=payload,
            status=status,
            parent_task_id=parent_task_id,
            metadata=metadata,
        )
        with self._lock:
            self._store.add(entry)
        return entry

    def read(self, task_id: str) -> BlackboardEntry | None:
        return self._store.get(task_id)


class EventBus:
    """Synchronous publish/subscribe bus.

    Dispatch is synchronous so a crew run returns a complete, deterministic
    result within a single request — appropriate for the MVP. The pub/sub API
    is preserved so a later phase can swap in SQS/PubSub/Kafka transport.
    """

    def __init__(self) -> None:
        self._subscribers: dict[str, list[Callable[[dict[str, Any]], None]]] = {}
        self.published: list[dict[str, Any]] = []

    def subscribe(self, event_type: str, callback: Callable[[dict[str, Any]], None]) -> None:
        self._subscribers.setdefault(event_type, []).append(callback)

    def publish(self, event_type: str, payload: dict[str, Any]) -> None:
        self.published.append({"type": event_type, "payload": payload})
        for callback in self._subscribers.get(event_type, []):
            callback(payload)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)
