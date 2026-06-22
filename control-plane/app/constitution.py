"""Brand Constitution loader and enforcement.

Loads brand_constitution.yaml and turns it into (a) a system prompt injected
into every agent run, and (b) a lightweight output check that flags banned
terms. This is the programmatic governance described in
docs/05-governance-security.md (5.1).
"""

from __future__ import annotations

from pathlib import Path

import yaml

DEFAULT_PATH = Path(__file__).resolve().parent.parent / "brand_constitution.yaml"


class BrandConstitution:
    def __init__(self, data: dict) -> None:
        self.version: str = data.get("version", "0.0.0")
        self.voice: dict = data.get("voice", {})
        self.preferred_terms: list[str] = data.get("preferred_terms", [])
        self.banned_terms: list[str] = data.get("banned_terms", [])
        self.guardrails: list[str] = data.get("guardrails", [])

    @classmethod
    def load(cls, path: Path = DEFAULT_PATH) -> "BrandConstitution":
        if not path.exists():
            return cls({})
        with path.open("r", encoding="utf-8") as fh:
            return cls(yaml.safe_load(fh) or {})

    def system_prompt(self, role: str, goal: str, backstory: str) -> str:
        parts = [
            f"You are acting as: {role}.",
            f"Your goal: {goal}.",
        ]
        if backstory:
            parts.append(f"Backstory: {backstory}")
        if self.voice.get("tone"):
            parts.append(f"Brand voice/tone: {self.voice['tone']}")
        if self.preferred_terms:
            parts.append("Preferred terms: " + ", ".join(self.preferred_terms))
        if self.banned_terms:
            parts.append("Never use these banned terms: " + ", ".join(self.banned_terms))
        for guard in self.guardrails:
            parts.append(f"Constraint: {guard}")
        parts.append(f"(Brand Constitution v{self.version})")
        return "\n".join(parts)

    def check_output(self, text: str) -> list[str]:
        """Return a list of governance flags for an output (empty == clean)."""
        lowered = text.lower()
        return [f"banned term used: '{term}'" for term in self.banned_terms if term.lower() in lowered]
