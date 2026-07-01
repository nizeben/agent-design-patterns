"""Fan-out-Gather pattern.

Minimal, framework-agnostic reference implementation of the pattern described in
column lecture 07-03. Several agents work on the *same* task in parallel, then a
reconciler merges their results into one trustworthy answer.

The trap this pattern exists to avoid: fan-out is the easy half — ``asyncio``
does it in one line — so people spend all their design there and then write the
gather as a single ``concatenate``. The result is an unreadable report where the
same finding appears three times. This file therefore makes the *gather* the
center of gravity; the fan-out is deliberately boring.

Like the sibling patterns this file is small (~150 lines) and is not a framework.
A pluggable ``FanoutFn`` is the seam where LangGraph, the Claude Agent SDK, or a
mock plugs in. The two tutorials (``langgraph/`` and ``claude-agent-sdk/``) plug
real agents into the same shape; the reconciler under test never changes.

Two named tools from the lecture:

* **The Aggregator's Four Questions** (聚合器四问) — answered *before* any
  fan-out: (1) additive or competing results? (2) how are conflicts
  adjudicated? (3) how is overlap de-duplicated? (4) who reviews the seams?
  Answering them turns gather from "one concatenate" into a designed pipeline.
  Encoded as :class:`AggregatorPolicy`.
* **Divergence-to-Root-Cause, three layers** (分歧定位三层) — when each worker is
  bound to an *attributable* boundary (one data source), the workers'
  divergence stops being noise and becomes a locator: agree -> not here;
  divergence that clusters two ways -> the gap *is* the root cause; divergence
  that does not -> human review. Encoded in :meth:`Reconciler.reconcile`.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from enum import Enum
from typing import Awaitable, Callable, Optional


class Strategy(str, Enum):
    """Aggregator's Four Questions · Q1. Decides the whole gather family."""

    ADDITIVE = "additive"        # each worker sees one facet; results sum into a whole
    COMPETING = "competing"      # workers answer the SAME question; results must reconcile


class Layer(str, Enum):
    """Divergence-to-Root-Cause · the three layers a line item can land in."""

    AGREE = "agree"              # sources concur -> the gap is not here
    ATTRIBUTABLE = "attributable"  # divergence clusters two ways -> gap located to a source
    UNEXPLAINED = "unexplained"  # divergence does not cluster -> human review


@dataclass
class SourceResult:
    """What one worker returns. In Fan-out-Gather every worker is bound to an
    *attributable* boundary (one data source / lens), which is what lets their
    divergence point at a root cause instead of just flagging uncertainty."""

    source: str                                  # "payroll" / "social_security" / "gl" ...
    line_items: dict[str, float] = field(default_factory=dict)  # item -> amount
    confidence: float = 1.0
    ok: bool = True                              # False = this worker failed, isolated out


# fanout(source_name, rows) -> SourceResult. The seam a real framework fills.
# Each worker MUST run in an isolated context and return only this artifact.
FanoutFn = Callable[[str, list[dict]], Awaitable[SourceResult]]


@dataclass(frozen=True)
class AggregatorPolicy:
    """The Aggregator's Four Questions, made legible. The order of the fields is
    the order you answer them, and the order you build the gather pipeline."""

    strategy: Strategy = Strategy.COMPETING       # Q1 additive or competing
    conflict_rule: str = "cluster-two-ways"       # Q2 how conflicts are adjudicated
    dedup_key: Optional[Callable[[str], str]] = None  # Q3 collapse aliased items
    seam_reviewer: Optional[Callable[[dict], list[str]]] = None  # Q4 who reads the seams


@dataclass
class LineItemVerdict:
    """One reconciled line item: which layer it fell in and the evidence."""

    item: str
    layer: Layer
    by_source: dict[str, float]
    gap: float = 0.0


