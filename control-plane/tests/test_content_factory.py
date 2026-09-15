"""Tests for the Content Factory crew and multi-checkpoint Human-in-the-Loop."""

from __future__ import annotations

import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    import app.store as store

    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    import app.main as main

    main = importlib.reload(main)
    return TestClient(main.app)


def test_content_factory_two_checkpoints(client):
    # 1) Start: runs Content Strategist, then pauses at the Scriptwriter checkpoint.
    run = client.post(
        "/api/crews/content_factory/run", json={"input": "Topic: Imposter Syndrome"}
    ).json()
    run_id = run["id"]
    assert run["status"] == "AWAITING_APPROVAL"
    assert len(run["entry_ids"]) == 2  # outline + script

    script_task = run["pending_task_id"]
    bb = {e["task_id"]: e for e in client.get("/api/blackboard").json()}
    assert bb[script_task]["artifact_type"] == "script"

    # 2) Approve the script: resumes through Voice + Video, pauses at the package.
    client.post(f"/api/blackboard/{script_task}/approve")
    mid = client.get(f"/api/crew-runs/{run_id}").json()
    assert mid["status"] == "AWAITING_APPROVAL"
    assert len(mid["entry_ids"]) == 5  # outline, script, voiceover, video, package
    package_task = mid["pending_task_id"]
    bb = {e["task_id"]: e for e in client.get("/api/blackboard").json()}
    assert bb[package_task]["artifact_type"] == "content_package"

    # 3) Approve the package: run completes.
    client.post(f"/api/blackboard/{package_task}/approve")
    done = client.get(f"/api/crew-runs/{run_id}").json()
    assert done["status"] == "COMPLETE"
    assert "Content Factory Brief" in (done["report"] or "")

    activity = client.get("/api/activity").json()
    assert any(a["blueprint_id"] == "crew:content_factory" for a in activity)


def test_content_factory_report_includes_all_roles(client):
    run = client.post("/api/crews/content_factory/run", json={"input": "x"}).json()
    # Drive both checkpoints to completion.
    for _ in range(2):
        latest = client.get(f"/api/crew-runs/{run['id']}").json()
        if latest["pending_task_id"]:
            client.post(f"/api/blackboard/{latest['pending_task_id']}/approve")
    done = client.get(f"/api/crew-runs/{run['id']}").json()
    report = done["report"]
    for role in ["Content Strategist", "Scriptwriter", "Voice Artist", "Video Producer"]:
        assert role in report


# --------------------------------------------------------------------------- #
# Format and length are pinned so the two agents cannot contradict each other
# --------------------------------------------------------------------------- #
def _content_factory_tasks():
    from app.constitution import BrandConstitution
    from app.crews import content_factory
    from app.crews.blackboard import Blackboard
    from app.store import BlackboardStore
    from app.vault import Vault

    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        crew = content_factory.build(
            blackboard=Blackboard(BlackboardStore(Path(tmp) / "bb.json")),
            vault=Vault(),
            constitution=BrandConstitution({}),
        )
        return {t.agent.role: t.description for t in crew.tasks}


def _content_factory_agents():
    from app.constitution import BrandConstitution
    from app.crews import content_factory
    from app.crews.blackboard import Blackboard
    from app.store import BlackboardStore
    from app.vault import Vault

    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        crew = content_factory.build(
            blackboard=Blackboard(BlackboardStore(Path(tmp) / "bb.json")),
            vault=Vault(),
            constitution=BrandConstitution({}),
        )
        return {t.agent.role: t.agent for t in crew.tasks}


def test_strategist_and_scriptwriter_share_one_format_rule():
    # The Strategist used to invent a platform (it picked Substack long-form)
    # while the Scriptwriter wrote short-form video — two contradictory artifacts
    # from one run. Both must now be given the same rule.
    from app.crews.content_factory import FORMAT_RULE

    tasks = _content_factory_tasks()
    assert FORMAT_RULE in tasks["Content Strategist"]
    assert FORMAT_RULE in tasks["Scriptwriter"]


def test_strategist_is_told_not_to_pick_its_own_platform():
    description = _content_factory_tasks()["Content Strategist"]
    assert "Do not choose a platform of your own." in description


