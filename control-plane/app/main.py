"""Control Plane MVP — FastAPI application.

Exposes a JSON API and a minimal server-rendered dashboard for:
  * defining agent blueprints (role / goal / backstory / tools / model)
  * holding API keys in a secure vault (masked, never persisted)
  * running a "hello world" agent and monitoring its activity log

Run locally:  uvicorn app.main:app --reload  (from the control-plane/ dir)
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from . import __version__
from .constitution import BrandConstitution
from .models import (
    ActivityLogEntry,
    AgentBlueprint,
    AgentBlueprintCreate,
    RunRequest,
    VaultKeyCreate,
    VaultKeyInfo,
)
from .runner import run_blueprint
from .store import build_stores
from .vault import Vault

TEMPLATES = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))

app = FastAPI(title="Blueprint Builder — Control Plane", version=__version__)

blueprints, activity = build_stores()
vault = Vault()
vault.seed_from_env()
constitution = BrandConstitution.load()


def _seed_default_blueprint() -> None:
    """Ensure a hello-world agent exists so the system is runnable out of the box."""
    if not blueprints.list():
        blueprints.add(
            AgentBlueprint(
                name="Hello World Agent",
                role="Onboarding Assistant",
                goal="Confirm the Control Plane can deploy, run, and monitor an agent.",
                backstory="The first agent deployed to validate the Phase 1 MVP.",
                tools=[],
                model="stub",
            )
        )


_seed_default_blueprint()


# --------------------------------------------------------------------------- #
# JSON API
# --------------------------------------------------------------------------- #
@app.get("/health")
def health() -> dict:
    return {"status": "ok", "version": __version__, "constitution": constitution.version}


@app.get("/api/blueprints", response_model=list[AgentBlueprint])
def list_blueprints() -> list[AgentBlueprint]:
    return blueprints.list()


@app.post("/api/blueprints", response_model=AgentBlueprint, status_code=201)
def create_blueprint(payload: AgentBlueprintCreate) -> AgentBlueprint:
    return blueprints.add(AgentBlueprint(**payload.model_dump()))


@app.get("/api/blueprints/{blueprint_id}", response_model=AgentBlueprint)
def get_blueprint(blueprint_id: str) -> AgentBlueprint:
    bp = blueprints.get(blueprint_id)
    if bp is None:
        raise HTTPException(status_code=404, detail="blueprint not found")
    return bp


@app.delete("/api/blueprints/{blueprint_id}", status_code=204)
def delete_blueprint(blueprint_id: str) -> None:
    if not blueprints.delete(blueprint_id):
        raise HTTPException(status_code=404, detail="blueprint not found")


@app.post("/api/blueprints/{blueprint_id}/run", response_model=ActivityLogEntry)
def run_agent(blueprint_id: str, payload: RunRequest) -> ActivityLogEntry:
    bp = blueprints.get(blueprint_id)
    if bp is None:
        raise HTTPException(status_code=404, detail="blueprint not found")
    return run_blueprint(
        bp, payload.input, vault=vault, constitution=constitution, activity=activity
    )


@app.get("/api/activity", response_model=list[ActivityLogEntry])
def list_activity(limit: int = 50) -> list[ActivityLogEntry]:
    return activity.list(limit=limit)


@app.get("/api/vault/keys", response_model=list[VaultKeyInfo])
def list_keys() -> list[VaultKeyInfo]:
    return vault.list_keys()


@app.post("/api/vault/keys", response_model=VaultKeyInfo, status_code=201)
def set_key(payload: VaultKeyCreate) -> VaultKeyInfo:
    vault.set_key(payload.name, payload.value)
    return vault.info(payload.name)


# --------------------------------------------------------------------------- #
# Minimal web dashboard (server-rendered, form-based — no JS required)
# --------------------------------------------------------------------------- #
@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request) -> HTMLResponse:
    return TEMPLATES.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "version": __version__,
            "constitution": constitution,
            "blueprints": blueprints.list(),
            "activity": activity.list(limit=25),
            "keys": vault.list_keys(),
        },
    )


@app.post("/ui/blueprints")
def ui_create_blueprint(
    name: str = Form(...),
    role: str = Form(...),
    goal: str = Form(...),
    backstory: str = Form(""),
    tools: str = Form(""),
    model: str = Form("stub"),
) -> RedirectResponse:
    tool_list = [t.strip() for t in tools.split(",") if t.strip()]
    blueprints.add(
        AgentBlueprint(name=name, role=role, goal=goal, backstory=backstory, tools=tool_list, model=model)
    )
    return RedirectResponse(url="/", status_code=303)


@app.post("/ui/blueprints/{blueprint_id}/run")
def ui_run_blueprint(blueprint_id: str, task_input: str = Form("")) -> RedirectResponse:
    bp = blueprints.get(blueprint_id)
    if bp is not None:
        run_blueprint(bp, task_input, vault=vault, constitution=constitution, activity=activity)
    return RedirectResponse(url="/", status_code=303)


@app.post("/ui/vault/keys")
def ui_set_key(name: str = Form(...), value: str = Form(...)) -> RedirectResponse:
    vault.set_key(name, value)
    return RedirectResponse(url="/", status_code=303)
