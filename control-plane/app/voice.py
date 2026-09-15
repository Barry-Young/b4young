"""Observed voice: samples of the brand's actual writing, for the system prompt.

The Brand Constitution (app/constitution.py) *describes* the voice — tone,
principles, banned terms. A description produces a competent impression of a
voice, not the voice. This module loads voice_samples.yaml, which *demonstrates*
it: real sentences, and pairs showing a generated line beside the author's
rewrite of it.

Both go into every agent's system prompt. Where they appear to disagree, the
samples win — they are what the writing does, the Constitution is what it
says it does.
"""

from __future__ import annotations

from pathlib import Path

import yaml

DEFAULT_PATH = Path(__file__).resolve().parent.parent / "voice_samples.yaml"


class VoiceSamples:
    def __init__(self, data: dict) -> None:
        self.version: str = data.get("version", "0.0.0")
        self.samples: list[dict] = data.get("samples") or []
        self.rewrites: list[dict] = data.get("rewrites") or []
        self.observations: list[dict] = data.get("observations") or []
        # open_questions are deliberately not loaded into the prompt: they are
        # inferences no sample yet supports, kept in the file so they are not
        # lost, not so they steer the model.

    @classmethod
    def load(cls, path: Path = DEFAULT_PATH) -> "VoiceSamples":
        if not path.exists():
            return cls({})
        with path.open("r", encoding="utf-8") as fh:
            return cls(yaml.safe_load(fh) or {})

    def __bool__(self) -> bool:
        return bool(self.samples or self.rewrites or self.observations)

    def prompt_section(self) -> str:
        """The samples as prompt text, or empty when none are configured."""
        if not self:
            return ""

        parts = [
            "HOW THIS BRAND ACTUALLY WRITES. The voice rules above describe "
            "the voice; what follows demonstrates it, in the author's own "
            "sentences. Where a rule and a sample seem to disagree, follow "
            "the sample. Match the rhythm and the sentence shapes — do not "
            "reuse these lines verbatim unless the artifact calls for the "
            "canon.",
        ]

        for sample in self.samples:
            text = _clean(sample.get("text"))
            if not text:
                continue
            shows = _clean(sample.get("shows"))
            parts.append(f'Sample — {shows}\n  "{text}"' if shows else f'Sample:\n  "{text}"')

        for rewrite in self.rewrites:
            generated, author = _clean(rewrite.get("generated")), _clean(rewrite.get("barry"))
            if not (generated and author):
                continue
            lines = [
                "Correction — a line this system wrote, and the author's rewrite:",
                f'  written: "{generated}"',
                f'  author:  "{author}"',
            ]
            changed = _clean(rewrite.get("changed"))
            if changed:
                lines.append(f"  what changed: {changed}")
            parts.append("\n".join(lines))

        for observation in self.observations:
            rule = _clean(observation.get("rule"))
            if rule:
                parts.append(f"Observed rule: {rule}")

        parts.append(f"(Voice samples v{self.version})")
        return "\n".join(parts)


def _clean(value: object) -> str:
    """YAML folded scalars keep a trailing newline; prompts read better without."""
    return str(value).strip() if isinstance(value, str) else ""
