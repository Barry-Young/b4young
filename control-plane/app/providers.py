"""LLM provider abstraction.

The Control Plane is model-agnostic (docs/04-technology-stack.md, 4.2.3): agents
are configured with a provider/model name and the runtime resolves the matching
provider. The MVP ships a deterministic StubProvider so the system runs with no
external dependencies; a real provider (e.g. Anthropic) can be added by
implementing `generate` and registering it in `get_provider`.
"""

from __future__ import annotations

from typing import Protocol

from .vault import Vault


class LLMProvider(Protocol):
    name: str

    def generate(self, prompt: str, *, system: str | None = None) -> str: ...


class StubProvider:
    """Deterministic, dependency-free provider used for hello-world runs."""

    name = "stub"

    def generate(self, prompt: str, *, system: str | None = None) -> str:
        lines = ["[stub agent response]"]
        if system:
            first = system.strip().splitlines()[0] if system.strip() else ""
            if first:
                lines.append(f"operating under: {first}")
        lines.append(f"received task: {prompt.strip() or '(no input)'}")
        lines.append("status: hello world — the Control Plane successfully ran this agent.")
        return "\n".join(lines)


def get_provider(model: str, vault: Vault) -> LLMProvider:
    """Resolve a provider by model/name.

    Unknown models fall back to the stub so a misconfigured blueprint still runs
    and is observable, rather than failing opaquely. Wire real providers here,
    pulling credentials from the vault (e.g. vault.get_secret("ANTHROPIC")).
    """

    return StubProvider()
