"""End-to-end API tests for the Control Plane MVP.

Uses a temporary data directory so tests never touch real persisted state.
"""

from __future__ import annotations

import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    # Point the store at a temp dir, then (re)import the app fresh.
    import app.store as store

    monkeypatch.setattr(store, "DATA_DIR", tmp_path)
    import app.main as main

    main = importlib.reload(main)
    return TestClient(main.app)


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_seeded_blueprint_present(client):
    r = client.get("/api/blueprints")
    assert r.status_code == 200
    names = [b["name"] for b in r.json()]
    assert "Hello World Agent" in names


def test_create_run_and_log(client):
    created = client.post(
        "/api/blueprints",
        json={"name": "Trend Spotter", "role": "Trend Analyst", "goal": "Find trends"},
    )
    assert created.status_code == 201
    bp_id = created.json()["id"]

    run = client.post(f"/api/blueprints/{bp_id}/run", json={"input": "scan the niche"})
    assert run.status_code == 200
    body = run.json()
    assert body["status"] == "COMPLETE"
    assert "hello world" in body["output"].lower()
    assert body["duration_ms"] is not None

    activity = client.get("/api/activity").json()
    assert any(a["blueprint_id"] == bp_id for a in activity)


def test_run_missing_blueprint_404(client):
    r = client.post("/api/blueprints/does-not-exist/run", json={"input": "x"})
    assert r.status_code == 404


def test_vault_masks_secret(client):
    r = client.post("/api/vault/keys", json={"name": "ANTHROPIC", "value": "sk-secret-1234"})
    assert r.status_code == 201
    info = r.json()
    assert info["is_set"] is True
    assert "sk-secret-1234" not in info["preview"]
    assert info["preview"].startswith("sk")

    listed = client.get("/api/vault/keys").json()
    assert all("sk-secret-1234" != k["preview"] for k in listed)


def test_governance_flags_banned_term(client, monkeypatch):
    # Force the stub output to contain a banned term and confirm it's flagged.
    import app.main as main

    monkeypatch.setattr(
        main, "constitution", main.BrandConstitution({"version": "test", "banned_terms": ["hello world"]})
    )
    created = client.post(
        "/api/blueprints", json={"name": "G", "role": "r", "goal": "g"}
    ).json()
    run = client.post(f"/api/blueprints/{created['id']}/run", json={"input": "hi"}).json()
    assert any("banned term" in f for f in run["governance_flags"])


def test_dashboard_renders(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "Control Plane" in r.text