def test_format_rule_names_the_directive_syntax_and_a_default():
    from app.crews.content_factory import DEFAULT_FORMAT, FORMAT_RULE

    assert "Format: <platform>, <length>" in FORMAT_RULE
    assert DEFAULT_FORMAT in FORMAT_RULE


def test_scriptwriter_gets_a_hard_spoken_word_budget():
    # Without a budget it writes until every section is covered — the first real
    # run produced ~3 minutes of speech for a 45-second brief.
    description = _content_factory_tasks()["Scriptwriter"]
    assert "LENGTH IS A HARD CONSTRAINT" in description
    assert "90 spoken words" in description
    assert "do not count toward the budget" in description


# --------------------------------------------------------------------------- #
# Faceless production format and the two tracks' CTA rules
# --------------------------------------------------------------------------- #
def test_scriptwriter_is_told_the_account_is_faceless():
    # It wrote "direct eye contact to camera" for an account that has no camera.
    from app.crews.content_factory import PRODUCTION_RULE

    description = _content_factory_tasks()["Scriptwriter"]
    assert PRODUCTION_RULE in description
    assert "faceless" in PRODUCTION_RULE
    assert "no presenter and no camera" in PRODUCTION_RULE
    assert "voiceover only" in PRODUCTION_RULE


def test_both_agents_get_the_track_cta_rule():
    from app.crews.content_factory import TRACK_RULE

    tasks = _content_factory_tasks()
    assert TRACK_RULE in tasks["Content Strategist"]
    assert TRACK_RULE in tasks["Scriptwriter"]


def test_track_b_is_the_default_and_forbids_a_paid_cta():
    # B fails safe: a Track A post given B's rule only loses a sales CTA, while
    # a Track B post given A's puts a paid ask in front of someone vulnerable.
    from app.crews.content_factory import DEFAULT_TRACK, TRACK_RULE

    assert DEFAULT_TRACK == "B"
    assert f"assume Track {DEFAULT_TRACK}" in TRACK_RULE
    assert "NO paid call to action" in TRACK_RULE
    assert "treat it as Track B" in TRACK_RULE, "the unsure case must fail safe"


def test_tasks_do_not_contradict_the_constitution():
    # The Constitution says "one idea, one foot" and "clarify, do not motivate".
    # These task lines were written against the old v1.1 and said the opposite.
    joined = " ".join(_content_factory_tasks().values())
    assert "one idea, one foot" in joined.lower()
    assert "two or three concrete steps" not in joined
    assert "short encouraging line" not in joined


def test_both_agents_get_the_faceless_production_rule():
    """The Strategist planned "face to camera" while the Scriptwriter wrote voiceover.

    The rule reached only the Scriptwriter, so the two artifacts from one run
    disagreed about whether a presenter exists — the same class of contradiction
    that sharing FORMAT_RULE was introduced to prevent.
    """
    from app.crews.content_factory import PRODUCTION_RULE

    tasks = _content_factory_tasks()
    assert PRODUCTION_RULE in tasks["Content Strategist"]
    assert PRODUCTION_RULE in tasks["Scriptwriter"]


def test_length_is_read_from_the_directive_and_falls_back_to_the_default():
    from app.crews.content_factory import parse_length_seconds

    assert parse_length_seconds("Topic | Format: Instagram Reel, 45 seconds") == 45
    assert parse_length_seconds("Topic | Format: YouTube Short, 1 minute") == 60
    assert parse_length_seconds("Topic | Format: TikTok, 90 secs") == 90
    # No Format clause: the crew's own default is what the script is judged by.
    assert parse_length_seconds("Regaining ground") == 45


def test_only_marked_lines_count_toward_the_spoken_budget():
    from app.crews.content_factory import spoken_words

    package = "\n".join(
        [
            "# SCRIPT PACKAGE",
            "**Spoken word count:** 4 words",
            "VO: Something opened up — and now nothing fits.",
            "**On-screen text:** *something opened up*",
            "| Hook | Empty hallway, low light |",
            "#spiritualawakening #thehallway",
        ]
    )
    # The em dash is punctuation, and nothing outside the marked line is spoken.
    assert spoken_words(package) == [
        "Something", "opened", "up", "and", "now", "nothing", "fits.",
    ]


