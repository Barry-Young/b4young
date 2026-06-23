"""The 'Content Factory' crew (docs/03-agent-crews.md, 3.2).

Executive Producer (orchestrator) coordinating Content Strategist, Scriptwriter,
Voice Artist, and Video Producer to turn a brief into a content package.

Human-in-the-Loop: the run pauses after the Scriptwriter's draft (a mid-pipeline
checkpoint) and again at the final content package — the two checkpoints called
for in Phase 3 of the roadmap (docs/06-roadmap.md, 6.3).
"""

from __future__ import annotations

from ..constitution import BrandConstitution
from ..models import CrewName
from ..vault import Vault
from .base import Agent, Crew, Task
from .blackboard import Blackboard, EventBus

DISPLAY_NAME = "Content Factory"
DESCRIPTION = (
    "An autonomous production house: turn a strategic brief into a brand-aligned "
    "content package (outline, script, voiceover, video), with human approval "
    "after the script and before publishing."
)


def build(
    *,
    blackboard: Blackboard,
    vault: Vault,
    constitution: BrandConstitution,
) -> Crew:
    orchestrator = Agent(
        role="Executive Producer",
        goal="Plan production and assemble the final content package.",
        backstory="Runs the production pipeline from brief to publish-ready assets.",
        artifact_type="content_package",
    )

    tasks = [
        Task(
            description="Refine the topic into a compelling angle and a detailed outline.",
            agent=Agent(
                role="Content Strategist",
                goal="Develop a content angle and outline optimized for the platform.",
                backstory="Shapes narratives around the brand's core pillars.",
                artifact_type="content_outline",
            ),
        ),
        Task(
            description="Write the full script from the approved outline, in brand voice.",
            agent=Agent(
                role="Scriptwriter",
                goal="Produce a compelling, brand-aligned script.",
                backstory="Writes in the byoungimprovements voice using few-shot examples.",
                artifact_type="script",
            ),
            checkpoint=True,  # HITL: approve the script before voiceover
        ),
        Task(
            description="Convert the approved script to a voiceover using the brand voice.",
            agent=Agent(
                role="Voice Artist",
                goal="Generate a consistent, authentic brand voiceover.",
                backstory="Uses a brand-cloned TTS voice.",
                artifact_type="voiceover_ref",
            ),
        ),
        Task(
            description="Assemble the final video from the voiceover and script.",
            agent=Agent(
                role="Video Producer",
                goal="Produce a polished, ready-to-publish video.",
                backstory="Assembles scenes, overlays, and avatar into the final cut.",
                artifact_type="video_package",
            ),
        ),
    ]

    return Crew(
        name=CrewName.CONTENT_FACTORY,
        display_name=DISPLAY_NAME,
        orchestrator=orchestrator,
        tasks=tasks,
        blackboard=blackboard,
        event_bus=EventBus(),
        vault=vault,
        constitution=constitution,
        final_artifact_type="content_package",
        final_checkpoint=True,  # HITL: approve the package before publishing
    )
