"""Tests for provider resolution and the model-backed evaluation judge.

These never call the real Anthropic API: resolution is checked structurally, and
the LLM judge path uses a fake provider.
"""

from __future__ import annotations

from app.constitution import BrandConstitution
from app.evaluation import judge
from app.models import CrewName, EvalCase
from app.providers import AnthropicProvider, StubProvider, get_provider
from app.vault import Vault


def test_stub_is_default():
    p = get_provider("stub", Vault())
    assert isinstance(p, StubProvider)
    assert p.is_stub is True


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
    vault = Vault()
    vault.set_key("ANTHROPIC", "sk-test-123")
    p = get_provider("claude", vault)
    assert isinstance(p, AnthropicProvider)
    assert p.model == "claude-sonnet-4-6"


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
