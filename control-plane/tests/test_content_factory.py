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
    assert "180 spoken words" in description
    assert "handed back" in description, "the budget is enforced, not just stated"
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
    assert parse_length_seconds("Regaining ground") == 90


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

    result = check_script_length(overrun, directive)
    assert len(result.flags) == 1
    assert "overruns its length" in result.flags[0]
    assert "120 spoken words" in result.flags[0]
    assert "45-second budget" in result.flags[0]

    # Inside the budget, and a shade over it, are both fine.
    assert not check_script_length("\n".join(["VO: word word"] * 40), directive)
    assert not check_script_length("\n".join(["VO: word word"] * 48), directive)


def test_the_default_length_matches_what_the_writing_actually_produces():
    """Two live runs landed at ~88 seconds whatever target they were given.

    Briefed at 45s: 185 spoken words. Rebriefed at 60s and handed back once to
    cut: 176. The model counts accurately — the app verifies it — so the target
    was the thing that was wrong, twice. Both of those real results now pass.
    """
    from app.crews.content_factory import DEFAULT_FORMAT, check_script_length

    assert "90 seconds" in DEFAULT_FORMAT

    for count in (176, 185):
        draft = "\n".join(["VO: word"] * count)
        assert not check_script_length(draft, "Regaining ground"), count

    # A genuine runaway — the three-minute draft from the first live run — is
    # still caught. The revision pass is a net for that, not a way to shave a
    # fifth off a script that is already good.
    runaway = "\n".join(["VO: word"] * 360)
    assert check_script_length(runaway, "Regaining ground")


def test_distance_ranks_two_overrunning_drafts():
    """Flag count cannot tell 185 words from 140; both carry exactly one flag."""
    from app.crews.content_factory import check_script_length

    directive = "Regaining ground | Format: Instagram Reel, 60 seconds"
    long_draft = check_script_length("\n".join(["VO: word"] * 185), directive)
    shorter = check_script_length("\n".join(["VO: word"] * 140), directive)

    assert len(long_draft.flags) == len(shorter.flags) == 1
    assert shorter.distance < long_draft.distance
    # In budget is distance zero, and beats both.
    assert check_script_length("\n".join(["VO: word"] * 110), directive).distance == 0


def test_an_unmarked_script_is_flagged_rather_than_silently_passing():
    # Without the marker the budget cannot be measured. Saying so beats a green
    # result that means "not checked", and unmeasurable must rank worse than any
    # measurable draft so a countable rewrite wins.
    from app.crews.content_factory import check_script_length

    result = check_script_length("**Spoken:** nothing is marked", "Format: Reel, 45 seconds")
    assert len(result.flags) == 1
    assert "not marked" in result.flags[0]
    assert result.distance == float("inf")


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


# --------------------------------------------------------------------------- #
# The revision pass: an overrunning draft is handed back once
# --------------------------------------------------------------------------- #
class _ScriptedProvider:
    """Returns each reply in turn, and records the prompts it was given."""

    name = "scripted"
    is_stub = False

    def __init__(self, *replies: str) -> None:
        self._replies = list(replies)
        self.prompts: list[str] = []

    def generate(self, prompt: str, *, system: str | None = None) -> str:
        self.prompts.append(prompt)
        return self._replies.pop(0) if self._replies else self._replies_exhausted()

    def _replies_exhausted(self) -> str:
        raise AssertionError("the agent asked for more drafts than the test scripted")


def _run_with(monkeypatch, provider, directive="Topic | Format: Instagram Reel, 60 seconds"):
    import tempfile
    from pathlib import Path

    from app.constitution import BrandConstitution
    from app.crews import base
    from app.crews.blackboard import Blackboard, EventBus
    from app.models import CrewName
    from app.store import BlackboardStore
    from app.vault import Vault

    monkeypatch.setattr(base, "get_provider", lambda model, vault: provider)
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


def test_an_overrunning_draft_is_handed_back_and_the_shorter_one_kept(monkeypatch):
    """185 words for a 60-second reel was the live result. Flagging it changed nothing."""
    over = "\n".join(["VO: word"] * 185)
    good = "\n".join(["VO: word"] * 110)
    provider = _ScriptedProvider(over, good)

    entry = _run_with(monkeypatch, provider)

    assert len(provider.prompts) == 2, "one retry, not a loop"
    assert entry.payload["output"] == good
    assert entry.metadata["governance_flags"] == []
    assert entry.metadata["revised"] is True

    # The retry is told what it missed, and by how much, and sees its own draft.
    retry = provider.prompts[1]
    assert "185 spoken words" in retry
    assert "60-second budget" in retry
    assert over in retry


def test_a_first_draft_inside_the_budget_is_not_revised(monkeypatch):
    provider = _ScriptedProvider("\n".join(["VO: word"] * 110))

    entry = _run_with(monkeypatch, provider)

    assert len(provider.prompts) == 1, "no retry when nothing is wrong"
    assert entry.metadata["revised"] is False


def test_a_worse_rewrite_is_discarded(monkeypatch):
    # A rewrite can overshoot the other way. Keeping the newer draft blindly
    # would ship the worse one.
    over = "\n".join(["VO: word"] * 140)
    worse = "\n".join(["VO: word"] * 300)
    provider = _ScriptedProvider(over, worse)

    entry = _run_with(monkeypatch, provider)

    assert entry.payload["output"] == over
    assert entry.metadata["revised"] is False
    assert "140 spoken words" in entry.metadata["governance_flags"][0]


def test_a_closer_but_still_long_rewrite_is_kept(monkeypatch):
    # Both overrun and both carry one flag, so only distance can choose.
    over = "\n".join(["VO: word"] * 185)
    closer = "\n".join(["VO: word"] * 140)
    provider = _ScriptedProvider(over, closer)

    entry = _run_with(monkeypatch, provider)

    assert entry.payload["output"] == closer
    assert entry.metadata["revised"] is True
    assert "140 spoken words" in entry.metadata["governance_flags"][0]


def test_placeholder_output_is_never_revised(client):
    # No key means stub text, and a retry would buy a second placeholder.
    client.post(
        "/api/crews/content_factory/run",
        json={"input": "Regaining ground | Format: Instagram Reel, 60 seconds"},
    )
    entries = client.get("/api/blackboard").json()
    script = next(e for e in entries if e["artifact_type"] == "script")
    assert script["metadata"]["is_stub"] is True
    assert script["metadata"]["revised"] is False
