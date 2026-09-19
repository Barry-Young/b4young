"""The 'Content Factory' crew (docs/03-agent-crews.md, 3.2).

Executive Producer (orchestrator) coordinating Content Strategist, Scriptwriter,
Voice Artist, and Video Producer to turn a brief into a content package.

Human-in-the-Loop: the run pauses after the Scriptwriter's draft (a mid-pipeline
checkpoint) and again at the final content package — the two checkpoints called
for in Phase 3 of the roadmap (docs/06-roadmap.md, 6.3).
"""

from __future__ import annotations

import re

from ..constitution import BrandConstitution
from ..models import CrewName
from ..vault import Vault
from .base import Agent, CheckResult, Crew, Task
from .blackboard import Blackboard, EventBus

DISPLAY_NAME = "Content Factory"
# The directive is free text, so the format is a stated convention rather than a
# parsed field. Both agents are given the same rule: honour a `Format:` clause if
# the directive carries one, else fall back to this default. Without it the
# Strategist invents a platform (it has picked Substack long-form) while the
# Scriptwriter writes short-form video, and the two artifacts contradict.
#
# The length is 90 seconds because that is where the writing actually lands.
# Briefed at 45 it produced 185 spoken words; rebriefed at 60, and handed back
# once to cut, it produced 176. The model counts accurately — the app verifies
# it — so this is not a failure to obey. It is what this structure costs in
# this voice: hook, the difficulty, the turn, one step, the door. Two targets
# were moved to fit a number neither run wanted. A genuinely short piece is a
# different shape, not this one trimmed.
DEFAULT_FORMAT = "Instagram Reel, 90 seconds"

FORMAT_RULE = (
    "FORMAT. The directive may name one, written as "
    "`Format: <platform>, <length>` (e.g. `Format: Instagram Reel, 30 seconds`). "
    f"If it does, use exactly that. If it does not, use {DEFAULT_FORMAT}. "
    "Never substitute a different platform or length than the one in force."
)

# Unhurried delivery is roughly two spoken words per second, so a 45-second
# video is about 90 spoken words. Without a budget the Scriptwriter writes until
# the structure is complete and lands 3+ minutes of speech in a 45-second brief.
SPOKEN_WORDS_PER_SECOND = 2

# The Scriptwriter reports its own spoken word count and gets it wrong — one
# 45-second script claimed 89 words and ran to about 120, half a minute over.
# Models cannot count their own output reliably, so the budget is checked here
# instead of trusted. Checking needs the spoken lines to be separable from
# on-screen text and production notes, hence the prefix: every spoken line
# stands alone, marked.
VO_PREFIX = "VO:"

# A script a shade over budget is not worth a flag; a script half again as long
# is the defect this catches.
LENGTH_TOLERANCE = 1.1

_LENGTH_PATTERN = re.compile(
    r"(\d+(?:\.\d+)?)\s*(seconds?|secs?|s|minutes?|mins?|m)\b", re.IGNORECASE
)
_WORD_PATTERN = re.compile(r"[0-9A-Za-z]")


def parse_length_seconds(directive: str) -> int | None:
    """Seconds of runtime the directive asks for, from its `Format:` clause.

    Falls back to the default format, so an unqualified directive is still
    checked. Returns None only when neither names a length.
    """
    for text in (directive, DEFAULT_FORMAT):
        match = _LENGTH_PATTERN.search(text or "")
        if match is None:
            continue
        value, unit = float(match.group(1)), match.group(2).lower()
        return round(value * 60) if unit.startswith("m") else round(value)
    return None


def spoken_words(output: str) -> list[str]:
    """Every word the voiceover actually says, from the marked lines.

    Punctuation-only tokens (a standalone em dash) are not words.
    """
    words: list[str] = []
    for line in output.splitlines():
        stripped = line.strip().lstrip("*_- ").strip()
        if not stripped.upper().startswith(VO_PREFIX):
            continue
        spoken = stripped[len(VO_PREFIX) :]
        words.extend(w for w in spoken.split() if _WORD_PATTERN.search(w))
    return words


def check_script_length(output: str, directive: str) -> CheckResult:
    """Flag a script that overruns its budget, or that can't be measured.

    `distance` is the count of words over budget, so a rewrite that cuts 185
    words to 140 is recognised as the better draft even though both overrun.
    """
    seconds = parse_length_seconds(directive)
    if seconds is None:
        return CheckResult()

    budget = seconds * SPOKEN_WORDS_PER_SECOND
    words = spoken_words(output)
    if not words:
        # Unmeasurable, so worse than any measurable draft: a rewrite that can
        # be counted at all should win, even if it also overruns.
        return CheckResult(
            flags=[
                f"spoken lines are not marked with `{VO_PREFIX}`, so the "
                f"{seconds}-second length budget could not be checked"
            ],
            distance=float("inf"),
        )

    count = len(words)
    if count > budget * LENGTH_TOLERANCE:
        over = round(count / SPOKEN_WORDS_PER_SECOND)
        return CheckResult(
            flags=[
                f"script overruns its length: {count} spoken words is about "
                f"{over} seconds, against a {seconds}-second budget of ~{budget} words"
            ],
            distance=count - budget,
        )
    return CheckResult()

