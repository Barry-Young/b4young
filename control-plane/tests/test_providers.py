"""Tests for provider resolution and the model-backed evaluation judge.

These never call the real Anthropic API: resolution is checked structurally, and
the LLM judge path uses a fake provider.
"""

from __future__ import annotations

import sys
import types

import pytest

from app.constitution import BrandConstitution
from app.crews.base import Agent
from app.evaluation import judge
from app.models import CrewName, EvalCase
from app.providers import (
    AUTO_MODEL,
    DEFAULT_MAX_TOKENS,
    AnthropicProvider,
    ProviderError,
    StubProvider,
    get_provider,
    real_generation_available,
    wants_real_model,
)
from app.vault import Vault


def _vault_with_key() -> Vault:
    vault = Vault()
    vault.set_key("ANTHROPIC", "sk-test-123")
    return vault


def test_stub_is_default():
    p = get_provider("stub", Vault())
    assert isinstance(p, StubProvider)
    assert p.is_stub is True


def test_stub_stays_offline_even_with_a_key():
    # An explicit `stub` model is an opt-out; the vault must not override it.
    assert isinstance(get_provider("stub", _vault_with_key()), StubProvider)


def test_claude_without_key_falls_back_to_stub():
    p = get_provider("claude-sonnet-4-6", Vault())  # no key set
    assert isinstance(p, StubProvider)


def test_claude_with_key_resolves_to_anthropic():
    vault = Vault()
    vault.set_key("ANTHROPIC", "sk-test-123")
    p = get_provider("claude-sonnet-4-6", vault)
    assert isinstance(p, AnthropicProvider)
    assert p.is_stub is False
    assert p.model == "claude-sonnet-4-6"


def test_bare_alias_uses_default_model():
    p = get_provider("claude", _vault_with_key())
    assert isinstance(p, AnthropicProvider)
    assert p.model == "claude-sonnet-4-6"


# --------------------------------------------------------------------------- #
# `auto`: adding a key is enough to switch crews to real output
# --------------------------------------------------------------------------- #
def test_auto_falls_back_to_stub_without_a_key():
    assert isinstance(get_provider(AUTO_MODEL, Vault()), StubProvider)


def test_auto_resolves_to_anthropic_once_a_key_is_added():
    vault = Vault()
    assert isinstance(get_provider(AUTO_MODEL, vault), StubProvider)

    # Same vault, key added at runtime — no restart, no env var.
    vault.set_key("ANTHROPIC", "sk-test-123")
    p = get_provider(AUTO_MODEL, vault)
    assert isinstance(p, AnthropicProvider)
    assert p.model == "claude-sonnet-4-6"


def test_agents_default_to_auto_so_the_vault_decides():
    agent = Agent(role="r", goal="g", backstory="b", artifact_type="script")
    assert agent.model == AUTO_MODEL


def test_real_generation_available_tracks_the_key():
    vault = Vault()
    assert real_generation_available(vault) is False
    vault.set_key("ANTHROPIC", "sk-test-123")
    assert real_generation_available(vault) is True


@pytest.mark.parametrize(
    ("model", "expected"),
    [
        ("auto", True),
        ("claude", True),
        ("anthropic", True),
        ("  Claude-Sonnet-4-6 ", True),
        ("stub", False),
        ("", False),
    ],
)
def test_wants_real_model(model, expected):
    assert wants_real_model(model) is expected


def test_max_tokens_leaves_room_for_a_full_script_package():
    # A hook + body + steps + close + production notes + caption + alt hooks
    # does not fit in a small budget; guard against a silent regression.
    assert DEFAULT_MAX_TOKENS >= 4096
    assert AnthropicProvider("claude-sonnet-4-6", "sk-test")._max_tokens == DEFAULT_MAX_TOKENS


