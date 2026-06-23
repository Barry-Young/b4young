"""Tests for the evaluation framework (golden dataset + LLM-as-judge stub)."""

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


def test_list_eval_cases(client):
    cases = client.get("/api/evaluation/cases").json()
    assert len(cases) >= 2
    assert {c["crew"] for c in cases} >= {"market_intelligence", "content_factory"}


def test_run_evaluation_all_pass(client):
    report = client.post("/api/evaluation/run").json()
    assert report["total"] >= 2
    assert report["passed"] == report["total"]
    assert report["average_score"] == 1.0
    for r in report["results"]:
        assert r["passed"] is True
        assert not r["governance_flags"]


def test_run_evaluation_filtered_by_crew(client):
    report = client.post("/api/evaluation/run", params={"crew": "content_factory"}).json()
    assert report["total"] == 1
    assert report["results"][0]["crew"] == "content_factory"


def test_evaluation_does_not_pollute_live_stores(client):
    client.post("/api/evaluation/run")
    # Eval uses an ephemeral store, so the live Blackboard/activity stay empty.
    assert client.get("/api/blackboard").json() == []
    assert client.get("/api/activity").json() == []
