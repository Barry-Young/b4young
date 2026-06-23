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


# --------------------------------------------------------------------------- #
# Data Plane: Blackboard + crews
# --------------------------------------------------------------------------- #
class CrewName(str, Enum):
    """Crews defined in docs/03-agent-crews.md (matches the Blackboard schema)."""

    MARKET_INTELLIGENCE = "market_intelligence"
    CONTENT_FACTORY = "content_factory"
    MARKETING_DISTRIBUTION = "marketing_distribution"
    AUTOMATED_SERVICE_DELIVERY = "automated_service_delivery"


class BlackboardStatus(str, Enum):
    """Lifecycle of a Blackboard artifact (matches the Blackboard schema).

    AWAITING_APPROVAL is the formal Human-in-the-Loop gate: downstream crews
    must not consume an entry until it reaches APPROVED (or COMPLETE).
    """

    IN_PROGRESS = "IN_PROGRESS"
    COMPLETE = "COMPLETE"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"


class BlackboardReference(BaseModel):
    """Pointer to a large binary asset stored outside the Blackboard."""

    kind: str
    uri: str
    content_type: str | None = None


class BlackboardEntry(BaseModel):
    """A single entry on the shared Blackboard.

    Conforms to docs/schemas/blackboard.schema.json (v1). Use
    `to_schema_dict()` to obtain a dict that validates against that schema.
    """

    schema_version: str = "1.0.0"
    task_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    parent_task_id: str | None = None
    crew: CrewName
    producer_agent: str
    artifact_type: str
    status: BlackboardStatus
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)
    references: list[BlackboardReference] = Field(default_factory=list)
    payload: dict = Field(default_factory=dict)
    metadata: dict | None = None

    def to_schema_dict(self) -> dict:
        """JSON-ready dict that validates against blackboard.schema.json."""
        import json

        return json.loads(self.model_dump_json(exclude_none=True))


class CrewRunStatus(str, Enum):
    """Lifecycle of a crew run (which may pause at HITL checkpoints)."""

    RUNNING = "RUNNING"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"


class CrewRun(BaseModel):
    """State of a single crew execution.

    Crew runs are resumable: when a checkpoint task produces its artifact the
    run pauses in AWAITING_APPROVAL until the artifact is approved, then resumes
    from `next_index`. This is the programmatic Human-in-the-Loop gate
    (docs/05-governance-security.md, 5.3).
    """

    id: str = Field(default_factory=_new_id)
    crew: CrewName
    directive: str = ""
    status: CrewRunStatus = CrewRunStatus.RUNNING
    next_index: int = 0
    entry_ids: list[str] = Field(default_factory=list)
    pending_task_id: str | None = None
    report: str | None = None
    activity_id: str | None = None
    error: str | None = None
    governance_flags: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)


class CrewInfo(BaseModel):
    """Catalog entry for a deployable crew."""

    key: CrewName
    display_name: str
    description: str


# --------------------------------------------------------------------------- #
# Evaluation framework (golden dataset + LLM-as-judge)
# --------------------------------------------------------------------------- #
class EvalCase(BaseModel):
    """A golden test case: a directive and expectations about the output."""

    id: str
    name: str
    crew: CrewName
    directive: str
    expect_terms: list[str] = Field(default_factory=list)
    forbid_terms: list[str] = Field(default_factory=list)


class EvalResult(BaseModel):
    """The judged outcome of running a single golden case."""

    case_id: str
    name: str
    crew: CrewName
    score: float
    passed: bool
    rationale: str
    governance_flags: list[str] = Field(default_factory=list)


class EvalReport(BaseModel):
    """Aggregate evaluation results."""

    results: list[EvalResult] = Field(default_factory=list)
    total: int = 0
    passed: int = 0
    average_score: float = 0.0