# --------------------------------------------------------------------------- #
# SDK failures become plain-English ProviderErrors
# --------------------------------------------------------------------------- #
def _install_fake_sdk(monkeypatch, *, response=None, raise_error_named=None):
    """Install a minimal fake `anthropic` module so no network call is made.

    `raise_error_named` names an exception class on the fake module, so the
    raised error is the same class the provider's except chain catches.
    """

    class _APIError(Exception):
        pass

    class _Messages:
        def create(self, **kwargs):
            if raise_error_named is not None:
                raise getattr(module, raise_error_named)("boom")
            return response

    class _Anthropic:
        def __init__(self, api_key=None):
            self.messages = _Messages()

    module = types.ModuleType("anthropic")
    module.Anthropic = _Anthropic
    module.APIStatusError = type("APIStatusError", (_APIError,), {})
    module.AuthenticationError = type("AuthenticationError", (module.APIStatusError,), {})
    module.RateLimitError = type("RateLimitError", (module.APIStatusError,), {})
    module.APIConnectionError = type("APIConnectionError", (_APIError,), {})
    monkeypatch.setitem(sys.modules, "anthropic", module)
    return module


class _Block:
    def __init__(self, type_: str, text: str = "") -> None:
        self.type = type_
        self.text = text


class _Message:
    def __init__(self, content, stop_reason="end_turn") -> None:
        self.content = content
        self.stop_reason = stop_reason


def test_generate_returns_joined_text(monkeypatch):
    _install_fake_sdk(monkeypatch, response=_Message([_Block("text", "Hook."), _Block("text", " CTA.")]))
    out = AnthropicProvider("claude-sonnet-4-6", "sk-test").generate("topic", system="rules")
    assert out == "Hook. CTA."


def test_bad_key_becomes_an_actionable_message(monkeypatch):
    _install_fake_sdk(monkeypatch, raise_error_named="AuthenticationError")
    with pytest.raises(ProviderError, match="rejected the API key"):
        AnthropicProvider("claude-sonnet-4-6", "sk-bad").generate("topic")


def test_connection_failure_becomes_an_actionable_message(monkeypatch):
    _install_fake_sdk(monkeypatch, raise_error_named="APIConnectionError")
    with pytest.raises(ProviderError, match="Could not reach"):
        AnthropicProvider("claude-sonnet-4-6", "sk-test").generate("topic")


def test_rate_limit_becomes_an_actionable_message(monkeypatch):
    _install_fake_sdk(monkeypatch, raise_error_named="RateLimitError")
    with pytest.raises(ProviderError, match="rate limit"):
        AnthropicProvider("claude-sonnet-4-6", "sk-test").generate("topic")


def test_refusal_is_not_returned_as_output(monkeypatch):
    _install_fake_sdk(monkeypatch, response=_Message([], stop_reason="refusal"))
    with pytest.raises(ProviderError, match="declined"):
        AnthropicProvider("claude-sonnet-4-6", "sk-test").generate("topic")


class _FakeProvider:
    name = "fake"
    is_stub = False

    def __init__(self, reply: str) -> None:
        self._reply = reply

    def generate(self, prompt: str, *, system: str | None = None) -> str:
        return self._reply


def _case() -> EvalCase:
    return EvalCase(
        id="t1",
        name="t",
        crew=CrewName.MARKET_INTELLIGENCE,
        directive="d",
        expect_terms=["alpha"],
        forbid_terms=["game-changer"],
    )


def test_llm_judge_parses_score():
    result = judge("alpha is covered", _case(), BrandConstitution({}), _FakeProvider("0.9"))
    assert result.score == 0.9
    assert result.passed is True
    assert "llm:fake" in result.rationale


def test_llm_judge_penalizes_forbidden_terms():
    result = judge("alpha game-changer", _case(), BrandConstitution({}), _FakeProvider("1.0"))
    assert result.score == 0.5  # halved for the forbidden term
    assert result.passed is False


def test_heuristic_used_for_stub_provider():
    result = judge("alpha here", _case(), BrandConstitution({}), StubProvider())
    assert "heuristic" in result.rationale
    assert result.score == 1.0
