# Adversarial Review — LangGraph Implementation

> "A review is a loop, and the loop needs a way out."

This notebook builds Adversarial Review as an **explicit LangGraph loop**: a review
node, a conditional edge that either sends the plan back for revision or exits, and
a **back-edge** from revise to review that is, literally, the loop.

The scenario is column lecture **07-04**: an AI travel assistant has assembled an
itinerary — flight, hotel, airport taxi — and is about to confirm and pay. An
**independent** reviewer audits it first. Here the reviewer catches a taxi whose ETA
lands after boarding closes; the loop sends it back, an earlier taxi is booked, and
the second review comes back clean.

The deterministic gate (`ReviewGate` from [`pattern.py`](../pattern.py)) decides
admission — a plan with an open blocker never confirms. The model finds faults; the
gate, not the model, grants passage.

## Two implementations, two philosophies

| | `langgraph/` (this notebook) | `claude-agent-sdk/` |
|---|---|---|
| **The loop** | An explicit back-edge: `revise → review`. Visible in LangGraph Studio. | A Python `for` loop that re-spawns the critic subagent each round. |
| **Independence** | You isolate: the review node reads only the plan. | Built in — the critic subagent runs in a fresh conversation, sees only the plan. |
| **Gate** | `route` reuses `ReviewGate`. | Python reuses `ReviewGate`. |

Same pattern, same `pattern.py` gate, two ways to wire the loop.

## Setup

```python
from __future__ import annotations

import os
import sys
from typing import TypedDict

sys.path.insert(0, os.path.abspath(os.path.join(os.getcwd(), "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.getcwd(), "../../..")))

from langgraph.graph import START, END, StateGraph

from pattern import Objection, ReviewGate, Severity   # the deterministic gate + types

print("Imports ready")
```

    Imports ready

## Step 1 — State: the plan, the objections, the round counter

The round counter is what makes the loop safe. Without it, a reviewer that keeps
finding new faults would loop forever. `MAX_ROUNDS` is the way out.

```python
GATE = ReviewGate()
MAX_ROUNDS = 3


class ReviewState(TypedDict):
    plan: dict
    objections: list
    round: int

print("State ready — note the round counter, the loop's safety valve")
```

    State ready — note the round counter, the loop's safety valve

## Step 2 — the review node: an independent critic

The review node reads **only** `state["plan"]` — never how the plan was built. That
is context isolation, done structurally. It returns objections, never an approval.

```python
def make_review(reviewer):
    def review(state: ReviewState) -> dict:
        return {"objections": reviewer(state["plan"])}   # sees only the plan
    return review


def mock_reviewer(plan: dict) -> list:
    """Independent check with no model: does the taxi make boarding?"""
    if plan["taxi_eta"] > plan["boarding"]:
        return [Objection(Severity.BLOCKER, "taxi",
                          f"taxi arrives {plan['taxi_eta']}, boarding {plan['boarding']}").__dict__]
    return []

print("Review node ready")
```

    Review node ready

## Step 3 — the loop: route, revise, and the way out

`route` is the conditional edge. It reuses `ReviewGate` to ask "any open blocker?"
If yes and there is round budget left, go revise. Otherwise exit. `revise` fixes the
blocker and bumps the round counter.

```python
def route(state: ReviewState) -> str:
    blockers = [o for o in state["objections"] if o["severity"] == Severity.BLOCKER]
    return "revise" if blockers and state["round"] < MAX_ROUNDS else END


def revise(state: ReviewState) -> dict:
    plan = dict(state["plan"])
    plan["taxi_eta"] = "19:00"                      # book an earlier taxi
    return {"plan": plan, "round": state["round"] + 1}

print("Loop parts ready")
```

    Loop parts ready

## Step 4 — wire the graph (the back-edge is the loop)

`START → review → (route) → revise → review …`. The edge from `revise` back to
`review` is the loop. The conditional edge from `review` is the only way out.

```python
def build_graph(reviewer):
    g = StateGraph(ReviewState)
    g.add_node("review", make_review(reviewer))
    g.add_node("revise", revise)
    g.add_edge(START, "review")
    g.add_conditional_edges("review", route, ["revise", END])   # loop or exit
    g.add_edge("revise", "review")                              # back-edge = the loop
    return g.compile()

print("Graph builder ready")
```

    Graph builder ready

## Step 5 — run it (mock, no API key)

The initial plan has a taxi arriving 19:40, ten minutes after boarding closes at
19:30. The reviewer should catch it, the loop should revise once, and the second
review should come back clean.

```python
app = build_graph(mock_reviewer)
out = app.invoke({"plan": {"taxi_eta": "19:40", "boarding": "19:30"},
                  "objections": [], "round": 0})
print("final round:    ", out["round"])
print("final objections:", out["objections"])
print("final taxi_eta: ", out["plan"]["taxi_eta"])
```

    final round:     1
    final objections: []
    final taxi_eta:  19:00

The loop ran review → revise → review and converged: the blocker in round 0
was gone by round 1, so `route` sent it to `END`. No plan with an open blocker ever
reached the exit.

### Real run — a model-backed reviewer

Swap `mock_reviewer` for a reviewer that calls a model with structured output
(`model.with_structured_output(list[Objection])`). The loop, the gate, and the
back-edge do not change — only how objections are produced.

```python
# from model_config import get_model
# model = get_model()
# def model_reviewer(plan):
#     critic = model.with_structured_output(...)      # returns list[Objection]
#     return critic.invoke(REVIEW_PROMPT.format(plan=plan))
# app = build_graph(model_reviewer)
print("Swap mock_reviewer for a model-backed reviewer; the loop is unchanged.")
```

    Swap mock_reviewer for a model-backed reviewer; the loop is unchanged.

## What LangGraph gives you here

1. **The loop is a first-class edge.** `revise → review` makes "review again after a
   fix" a visible part of the graph, not a hidden `while`.
2. **A guaranteed way out.** The `round < MAX_ROUNDS` check in `route` is the
   difference between a review loop and an infinite one.
3. **The gate is reused, not reinvented.** `route` calls `ReviewGate`, the same
   deterministic rule the framework-agnostic `pattern.py` and its tests use.

## When this breaks

| Failure | In this graph |
|---|---|
| **Rubber stamp** | The review node reading the planner's trace, not just the plan. Keep it reading only `state["plan"]`. |
| **Infinite loop** | Dropping the `round < MAX_ROUNDS` guard in `route`. The counter is not optional. |
| **Severity laundering** | A revise step that downgrades a blocker to a warning to escape. Severity must have an objective basis. |

Next: the same pattern with the Claude Agent SDK, where the critic's independence
is built into the subagent primitive →
[`../claude-agent-sdk/tutorial.md`](../claude-agent-sdk/tutorial.md).
