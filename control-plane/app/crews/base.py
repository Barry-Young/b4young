"""Agent / Task / Crew primitives for the Data Plane.

Adapted from the reference implementation (blueprint_builder_v1.py) and unified
with the Control Plane: agents run through the model-agnostic provider
abstraction (app/providers.py) under the Brand Constitution (app/constitution.py),
and write their output to the schema-aware Blackboard.

Crews follow the Orchestrator-Worker pattern (docs/02-multi-agent-ecosystem.md,
2.2). Execution and the resumable Human-in-the-Loop lifecycle live in
engine.py; this module holds the primitives.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..constitution import BrandConstitution
from ..models import BlackboardEntry, BlackboardStatus, CrewName
from ..providers import DEFAULT_AGENT_MODEL, get_provider
from ..vault import Vault
from .blackboard import Blackboard, EventBus


@dataclass
class Agent:
    """A specialized agent within a crew."""

    role: str
    goal: str
    backstory: str
    artifact_type: str
    model: str = field(default_factory=lambda: DEFAULT_AGENT_MODEL)

    def perform_task(
        self,
        *,
        description: str,
        directive: str,
        crew: CrewName,
        blackboard: Blackboard,
        event_bus: EventBus,
        vault: Vault,
        constitution: BrandConstitution,
        status: BlackboardStatus = BlackboardStatus.COMPLETE,
        parent_task_id: str | None = None,
    ) -> BlackboardEntry:
        provider = get_provider(self.model, vault)
        system = constitution.system_prompt(self.role, self.goal, self.backstory)
        prompt = f"{description}\n\nDirective: {directive}".strip()
        output = provider.generate(prompt, system=system)
        flags = constitution.check_output(output)

        entry = blackboard.write_entry(
            crew=crew,
            producer_agent=self.role,
            artifact_type=self.artifact_type,
            payload={"task": description, "directive": directive, "output": output},
            status=status,
            parent_task_id=parent_task_id,
            metadata={"model": self.model, "governance_flags": flags},
        )
        event_bus.publish(f"{self.role}.complete", {"task_id": entry.task_id})
        return entry


@dataclass
class Task:
    """A unit of work assigned to a worker agent.

    `checkpoint=True` makes the run pause for human approval after this task's
    artifact is produced (a Human-in-the-Loop gate).
    """

    description: str
    agent: Agent
    checkpoint: bool = False


@dataclass
class Crew:
    """A deployable crew: an orchestrator plus ordered worker tasks."""

    name: CrewName
    display_name: str
    orchestrator: Agent
    tasks: list[Task]
    blackboard: Blackboard
    event_bus: EventBus
    vault: Vault
    constitution: BrandConstitution
    final_artifact_type: str = "brief"
    final_checkpoint: bool = True
