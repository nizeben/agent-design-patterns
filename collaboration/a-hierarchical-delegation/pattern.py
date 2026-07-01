"""Hierarchical Delegation pattern.

Minimal, framework-agnostic reference implementation of the supervisor-worker
pattern described in column lecture 07-02. A supervisor agent breaks a job too
big for one agent into batches, dispatches each to a worker in an isolated
context, and only ever sees the workers' structured artifacts — never their raw
work. The model is the same as a manager who delegates and reviews but never
does the line work themselves.

This file is intentionally small (~130 lines). It is not a framework. It is the
smallest amount of code that captures the pattern, with a pluggable ``dispatch``
callable so you can drop in LangGraph, the Claude Agent SDK, or a mock. The two
tutorials (``langgraph/`` and ``claude-agent-sdk/``) plug real agents into the
same shape.

The pattern encodes two named tools from the lecture:

* **The Delegation Kit** (三件套) — before dispatching, every worker is pinned by
  a ``WorkerSpec`` (Spec), runs in isolation and returns only an artifact
  (Budget), and is admitted only through ``SafetyBoundary`` (Gate).
* **The Manager-Never-Executes rule** (主管不下场) — the supervisor only
  decomposes / dispatches / synthesizes / gates. It reads artifacts, never a
  worker's intermediate trace, and workers never talk to each other.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from enum import Enum
from typing import Awaitable, Callable


class Verdict(str, Enum):
    """A worker's self-reported outcome. PARTIAL/FAILURE never auto-approve."""

    SUCCESS = "success"
    PARTIAL = "partial"      # produced results but flagged rows for review
    FAILURE = "failure"      # could not complete; supervisor decides retry/degrade


@dataclass(frozen=True)
class WorkerSpec:
    """Delegation Kit · Spec (任务规约). Four things pinned before any dispatch:
    objective, output shape, tool whitelist, and boundary (what is NOT its job).
    """

    batch_id: str
    objective: str
    output_schema: str = "SalaryBatchArtifact"
    allowed_tools: tuple[str, ...] = ()
    boundary: str = ""       # e.g. "only this batch; do not touch other clients"


@dataclass
class SalaryBatchArtifact:
    """Delegation Kit · Budget, product side (上下文预算). The ONLY thing a worker
    returns. Its raw computation stays in its isolated context; the supervisor
    sees this compact, schema-shaped result and nothing else.
    """

    batch_id: str
    verdict: Verdict
    employee_count: int
    total_amount: float
    anomalies: list[str] = field(default_factory=list)      # e.g. "commission 3x dept mean"
    needs_review: list[str] = field(default_factory=list)   # employee ids to escalate
    confidence: float = 1.0
    batch_hash: str = ""     # tamper check at reconciliation time


# dispatch(spec, rows) -> artifact. The seam where a real framework plugs in.
# The worker MUST start from a blank context and return only the artifact.
Dispatch = Callable[[WorkerSpec, list[dict]], Awaitable[SalaryBatchArtifact]]


class SafetyBoundary:
    """Delegation Kit · Gate (验收闸门). A deterministic admission rule, coded in
    the program — never left to a prompt. Anything risky is routed to a human.
    """

    def __init__(self, amount_threshold: float = 100_000, min_confidence: float = 0.85):
        self.amount_threshold = amount_threshold
        self.min_confidence = min_confidence

    def must_escalate(self, art: SalaryBatchArtifact) -> bool:
        return (
            art.total_amount > self.amount_threshold
            or art.confidence < self.min_confidence
            or bool(art.needs_review)
            or art.verdict is not Verdict.SUCCESS
        )


class SettlementSupervisor:
    """The supervisor. It only decomposes / dispatches / synthesizes / gates and
    never computes a single employee's pay itself (Manager-Never-Executes).
    """

    def __init__(
        self,
        dispatch: Dispatch,
        boundary: SafetyBoundary | None = None,
        *,
        max_concurrent: int = 5,     # caps parallelism, and so caps token multiplier
        worker_timeout: float = 120.0,
    ):
        self.dispatch = dispatch
        self.boundary = boundary or SafetyBoundary()
        self._sem = asyncio.Semaphore(max_concurrent)
        self.worker_timeout = worker_timeout

    def decompose(self, roster: list[dict]) -> list[tuple[WorkerSpec, list[dict]]]:
        """Split the roster into independent per-client batches. Each spec pins a
        boundary so workers never overlap (the #1 source of delegation failure)."""
        by_client: dict[str, list[dict]] = {}
        for row in roster:
            by_client.setdefault(row["client"], []).append(row)
        batches = []
        for client, rows in by_client.items():
            spec = WorkerSpec(
                batch_id=f"batch::{client}",
                objective=f"Compute payroll for {client} only, per the given rules.",
                allowed_tools=("read_roster", "calc_salary"),   # whitelist; no DB writes
                boundary="Only this batch. Do not read other clients or write the HR DB.",
            )
            batches.append((spec, rows))
        return batches

    async def _run_one(self, spec: WorkerSpec, rows: list[dict]) -> SalaryBatchArtifact:
        async with self._sem:
            try:
                return await asyncio.wait_for(self.dispatch(spec, rows), self.worker_timeout)
            except Exception:
                # Worker failure isolation: never let an exception hit the
                # supervisor's reasoning loop. Degrade to a FAILURE artifact so
                # one dead batch costs only that batch.
                return SalaryBatchArtifact(
                    batch_id=spec.batch_id, verdict=Verdict.FAILURE,
                    employee_count=len(rows), total_amount=0.0,
                    needs_review=[r["id"] for r in rows], confidence=0.0,
                )

    async def run(self, roster: list[dict]) -> dict:
        batches = self.decompose(roster)
        # Fan out in parallel; the supervisor only ever awaits artifacts.
        artifacts = await asyncio.gather(*(self._run_one(s, r) for s, r in batches))
        return self.synthesize(artifacts)

    def synthesize(self, artifacts: list[SalaryBatchArtifact]) -> dict:
        """Read artifacts (never raw worker traces) and gate. High-amount, low-
        confidence, or flagged batches go to a human; the rest auto-approve."""
        to_human = [a for a in artifacts if self.boundary.must_escalate(a)]
        clean = [a for a in artifacts if not self.boundary.must_escalate(a)]
        return {
            "total": round(sum(a.total_amount for a in clean), 2),
            "employee_count": sum(a.employee_count for a in artifacts),
            "auto_approved": [a.batch_id for a in clean],
            "human_review": [a.batch_id for a in to_human],   # queued for HR / finance
        }
