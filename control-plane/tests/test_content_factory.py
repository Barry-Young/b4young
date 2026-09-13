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
