"""The Brand Constitution is what makes output sound like the brand.

These tests pin the parts every agent depends on: that the shipped constitution
carries the validated voice, and that voice, audience, principles, preferred and
banned terms, and guardrails all reach the agent's system prompt.
"""

from __future__ import annotations

from app.constitution import BrandConstitution


def test_shipped_constitution_matches_the_source_document():
    """The YAML mirrors Barry's own `01-identity/brand-constitution.md`.

    v1.1 was written from an approved sample rather than that document and
    inverted the defining rule — it told agents to motivate. These assertions
    pin the parts that drifted.
    """
    c = BrandConstitution.load()
    assert c.version.startswith("2.")

    tone = c.voice["tone"].lower()
    assert "clarifies, doesn't motivate" in tone
    assert "never a guru" in tone

    principles = " ".join(c.principles).lower()
    assert "staccato" in principles, "the signature register"
    assert "concrete over cosmic" in principles
    assert "first person" in principles, "lived experience is the credential"
    assert "one idea, one foot" in principles

    guardrails = " ".join(c.guardrails).lower()
    assert "i promise to help you see what's actually there" in guardrails, "canon"
    assert "clarify, do not motivate" in guardrails
    assert "not a counselor, therapist" in guardrails


def test_the_three_banned_categories_are_all_covered():
    # cosmic (rule 2), clinical (rule 5, a legal line), hype (rule 6).
    banned = {t.lower() for t in BrandConstitution.load().banned_terms}
    assert {"vibrations", "frequencies"} <= banned, "cosmic"
    assert {"trauma", "anxiety", "healing", "diagnos"} <= banned, "clinical"
    assert {"crush it", "hustle harder"} <= banned, "hype"


def test_clinical_stems_catch_the_forms_that_actually_get_written():
    # The list held only plurals, so "a symptom" and "it triggered" walked past.
    c = BrandConstitution.load()
    assert c.check_output("That is a symptom of something.")
    assert c.check_output("It triggered me.")


def test_the_clinical_ban_is_on_diagnosing_a_person_not_on_the_word():
    """Barry's own essay uses "diagnosed" of a house. The ban is on the act.

    The source document marks the clinical terms a legal line — the brand must
    not diagnose a reader. Banning the letters also banned one of his own best
    sentences.
    """
    c = BrandConstitution.load()

    # His sentence, from the-hallway.md, passes.
    assert c.check_output(
        "The man who walked with customers through their houses and diagnosed "
        "them is not that far from the man who sits with people doing their "
        "own diagnosing."
    ) == []

    # Clinical use, including the denial an agent keeps reaching for, does not.
    assert c.check_output("It's not a diagnosis.") == ["banned term used: 'diagnos'"]
    assert c.check_output("You should get a diagnosis.") == ["banned term used: 'diagnos'"]

    # The narrowing is per sentence, so one clean use does not excuse a dirty one.
    both = c.check_output(
        "He diagnosed their houses for years. Now he can diagnose your condition."
    )
    assert both == ["banned term used: 'diagnos'"]


def test_agents_are_told_not_to_name_a_banned_term_in_order_to_deny_it():
    # Two live runs produced "It's not a diagnosis" — sensible writing that
    # still puts the word in front of the reader, and still trips the check.
    prompt = BrandConstitution.load().system_prompt("Strategist", "Plan", "")
    assert "in order to deny it" in prompt
    assert "clinical sense only" in prompt


def test_the_trade_vocabulary_is_preferred():
    preferred = {t.lower() for t in BrandConstitution.load().preferred_terms}
    assert {"footing", "blueprint", "load-bearing"} <= preferred
    # Corporate filler from v1.1 that is not in the source document.
    assert "growth mindset" not in preferred
    assert "strategic agility" not in preferred


def test_system_prompt_includes_every_policy_section():
    c = BrandConstitution(
        {
            "version": "9.9.9",
            "voice": {"tone": "Grounded and honest.", "audience": "People rebuilding."},
            "principles": ["Name the hard part first."],
            "preferred_terms": ["steady ground"],
            "banned_terms": ["crush it"],
            "guardrails": ["Do not promise fast results."],
        }
    )

    prompt = c.system_prompt("Scriptwriter", "Write a reel", "Short-form specialist")

    assert "Scriptwriter" in prompt
    assert "Write a reel" in prompt
    assert "Short-form specialist" in prompt
    assert "Grounded and honest." in prompt
    assert "People rebuilding." in prompt
    assert "Name the hard part first." in prompt
    assert "steady ground" in prompt
    assert "crush it" in prompt
    assert "Do not promise fast results." in prompt
    assert "9.9.9" in prompt


def test_missing_sections_are_simply_omitted():
    prompt = BrandConstitution({}).system_prompt("Role", "Goal", "")
    assert "Role" in prompt and "Goal" in prompt
    assert "Principle:" not in prompt
    assert "Audience:" not in prompt


def test_banned_terms_are_flagged_case_insensitively():
    c = BrandConstitution({"banned_terms": ["Crush It"]})
    assert c.check_output("Time to crush it today") == ["banned term used: 'Crush It'"]
    assert c.check_output("Time to build steadily") == []
