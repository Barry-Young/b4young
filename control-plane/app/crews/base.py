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

from collections.abc import Callable
from dataclasses import dataclass, field

from ..constitution import BrandConstitution
from ..models import BlackboardEntry, BlackboardStatus, CrewName
from ..providers import DEFAULT_AGENT_MODEL, get_provider
from ..vault import Vault
from .blackboard import Blackboard, EventBus


@dataclass
class CheckResult:
    """The verdict of an artifact-specific check on one draft.

    `flags` is what the human sees. `distance` is how far the draft is from
    meeting the requirement — 0 when it meets it, higher when it misses by
    more — and exists so two drafts can be compared. Flag count alone cannot:
    a script cut from 185 words to 140 still carries one flag, and is plainly
    the better draft.
    """

    flags: list[str] = field(default_factory=list)
    distance: float = 0.0

    def __bool__(self) -> bool:
        return bool(self.flags)


@dataclass
class Agent:
    """A specialized agent within a crew."""

    role: str
    goal: str
    backstory: str
    artifact_type: str
    model: str = field(default_factory=lambda: DEFAULT_AGENT_MODEL)
    # An optional artifact-specific check, run alongside the Brand Constitution's
    # and merged into the same governance flags. The Constitution polices voice,
    # which is shared by every agent; a rule like "a 60-second script is about
    # 120 spoken words" belongs to one artifact and cannot live there. Takes the
    # output and the directive, returns a CheckResult.
    output_check: Callable[[str, str], CheckResult] | None = None
    # When the check fails, hand the draft back once with the reason. Objective
    # requirements — a word budget — are worth one more attempt; a warning
    # nobody acts on is not a constraint, it is a note.
    revise_once: bool = False

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

        # Placeholder text is not the artifact, so artifact-specific rules have
        # nothing to say about it — running them on a stub only reports that the
        # stub isn't a script. Voice rules still apply: a banned term in stub
        # output is worth seeing.
        checking = self.output_check is not None and not provider.is_stub
        result = self.output_check(output, directive) if checking else CheckResult()

        revised = False
        if result and self.revise_once:
            output, result, revised = self._revise(
                provider=provider,
                system=system,
                prompt=prompt,
                draft=output,
                result=result,
                directive=directive,
            )

        flags = constitution.check_output(output) + list(result.flags)

        entry = blackboard.write_entry(
            crew=crew,
            producer_agent=self.role,
            artifact_type=self.artifact_type,
            payload={"task": description, "directive": directive, "output": output},
            status=status,
            parent_task_id=parent_task_id,
            # Record the *resolved* provider, not just the requested model: with
            # `auto` the two differ, and the log has to make it obvious whether
            # this artifact is a real draft or stub placeholder text.
            metadata={
                "model": self.model,
                "resolved_model": provider.name,
                "is_stub": provider.is_stub,
                "governance_flags": flags,
                "revised": revised,
            },
        )
        event_bus.publish(f"{self.role}.complete", {"task_id": entry.task_id})
        return entry

    def _revise(
        self,
        *,
        provider,
        system: str,
        prompt: str,
        draft: str,
        result: CheckResult,
        directive: str,
    ) -> tuple[str, CheckResult, bool]:
        """One more attempt, told exactly what it missed and by how much.

        The retry keeps the closer of the two drafts rather than the newer one:
        a rewrite can overshoot in the other direction, and the first draft is
        not automatically the worse of the pair.
        """
        reasons = "\n".join(f"  - {flag}" for flag in result.flags)
        retry_prompt = (
            f"{prompt}\n\n"
            "REVISE. A previous attempt at this task failed a hard requirement:\n"
            f"{reasons}\n\n"
            "That attempt was:\n"
            "---\n"
            f"{draft}\n"
            "---\n\n"
            "Produce the whole artifact again, meeting the requirement this "
            "time. Keep what is good — the angle, the voice, the strongest "
            "lines — and cut or tighten the rest. Do not simply trim the "
            "ending. Meeting the requirement is not optional; a draft that "
            "misses it again has failed twice."
        )

        candidate = provider.generate(retry_prompt, system=system)
        candidate_result = (
            self.output_check(candidate, directive)
            if self.output_check is not None
            else CheckResult()
        )
        if candidate_result.distance < result.distance:
            return candidate, candidate_result, True
        return draft, result, False


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
