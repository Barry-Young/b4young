"""Brand Constitution loader and enforcement.

Loads brand_constitution.yaml and turns it into (a) a system prompt injected
into every agent run, and (b) a lightweight output check that flags banned
terms. This is the programmatic governance described in
docs/05-governance-security.md (5.1).

The prompt also carries the observed voice (app/voice.py) — samples of the
brand's actual writing. The Constitution says what the voice is; the samples
show it. Both are needed: agents given only the description produced work that
read as an impression of the voice rather than the voice.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from .voice import VoiceSamples

DEFAULT_PATH = Path(__file__).resolve().parent.parent / "brand_constitution.yaml"

# Flags are raised per sentence, so a term's context is the sentence holding it.
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")


class BannedTerm:
    """A banned term, optionally narrowed to the sense that is actually banned.

    The clinical terms exist to stop the brand diagnosing a reader — a legal
    line, not a style choice. That is a ban on an act, not on letters: Barry's
    own essay uses "diagnosed" of a house he was surveying. An entry may carry
    `unless`, a pattern that passes the use when it appears in the same
    sentence. Heuristic by nature, and the flag is advisory — it never blocks.
    """

    def __init__(self, spec: object) -> None:
        if isinstance(spec, dict):
            self.term = str(spec.get("term", "")).strip()
            unless = str(spec.get("unless", "")).strip()
            self.unless = re.compile(unless, re.IGNORECASE) if unless else None
            self.note = str(spec.get("note", "")).strip()
        else:
            self.term = str(spec).strip()
            self.unless = None
            self.note = ""

    def offending_sentences(self, text: str) -> list[str]:
        needle = self.term.lower()
        if not needle:
            return []
        hits = [s for s in _SENTENCE_SPLIT.split(text) if needle in s.lower()]
        if self.unless is not None:
            hits = [s for s in hits if not self.unless.search(s)]
        return hits


class BrandConstitution:
    def __init__(self, data: dict, voice_samples: VoiceSamples | None = None) -> None:
        self.version: str = data.get("version", "0.0.0")
        self.voice: dict = data.get("voice", {})
        self.principles: list[str] = data.get("principles", [])
        self.preferred_terms: list[str] = data.get("preferred_terms", [])
        self._banned = [BannedTerm(spec) for spec in data.get("banned_terms", []) or []]
        # The plain strings, for display and for the prompt.
        self.banned_terms: list[str] = [b.term for b in self._banned if b.term]
        self.guardrails: list[str] = data.get("guardrails", [])
        # Injected rather than loaded here, so a constitution built in a test
        # carries no samples unless the test asks for them.
        self.voice_samples = voice_samples or VoiceSamples({})

    @classmethod
    def load(
        cls, path: Path = DEFAULT_PATH, voice_path: Path | None = None
    ) -> "BrandConstitution":
        samples = VoiceSamples.load(voice_path) if voice_path else VoiceSamples.load()
        if not path.exists():
            return cls({}, samples)
        with path.open("r", encoding="utf-8") as fh:
            return cls(yaml.safe_load(fh) or {}, samples)

    def system_prompt(self, role: str, goal: str, backstory: str) -> str:
        parts = [
            f"You are acting as: {role}.",
            f"Your goal: {goal}.",
        ]
        if backstory:
            parts.append(f"Backstory: {backstory}")
        if self.voice.get("tone"):
            parts.append(f"Brand voice/tone: {self.voice['tone']}")
        if self.voice.get("audience"):
            parts.append(f"Audience: {self.voice['audience']}")
        for principle in self.principles:
            parts.append(f"Principle: {principle}")
        if self.preferred_terms:
            parts.append("Preferred terms: " + ", ".join(self.preferred_terms))
        if self.banned_terms:
            parts.append("Never use these banned terms: " + ", ".join(self.banned_terms))
            # Observed twice in live runs: an agent reaches for a banned term in
            # order to rule it out, which still puts the word in front of the
            # reader and still trips the check.
            parts.append(
                "Do not reach for a banned term in order to deny it — writing "
                "\"it's not a diagnosis\" still puts the word in the reader's "
                "head. Say what a thing is, not what it isn't."
            )
            for banned in self._banned:
                if banned.unless is not None:
                    parts.append(
                        f"On '{banned.term}': banned in the clinical sense only — "
                        "applied to a person. The trade sense, diagnosing a house "
                        "or a room, is the brand's own and is allowed."
                    )
        for guard in self.guardrails:
            parts.append(f"Constraint: {guard}")
        parts.append(f"(Brand Constitution v{self.version})")
        # Last, and closest to the task: examples steer hardest when they sit
        # next to the work rather than behind a wall of policy.
        section = self.voice_samples.prompt_section()
        if section:
            parts.append("")
            parts.append(section)
        return "\n".join(parts)

    def check_output(self, text: str) -> list[str]:
        """Return a list of governance flags for an output (empty == clean)."""
        return [
            f"banned term used: '{banned.term}'"
            for banned in self._banned
            if banned.offending_sentences(text)
        ]
