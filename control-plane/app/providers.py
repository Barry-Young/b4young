"""LLM provider abstraction.

The Control Plane is model-agnostic (docs/04-technology-stack.md, 4.2.3): agents
are configured with a provider/model name and the runtime resolves the matching
provider via `get_provider`.

- `StubProvider` is deterministic and dependency-free — the default, so the
  system runs with no external services or API keys.
- `AnthropicProvider` calls the real Claude API, with the key pulled from the
  vault (`ANTHROPIC`). If a Claude model is requested but no key is set, we fall
  back to the stub so the system still runs and is observable.

Set `BYI_AGENT_MODEL` (e.g. `claude-sonnet-4-6`) to make crews use a real model
by default, and provide the key via `BYI_KEY_ANTHROPIC`.
"""

from __future__ import annotations

import os
from typing import Protocol, runtime_checkable

from .vault import Vault

# Model crews/agents use unless a blueprint overrides it. Defaults to the stub.
DEFAULT_AGENT_MODEL = os.getenv("BYI_AGENT_MODEL", "stub")
# Concrete Claude model used when a bare "claude"/"anthropic" alias is requested.
DEFAULT_ANTHROPIC_MODEL = "claude-sonnet-4-6"
ANTHROPIC_KEY_NAME = "ANTHROPIC"


@runtime_checkable
class LLMProvider(Protocol):
    name: str
    is_stub: bool

    def generate(self, prompt: str, *, system: str | None = None) -> str: ...


class StubProvider:
    """Deterministic, dependency-free provider used for hello-world runs."""

    name = "stub"
    is_stub = True

    def generate(self, prompt: str, *, system: str | None = None) -> str:
        lines = ["[stub agent response]"]
        if system:
            first = system.strip().splitlines()[0] if system.strip() else ""
            if first:
                lines.append(f"operating under: {first}")
        lines.append(f"received task: {prompt.strip() or '(no input)'}")
        lines.append("status: hello world — the Control Plane successfully ran this agent.")
        return "\n".join(lines)


class AnthropicProvider:
    """Calls the Claude API. The `anthropic` SDK is imported lazily so the
    package is only required when a real model is actually used."""

    is_stub = False

    def __init__(self, model: str, api_key: str, *, max_tokens: int = 1024) -> None:
        self.name = model
        self.model = model
        self._api_key = api_key
        self._max_tokens = max_tokens

    def generate(self, prompt: str, *, system: str | None = None) -> str:
        import anthropic

        client = anthropic.Anthropic(api_key=self._api_key)
        message = client.messages.create(
            model=self.model,
            max_tokens=self._max_tokens,
            system=system or "",
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(block.text for block in message.content if block.type == "text")


def get_provider(model: str, vault: Vault) -> LLMProvider:
    """Resolve a provider by model/name.

    Claude models resolve to AnthropicProvider when an `ANTHROPIC` key is in the
    vault; otherwise (and for any unknown model) we fall back to the stub so a
    run still completes and is observable rather than failing opaquely.
    """
    name = (model or "").lower()
    if name in ("claude", "anthropic") or name.startswith("claude"):
        api_key = vault.get_secret(ANTHROPIC_KEY_NAME)
        if api_key:
            api_model = DEFAULT_ANTHROPIC_MODEL if name in ("claude", "anthropic") else model
            return AnthropicProvider(api_model, api_key)
    return StubProvider()
