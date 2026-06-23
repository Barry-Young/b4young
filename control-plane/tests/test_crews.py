"""Tests for the Market Intelligence crew, Blackboard schema conformance,
and the resumable Human-in-the-Loop gate."""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

SCHEMA_PATH = (
    Path(__file__).resolve().parent.parent.parent / "docs" / "schemas" / "blackboard.schema.json"
)


@pytest.fixture()
def client(tmp_path, monkeypatch):
    import app.store as store

    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    import app.main as main

    main = importlib.reload(main)
    return TestClient(main.app)


@pytest.fixture(scope="session")
def validator() -> Draft202012Validator:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def test_list_crews(client):
    keys = [c["key"] for c in client.get("/api/crews").json()]
    assert "market_intelligence" in keys
    assert "content_factory" in keys


def test_run_market_intelligence_pauses_for_approval(client):
    run = client.post("/api/crews/market_intelligence/run", json={"input": "Q4 entrepreneurs"})
    assert run.status_code == 200
    body = run.json()
    # 3 workers (no checkpoints) + 1 orchestrator brief (final checkpoint).
    assert body["status"] == "AWAITING_APPROVAL"
    assert body["pending_task_id"] is not None
    assert len(body["entry_ids"]) == 4


def test_blackboard_schema_conformance(client, validator):
    client.post("/api/crews/market_intelligence/run", json={"input": "x"})
    entries = client.get("/api/blackboard").json()
    assert len(entries) == 4
    for entry in entries:
        cleaned = {k: v for k, v in entry.items() if v is not None}
        errors = sorted(validator.iter_errors(cleaned), key=str)
        assert not errors, f"schema errors: {[e.message for e in errors]}"


def test_market_intelligence_hitl_completes_run(client):
    run = client.post("/api/crews/market_intelligence/run", json={"input": "x"}).json()
    run_id, pending = run["id"], run["pending_task_id"]

    approved = client.post(f"/api/blackboard/{pending}/approve")
    assert approved.status_code == 200
    assert approved.json()["status"] == "APPROVED"

    # Approving the final brief completes the run and logs activity.
    finished = client.get(f"/api/crew-runs/{run_id}").json()
    assert finished["status"] == "COMPLETE"
    activity = client.get("/api/activity").json()
    assert any(a["blueprint_id"] == "crew:market_intelligence" for a in activity)


def test_double_approve_conflict(client):
    run = client.post("/api/crews/market_intelligence/run", json={"input": "x"}).json()
    pending = run["pending_task_id"]
    assert client.post(f"/api/blackboard/{pending}/approve").status_code == 200
    assert client.post(f"/api/blackboard/{pending}/approve").status_code == 409


def test_approve_unknown_entry_404(client):
    assert client.post("/api/blackboard/nope/approve").status_code == 404


def test_unknown_crew_404(client):
    assert client.post("/api/crews/marketing_distribution/run", json={"input": "x"}).status_code == 404
