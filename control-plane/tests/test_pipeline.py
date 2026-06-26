"""Tests for end-to-end crew chaining (Market Intelligence -> Content Factory)."""

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


def test_pipeline_endpoint(client):
    assert client.get("/api/pipeline").json() == {"market_intelligence": "content_factory"}


def test_approving_brief_chains_to_content_factory(client):
    # Run Market Intelligence and approve its final brief.
    mi = client.post("/api/crews/market_intelligence/run", json={"input": "Q4 niche"}).json()
    brief_task = mi["pending_task_id"]
    client.post(f"/api/blackboard/{brief_task}/approve")

    # The MI run is complete...
    assert client.get(f"/api/crew-runs/{mi['id']}").json()["status"] == "COMPLETE"

    # ...and a Content Factory run was auto-deployed from that brief.
    runs = client.get("/api/crew-runs").json()
    chained = [r for r in runs if r["crew"] == "content_factory"]
    assert len(chained) == 1
    cf = chained[0]
    assert cf["source_task_id"] == brief_task
    # CF paused at its first checkpoint (the script).
    assert cf["status"] == "AWAITING_APPROVAL"

    # Chained CF artifacts are linked back to the originating brief.
    bb = {e["task_id"]: e for e in client.get("/api/blackboard").json()}
    assert bb[cf["pending_task_id"]]["parent_task_id"] == brief_task


def test_content_factory_does_not_chain(client):
    cf = client.post("/api/crews/content_factory/run", json={"input": "topic"}).json()
    # Drive CF to completion (script, then package).
    for _ in range(2):
        latest = client.get(f"/api/crew-runs/{cf['id']}").json()
        if latest["pending_task_id"]:
            client.post(f"/api/blackboard/{latest['pending_task_id']}/approve")
    # No downstream crew exists for Content Factory.
    runs = client.get("/api/crew-runs").json()
    assert len(runs) == 1
    assert runs[0]["crew"] == "content_factory"


def test_unrelated_crew_does_not_chain(client):
    run = client.post("/api/crews/marketing_distribution/run", json={"input": "x"}).json()
    client.post(f"/api/blackboard/{run['pending_task_id']}/approve")
    runs = client.get("/api/crew-runs").json()
    assert {r["crew"] for r in runs} == {"marketing_distribution"}
