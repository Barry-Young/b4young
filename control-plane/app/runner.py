"""Agent runner.

Executes a single agent blueprint: builds a Brand-Constitution-aware system
prompt, calls the configured provider, enforces governance on the output, and
records the run in the activity log. This is the minimal stand-in for the Data
Plane's task execution + activity streaming (docs/01-architecture.md, 1.3.2).
"""

from __future__ import annotations

from datetime import timezone

from .constitution import BrandConstitution
from .models import ActivityLogEntry, AgentBlueprint, RunStatus
from .providers import get_provider
from .store import ActivityStore
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
