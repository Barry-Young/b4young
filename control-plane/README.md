# Control Plane + Data Plane

The strategic core of the Blueprint Builder system (Control Plane) plus a first
slice of the **Data Plane** — runnable agent crews coordinated over a shared
Blackboard.

## Control Plane (Phase 1 MVP)

Implements the [Phase 1 roadmap milestones](../docs/06-roadmap.md#61-phase-1-foundational-infrastructure-and-control-plane-mvp):

- **Agent Design Studio (minimal):** define agent blueprints — Role, Goal,
  Backstory, Tools, Model — via API or the web UI.
- **Secure Key Vault:** hold API keys in memory; secrets are never persisted or
  returned (only a masked preview). Seedable from `BYI_KEY_<NAME>` env vars.
- **Brand Constitution v1.1:** [`brand_constitution.yaml`](./brand_constitution.yaml)
  carries the brand's voice, audience, structural principles, preferred/banned
  terms, and guardrails. It is injected into every agent run and enforced
  (banned-term flagging) on output.
- **Activity dashboard:** run an agent or a crew and monitor every run, its
  output, duration, and governance flags.

With no API key the agent runner uses a deterministic **stub** provider, so the
system runs with no external dependencies.

### Turning on real output (Claude)

Agents default to the **`auto`** model, which follows the vault:

| Vault state | What agents produce |
|---|---|
| No `ANTHROPIC` key | Stub placeholder text — offline, free, deterministic |
| `ANTHROPIC` key set | Real drafts from `claude-sonnet-4-6` |

So adding the key is the whole switch:

1. Create a key at [console.anthropic.com](https://console.anthropic.com/settings/keys).
2. Paste it into the **Secure Key Vault** card on the dashboard as `ANTHROPIC`.
   It takes effect on the next run — no restart, no env var.
3. The banner at the top of the dashboard flips to **Real AI is ON**.

To have the key present from startup instead, export it before launching:

```bash
export BYI_KEY_ANTHROPIC=sk-ant-...      # seeded into the vault at startup
export BYI_AGENT_MODEL=claude-sonnet-4-6 # optional: pin agents to a model
```

Notes:

- The vault is **in-memory only** — nothing is written to disk, and the API
  returns a masked preview, never the secret. Restarting clears it.
- `BYI_AGENT_MODEL=stub` keeps agents offline even when a key is present.
  Individual blueprints can also set `model` directly (e.g. `claude-opus-4-8`).
- A Claude model with no key falls back to the stub rather than failing, so a
  missing key never breaks a run — the dashboard banner and each Blackboard
  entry's `resolved_model` / `is_stub` metadata tell you which one actually ran.
- A rejected key or an upstream outage surfaces as a `502` with a plain-English
  reason, and the crew run is recorded as `FAILED`.
- The evaluation **LLM-as-judge** uses a real model automatically when the
  `ANTHROPIC` key is present, and the heuristic judge otherwise.

## Data Plane: crews + Blackboard (Phase 2–3)

The Control Plane can deploy and run **agent crews**
([docs/02](../docs/02-multi-agent-ecosystem.md), [docs/03](../docs/03-agent-crews.md)):

- **Crews & Orchestrator-Worker** (all four from docs/03):
  - **Market Intelligence** — Chief Strategist + Trend Spotter + Competitor
    Analyst + Audience Profiler.
  - **Content Factory** — Executive Producer + Content Strategist + Scriptwriter
    + Voice Artist + Video Producer.
  - **Marketing & Distribution** — Campaign Manager + Social Media Manager +
    Affiliate Program Manager + Engagement Bot.
  - **Automated Service Delivery** — Product Manager + Webinar Host +
    Personalized Coaching Bot.
- **Shared Blackboard:** every artifact is written as an entry that conforms to
  the versioned [`docs/schemas/blackboard.schema.json`](../docs/schemas/blackboard.schema.json)
  (a test validates conformance against that file) and is persisted for
  inspection and cross-crew consumption.
- **Event bus:** agents publish completion events over a synchronous pub/sub bus
  (swap-in transport later).
- **Resumable Human-in-the-Loop gate:** crew runs **pause** at checkpoints and
  resume on approval. Market Intelligence pauses at its final brief; Content
  Factory pauses **after the script** and again **before the final package**.
  Approve via `POST /api/blackboard/{task_id}/approve` (or the dashboard); the
  run advances to the next checkpoint or completes. Run state lives in
  `CrewRun` records (`GET /api/crew-runs`).
- **Cross-crew pipeline:** approving a crew's final brief automatically deploys
  the downstream crew with that brief as its directive (`GET /api/pipeline`).
  Out of the box, an approved **Market Intelligence** brief auto-launches the
  **Content Factory**; chained runs/artifacts carry `source_task_id` /
  `parent_task_id` back to the originating brief.
- **Evaluation framework:** a golden dataset
  ([`evaluation/golden_dataset.yaml`](./evaluation/golden_dataset.yaml)) is run
  end-to-end (auto-approving checkpoints) and scored by an LLM-as-judge stub for
  brand alignment — `POST /api/evaluation/run`. Eval runs use an ephemeral store
  and never touch live state.

The crew runtime is adapted from the standalone reference at
[`reference/blueprint_builder_v1.py`](./reference/blueprint_builder_v1.py),
unified with the Control Plane's provider abstraction, Brand Constitution, and
activity log. Add more crews by implementing a builder under `app/crews/` and
registering it in `app/crews/__init__.py`.

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
| `GET` | `/api/crews` | List deployable crews |
| `POST` | `/api/crews/{key}/run` | Deploy & run a crew until done or first checkpoint |
| `GET` | `/api/crew-runs` | List crew runs (with status) |
| `GET` | `/api/crew-runs/{id}` | Get a crew run |
| `GET` | `/api/blackboard` | Recent Blackboard entries |
| `POST` | `/api/blackboard/{task_id}/approve` | HITL: approve an entry and resume its run |
| `GET` | `/api/evaluation/cases` | List golden evaluation cases |
| `POST` | `/api/evaluation/run` | Run the evaluation (optional `?crew=`) |

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
    providers.py     # LLM provider abstraction: StubProvider + AnthropicProvider
    constitution.py  # Brand Constitution loader + enforcement
    runner.py        # executes a blueprint or starts/resumes a crew run
    evaluation.py    # golden dataset runner + LLM-as-judge stub
    crews/           # Data Plane
      blackboard.py        # schema-aware Blackboard + EventBus
      base.py              # Agent / Task / Crew primitives
      engine.py            # resumable run engine + HITL checkpoints
      market_intelligence.py
      content_factory.py
      marketing_distribution.py
      automated_service_delivery.py
      __init__.py          # crew registry
    templates/       # dashboard HTML
  brand_constitution.yaml
  evaluation/        # golden_dataset.yaml
  reference/         # original standalone reference (blueprint_builder_v1.py)
  tests/
  requirements.txt
```

## Not yet implemented

All four crews from the architecture are implemented, and a real Claude provider
+ LLM-as-judge are wired in (with stub fallback). Later phases still add:
tool-backed agents (web search, social/affiliate/TTS/video APIs), a distributed
event-bus transport (SQS/PubSub/Kafka) in place of the in-process bus, managed
datastores in place of the JSON files, and RBAC. This remains a single-node,
file-backed stand-in.
