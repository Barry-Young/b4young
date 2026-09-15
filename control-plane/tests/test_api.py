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


def test_health_reports_ai_off_until_a_key_is_added(client):
    ai = client.get("/health").json()["ai"]
    assert ai["enabled"] is False
    assert ai["key_name"] == "ANTHROPIC"

    client.post("/api/vault/keys", json={"name": "ANTHROPIC", "value": "sk-ant-test"})
    assert client.get("/health").json()["ai"]["enabled"] is True


def test_dashboard_warns_when_output_is_placeholder(client):
    # Without a key the dashboard must say so — a stub run should never be
    # mistaken for a real draft.
    assert "Real AI is OFF" in client.get("/").text

    client.post("/api/vault/keys", json={"name": "ANTHROPIC", "value": "sk-ant-test"})
    assert "Real AI is ON" in client.get("/").text


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


def test_provider_failure_returns_an_actionable_502(client, monkeypatch):
    # A mistyped key is a user error, not a crash: the API should say what is
    # wrong and the run should be recorded as FAILED, not return a bare 500.
    from app.providers import AnthropicProvider, ProviderError

    def _boom(self, prompt, *, system=None):
        raise ProviderError("Anthropic rejected the API key.")

    monkeypatch.setattr(AnthropicProvider, "generate", _boom)
    client.post("/api/vault/keys", json={"name": "ANTHROPIC", "value": "sk-ant-bad"})

    r = client.post("/api/crews/content_factory/run", json={"input": "test"})
    assert r.status_code == 502
    assert "rejected the API key" in r.json()["detail"]

    runs = client.get("/api/crew-runs").json()
    assert runs[0]["status"] == "FAILED"
    assert "rejected the API key" in runs[0]["error"]


def test_dashboard_documents_the_directive_format_convention(client):
    # The format is a convention typed into a free-text box, so the dashboard has
    # to state it — otherwise only the source code knows it exists.
    from app.crews.content_factory import DEFAULT_FORMAT

    page = client.get("/").text
    assert "Format: &lt;platform&gt;, &lt;length&gt;" in page
    assert DEFAULT_FORMAT in page


def test_dashboard_renders(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "Control Plane" in r.text


def test_blackboard_shows_the_artifact_text_not_just_its_label(client):
    """The HITL gate is meaningless if you can't read what you're approving.

    The card used to show only metadata — crew, producer, artifact type — so the
    only way to read a generated script was to hit /api/blackboard by hand and
    pick it out of the raw JSON.
    """
    client.post("/api/crews/content_factory/run", json={"input": "Regaining ground"})

    page = client.get("/").text
    entries = client.get("/api/blackboard").json()
    script = next(e for e in entries if e["artifact_type"] == "script")

    # The script's own text is on the page, and the entry awaiting approval is
    # expanded so it is read rather than skipped past.
    assert script["payload"]["output"][:60] in page
    assert "<details class=\"artifact\" open>" in page
    assert "Read the script" in page
    assert "Directive: Regaining ground" in page


def test_blackboard_marks_placeholder_text_as_placeholder(client):
    # With no key every artifact is stub output. Saying so on the artifact
    # itself stops a placeholder being mistaken for a draft worth approving.
    client.post("/api/crews/content_factory/run", json={"input": "Regaining ground"})
    assert "placeholder text — no API key" in client.get("/").text


def test_blackboard_surfaces_governance_flags_on_the_artifact(client):
    # A banned term is a Brand Constitution violation; it belongs next to the
    # text that carries it, not only in the JSON.
    from app.models import BlackboardEntry, BlackboardStatus, CrewName

    entry = BlackboardEntry(
        crew=CrewName.CONTENT_FACTORY,
        producer_agent="Content Strategist",
        artifact_type="content_outline",
        status=BlackboardStatus.COMPLETE,
        payload={"output": "It is not a diagnosis.", "directive": "Regaining ground"},
        metadata={"governance_flags": ["banned term used: 'diagnosis'"]},
    )
    import app.main as main

    main.blackboard_store.add(entry)

    assert "banned term used: &#39;diagnosis&#39;" in client.get("/").text
