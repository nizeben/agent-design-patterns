"""Tests for the Hierarchical Delegation pattern.

Run: pytest collaboration/a-hierarchical-delegation/test_pattern.py -v

No API key needed — a mock ``dispatch`` stands in for a real worker agent, so
every test is deterministic. The tutorials swap the mock for LangGraph / the
Claude Agent SDK; the supervisor logic under test never changes.
"""
from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
sys.modules.pop("pattern", None)   # ensure we pick up THIS folder's pattern.py

from pattern import (   # noqa: E402
    SafetyBoundary,
    SalaryBatchArtifact,
    SettlementSupervisor,
    Verdict,
    WorkerSpec,
)

ROSTER = [
    {"id": "e1", "client": "acme", "base": 8000},
    {"id": "e2", "client": "acme", "base": 9000},
    {"id": "e3", "client": "globex", "base": 7000},
    {"id": "e4", "client": "initech", "base": 6000},
]


def _ok_dispatch(total: float = 1000.0, verdict: Verdict = Verdict.SUCCESS):
    async def dispatch(spec: WorkerSpec, rows: list[dict]) -> SalaryBatchArtifact:
        return SalaryBatchArtifact(
            batch_id=spec.batch_id, verdict=verdict,
            employee_count=len(rows), total_amount=total, confidence=1.0,
        )
    return dispatch


# ----- Decompose: per-client batches, each with a boundary (anti-overlap) -----

def test_decompose_splits_by_client():
    sup = SettlementSupervisor(dispatch=_ok_dispatch())
    batches = sup.decompose(ROSTER)
    ids = sorted(spec.batch_id for spec, _ in batches)
    assert ids == ["batch::acme", "batch::globex", "batch::initech"]


def test_every_spec_pins_a_boundary_and_tool_whitelist():
    sup = SettlementSupervisor(dispatch=_ok_dispatch())
    for spec, _ in sup.decompose(ROSTER):
        assert spec.boundary, "Spec must pin a boundary (what is NOT its job)"
        assert spec.allowed_tools, "Spec must whitelist tools"
        assert "calc_salary" in spec.allowed_tools


# ----- Gate (SafetyBoundary): the four deterministic escalation triggers -----

def test_gate_escalates_high_amount():
    g = SafetyBoundary(amount_threshold=50_000)
    art = SalaryBatchArtifact("b", Verdict.SUCCESS, 10, total_amount=60_000)
    assert g.must_escalate(art)


def test_gate_escalates_low_confidence():
    g = SafetyBoundary(min_confidence=0.85)
    art = SalaryBatchArtifact("b", Verdict.SUCCESS, 10, total_amount=1000, confidence=0.5)
    assert g.must_escalate(art)


def test_gate_escalates_on_needs_review_or_non_success():
    g = SafetyBoundary()
    assert g.must_escalate(
        SalaryBatchArtifact("b", Verdict.SUCCESS, 10, 1000, needs_review=["e1"])
    )
    assert g.must_escalate(SalaryBatchArtifact("b", Verdict.PARTIAL, 10, 1000))


def test_gate_passes_clean_batch():
    g = SafetyBoundary(amount_threshold=100_000)
    art = SalaryBatchArtifact("b", Verdict.SUCCESS, 10, total_amount=1000, confidence=1.0)
    assert not g.must_escalate(art)


# ----- Worker failure isolation: one dead batch costs only that batch -----

def test_worker_exception_becomes_failure_artifact():
    async def flaky(spec, rows):
        if spec.batch_id == "batch::globex":
            raise RuntimeError("worker crashed")
        return SalaryBatchArtifact(spec.batch_id, Verdict.SUCCESS, len(rows), 1000.0)

    sup = SettlementSupervisor(dispatch=flaky)
    result = asyncio.run(sup.run(ROSTER))
    # The crash did not blow up the run; globex was isolated to human review.
    assert "batch::globex" in result["human_review"]
    assert "batch::acme" in result["auto_approved"]
    assert result["employee_count"] == 4


# ----- Synthesize: supervisor reads artifacts only, and gates -----

def test_synthesize_separates_clean_from_human():
    async def mixed(spec, rows):
        # initech comes back over the amount threshold -> must escalate
        total = 200_000.0 if spec.batch_id == "batch::initech" else 1000.0
        return SalaryBatchArtifact(spec.batch_id, Verdict.SUCCESS, len(rows), total, confidence=1.0)

    sup = SettlementSupervisor(dispatch=mixed, boundary=SafetyBoundary(amount_threshold=100_000))
    result = asyncio.run(sup.run(ROSTER))
    assert "batch::initech" in result["human_review"]
    assert set(result["auto_approved"]) == {"batch::acme", "batch::globex"}
    # total counts only auto-approved batches (initech held for review)
    assert result["total"] == 2000.0


def test_run_dispatches_every_batch_in_parallel():
    seen: list[str] = []

    async def track(spec, rows):
        seen.append(spec.batch_id)
        await asyncio.sleep(0)  # yield, proving concurrent scheduling
        return SalaryBatchArtifact(spec.batch_id, Verdict.SUCCESS, len(rows), 1000.0)

    sup = SettlementSupervisor(dispatch=track)
    asyncio.run(sup.run(ROSTER))
    assert sorted(seen) == ["batch::acme", "batch::globex", "batch::initech"]
