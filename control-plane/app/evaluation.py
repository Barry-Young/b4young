"""Evaluation framework: golden dataset + LLM-as-judge (docs/06-roadmap.md, 6.3).

Runs each golden case through its crew end-to-end (auto-approving HITL
checkpoints so the run completes), then scores the synthesized report. The judge
here is a deterministic stub standing in for an LLM-as-judge: it scores by
coverage of expected terms and penalizes forbidden/banned terms. Swap in a real
model-backed judge later without changing the API.

Evaluation runs use an ephemeral, temp-dir store so they never pollute the live
Blackboard / activity log.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import yaml

from . import crews as crew_registry
from .constitution import BrandConstitution
from .crews import engine
from .crews.blackboard import Blackboard
from .models import EvalCase, EvalReport, EvalResult
from .store import build_stores
from .vault import Vault

DATASET_PATH = Path(__file__).resolve().parent.parent / "evaluation" / "golden_dataset.yaml"
PASS_THRESHOLD = 0.7


def load_cases(path: Path = DATASET_PATH) -> list[EvalCase]:
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return [EvalCase(**row) for row in data.get("cases", [])]


def judge(report: str, case: EvalCase, constitution: BrandConstitution) -> EvalResult:
    text = report.lower()
    expected = case.expect_terms or []
    hits = [t for t in expected if t.lower() in text]
    coverage = (len(hits) / len(expected)) if expected else 1.0

    forbidden_hits = [t for t in case.forbid_terms if t.lower() in text]
    governance_flags = constitution.check_output(report)

    score = coverage
    if forbidden_hits or governance_flags:
        score *= 0.5  # penalize policy violations
    passed = coverage == 1.0 and not forbidden_hits and not governance_flags

    rationale = (
        f"expected-term coverage {len(hits)}/{len(expected)}; "
        f"forbidden hits: {forbidden_hits or 'none'}; "
        f"governance flags: {governance_flags or 'none'}"
    )
    return EvalResult(
        case_id=case.id,
        name=case.name,
        crew=case.crew,
        score=round(score, 3),
        passed=passed,
        rationale=rationale,
        governance_flags=governance_flags,
    )


def run_evaluation(
    *,
    vault: Vault,
    constitution: BrandConstitution,
    crew_filter: str | None = None,
    cases: list[EvalCase] | None = None,
) -> EvalReport:
    cases = cases if cases is not None else load_cases()
    if crew_filter:
        cases = [c for c in cases if c.crew.value == crew_filter]

    results: list[EvalResult] = []
    with tempfile.TemporaryDirectory() as tmp:
        _bp, activity, blackboard_store, crew_runs = build_stores(Path(tmp))
        for case in cases:
            blackboard = Blackboard(blackboard_store)
            crew = crew_registry.build_crew(
                case.crew, blackboard=blackboard, vault=vault, constitution=constitution
            )
            run = engine.start_run(
                crew, case.directive, activity=activity, crew_runs=crew_runs, auto_approve=True
            )
            results.append(judge(run.report or "", case, constitution))

    passed = sum(1 for r in results if r.passed)
    average = round(sum(r.score for r in results) / len(results), 3) if results else 0.0
    return EvalReport(results=results, total=len(results), passed=passed, average_score=average)
