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

from pathlib import Path

import yaml

from .voice import VoiceSamples

DEFAULT_PATH = Path(__file__).resolve().parent.parent / "brand_constitution.yaml"


class BrandConstitution:
    def __init__(self, data: dict, voice_samples: VoiceSamples | None = None) -> None:
        self.version: str = data.get("version", "0.0.0")
        self.voice: dict = data.get("voice", {})
        self.principles: list[str] = data.get("principles", [])
        self.preferred_terms: list[str] = data.get("preferred_terms", [])
        self.banned_terms: list[str] = data.get("banned_terms", [])
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
        lowered = text.lower()
        return [f"banned term used: '{term}'" for term in self.banned_terms if term.lower() in lowered]