# The account is faceless (04-content/content-engine.md): animated on-screen
# text over stock B-roll, assembled in CapCut. Nothing told the Scriptwriter
# that, so it wrote shots like "direct eye contact to camera" — direction that
# cannot be filmed for this account.
PRODUCTION_RULE = (
    "PRODUCTION FORMAT. The account is faceless: animated on-screen text over "
    "stock B-roll, assembled in CapCut. There is no presenter and no camera. "
    "Never write a shot of a person speaking, eye contact with the lens, or any "
    "direction that needs someone on screen. Spoken lines are voiceover only, "
    "and every B-roll suggestion must be something findable as stock footage."
)

# The two tracks carry different CTA rules (04-content/content-engine.md,
# 02-audience/icp-*.md). Track A monetises now; Track B is paid-GATED — a paid
# ask there reaches someone in a vulnerable moment, which the brand ethics rule
# out. The directive may name a track; the default is B because it fails safe:
# a Track A post given B's rule only loses a sales CTA, while a Track B post
# given A's breaks an ethics line.
DEFAULT_TRACK = "B"

TRACK_RULE = (
    "TRACK. The directive may name one, written as `Track: A` or `Track: B`. "
    f"If it does not, assume Track {DEFAULT_TRACK}.\n"
    "Track A (the Rebuilder — solopreneurs and career changers between "
    "chapters): a paid call to action is allowed.\n"
    "Track B (the Hallway Walker — life upended after an awakening, a loss, or "
    "a slow unraveling): NO paid call to action, no product, no price, no "
    "booking. The only doors are the Hallway essay and the email list, reached "
    "through the link in bio. The job of the piece is recognition, not "
    "conversion. If you are unsure which track a topic belongs to, treat it as "
    "Track B."
)


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
                "reframe that shifts it, and the single next step the piece will "
                "leave them with — one idea, one foot, not a numbered system.\n\n"
                f"{FORMAT_RULE}\n"
                "Open the outline by stating the platform and length you are "
                "working to, then size every section to fit that length. Do not "
                "choose a platform of your own.\n\n"
                f"{PRODUCTION_RULE}\n\n"
                f"{TRACK_RULE}\n"
                "State the track you are working to alongside the platform, and "
                "plan the closing call to action to match it."
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
                "3. Practical anchor — one next step the reader can actually take. "
                "One idea, one foot: not a numbered system, not a framework.\n"
                "4. Close — recognition, then the call to action for the track in "
                "force. No pep talk and no inspirational sign-off; the job is to "
                "show what is there, not to rally anyone.\n"
                "5. Production notes — on-screen text and b-roll per section.\n"
                "6. Caption — post copy plus relevant hashtags.\n"
                "7. Two alternate hooks to A/B test.\n"
                "Write spoken lines the way they will be said out loud.\n\n"
                f"{FORMAT_RULE}\n"
                "LENGTH IS A HARD CONSTRAINT, not a suggestion. Delivery is "
                f"unhurried — about {SPOKEN_WORDS_PER_SECOND} spoken words per "
                "second — so a 90-second video is roughly 180 spoken words in "
                "total, across hook, body, steps and close combined. Work out "
                "the budget for the length in force, count the spoken words you "
                "have written, and cut until you are inside it. A script that "
                "covers every section but overruns the length is a failed "
                "script: cut the number of steps or the depth of the reframe "
                "before you exceed it. An overrunning draft is handed back "
                "to you to write again, so write to the budget the first "
                "time.\n"
                "On-screen text, production notes, the caption and the hashtags "
                "are read, not spoken, and do not count toward the budget.\n"
                f"Put every spoken line on its own line beginning with "
                f"`{VO_PREFIX}` — nothing else on that line, and nothing spoken "
                "anywhere else. On-screen text, production notes and the caption "
                f"are never marked `{VO_PREFIX}`. The app counts those lines to "
                "check the budget, so a script that overruns is flagged whatever "
                "count you claim.\n"
                "State the spoken word count and the length you wrote to at the "
                "top of the package.\n\n"
                f"{PRODUCTION_RULE}\n\n"
                f"{TRACK_RULE}"
            ),
            agent=Agent(
                role="Scriptwriter",
                goal=(
                    "Produce a ready-to-film, brand-aligned short-form script package: "
                    "hook, body, one practical next step, close, production notes, "
                    "caption with hashtags, and alternate hooks to test."
                ),
                backstory=(
                    "A short-form specialist who has studied what makes the first three "
                    "seconds work, writing in the byoungimprovements voice. Writes for one "
                    "person watching alone, never for an audience."
                ),
                artifact_type="script",
                output_check=check_script_length,
                revise_once=True,
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
