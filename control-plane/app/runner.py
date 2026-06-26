"""Agent runner.

Executes a single agent blueprint: builds a Brand-Constitution-aware system
prompt, calls the configured provider, enforces governance on the output, and
records the run in the activity log. This is the minimal stand-in for the Data
Plane's task execution + activity streaming (docs/01-architecture.md, 1.3.2).
"""

from __future__ import annotations

from datetime import timezone

from . import crews as crew_registry
from .constitution import BrandConstitution
from .crews import engine
from .crews.blackboard import Blackboard
from .models import (
    ActivityLogEntry,
    AgentBlueprint,
    BlackboardEntry,
    CrewName,
    CrewRun,
    CrewRunStatus,
    RunStatus,
)
from .providers import get_provider
from .store import ActivityStore, BlackboardStore, CrewRunStore
from .vault import Vault


def run_blueprint(
    blueprint: AgentBlueprint,
    task_input: str,
    *,
    vault: Vault,
    constitution: BrandConstitution,
    activity: ActivityStore,
) -> ActivityLogEntry:
    entry = ActivityLogEntry(
        blueprint_id=blueprint.id,
        blueprint_name=blueprint.name,
        status=RunStatus.RUNNING,
        input=task_input,
    )

    try:
        provider = get_provider(blueprint.model, vault)
        system = constitution.system_prompt(blueprint.role, blueprint.goal, blueprint.backstory)
        output = provider.generate(task_input, system=system)
        entry.output = output
        entry.governance_flags = constitution.check_output(output)
        entry.status = RunStatus.COMPLETE
    except Exception as exc:  # noqa: BLE001 - surface any failure in the log
        entry.status = RunStatus.FAILED
        entry.error = f"{type(exc).__name__}: {exc}"

    entry.finished_at = entry.finished_at or _utcnow(entry)
    entry.duration_ms = int((entry.finished_at - entry.started_at).total_seconds() * 1000)
    return activity.add(entry)


def _utcnow(entry: ActivityLogEntry):
    from datetime import datetime

    # started_at is tz-aware; keep finished_at consistent.
    return datetime.now(timezone.utc)


# Crew pipeline: when a crew's final artifact is APPROVED, the downstream crew
# is automatically deployed with that artifact as its directive (consuming the
# approved Blackboard entry — docs/02-multi-agent-ecosystem.md, cross-crew flow).
PIPELINE: dict[CrewName, CrewName] = {
    CrewName.MARKET_INTELLIGENCE: CrewName.CONTENT_FACTORY,
}


def start_crew(
    crew_key: CrewName,
    directive: str,
    *,
    vault: Vault,
    constitution: BrandConstitution,
    activity: ActivityStore,
    blackboard_store: BlackboardStore,
    crew_runs: CrewRunStore,
    source_task_id: str | None = None,
) -> CrewRun:
    """Deploy a crew and run it until completion or the first HITL checkpoint."""
    blackboard = Blackboard(blackboard_store)
    crew = crew_registry.build_crew(
        crew_key, blackboard=blackboard, vault=vault, constitution=constitution
    )
    return engine.start_run(
        crew, directive, activity=activity, crew_runs=crew_runs, source_task_id=source_task_id
    )


def maybe_chain_downstream(
    approved_entry: BlackboardEntry,
    completed_run: CrewRun | None,
    *,
    vault: Vault,
    constitution: BrandConstitution,
    activity: ActivityStore,
    blackboard_store: BlackboardStore,
    crew_runs: CrewRunStore,
) -> CrewRun | None:
    """If approving an entry completed a crew run that has a downstream crew in
    the pipeline, deploy that downstream crew with the approved brief."""
    if completed_run is None or completed_run.status != CrewRunStatus.COMPLETE:
        return None
    downstream = PIPELINE.get(completed_run.crew)
    if downstream is None:
        return None
    directive = approved_entry.payload.get("report") or approved_entry.payload.get("output") or ""
    return start_crew(
        downstream,
        directive,
        vault=vault,
        constitution=constitution,
        activity=activity,
        blackboard_store=blackboard_store,
        crew_runs=crew_runs,
        source_task_id=approved_entry.task_id,
    )


def resume_crew_for_entry(
    task_id: str,
    *,
    vault: Vault,
    constitution: BrandConstitution,
    activity: ActivityStore,
    blackboard_store: BlackboardStore,
    crew_runs: CrewRunStore,
) -> CrewRun | None:
    """Resume the crew run (if any) waiting on the given approved checkpoint."""
    run = crew_runs.find_by_pending(task_id)
    if run is None:
        return None
    blackboard = Blackboard(blackboard_store)
    crew = crew_registry.build_crew(
        run.crew, blackboard=blackboard, vault=vault, constitution=constitution
    )
    return engine.resume_run(run, crew, activity=activity, crew_runs=crew_runs)
