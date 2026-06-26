"""Tests for the Phase 4 crews (Marketing & Distribution, Automated Service
Delivery) and evaluation coverage across all four crews."""

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


def test_all_four_crews_registered(client):
    keys = {c["key"] for c in client.get("/api/crews").json()}
    assert keys == {
        "market_intelligence",
        "content_factory",
        "marketing_distribution",
        "automated_service_delivery",
    }


@pytest.mark.parametrize(
    "crew_key,roles,final_artifact",
    [
        (
            "marketing_distribution",
            ["Social Media Manager", "Affiliate Program Manager", "Engagement Bot"],
            "distribution_plan",
        ),
        (
            "automated_service_delivery",
            ["Webinar Host", "Personalized Coaching Bot"],
            "service_plan",
        ),
    ],
)
def test_crew_runs_to_completion(client, crew_key, roles, final_artifact):
    run = client.post(f"/api/crews/{crew_key}/run", json={"input": "go"}).json()
    # Workers have no mid-checkpoints; run pauses at the final artifact.
    assert run["status"] == "AWAITING_APPROVAL"
    bb = {e["task_id"]: e for e in client.get("/api/blackboard").json()}
    assert bb[run["pending_task_id"]]["artifact_type"] == final_artifact

    finished = client.post(f"/api/blackboard/{run['pending_task_id']}/approve")
    assert finished.status_code == 200
    done = client.get(f"/api/crew-runs/{run['id']}").json()
    assert done["status"] == "COMPLETE"
    for role in roles:
        assert role in done["report"]

    activity = client.get("/api/activity").json()
    assert any(a["blueprint_id"] == f"crew:{crew_key}" for a in activity)


def test_evaluation_covers_all_crews(client):
    report = client.post("/api/evaluation/run").json()
    assert report["total"] == 4
    assert report["passed"] == 4
    assert report["average_score"] == 1.0
    crews = {r["crew"] for r in report["results"]}
    assert crews == {
        "market_intelligence",
        "content_factory",
        "marketing_distribution",
        "automated_service_delivery",
    }
