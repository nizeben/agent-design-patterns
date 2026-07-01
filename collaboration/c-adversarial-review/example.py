"""Runnable example: an AI travel assistant, one blocker away from a broken trip.

    python collaboration/c-adversarial-review/example.py

No API key needed. A mock planner hands over an itinerary that looks fine — flight
booked, hotel booked, airport taxi booked — but the taxi's ETA lands after
boarding closes. A mock independent reviewer catches exactly that, the reviser
books an earlier taxi, and the second review comes back clean, so the gate
confirms. Swap the mocks for a LangGraph loop or Claude Agent SDK subagents (see
the tutorials) and the review loop under it never changes.
"""
from __future__ import annotations

import asyncio

from pattern import AdversarialReview, Itinerary, Objection, Severity

# The plan the travel assistant produced. The taxi picks up too late to make
# boarding — a mistake a confident planner ships, and a reviewer must catch.
INITIAL = Itinerary(
    legs=[
        {"type": "flight", "code": "MU5102", "depart": "20:00", "boarding": "19:30"},
        {"type": "taxi", "provider": "didi", "pickup": "19:10", "airport_eta": "19:40"},
        {"type": "hotel", "provider": "ctrip", "checkin": "2026-07-02", "nights": 2},
    ],
    total_price=3180.0,
)


async def reviewer(plan: Itinerary) -> list[Objection]:
    """Independent critic. Sees ONLY the plan (context isolation), and returns
    objections — never an approval. Here it checks the taxi against boarding."""
    await asyncio.sleep(0.01)
    objs: list[Objection] = []
    taxi = next((l for l in plan.legs if l["type"] == "taxi"), None)
    flight = next((l for l in plan.legs if l["type"] == "flight"), None)
    if taxi and flight and taxi["airport_eta"] > flight["boarding"]:
        objs.append(Objection(
            Severity.BLOCKER, "taxi",
            f"taxi arrives {taxi['airport_eta']} but boarding closes {flight['boarding']}",
        ))
    return objs


async def reviser(plan: Itinerary, blockers: list[Objection]) -> Itinerary:
    """Books an earlier taxi to clear the blocker. In production this is the
    planner agent, re-invoked with the objections in hand."""
    await asyncio.sleep(0.01)
    legs = []
    for leg in plan.legs:
        if leg["type"] == "taxi":
            leg = {**leg, "pickup": "18:30", "airport_eta": "19:00"}   # earlier
        legs.append(leg)
    return Itinerary(legs=legs, total_price=plan.total_price + 20.0)    # earlier ride costs a bit more


async def main() -> None:
    review = AdversarialReview(reviewer=reviewer, reviser=reviser, max_rounds=3)
    result = await review.run(INITIAL)

    print(f"Outcome: {result['outcome'].value}\n")
    for i, r in enumerate(result["rounds"], 1):
        print(f"  round {i}: revision {r['revision']} · "
              f"{r['objections']} objection(s), {r['blockers']} blocker(s)")
    taxi = next(l for l in result["plan"].legs if l["type"] == "taxi")
    print(f"\nFinal taxi ETA: {taxi['airport_eta']} (boarding 19:30) · "
          f"total ¥{result['plan'].total_price:,.0f}")
    print("\nThe planner never got to grade its own homework. An independent "
          "reviewer found the blocker; only after it raised no blocker did the "
          "gate confirm.")


if __name__ == "__main__":
    asyncio.run(main())
