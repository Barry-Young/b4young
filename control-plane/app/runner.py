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
from .crews.blackboard import Blackboard
from .models import (
    ActivityLogEntry,
    AgentBlueprint,
    CrewName,
    CrewRunResult,
    RunStatus,
)
from .providers import get_provider
from .store import ActivityStore, BlackboardStore
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


def run_crew(
    crew_key: CrewName,
    directive: str,
    *,
    vault: Vault,
    constitution: BrandConstitution,
    activity: ActivityStore,
    blackboard_store: BlackboardStore,
) -> CrewRunResult:
    """Deploy and run a crew, persisting Blackboard entries and logging the run."""
    from datetime import datetime

    blackboard = Blackboard(blackboard_store)
    crew = crew_registry.build_crew(
        crew_key, blackboard=blackboard, vault=vault, constitution=constitution
    )

    log = ActivityLogEntry(
        blueprint_id=f"crew:{crew_key.value}",
        blueprint_name=crew.display_name,
        status=RunStatus.RUNNING,
        input=directive,
    )
    try:
        report, entries, final_task_id = crew.run(directive)
        flags = sorted(
            {
                flag
                for entry in entries
                for flag in (entry.metadata or {}).get("governance_flags", [])
            }
        )
        log.output = report
        log.governance_flags = flags
        log.status = RunStatus.COMPLETE
    except Exception as exc:  # noqa: BLE001
        log.status = RunStatus.FAILED
        log.error = f"{type(exc).__name__}: {exc}"
        log.finished_at = datetime.now(timezone.utc)
        log.duration_ms = int((log.finished_at - log.started_at).total_seconds() * 1000)
        activity.add(log)
        raise

    log.finished_at = datetime.now(timezone.utc)
    log.duration_ms = int((log.finished_at - log.started_at).total_seconds() * 1000)
    activity.add(log)

    return CrewRunResult(
        crew=crew_key,
        directive=directive,
        report=report,
        final_task_id=final_task_id,
        entries=entries,
        activity_id=log.id,
        governance_flags=flags,
    )
