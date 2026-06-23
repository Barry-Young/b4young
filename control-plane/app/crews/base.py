"""Agent / Task / Crew primitives for the Data Plane.

Adapted from the reference implementation (blueprint_builder_v1.py) and unified
with the Control Plane: agents run through the model-agnostic provider
abstraction (app/providers.py) under the Brand Constitution (app/constitution.py),
and write their output to the schema-aware Blackboard.

Crews follow the Orchestrator-Worker pattern (docs/02-multi-agent-ecosystem.md,
2.2): workers produce artifacts, then the orchestrator synthesizes a final brief
that is parked in AWAITING_APPROVAL — the formal Human-in-the-Loop gate.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..constitution import BrandConstitution
from ..models import BlackboardEntry, BlackboardStatus, CrewName
from ..providers import get_provider
from ..vault import Vault
from .blackboard import Blackboard, EventBus


@dataclass
class Agent:
    """A specialized agent within a crew."""

    role: str
    goal: str
    backstory: str
    artifact_type: str
    model: str = "stub"

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
            status=BlackboardStatus.COMPLETE,
            metadata={"model": self.model, "governance_flags": flags},
        )
        event_bus.publish(f"{self.role}.complete", {"task_id": entry.task_id})
        return entry


@dataclass
class Task:
    """A unit of work assigned to a worker agent."""

    description: str
    agent: Agent


@dataclass
class Crew:
    """Coordinates an orchestrator and its worker agents over a directive."""

    name: CrewName
    display_name: str
    orchestrator: Agent
    tasks: list[Task]
    blackboard: Blackboard
    event_bus: EventBus
    vault: Vault
    constitution: BrandConstitution
    _completed: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        for task in self.tasks:
            self.event_bus.subscribe(
                f"{task.agent.role}.complete",
                lambda payload: self._completed.append(payload["task_id"]),
            )

    def run(self, directive: str) -> tuple[str, list[BlackboardEntry], str]:
        """Run all worker tasks, then synthesize the orchestrator's brief.

        Returns (report, entries, final_task_id).
        """
        entries: list[BlackboardEntry] = []
        for task in self.tasks:
            entries.append(
                task.agent.perform_task(
                    description=task.description,
                    directive=directive,
                    crew=self.name,
                    blackboard=self.blackboard,
                    event_bus=self.event_bus,
                    vault=self.vault,
                    constitution=self.constitution,
                )
            )

        report = self._synthesize_report(directive, entries)
        final = self.blackboard.write_entry(
            crew=self.name,
            producer_agent=self.orchestrator.role,
            artifact_type="intelligence_brief",
            payload={"directive": directive, "report": report},
            status=BlackboardStatus.AWAITING_APPROVAL,  # HITL gate
            metadata={"model": self.orchestrator.model, "worker_tasks": len(entries)},
        )
        entries.append(final)
        return report, entries, final.task_id

    def _synthesize_report(self, directive: str, entries: list[BlackboardEntry]) -> str:
        lines = [
            f"# {self.display_name} Brief",
            f"**Directive:** {directive or '(none)'}",
            "",
        ]
        for entry in entries:
            lines.append(f"## {entry.producer_agent}")
            lines.append(entry.payload.get("output", ""))
            lines.append("")
        return "\n".join(lines).strip()
