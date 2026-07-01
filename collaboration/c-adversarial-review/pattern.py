"""Adversarial Review pattern.

Minimal, framework-agnostic reference implementation of the pattern described in
column lecture 07-04. A second agent is added to a high-stakes output for one
purpose only: to attack it. Not to help write it, not to co-sign it — to find the
flaw a confident author would ship.

Scenario: an AI travel assistant assembles a multi-leg itinerary — flight, hotel,
airport taxi — and is about to confirm and pay. Before it does, an INDEPENDENT
reviewer audits the plan for conflicts a confident planner misses: the taxi ETA
lands after boarding closes, the hotel check-in is a day off, the layover is too
short to clear customs. The failure this pattern exists to prevent is a reviewer
that rubber-stamps — an author grading its own homework.

Like the sibling patterns this file is small (~150 lines) and is not a framework.
A pluggable ``Reviewer`` (and ``Reviser``) is the seam LangGraph, the Claude Agent
SDK, or a mock plugs into. The two tutorials wire real agents into the same loop.

Two named tools from the lecture:

* **The Three Isolations of Independence** (独立性三隔离) — a reviewer is only
  independent if three things are isolated from the author: *context* (it sees the
  plan, not the planner's private reasoning), *objective* (its job is to find
  blockers, not to approve), and *identity* (a different agent, not the same one
  grading itself). Encoded in :class:`IndependenceGuard` and the ``Reviewer`` seam.
* **Objections, never endorsement** (只提异议不背书) — the reviewer returns a list
  of :class:`Objection`. There is no "looks good" it can return. Approval is
  decided by a deterministic :class:`ReviewGate` (zero open blockers), never by the
  critic's say-so. A critic that *can* approve will eventually approve to be
  agreeable.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Awaitable, Callable


class Severity(str, Enum):
    """How bad an objection is. Only BLOCKER can hold a confirmation."""

    BLOCKER = "blocker"      # ship this and the trip breaks — must be resolved
    WARNING = "warning"      # risky but not fatal — surfaced, does not hold
    INFO = "info"            # note for the traveler


class Outcome(str, Enum):
    CONFIRMED = "confirmed"          # converged clean → auto-confirm
    HELD_FOR_HUMAN = "held_for_human"  # blockers survived max rounds → escalate
    NO_REVIEWER = "no_reviewer"      # independence violated → refuse to run


@dataclass
class Itinerary:
    """The artifact under review. Deliberately plain data — the reviewer must
    judge the plan, not be told how it was reached."""

    legs: list[dict] = field(default_factory=list)   # [{type,start,end,price,...}]
    total_price: float = 0.0
    revision: int = 0


@dataclass(frozen=True)
class Objection:
    """The ONLY thing a reviewer returns. Not a score, not an approval — a fault."""

    severity: Severity
    leg_ref: str
    issue: str


# The seam. A Reviewer is CONTEXT-ISOLATED by its signature: it receives only the
# Itinerary, never the planner's reasoning. It returns objections, never approval.
Reviewer = Callable[[Itinerary], Awaitable[list[Objection]]]
# A Reviser tries to fix the blockers. It is a SEPARATE callable (identity isolation).
Reviser = Callable[[Itinerary, list[Objection]], Awaitable[Itinerary]]


class IndependenceGuard:
    """The Three Isolations, made checkable. Two of the three are structural and
    can be asserted before the loop even runs; the third (objective) is enforced
    by the ``Reviewer`` contract — it may only return objections."""

    @staticmethod
    def check(reviewer: Reviewer, reviser: Reviser | None) -> bool:
        # Identity isolation: the reviewer must not be the very object that wrote
        # or revises the plan. A self-review is not a review.
        if reviser is not None and reviewer is reviser:
            return False
        # Context isolation is structural: Reviewer's signature takes only an
        # Itinerary, so a planner's private trace cannot reach it by construction.
        return callable(reviewer)


class ReviewGate:
    """Deterministic admission. Approval is a property of the objections, never a
    thing the critic can grant. Coded here, never left to a prompt."""

    def open_blockers(self, objections: list[Objection]) -> list[Objection]:
        return [o for o in objections if o.severity is Severity.BLOCKER]

    def may_confirm(self, objections: list[Objection]) -> bool:
        return not self.open_blockers(objections)


class AdversarialReview:
    """Generate → review → revise → review … until the reviewer raises no blocker
    or the round budget runs out. The loop is the topology (collaborate × loop);
    the gate is what makes the reviewer's independence matter."""

    def __init__(
        self,
        reviewer: Reviewer,
        reviser: Reviser | None = None,
        gate: ReviewGate | None = None,
        *,
        max_rounds: int = 3,
    ):
        self.reviewer = reviewer
        self.reviser = reviser
        self.gate = gate or ReviewGate()
        self.max_rounds = max_rounds

    async def run(self, plan: Itinerary) -> dict:
        if not IndependenceGuard.check(self.reviewer, self.reviser):
            # Refuse to "review" if the critic isn't independent. A rubber stamp
            # is worse than no stamp, because it manufactures false confidence.
            return {"outcome": Outcome.NO_REVIEWER, "plan": plan, "objections": []}

        history: list[dict] = []
        objections: list[Objection] = []
        for _ in range(self.max_rounds):
            objections = await self.reviewer(plan)          # attack the current plan
            blockers = self.gate.open_blockers(objections)
            history.append({"revision": plan.revision, "objections": len(objections),
                            "blockers": len(blockers)})
            if not blockers:
                return {"outcome": Outcome.CONFIRMED, "plan": plan,
                        "objections": objections, "rounds": history}
            if self.reviser is None:
                break                                        # nothing can fix it here
            plan = await self.reviser(plan, blockers)        # send blockers back
            plan.revision += 1

        # Blockers survived the budget → a human decides. Never auto-confirm.
        return {"outcome": Outcome.HELD_FOR_HUMAN, "plan": plan,
                "objections": objections, "rounds": history}
