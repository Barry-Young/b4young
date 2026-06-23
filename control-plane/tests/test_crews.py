"""Tests for the Data Plane crews, Blackboard schema conformance, and HITL gate."""

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
    crews = client.get("/api/crews").json()
    keys = [c["key"] for c in crews]
    assert "market_intelligence" in keys


def test_run_market_intelligence_and_schema_conformance(client, validator):
    run = client.post("/api/crews/market_intelligence/run", json={"input": "Q4 entrepreneurs"})
    assert run.status_code == 200
    body = run.json()
    assert "Market Intelligence Brief" in body["report"]
    # 3 worker artifacts + 1 orchestrator brief
    assert len(body["entries"]) == 4

    # Every Blackboard entry must validate against the published JSON schema.
    for entry in body["entries"]:
        # Strip nulls the way the runtime persists them, mirroring to_schema_dict.
        cleaned = {k: v for k, v in entry.items() if v is not None}
        errors = sorted(validator.iter_errors(cleaned), key=str)
        assert not errors, f"schema errors: {[e.message for e in errors]}"

    # The orchestrator's brief is parked for human approval (HITL gate).
    brief = next(e for e in body["entries"] if e["artifact_type"] == "intelligence_brief")
    assert brief["status"] == "AWAITING_APPROVAL"
    assert brief["task_id"] == body["final_task_id"]


def test_crew_run_is_logged_to_activity(client):
    client.post("/api/crews/market_intelligence/run", json={"input": "x"})
    activity = client.get("/api/activity").json()
    assert any(a["blueprint_id"] == "crew:market_intelligence" for a in activity)


def test_blackboard_listing(client):
    client.post("/api/crews/market_intelligence/run", json={"input": "x"})
    entries = client.get("/api/blackboard").json()
    assert len(entries) >= 4
    assert all(e["schema_version"] == "1.0.0" for e in entries)


def test_hitl_approve_flow(client):
    run = client.post("/api/crews/market_intelligence/run", json={"input": "x"}).json()
    task_id = run["final_task_id"]

    approved = client.post(f"/api/blackboard/{task_id}/approve")
    assert approved.status_code == 200
    assert approved.json()["status"] == "APPROVED"

    # Re-approving is a conflict.
    again = client.post(f"/api/blackboard/{task_id}/approve")
    assert again.status_code == 409


def test_approve_unknown_entry_404(client):
    r = client.post("/api/blackboard/does-not-exist/approve")
    assert r.status_code == 404


def test_unknown_crew_404(client):
    r = client.post("/api/crews/content_factory/run", json={"input": "x"})
    assert r.status_code == 404
