"""Tests for the Adversarial Review pattern.

Run: pytest collaboration/c-adversarial-review/test_pattern.py -v

No API key needed — mock ``Reviewer`` / ``Reviser`` callables stand in for real
agents, so every test is deterministic. The tutorials swap the mocks for
LangGraph / the Claude Agent SDK; the review loop under test never changes.
"""
from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
sys.modules.pop("pattern", None)   # ensure we pick up THIS folder's pattern.py

from pattern import (   # noqa: E402
    AdversarialReview,
    IndependenceGuard,
    Itinerary,
    Objection,
    Outcome,
    ReviewGate,
    Reviewer,
    Severity,
)


def _plan(price: float = 3000.0) -> Itinerary:
    return Itinerary(legs=[{"type": "flight"}, {"type": "hotel"}], total_price=price)


def _reviewer(objs: list[Objection]) -> Reviewer:
    async def review(plan: Itinerary) -> list[Objection]:
        return list(objs)
    return review


BLOCKER = Objection(Severity.BLOCKER, "taxi", "ETA 19:40 > boarding 19:30")
WARNING = Objection(Severity.WARNING, "layover", "55 min layover is tight")


# ----- Independence: a self-review is not a review ----------------------------

def test_reviewer_that_is_the_reviser_is_rejected():
    async def both(*a):            # same object used as reviewer AND reviser
        return []
    review = AdversarialReview(reviewer=both, reviser=both)
    result = asyncio.run(review.run(_plan()))
    assert result["outcome"] is Outcome.NO_REVIEWER


def test_independence_guard_passes_distinct_agents():
    assert IndependenceGuard.check(_reviewer([]), None)


# ----- The gate: approval is a property of objections, not a critic's say-so --

def test_gate_open_blockers_filters_severity():
    g = ReviewGate()
    assert g.open_blockers([BLOCKER, WARNING]) == [BLOCKER]
    assert g.may_confirm([WARNING]) is True      # warnings never hold
    assert g.may_confirm([BLOCKER]) is False


# ----- The loop: converge, revise, or escalate --------------------------------

def test_clean_plan_confirms_first_round():
    review = AdversarialReview(reviewer=_reviewer([]))
    result = asyncio.run(review.run(_plan()))
    assert result["outcome"] is Outcome.CONFIRMED
    assert len(result["rounds"]) == 1


def test_warnings_alone_still_confirm():
    review = AdversarialReview(reviewer=_reviewer([WARNING]))
    result = asyncio.run(review.run(_plan()))
    assert result["outcome"] is Outcome.CONFIRMED     # a warning does not hold


def test_blocker_gets_revised_then_confirms():
    # Reviewer objects once; after a revision the plan comes back clean.
    calls = {"n": 0}

    async def reviewer(plan: Itinerary) -> list[Objection]:
        calls["n"] += 1
        return [BLOCKER] if plan.revision == 0 else []

    async def reviser(plan: Itinerary, blockers) -> Itinerary:
        return Itinerary(legs=plan.legs, total_price=plan.total_price)  # "fixed"

    review = AdversarialReview(reviewer=reviewer, reviser=reviser, max_rounds=3)
    result = asyncio.run(review.run(_plan()))
    assert result["outcome"] is Outcome.CONFIRMED
    assert result["plan"].revision == 1
    assert calls["n"] == 2


def test_unfixable_blocker_is_held_for_human():
    async def reviser(plan: Itinerary, blockers) -> Itinerary:
        return plan                                   # revision that never fixes it

    review = AdversarialReview(reviewer=_reviewer([BLOCKER]), reviser=reviser, max_rounds=3)
    result = asyncio.run(review.run(_plan()))
    assert result["outcome"] is Outcome.HELD_FOR_HUMAN
    assert len(result["rounds"]) == 3                 # used the whole budget


def test_blocker_without_reviser_escalates_immediately():
    review = AdversarialReview(reviewer=_reviewer([BLOCKER]))   # no reviser
    result = asyncio.run(review.run(_plan()))
    assert result["outcome"] is Outcome.HELD_FOR_HUMAN
    assert len(result["rounds"]) == 1                 # can't fix → stop after one look


async def _never_fix(plan: Itinerary, blockers) -> Itinerary:
    return plan                                       # a reviser that never resolves


def test_never_auto_confirms_with_an_open_blocker():
    # The core safety invariant: no path returns CONFIRMED while a blocker stands.
    no_reviser = AdversarialReview(reviewer=_reviewer([BLOCKER]))
    bad_reviser = AdversarialReview(reviewer=_reviewer([BLOCKER]),
                                    reviser=_never_fix, max_rounds=2)
    for review in (no_reviser, bad_reviser):
        result = asyncio.run(review.run(_plan()))
        assert result["outcome"] is not Outcome.CONFIRMED
