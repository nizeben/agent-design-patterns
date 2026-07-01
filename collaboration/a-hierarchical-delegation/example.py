"""Runnable example: the June payroll run for 800 employees, delegated.

    python collaboration/a-hierarchical-delegation/example.py

No API key needed. A mock worker stands in for a real worker agent so you can
see the whole shape run end to end: the supervisor splits the roster by client,
fans the batches out in parallel, reads back only compact artifacts, and gates
the risky ones to human review. Swap ``mock_worker`` for a LangGraph node or a
Claude Agent SDK subagent (see the two tutorials) and nothing else changes.
"""
from __future__ import annotations

import asyncio
import random

from pattern import (
    SafetyBoundary,
    SalaryBatchArtifact,
    SettlementSupervisor,
    Verdict,
    WorkerSpec,
)

CLIENTS = ["acme", "globex", "initech", "umbrella", "wayne", "stark"]


def build_roster(n: int = 800) -> list[dict]:
    rng = random.Random(42)  # deterministic
    return [
        {"id": f"e{i}", "client": rng.choice(CLIENTS), "base": rng.randint(5000, 20000)}
        for i in range(n)
    ]


async def mock_worker(spec: WorkerSpec, rows: list[dict]) -> SalaryBatchArtifact:
    """Stand-in for a real worker agent. In its own isolated context it would
    compute each person's pay, then return ONLY this artifact — never its
    per-employee working. Here we fake the numbers deterministically."""
    await asyncio.sleep(0.01)  # pretend the model is thinking
    total = float(sum(r["base"] * 1.3 for r in rows))  # base + ~30% loading
    # Flag a couple of batches to show the gate doing its job.
    anomalies, needs_review, confidence = [], [], 1.0
    if spec.batch_id.endswith("stark"):        # pretend this batch has a weird row
        anomalies = ["employee e_x commission 3x dept mean"]
        needs_review = [rows[0]["id"]] if rows else []
        confidence = 0.6
    return SalaryBatchArtifact(
        batch_id=spec.batch_id, verdict=Verdict.SUCCESS if not needs_review else Verdict.PARTIAL,
        employee_count=len(rows), total_amount=round(total, 2),
        anomalies=anomalies, needs_review=needs_review, confidence=confidence,
    )


async def main() -> None:
    roster = build_roster(800)
    supervisor = SettlementSupervisor(
        dispatch=mock_worker,
        boundary=SafetyBoundary(amount_threshold=5_000_000, min_confidence=0.85),
        max_concurrent=5,
    )

    print(f"Supervisor: 1 · Workers: {len(set(r['client'] for r in roster))} "
          f"· Employees: {len(roster)}\n")
    result = await supervisor.run(roster)

    print(f"Total (auto-approved):  {result['total']:,.2f}")
    print(f"Employees processed:    {result['employee_count']}")
    print(f"Auto-approved batches:  {result['auto_approved']}")
    print(f"Held for human review:  {result['human_review']}")
    print("\nThe supervisor never computed a single paycheck itself, and never "
          "saw a worker's raw working — only the artifacts it gated on.")


if __name__ == "__main__":
    asyncio.run(main())
