"""Simple JSON-file backed persistence for blueprints and activity logs.

This is the Phase 1 MVP store. It is intentionally minimal: a thread-safe,
file-backed repository sufficient for a single-node Control Plane. The roadmap
(docs/06-roadmap.md) replaces this with a managed relational/NoSQL store in
later phases.

Secrets are deliberately NOT persisted here; see vault.py.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

from .models import ActivityLogEntry, AgentBlueprint

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


class _JsonRepository:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.Lock()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        if not self._path.exists():
            self._write([])

    def _read(self) -> list[dict]:
        with self._path.open("r", encoding="utf-8") as fh:
            return json.load(fh)

    def _write(self, items: list[dict]) -> None:
        tmp = self._path.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump(items, fh, indent=2, default=str)
        tmp.replace(self._path)


class BlueprintStore(_JsonRepository):
    def list(self) -> list[AgentBlueprint]:
        return [AgentBlueprint(**row) for row in self._read()]

    def get(self, blueprint_id: str) -> AgentBlueprint | None:
        for row in self._read():
            if row["id"] == blueprint_id:
                return AgentBlueprint(**row)
        return None

    def add(self, blueprint: AgentBlueprint) -> AgentBlueprint:
        with self._lock:
            rows = self._read()
            rows.append(json.loads(blueprint.model_dump_json()))
            self._write(rows)
        return blueprint

    def delete(self, blueprint_id: str) -> bool:
        with self._lock:
            rows = self._read()
            kept = [r for r in rows if r["id"] != blueprint_id]
            if len(kept) == len(rows):
                return False
            self._write(kept)
        return True


class ActivityStore(_JsonRepository):
    def add(self, entry: ActivityLogEntry) -> ActivityLogEntry:
        with self._lock:
            rows = self._read()
            rows.append(json.loads(entry.model_dump_json()))
            self._write(rows)
        return entry

    def list(self, limit: int = 50) -> list[ActivityLogEntry]:
        rows = self._read()
        rows.sort(key=lambda r: r.get("started_at", ""), reverse=True)
        return [ActivityLogEntry(**row) for row in rows[:limit]]


def build_stores(data_dir: Path = DATA_DIR) -> tuple[BlueprintStore, ActivityStore]:
    return (
        BlueprintStore(data_dir / "blueprints.json"),
        ActivityStore(data_dir / "activity.json"),
    )
