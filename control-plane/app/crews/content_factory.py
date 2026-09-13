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
# The directive is free text, so the format is a stated convention rather than a
# parsed field. Both agents are given the same rule: honour a `Format:` clause if
# the directive carries one, else fall back to this default. Without it the
# Strategist invents a platform (it has picked Substack long-form) while the
# Scriptwriter writes short-form video, and the two artifacts contradict.
DEFAULT_FORMAT = "Instagram Reel, 45 seconds"

FORMAT_RULE = (
    "FORMAT. The directive may name one, written as "
    "`Format: <platform>, <length>` (e.g. `Format: Instagram Reel, 45 seconds`). "
    f"If it does, use exactly that. If it does not, use {DEFAULT_FORMAT}. "
    "Never substitute a different platform or length than the one in force."
)

# Unhurried delivery is roughly two spoken words per second, so a 45-second
# video is about 90 spoken words. Without a budget the Scriptwriter writes until
# the structure is complete and lands 3+ minutes of speech in a 45-second brief.
SPOKEN_WORDS_PER_SECOND = 2

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
                "piece will leave them with.\n\n"
                f"{FORMAT_RULE}\n"
                "Open the outline by stating the platform and length you are "
                "working to, then size every section to fit that length. Do not "
                "choose a platform of your own."
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
                "Write spoken lines the way they will be said out loud.\n\n"
                f"{FORMAT_RULE}\n"
                "LENGTH IS A HARD CONSTRAINT, not a suggestion. Delivery is "
                f"unhurried — about {SPOKEN_WORDS_PER_SECOND} spoken words per "
                "second — so a 45-second video is roughly 90 spoken words in "
                "total, across hook, body, steps and close combined. Work out "
                "the budget for the length in force, count the spoken words you "
                "have written, and cut until you are inside it. A script that "
                "covers every section but overruns the length is a failed "
                "script: cut the number of steps or the depth of the reframe "
                "before you exceed it.\n"
                "On-screen text, production notes, the caption and the hashtags "
                "are read, not spoken, and do not count toward the budget.\n"
                "State the spoken word count and the length you wrote to at the "
                "top of the package."
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
