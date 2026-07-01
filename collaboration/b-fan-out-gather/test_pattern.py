"""Tests for the Fan-out-Gather pattern.

Run: pytest collaboration/b-fan-out-gather/test_pattern.py -v

No API key needed — a mock ``FanoutFn`` stands in for a real worker agent, so
every test is deterministic. The tutorials swap the mock for LangGraph / the
Claude Agent SDK; the reconciler under test never changes.
"""
from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
sys.modules.pop("pattern", None)   # ensure we pick up THIS folder's pattern.py

from pattern import (   # noqa: E402
    AggregatorPolicy,
    FanOutGather,
    Layer,
    Reconciler,
    SourceResult,
    Strategy,
)

ROWS = [{"id": "e1"}, {"id": "e2"}]


def _source(name: str, items: dict, ok: bool = True):
    async def fn(source: str, rows: list[dict]) -> SourceResult:
        await asyncio.sleep(0)   # yield, proving concurrent scheduling
        return SourceResult(source=name, line_items=items, ok=ok)
    return fn


# ----- Fan-out: parallel dispatch + failure isolation + the compliance floor --

def test_run_dispatches_every_source_in_parallel():
    seen: list[str] = []

    def track(name):
        async def fn(source, rows):
            seen.append(name)
            await asyncio.sleep(0)
            return SourceResult(source=name, line_items={"x": 1.0})
        return fn

    fog = FanOutGather({"a": track("a"), "b": track("b"), "c": track("c")})
    asyncio.run(fog.run(ROWS))
    assert sorted(seen) == ["a", "b", "c"]


def test_worker_exception_is_isolated_not_fatal():
    async def boom(source, rows):
        raise RuntimeError("source crashed")

    fog = FanOutGather(
        {"a": _source("a", {"x": 10.0}), "b": _source("b", {"x": 10.0}),
         "c": _source("c", {"x": 10.0}), "dead": boom},
        min_success_rate=0.5,
    )
    result = asyncio.run(fog.run(ROWS))
    # One crash did not blow up the run; it was isolated and the rest reconciled.
    assert result["status"] == "reconciled"


def test_min_success_floor_refuses_a_verdict():
    async def boom(source, rows):
        raise RuntimeError("down")

    fog = FanOutGather(
        {"a": _source("a", {"x": 10.0}), "dead1": boom, "dead2": boom, "dead3": boom},
        min_success_rate=0.95,
    )
    result = asyncio.run(fog.run(ROWS))
    assert result["status"] == "insufficient_sources"
    assert result["got"] == 1


# ----- Gather · COMPETING: the three divergence layers ------------------------

def test_agreement_lands_in_layer_one():
    r = Reconciler(tol=1.0)
    results = [
        SourceResult("payroll", {"社保代扣": 120_000.0}),
        SourceResult("gl", {"社保代扣": 120_000.5}),
        SourceResult("ss", {"社保代扣": 120_000.0}),
    ]
    report = r.reconcile(results)
    assert "社保代扣" in report["agreed_items"]
    assert not report["root_causes"]


def test_two_sided_divergence_is_attributable_to_a_source():
    r = Reconciler(tol=1.0)
    # payroll & gl agree; social_security is 12万 low -> the gap points at ss.
    results = [
        SourceResult("payroll", {"社保代扣": 120_000.0}),
        SourceResult("gl", {"社保代扣": 120_000.0}),
        SourceResult("social_security", {"社保代扣": 108_000.0}),
    ]
    report = r.reconcile(results)
    assert not report["agreed_items"]
    assert len(report["root_causes"]) == 1
    rc = report["root_causes"][0]
    assert rc["item"] == "社保代扣"
    assert rc["gap"] == 12_000.0
    assert rc["low_sources"] == ["social_security"]
    assert set(rc["high_sources"]) == {"payroll", "gl"}


def test_three_way_scatter_goes_to_human():
    r = Reconciler(tol=1.0)
    results = [
        SourceResult("a", {"加班费": 100_000.0}),
        SourceResult("b", {"加班费": 250_000.0}),
        SourceResult("c", {"加班费": 400_000.0}),
    ]
    report = r.reconcile(results)
    assert not report["agreed_items"]
    assert not report["root_causes"]
    assert report["to_human"][0]["item"] == "加班费"
    assert report["to_human"][0]["reason"] == "unexplained-divergence"


def test_single_source_item_cannot_be_reconciled():
    r = Reconciler(tol=1.0)
    results = [
        SourceResult("payroll", {"孤项": 5000.0}),
        SourceResult("gl", {"社保代扣": 1.0}),
        SourceResult("ss", {"社保代扣": 1.0}),
    ]
    report = r.reconcile(results)
    lonely = [x for x in report["to_human"] if x["item"] == "孤项"]
    assert lonely and lonely[0]["reason"] == "single-source"


# ----- Gather · ADDITIVE: merge facets, de-duplicate aliases (Q3) -------------

def test_additive_sums_distinct_facets():
    r = Reconciler(AggregatorPolicy(strategy=Strategy.ADDITIVE))
    results = [
        SourceResult("a", {"base": 100.0}),
        SourceResult("b", {"bonus": 40.0}),
    ]
    report = r.reconcile(results)
    assert report["total"] == 140.0


def test_additive_dedup_collapses_aliased_items():
    # Two workers name the same risk differently; dedup_key canonicalises them.
    r = Reconciler(AggregatorPolicy(
        strategy=Strategy.ADDITIVE,
        dedup_key=lambda s: "earnout" if s in ("对赌条款增加", "earnout扩大") else s,
    ))
    results = [
        SourceResult("a", {"对赌条款增加": 1.0}),
        SourceResult("b", {"earnout扩大": 1.0}),
    ]
    report = r.reconcile(results)
    assert report["deduped"] == 1
    assert report["merged"]["earnout"] == 2.0


# ----- Gather · Q4: the seam reviewer reads the whole, not a slice ------------

def test_seam_reviewer_surfaces_cross_worker_findings():
    def reviewer(report: dict) -> list[str]:
        # A finding only visible across workers: two root causes on linked systems.
        if len(report.get("root_causes", [])) >= 2:
            return ["加班规则改动同时冲击考勤与工资系统 — 需一并回归"]
        return []

    r = Reconciler(AggregatorPolicy(seam_reviewer=reviewer), tol=1.0)
    results = [
        SourceResult("payroll", {"社保代扣": 120_000.0, "加班费": 100_000.0}),
        SourceResult("gl", {"社保代扣": 120_000.0, "加班费": 100_000.0}),
        SourceResult("ss", {"社保代扣": 108_000.0, "加班费": 100_000.0}),
        SourceResult("attendance", {"社保代扣": 120_000.0, "加班费": 250_000.0}),
    ]
    report = r.reconcile(results)
    assert report["seam_findings"]


def test_end_to_end_ledger_reconciliation_locates_the_gap():
    # Four data sources, same June total; two attributable gaps should surface.
    sources = {
        "payroll": _source("payroll", {"社保代扣": 120_000.0, "加班费": 100_000.0}),
        "gl": _source("gl", {"社保代扣": 120_000.0, "加班费": 100_000.0}),
        "social_security": _source("social_security",
                                   {"社保代扣": 108_000.0, "加班费": 100_000.0}),
        "attendance": _source("attendance", {"社保代扣": 120_000.0, "加班费": 250_000.0}),
    }
    fog = FanOutGather(sources, Reconciler(tol=1.0))
    result = asyncio.run(fog.run(ROWS))
    assert result["status"] == "reconciled"
    located = {rc["item"] for rc in result["root_causes"]}
    assert located == {"社保代扣", "加班费"}
