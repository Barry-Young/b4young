"""The observed voice: samples of real writing, injected alongside the rules.

The Constitution describes the voice and produced work that read as an
impression of it. These tests pin the thing that fixes that — that the author's
own sentences, and the corrections they made to generated lines, reach the
agent's system prompt.
"""

from __future__ import annotations

import pytest

from app.constitution import BrandConstitution
from app.voice import VoiceSamples


def test_the_shipped_samples_carry_the_corrections_barry_made():
    v = VoiceSamples.load()
    assert v.version.startswith("2.")

    rewrites = {r["generated"]: r["barry"] for r in v.rewrites}
    chopped = "It's not a breakdown. It's not a breakthrough either — not yet."
    assert rewrites[chopped] == "It's not a breakdown and it's not a breakthrough."

    # The two rules the rewrites earned.
    rules = " ".join(o["rule"] for o in v.observations).lower()
    assert "staccato" in rules and "punctuation, not the register" in rules
    assert "must name its place" in rules


def test_the_spoken_answers_ship_verbatim():
    """Speech is the rawest sample there is; a tidied transcript is not evidence."""
    spoken = {a["question"]: a["text"] for a in VoiceSamples.load().spoken}
    assert len(spoken) == 5

    job_site = next(t for q, t in spoken.items() if "job site" in q)
    # The regional double negative and the repeated admission both survive.
    assert "I can't hardly find the words" in job_site
    assert job_site.count("words") >= 3, "not having words for it is the point"
    assert "Uh," in job_site, "filler is kept in the file, not tidied away"

    irritated = next(t for q, t in spoken.items() if "grateful" in q)
    assert irritated.endswith("Let's see you be grateful.")


def test_the_rules_the_spoken_answers_earned():
    rules = " ".join(o["rule"] for o in VoiceSamples.load().observations).lower()
    assert "do not write him articulate" in rules
    assert "losing my mind" in rules, "his own words for the fear are allowed"
    assert "beautiful" in rules, "his word for the far side"
    assert "throws the question back" in rules, "the irritated register"


def test_the_forecasting_question_is_recorded_as_resolved_and_wrong():
    """The inference was wrong in the direction that would have chilled the voice.

    Keeping the correction in the file is what stops it being re-derived from
    the same deleted phrase later.
    """
    import yaml

    from app.voice import DEFAULT_PATH

    raw = yaml.safe_load(DEFAULT_PATH.read_text(encoding="utf-8"))
    resolved = raw["resolved_questions"]
    assert any("beautiful" in entry["answer"] for entry in resolved)

    # And it is not in the prompt, either as a question or as a correction.
    prompt = VoiceSamples.load().prompt_section()
    for entry in resolved:
        assert entry["resolved_by"] not in prompt


def test_every_shipped_rule_cites_its_evidence():
    # A rule no sample supports is an opinion, and this file is for evidence.
    for observation in VoiceSamples.load().observations:
        assert observation.get("evidence", "").strip(), observation.get("rule")


def test_open_questions_are_recorded_but_never_injected():
    """An inference drawn from one deleted phrase must not steer the model."""
    import yaml

    from app.voice import DEFAULT_PATH

    raw = yaml.safe_load(DEFAULT_PATH.read_text(encoding="utf-8"))
    questions = raw["open_questions"]
    assert questions, "the unconfirmed reads are kept in the file"

    prompt = VoiceSamples.load().prompt_section()
    for entry in questions:
        assert entry["question"].split(".")[0] not in prompt
        assert entry["status"] not in prompt
    assert "unconfirmed" not in prompt


def test_samples_reach_the_system_prompt_and_outrank_the_description():
    prompt = BrandConstitution.load().system_prompt("Scriptwriter", "Write a reel", "")

    # A sample, a correction pair, and the instruction on which wins.
    assert "That's the hallway. I've stood in it." in prompt
    assert "It's not a breakdown and it's not a breakthrough." in prompt
    assert "But wherever you're going is beautiful." in prompt
    assert "follow the sample" in prompt.lower()
    assert "not the filler" in prompt, "transcripts must not be copied wholesale"

    # The described voice is still there — samples add to it, they don't replace it.
    assert "clarifies, doesn't motivate" in prompt.lower()


def test_a_constitution_built_without_samples_is_unchanged():
    # Tests and callers that construct one directly must not pick up the
    # shipped samples by accident.
    prompt = BrandConstitution({"version": "9.9.9"}).system_prompt("Role", "Goal", "")
    assert "HOW THIS BRAND ACTUALLY WRITES" not in prompt
    assert prompt.endswith("(Brand Constitution v9.9.9)")


def test_missing_or_empty_samples_degrade_to_nothing(tmp_path):
    assert VoiceSamples.load(tmp_path / "absent.yaml").prompt_section() == ""

    empty = tmp_path / "empty.yaml"
    empty.write_text("version: '1.0.0'\n", encoding="utf-8")
    assert VoiceSamples.load(empty).prompt_section() == ""


@pytest.mark.parametrize(
    "data",
    [
        {"samples": [{"shows": "no text at all"}]},
        {"rewrites": [{"generated": "only one side"}]},
        {"observations": [{"evidence": "no rule"}]},
    ],
)
def test_incomplete_entries_are_skipped_rather_than_rendered_half(data):
    # Hand-edited YAML should never put a dangling label into a system prompt.
    section = VoiceSamples({"version": "1.0.0", **data}).prompt_section()
    assert "None" not in section
    assert 'written: ""' not in section
