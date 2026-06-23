"""Pydantic models for the Control Plane.

These mirror the agent configuration concepts described in
docs/01-architecture.md (Agent Design Studio: Role, Goal, Backstory, Tools) and
the activity records streamed back from the Data Plane.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> str:
    return uuid.uuid4().hex


class RunStatus(str, Enum):
    """Lifecycle of a single agent run, recorded in the activity log."""

    RUNNING = "RUNNING"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"


class AgentBlueprintCreate(BaseModel):
    """Input payload for defining a new agent blueprint."""

    name: str = Field(..., min_length=1, max_length=120)
    role: str = Field(..., min_length=1, description="The agent's job title, e.g. 'Trend Analyst'.")
    goal: str = Field(..., min_length=1, description="The intended outcome of the agent's tasks.")
    backstory: str = Field("", description="Context that primes the model for role-appropriate output.")
    tools: list[str] = Field(default_factory=list, description="Names of tools/APIs the agent may use.")
    model: str = Field("stub", description="Provider/model the agent runs on. 'stub' = no external LLM.")


class AgentBlueprint(AgentBlueprintCreate):
    """A stored agent blueprint."""

    id: str = Field(default_factory=_new_id)
    created_at: datetime = Field(default_factory=_now)


class RunRequest(BaseModel):
    """Input passed to an agent when it is run."""

    input: str = Field("", description="The task/prompt for the agent.")


class ActivityLogEntry(BaseModel):
    """A single record of agent activity, the unit shown on the dashboard."""

    id: str = Field(default_factory=_new_id)
    blueprint_id: str
    blueprint_name: str
    status: RunStatus
    input: str = ""
    output: str = ""
    error: str | None = None
    governance_flags: list[str] = Field(default_factory=list)
    started_at: datetime = Field(default_factory=_now)
    finished_at: datetime | None = None
    duration_ms: int | None = None


class VaultKeyCreate(BaseModel):
    """Register/update a secret in the vault."""

    name: str = Field(..., min_length=1, max_length=120)
    value: str = Field(..., min_length=1)


class VaultKeyInfo(BaseModel):
    """Non-sensitive view of a vault key (never exposes the raw secret)."""

    name: str
    is_set: bool
    preview: str
