"""LLM provider abstraction.

The Control Plane is model-agnostic (docs/04-technology-stack.md, 4.2.3): agents
are configured with a provider/model name and the runtime resolves the matching
provider via `get_provider`.

- `StubProvider` is deterministic and dependency-free, so the system runs with
  no external services or API keys.
- `AnthropicProvider` calls the real Claude API, with the key pulled from the
  vault (`ANTHROPIC`). If a Claude model is requested but no key is set, we fall
  back to the stub so the system still runs and is observable.

Agents default to the `auto` model, which follows the vault: real Claude output
once an `ANTHROPIC` key is present, the stub before that. Adding the key on the
dashboard is therefore enough to switch a crew from placeholder text to real
drafts — no restart, no env var. Pin a specific model with `BYI_AGENT_MODEL`
(e.g. `claude-sonnet-4-6`, or `stub` to stay offline regardless of the vault).
"""

from __future__ import annotations

import os
from typing import Protocol, runtime_checkable

from .vault import Vault

# Sentinel model meaning "real Claude if the vault has a key, stub otherwise".
AUTO_MODEL = "auto"
# Model crews/agents use unless a blueprint overrides it.
DEFAULT_AGENT_MODEL = os.getenv("BYI_AGENT_MODEL", AUTO_MODEL)
# Concrete Claude model used when a bare "claude"/"anthropic"/"auto" alias is requested.
DEFAULT_ANTHROPIC_MODEL = "claude-sonnet-4-6"
ANTHROPIC_KEY_NAME = "ANTHROPIC"
# Output ceiling per agent turn. A full short-form script package (script,
# on-screen text, b-roll notes, caption, hashtags, alternate hooks) does not fit
# in a small budget — an undersized ceiling truncates the deliverable mid-draft.
DEFAULT_MAX_TOKENS = 4096

# Aliases that mean "use the default Claude model" rather than naming one.
_CLAUDE_ALIASES = ("claude", "anthropic")


class ProviderError(RuntimeError):
    """A provider call failed, with a message safe to show a human.

    Wraps SDK-specific exceptions so callers (and the dashboard) get "the key was
    rejected" rather than a stack trace.
    """


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

    def __init__(self, model: str, api_key: str, *, max_tokens: int = DEFAULT_MAX_TOKENS) -> None:
        self.name = model
        self.model = model
        self._api_key = api_key
        self._max_tokens = max_tokens

    def generate(self, prompt: str, *, system: str | None = None) -> str:
        try:
            import anthropic
        except ImportError as exc:  # pragma: no cover - depends on install state
            raise ProviderError(
                "the 'anthropic' package is not installed; run `pip install -r requirements.txt`"
            ) from exc

        client = anthropic.Anthropic(api_key=self._api_key)
        try:
            message = client.messages.create(
                model=self.model,
                max_tokens=self._max_tokens,
                system=system or "",
                messages=[{"role": "user", "content": prompt}],
            )
        except anthropic.AuthenticationError as exc:
            raise ProviderError(
                f"Anthropic rejected the API key. Replace the {ANTHROPIC_KEY_NAME} key in the vault."
            ) from exc
        except anthropic.RateLimitError as exc:
            raise ProviderError("Anthropic rate limit reached — wait a moment and run again.") from exc
        except anthropic.APIStatusError as exc:
            raise ProviderError(f"Anthropic API error ({exc.status_code}): {exc.message}") from exc
        except anthropic.APIConnectionError as exc:
            raise ProviderError(f"Could not reach the Anthropic API: {exc}") from exc

        if message.stop_reason == "refusal":
            raise ProviderError("Anthropic declined this request for safety reasons.")

        return "".join(block.text for block in message.content if block.type == "text")


def wants_real_model(model: str) -> bool:
    """True when this model asks for real generation (rather than the stub)."""
    name = (model or "").strip().lower()
    return name == AUTO_MODEL or name in _CLAUDE_ALIASES or name.startswith("claude")


def real_generation_available(vault: Vault) -> bool:
    """True when a key is present, i.e. `auto` agents will produce real output."""
    return bool(vault.get_secret(ANTHROPIC_KEY_NAME))


def get_provider(model: str, vault: Vault) -> LLMProvider:
    """Resolve a provider by model/name.

    `auto` (the default) and Claude models resolve to AnthropicProvider when an
    `ANTHROPIC` key is in the vault; otherwise (and for any unknown model) we
    fall back to the stub so a run still completes and is observable rather than
    failing opaquely. `stub` always stays offline.
    """
    name = (model or "").strip().lower()
    if wants_real_model(name):
        api_key = vault.get_secret(ANTHROPIC_KEY_NAME)
        if api_key:
            named = name not in _CLAUDE_ALIASES and name != AUTO_MODEL
            return AnthropicProvider(model if named else DEFAULT_ANTHROPIC_MODEL, api_key)
    return StubProvider()