def test_a_script_that_overruns_its_length_is_flagged():
    # The real defect: a 45-second script claiming 89 words that ran to ~120.
    from app.crews.content_factory import check_script_length

    directive = "Regaining ground | Format: Instagram Reel, 45 seconds"
    overrun = "\n".join(f"VO: {'word ' * 10}" for _ in range(12))

    flags = check_script_length(overrun, directive)
    assert len(flags) == 1
    assert "overruns its length" in flags[0]
    assert "120 spoken words" in flags[0]
    assert "45-second budget" in flags[0]

    # Inside the budget, and a shade over it, are both fine.
    assert check_script_length("\n".join(["VO: word word"] * 40), directive) == []
    assert check_script_length("\n".join(["VO: word word"] * 48), directive) == []


def test_an_unmarked_script_is_flagged_rather_than_silently_passing():
    # Without the marker the budget cannot be measured. Saying so beats a green
    # result that means "not checked".
    from app.crews.content_factory import check_script_length

    flags = check_script_length("**Spoken:** nothing is marked", "Format: Reel, 45 seconds")
    assert len(flags) == 1
    assert "not marked" in flags[0]


def test_the_scriptwriter_is_told_to_mark_spoken_lines_and_is_checked():
    from app.crews.content_factory import VO_PREFIX, check_script_length

    tasks = _content_factory_tasks()
    assert VO_PREFIX in tasks["Scriptwriter"]

    scriptwriter = _content_factory_agents()["Scriptwriter"]
    assert scriptwriter.output_check is check_script_length


class _FakeProvider:
    """A non-stub provider returning a fixed reply, so checks actually run."""

    name = "fake"
    is_stub = False

    def __init__(self, reply: str) -> None:
        self._reply = reply

    def generate(self, prompt: str, *, system: str | None = None) -> str:
        return self._reply


def _run_scriptwriter(monkeypatch, reply: str, directive: str):
    """Run the real Scriptwriter agent over a fixed reply, return its entry."""
    import tempfile
    from pathlib import Path

    from app.constitution import BrandConstitution
    from app.crews import base
    from app.crews.blackboard import Blackboard, EventBus
    from app.models import CrewName
    from app.store import BlackboardStore
    from app.vault import Vault

    monkeypatch.setattr(base, "get_provider", lambda model, vault: _FakeProvider(reply))
    agent = _content_factory_agents()["Scriptwriter"]

    with tempfile.TemporaryDirectory() as tmp:
        return agent.perform_task(
            description="write it",
            directive=directive,
            crew=CrewName.CONTENT_FACTORY,
            blackboard=Blackboard(BlackboardStore(Path(tmp) / "bb.json")),
            event_bus=EventBus(),
            vault=Vault(),
            constitution=BrandConstitution({}),
        )


def test_the_length_flag_reaches_the_blackboard(monkeypatch):
    # A flag is only useful if it lands on the artifact the human reads.
    overrun = "\n".join(f"VO: {'word ' * 10}" for _ in range(12))
    entry = _run_scriptwriter(
        monkeypatch, overrun, "Regaining ground | Format: Instagram Reel, 45 seconds"
    )

    flags = entry.metadata["governance_flags"]
    assert any("overruns its length" in f for f in flags)
    assert entry.governance_flags == flags, "and reaches the dashboard accessor"


def test_a_script_inside_its_budget_carries_no_flag(monkeypatch):
    entry = _run_scriptwriter(
        monkeypatch,
        "\n".join(["VO: word word"] * 40),
        "Regaining ground | Format: Instagram Reel, 45 seconds",
    )
    assert entry.metadata["governance_flags"] == []


def test_placeholder_output_is_not_judged_as_a_script(client):
    """Artifact rules have nothing to say about stub text.

    Run with no key, every script would otherwise be flagged for not marking
    spoken lines — a complaint that the placeholder isn't a script, which tells
    nobody anything.
    """
    client.post(
        "/api/crews/content_factory/run",
        json={"input": "Regaining ground | Format: Instagram Reel, 45 seconds"},
    )

    entries = client.get("/api/blackboard").json()
    script = next(e for e in entries if e["artifact_type"] == "script")
    assert script["metadata"]["is_stub"] is True
    assert script["metadata"]["governance_flags"] == []
