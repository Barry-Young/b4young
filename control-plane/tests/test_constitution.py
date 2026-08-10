"""The Brand Constitution is what makes output sound like the brand.

These tests pin the parts every agent depends on: that the shipped constitution
carries the validated voice, and that voice, audience, principles, preferred and
banned terms, and guardrails all reach the agent's system prompt.
"""

from __future__ import annotations

from app.constitution import BrandConstitution


def test_shipped_constitution_carries_the_validated_voice():
    c = BrandConstitution.load()
    assert c.version.startswith("1.1")
    assert c.voice.get("tone")
    assert c.voice.get("audience")
    assert c.principles, "principles are what give the output its shape"
    # Guardrails that protect the audience, not just the prose.
    joined = " ".join(c.guardrails).lower()
    assert "medical" in joined
    assert "shame" in joined


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
