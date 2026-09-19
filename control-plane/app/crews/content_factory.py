"""The 'Content Factory' crew (docs/03-agent-crews.md, 3.2).

Executive Producer (orchestrator) coordinating Content Strategist, Scriptwriter,
Voice Artist, and Video Producer to turn a brief into a content package.

Human-in-the-Loop: the run pauses after the Scriptwriter's draft (a mid-pipeline
checkpoint) and again at the final content package — the two checkpoints called
for in Phase 3 of the roadmap (docs/06-roadmap.md, 6.3).
"""

from __future__ import annotations

import math
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

# The Scriptwriter cannot count its own output, and the misses run one way.
# Measured twice against the app's count: it reported 89 spoken words having
# written about 120, then reported 178 having written 220 — low by 35% and by
# 24%. Both times it aimed correctly at the number it was given; both times it
# was wrong about where it had landed. So neither telling it the real budget
# nor handing the draft back with the real count can work: it re-aims at the
# same number and misses the same way. Raising the target only raises the
# output (60s produced 176, 90s produced 220).
#
# It is therefore not asked to total anything. It is given two limits it can
# check by looking — discrete things it can see, rather than arithmetic over
# the whole script:
#
#   * a cap on the words in any one spoken line
#   * a cap on how many spoken lines exist, one per N seconds of runtime
#
# Together these come to about 1.6 words per second against the real budget of
# 2, and that headroom is what absorbs the overshoot. The app keeps counting
# honestly against the real budget, so if the bias moves, the flag says so.
MAX_WORDS_PER_VO_LINE = 13
SECONDS_PER_VO_LINE = 8


def max_vo_lines(seconds: int) -> int:
    """How many spoken lines a piece of this length gets. At least one."""
    return max(1, math.floor(seconds / SECONDS_PER_VO_LINE))

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
        spoken = _spoken_part(line)
        if spoken is None:
            continue
        words.extend(w for w in spoken.split() if _WORD_PATTERN.search(w))
    return words


def _spoken_part(line: str) -> str | None:
    """The words of a marked spoken line, or None if the line is not one."""
    stripped = line.strip().lstrip("*_- ").strip()
    if not stripped.upper().startswith(VO_PREFIX):
        return None
    return stripped[len(VO_PREFIX) :]


def _is_spoken_line(line: str) -> bool:
    return _spoken_part(line) is not None


def spoken_line_count(output: str) -> int:
    """How many marked spoken lines the script has."""
    return sum(1 for line in output.splitlines() if _is_spoken_line(line))


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
        lines = spoken_line_count(output)
        allowed = max_vo_lines(seconds)
        return CheckResult(
            flags=[
                f"script overruns its length: {count} spoken words is about "
                f"{over} seconds, against a {seconds}-second budget of ~{budget} "
                f"words — {lines} spoken lines, against a cap of {allowed}"
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
                f"Put every spoken line on its own line beginning with "
                f"`{VO_PREFIX}` — nothing else on that line, and nothing spoken "
                "anywhere else. On-screen text, production notes and the caption "
                f"are never marked `{VO_PREFIX}`.\n\n"
                "LENGTH IS A HARD CONSTRAINT, and it is measured rather than "
                "trusted: the app counts your spoken lines and flags a script "
                "that runs long.\n"
                "DO NOT TOTAL THE WORDS YOURSELF. That count has been checked "
                "against the app's every time, and it has been wrong every "
                "time, always low, by roughly a quarter — a script reporting "
                "178 spoken words had written 220. Aiming at a total you "
                "cannot measure is what has failed, twice, so do not do it.\n"
                "Work to these two limits instead. Both are things you can "
                "check by looking, one line at a time:\n"
                f"  1. No more than {MAX_WORDS_PER_VO_LINE} spoken words in any "
                f"single `{VO_PREFIX}` line. Count that line, on its own, and "
                "cut it if it runs over.\n"
                f"  2. One `{VO_PREFIX}` line for every "
                f"{SECONDS_PER_VO_LINE} seconds of runtime, rounded down — so "
                f"{max_vo_lines(90)} lines for a 90-second video, "
                f"{max_vo_lines(60)} for a 60-second one. Count the lines when "
                "you are done. If there are too many, cut whole lines: drop "
                "the weakest beat entirely rather than shortening every line "
                "into shorthand.\n"
                "Staying inside both limits is what meeting the length means. "
                "A script that covers every section but breaks them is a "
                "failed script, and is handed back to you to write again.\n"
                "On-screen text, production notes, the caption and the "
                "hashtags are read, not spoken, and are not subject to either "
                "limit.\n"
                f"State the length you wrote to and the number of `{VO_PREFIX}` "
                "lines at the top of the package. Do not state a word total.\n\n"
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
