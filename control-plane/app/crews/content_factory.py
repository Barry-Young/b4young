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
            description=(
                "Refine the topic into a compelling angle and a detailed outline. "
                "State the specific difficulty the audience is living with, the "
                "reframe that shifts it, and the two or three concrete steps the "
                "piece will leave them with. Name the platform and target length."
            ),
            agent=Agent(
                role="Content Strategist",
                goal="Develop a content angle and outline optimized for the platform.",
                backstory="Shapes narratives around the brand's core pillars.",
                artifact_type="content_outline",
            ),
        ),
        Task(
            description=(
                "Write the full script from the approved outline, in brand voice. "
                "Deliver a package that can be filmed as-is:\n"
                "1. Hook — the first three seconds, as spoken words plus on-screen text.\n"
                "2. Body — name the real difficulty, then the reframe.\n"
                "3. Practical anchor — two or three concrete, small steps.\n"
                "4. Close — a short encouraging line and a soft call to action.\n"
                "5. Production notes — on-screen text and b-roll per section.\n"
                "6. Caption — post copy plus relevant hashtags.\n"
                "7. Two alternate hooks to A/B test.\n"
                "Write spoken lines the way they will be said out loud."
            ),
            agent=Agent(
                role="Scriptwriter",
                goal=(
                    "Produce a ready-to-film, brand-aligned short-form script package: "
                    "hook, body, practical steps, close, production notes, caption with "
                    "hashtags, and alternate hooks to test."
                ),
                backstory=(
                    "A short-form specialist who has studied what makes the first three "
                    "seconds work, writing in the byoungimprovements voice. Writes for one "
                    "person watching alone, never for an audience."
                ),
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
