# Control Plane (Phase 1 MVP)

The strategic core of the Blueprint Builder system. This MVP implements the
[Phase 1 roadmap milestones](../docs/06-roadmap.md#61-phase-1-foundational-infrastructure-and-control-plane-mvp):

- **Agent Design Studio (minimal):** define agent blueprints — Role, Goal,
  Backstory, Tools, Model — via API or the web UI.
- **Secure Key Vault:** hold API keys in memory; secrets are never persisted or
  returned (only a masked preview). Seedable from `BYI_KEY_<NAME>` env vars.
- **Brand Constitution v1.0:** [`brand_constitution.yaml`](./brand_constitution.yaml)
  is injected into every agent run and enforced (banned-term flagging) on output.
- **Activity dashboard:** run a "hello world" agent and monitor every run, its
  output, duration, and governance flags.

The agent runner uses a deterministic **stub** provider, so the system runs with
no external dependencies. A real LLM provider can be added in
[`app/providers.py`](./app/providers.py) (pull credentials from the vault).

## Quickstart

```bash
cd control-plane
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

uvicorn app.main:app --reload
# open http://127.0.0.1:8000  (dashboard)  ·  /docs  (OpenAPI)
```

A "Hello World Agent" is seeded on first start, so you can click **Run**
immediately to confirm the Control Plane can deploy, run, and monitor an agent
— the Phase 1 success criterion.

## API

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/health` | Liveness + versions |
| `GET` | `/api/blueprints` | List blueprints |
| `POST` | `/api/blueprints` | Create a blueprint |
| `GET` | `/api/blueprints/{id}` | Get a blueprint |
| `DELETE` | `/api/blueprints/{id}` | Delete a blueprint |
| `POST` | `/api/blueprints/{id}/run` | Run the agent, returns the activity entry |
| `GET` | `/api/activity` | Recent activity log |
| `GET` | `/api/vault/keys` | List keys (masked) |
| `POST` | `/api/vault/keys` | Set a key |

Example:

```bash
curl -s localhost:8000/api/blueprints \
  -H 'content-type: application/json' \
  -d '{"name":"Trend Spotter","role":"Trend Analyst","goal":"Find trends"}'

curl -s localhost:8000/api/blueprints/<id>/run \
  -H 'content-type: application/json' -d '{"input":"scan the niche"}'
```

## Tests

```bash
cd control-plane
pip install -r requirements.txt
pytest
```

## Layout

```
control-plane/
  app/
    main.py          # FastAPI app: JSON API + server-rendered dashboard
    models.py        # Pydantic models (blueprints, activity, vault)
    store.py         # JSON-file persistence for blueprints & activity
    vault.py         # in-memory secret vault (masked, env-seedable)
    providers.py     # LLM provider abstraction + StubProvider
    constitution.py  # Brand Constitution loader + enforcement
    runner.py        # executes a blueprint, logs activity
    templates/       # dashboard HTML
  brand_constitution.yaml
  tests/
  requirements.txt
```

## Not in this MVP

Per the roadmap, later phases add the real Data Plane runtime, event bus +
Blackboard, managed datastores, RBAC, and real agent crews. This MVP is
deliberately a single-node, file-backed stand-in to satisfy the Phase 1 success
criteria.
