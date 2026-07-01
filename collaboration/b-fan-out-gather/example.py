"""Runnable example: the June ledger that would not reconcile.

    python collaboration/b-fan-out-gather/example.py

No API key needed. Four mock workers stand in for real agents, each bound to one
data source (payroll / social-security / attendance / GL). They all compute the
*same* June total, and the fan-out sends the same roster to all four in
parallel. The gather does NOT concatenate — it compares each line item across
the four sources and sorts the divergence into three layers, so the gap locates
itself to a subsystem instead of being guessed at.

Swap the mock ``FanoutFn``s for LangGraph nodes or Claude Agent SDK subagents
(see the two tutorials) and the reconciler under it never changes.
"""
from __future__ import annotations

import asyncio

from pattern import FanOutGather, Reconciler, SourceResult

ROSTER = [{"id": f"e{i}"} for i in range(800)]

# Each source's view of the same June total. payroll & GL agree on everything;
# social_security is 12万 low on 社保代扣 (base not synced this month); attendance
# is 15万 high on 加班费 (overtime rule changed, payroll never got it). Those two
# gaps ARE the missing 缺口 — the divergence points straight at the two systems.
LEDGER = {
    "payroll":         {"基本工资": 3_100_000.0, "社保代扣": 120_000.0, "加班费": 100_000.0},
    "gl":              {"基本工资": 3_100_000.0, "社保代扣": 120_000.0, "加班费": 100_000.0},
    "social_security": {"基本工资": 3_100_000.0, "社保代扣": 108_000.0, "加班费": 100_000.0},
    "attendance":      {"基本工资": 3_100_000.0, "社保代扣": 120_000.0, "加班费": 250_000.0},
}


def build_source(name: str, items: dict):
    async def fn(source: str, rows: list[dict]) -> SourceResult:
        await asyncio.sleep(0.01)   # pretend the model is thinking
        return SourceResult(source=name, line_items=items)
    return fn


async def main() -> None:
    sources = {name: build_source(name, items) for name, items in LEDGER.items()}
    fog = FanOutGather(sources, Reconciler(tol=1.0), max_concurrent=5)

    print(f"Fan-out: {len(sources)} data sources · same June total · {len(ROSTER)} employees\n")
    result = await fog.run(ROSTER)

    print(f"status: {result['status']}\n")
    print(f"Agreed (gap is NOT here):   {result['agreed_items']}")
    print("\nLocated root causes (divergence -> subsystem):")
    for rc in result["root_causes"]:
        lo, hi = ", ".join(rc["low_sources"]), ", ".join(rc["high_sources"])
        print(f"  · {rc['item']}: gap {rc['gap']:,.0f}  "
              f"[{lo} low  vs  {hi} high]")
    print(f"\nUnexplained -> human review: {[x['item'] for x in result['to_human']]}")
    print("\nNo agent guessed where the money went. Four sources computed the same "
          "total; the two line items they disagreed on ARE the gap.")


if __name__ == "__main__":
    asyncio.run(main())