class Reconciler:
    """The gather. This is the soul of the pattern — not the fan-out.

    For COMPETING results it does not concatenate; it compares the same line item
    across sources and sorts it into the three divergence layers. For ADDITIVE
    results it merges facets into a whole, collapsing aliased items via the
    policy's ``dedup_key`` (Q3).
    """

    def __init__(self, policy: AggregatorPolicy | None = None, *, tol: float = 1.0):
        self.policy = policy or AggregatorPolicy()
        self.tol = tol

    def reconcile(self, results: list[SourceResult]) -> dict:
        if self.policy.strategy is Strategy.ADDITIVE:
            report = self._merge_additive(results)
        else:
            report = self._reconcile_competing(results)
        # Q4 — a seam reviewer reads the assembled report for cross-worker
        # problems no single worker could see. It runs AFTER the merge, on the
        # whole, never on a slice.
        if self.policy.seam_reviewer:
            report["seam_findings"] = self.policy.seam_reviewer(report)
        return report

    # ----- COMPETING: the divergence-location specialisation (the star) --------

    def _reconcile_competing(self, results: list[SourceResult]) -> dict:
        items = {k for r in results for k in r.line_items}
        agreed, root_causes, to_human = [], [], []
        for item in sorted(items):
            pairs = [(r.source, r.line_items[item]) for r in results if item in r.line_items]
            if len(pairs) < 2:
                # Only one source knows this item — nothing to reconcile against.
                to_human.append({"item": item, "by_source": dict(pairs),
                                 "reason": "single-source"})
                continue
            clusters = _cluster(pairs, self.tol)
            by_source = {s: v for s, v in pairs}
            if len(clusters) == 1:
                agreed.append(item)                                   # Layer 1
            elif len(clusters) == 2:                                  # Layer 2
                lo, hi = clusters[0], clusters[-1]
                root_causes.append({
                    "item": item, "by_source": by_source,
                    "gap": round(hi[-1][1] - lo[0][1], 2),
                    "low_sources": [s for s, _ in lo],
                    "high_sources": [s for s, _ in hi],
                })
            else:                                                     # Layer 3
                to_human.append({"item": item, "by_source": by_source,
                                 "reason": "unexplained-divergence"})
        return {"agreed_items": agreed, "root_causes": root_causes, "to_human": to_human}

    # ----- ADDITIVE: merge facets into a whole, de-duplicating (Q3) ------------

    def _merge_additive(self, results: list[SourceResult]) -> dict:
        key = self.policy.dedup_key or (lambda s: s)
        merged: dict[str, float] = {}
        collapsed = 0
        for r in results:
            for item, amount in r.line_items.items():
                canon = key(item)
                if canon in merged and canon != item:
                    collapsed += 1
                merged[canon] = merged.get(canon, 0.0) + amount
        return {"merged": merged, "total": round(sum(merged.values()), 2),
                "deduped": collapsed}


class FanOutGather:
    """Dispatch the same task to every source in parallel, isolate failures, then
    hand the survivors to the reconciler. The fan-out is intentionally the small
    part; the reconciler is where the work is."""

    def __init__(
        self,
        sources: dict[str, FanoutFn],
        reconciler: Reconciler | None = None,
        *,
        max_concurrent: int = 5,        # caps parallelism, and so caps the token multiplier
        worker_timeout: float = 90.0,
        min_success_rate: float = 0.95,  # compliance floor: too many dead sources -> no verdict
    ):
        self.sources = sources
        self.reconciler = reconciler or Reconciler()
        self._sem = asyncio.Semaphore(max_concurrent)
        self.worker_timeout = worker_timeout
        self.min_success_rate = min_success_rate

    async def _run_one(self, name: str, fn: FanoutFn, rows: list[dict]) -> SourceResult:
        async with self._sem:
            try:
                return await asyncio.wait_for(fn(name, rows), self.worker_timeout)
            except Exception:
                # Straggler / partial-failure isolation: one dead source must not
                # take down the batch. Degrade to ok=False and let the floor decide.
                return SourceResult(source=name, ok=False)

    async def run(self, rows: list[dict]) -> dict:
        results = await asyncio.gather(
            *(self._run_one(n, f, rows) for n, f in self.sources.items())
        )
        ok = [r for r in results if r.ok]
        if len(ok) / len(results) < self.min_success_rate:
            return {"status": "insufficient_sources", "got": len(ok), "total": len(results)}
        report = self.reconciler.reconcile(ok)
        report["status"] = "reconciled"
        return report


def _cluster(pairs: list[tuple[str, float]], tol: float) -> list[list[tuple[str, float]]]:
    """Sort values and split them where the gap to the previous value exceeds
    ``tol``. One cluster = everyone agrees; two clusters = an attributable split
    (some sources high, some low); three or more = it does not cluster."""
    ordered = sorted(pairs, key=lambda p: p[1])
    clusters: list[list[tuple[str, float]]] = [[ordered[0]]]
    for src, val in ordered[1:]:
        if val - clusters[-1][-1][1] <= tol:
            clusters[-1].append((src, val))
        else:
            clusters.append([(src, val)])
    return clusters
