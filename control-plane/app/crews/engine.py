"""Crew execution engine with a resumable Human-in-the-Loop lifecycle.

A crew run executes its worker tasks in order, then the orchestrator synthesizes
a final artifact. Any task marked as a checkpoint (and the final artifact, when
`final_checkpoint` is set) pauses the run in AWAITING_APPROVAL until the artifact
is approved, at which point the run resumes from where it left off.

`auto_approve=True` runs straight through without pausing — used by the
evaluation framework.
"""

from __future__ import annotations

from datetime import datetime, timezone

from ..constitution import BrandConstitution
from ..models import (
    ActivityLogEntry,
    BlackboardStatus,
    CrewName,
    CrewRun,
    CrewRunStatus,
    RunStatus,
)
from ..store import ActivityStore, BlackboardStore, CrewRunStore
from ..vault import Vault
from .base import Crew
from .blackboard import Blackboard


def _now() -> datetime:
    return datetime.now(timezone.utc)


def start_run(
    crew: Crew,
    directive: str,
    *,
    activity: ActivityStore,
    crew_runs: CrewRunStore,
    auto_approve: bool = False,
) -> CrewRun:
    run = CrewRun(crew=crew.name, directive=directive, status=CrewRunStatus.RUNNING)
    crew_runs.add(run)
    return _advance(run, crew, activity=activity, crew_runs=crew_runs, auto_approve=auto_approve)


def resume_run(
    run: CrewRun,
    crew: Crew,
    *,
    activity: ActivityStore,
    crew_runs: CrewRunStore,
) -> CrewRun:
    run.pending_task_id = None
    run.status = CrewRunStatus.RUNNING
    run.updated_at = _now()
    crew_runs.update(run)
    return _advance(run, crew, activity=activity, crew_runs=crew_runs, auto_approve=False)


def _advance(
    run: CrewRun,
    crew: Crew,
    *,
    activity: ActivityStore,
    crew_runs: CrewRunStore,
    auto_approve: bool,
) -> CrewRun:
    n = len(crew.tasks)
    try:
        while True:
            i = run.next_index
            if i < n:
                task = crew.tasks[i]
                is_checkpoint = task.checkpoint and not auto_approve
                entry = task.agent.perform_task(
                    description=task.description,
                    directive=run.directive,
                    crew=crew.name,
                    blackboard=crew.blackboard,
                    event_bus=crew.event_bus,
                    vault=crew.vault,
                    constitution=crew.constitution,
                    status=BlackboardStatus.AWAITING_APPROVAL
                    if is_checkpoint
                    else BlackboardStatus.COMPLETE,
                )
                run.entry_ids.append(entry.task_id)
                run.next_index = i + 1
                if is_checkpoint:
                    return _pause(run, entry.task_id, crew_runs)
            elif i == n:
                entry = _synthesize(run, crew, auto_approve=auto_approve)
                run.entry_ids.append(entry.task_id)
                run.next_index = i + 1
                if crew.final_checkpoint and not auto_approve:
                    return _pause(run, entry.task_id, crew_runs)
            else:
                return _complete(run, crew, activity=activity, crew_runs=crew_runs)
    except Exception as exc:  # noqa: BLE001 - surface failures on the run
        run.status = CrewRunStatus.FAILED
        run.error = f"{type(exc).__name__}: {exc}"
        run.updated_at = _now()
        crew_runs.update(run)
        raise


def _pause(run: CrewRun, task_id: str, crew_runs: CrewRunStore) -> CrewRun:
    run.pending_task_id = task_id
    run.status = CrewRunStatus.AWAITING_APPROVAL
    run.updated_at = _now()
    return crew_runs.update(run)


def _synthesize(run: CrewRun, crew: Crew, *, auto_approve: bool):
    """Orchestrator aggregates worker artifacts into the final report."""
    lines = [f"# {crew.display_name} Brief", f"**Directive:** {run.directive or '(none)'}", ""]
    for task_id in run.entry_ids:
        entry = crew.blackboard.read(task_id)
        if entry is None:
            continue
        lines.append(f"## {entry.producer_agent} — {entry.artifact_type}")
        lines.append(entry.payload.get("output", ""))
        lines.append("")
    report = "\n".join(lines).strip()
    run.report = report

    status = BlackboardStatus.COMPLETE if auto_approve else BlackboardStatus.AWAITING_APPROVAL
    return crew.blackboard.write_entry(
        crew=crew.name,
        producer_agent=crew.orchestrator.role,
        artifact_type=crew.final_artifact_type,
        payload={"directive": run.directive, "report": report},
        status=status,
        metadata={"model": crew.orchestrator.model, "worker_tasks": len(crew.tasks)},
    )


def _complete(
    run: CrewRun,
    crew: Crew,
    *,
    activity: ActivityStore,
    crew_runs: CrewRunStore,
) -> CrewRun:
    flags = sorted(
        {
            flag
            for task_id in run.entry_ids
            for flag in ((crew.blackboard.read(task_id) or _empty()).metadata or {}).get(
                "governance_flags", []
            )
        }
    )
    log = ActivityLogEntry(
        blueprint_id=f"crew:{crew.name.value}",
        blueprint_name=crew.display_name,
        status=RunStatus.COMPLETE,
        input=run.directive,
        output=run.report or "",
        governance_flags=flags,
        finished_at=_now(),
        duration_ms=0,
    )
    activity.add(log)

    run.status = CrewRunStatus.COMPLETE
    run.pending_task_id = None
    run.governance_flags = flags
    run.activity_id = log.id
    run.updated_at = _now()
    return crew_runs.update(run)


class _empty:
    metadata: dict | None = None
