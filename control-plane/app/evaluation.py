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

import re
import tempfile
from pathlib import Path

import yaml

from . import crews as crew_registry
from .constitution import BrandConstitution
from .crews import engine
from .crews.blackboard import Blackboard
from .models import EvalCase, EvalReport, EvalResult
from .providers import get_provider
from .store import build_stores
from .vault import Vault

DATASET_PATH = Path(__file__).resolve().parent.parent / "evaluation" / "golden_dataset.yaml"
PASS_THRESHOLD = 0.7


def load_cases(path: Path = DATASET_PATH) -> list[EvalCase]:
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return [EvalCase(**row) for row in data.get("cases", [])]


JUDGE_MODEL = "claude-sonnet-4-6"


def _llm_score(report: str, case: EvalCase, provider) -> tuple[float, str]:
    """Ask a real model to score brand alignment / coverage in [0, 1]."""
    expected = ", ".join(case.expect_terms) or "(none)"
    prompt = (
        "You are evaluating an AI agent crew's output for the byoungimprovements brand.\n"
        f"Directive: {case.directive}\n"
        f"The output should cover these points: {expected}.\n\n"
        f"OUTPUT:\n{report}\n\n"
        "Respond with ONLY a number from 0 to 1 scoring how well the output reflects "
        "the brand and covers the points (1 = excellent)."
    )
    raw = provider.generate(prompt, system="You are a strict evaluation judge. Reply with a single number.")
    match = re.search(r"[01](?:\.\d+)?", raw)
    score = min(1.0, max(0.0, float(match.group()))) if match else 0.0
    return score, f"[llm:{provider.name}] raw='{raw.strip()[:60]}'"


def judge(report: str, case: EvalCase, constitution: BrandConstitution, provider=None) -> EvalResult:
    text = report.lower()
    forbidden_hits = [t for t in case.forbid_terms if t.lower() in text]
    governance_flags = constitution.check_output(report)

    if provider is not None and not provider.is_stub:
        score, rationale = _llm_score(report, case, provider)
    else:
        expected = case.expect_terms or []
        hits = [t for t in expected if t.lower() in text]
        score = (len(hits) / len(expected)) if expected else 1.0
        rationale = f"[heuristic] expected-term coverage {len(hits)}/{len(expected)}"

    if forbidden_hits or governance_flags:
        score *= 0.5  # penalize policy violations
    passed = score >= PASS_THRESHOLD and not forbidden_hits and not governance_flags

    rationale += f"; forbidden hits: {forbidden_hits or 'none'}; governance flags: {governance_flags or 'none'}"
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

    # A real model judges when an ANTHROPIC key is present; otherwise the
    # heuristic judge is used (so eval is deterministic and offline by default).
    judge_provider = get_provider(JUDGE_MODEL, vault)

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
            results.append(judge(run.report or "", case, constitution, judge_provider))

    passed = sum(1 for r in results if r.passed)
    average = round(sum(r.score for r in results) / len(results), 3) if results else 0.0
    return EvalReport(results=results, total=len(results), passed=passed, average_score=average)
