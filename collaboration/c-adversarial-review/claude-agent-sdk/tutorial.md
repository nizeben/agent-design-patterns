# Adversarial Review — Claude Agent SDK Implementation

> "The critic you don't build is the critic that can see your mistake."

This notebook builds Adversarial Review with the **Claude Agent SDK**. The reviewer
is a declarative `AgentDefinition` — an *independent* auditor. Two of the pattern's
three isolations come for free: the critic runs in its own fresh conversation
(context isolation) and is a different agent, optionally on a different model
(identity isolation). The third — objective isolation — is written into its prompt.

But admission stays in Python. The critic returns objections; a deterministic
`ReviewGate` decides whether the itinerary may be booked. A critic that *can* approve
will eventually approve to be agreeable, so it is never given that power.

Scenario: column lecture **07-04** — an AI travel assistant is about to confirm a
flight/hotel/taxi itinerary, and an independent critic audits it first.

## Two implementations, two philosophies

| | `langgraph/` | `claude-agent-sdk/` (this notebook) |
|---|---|---|
| **The loop** | An explicit `revise → review` back-edge. | A Python `for` loop that re-spawns the critic each round. |
| **Isolation** | You wire it (review node reads only the plan). | **Built in** — the critic is a fresh conversation on its own model. |
| **Gate** | `route` reuses `ReviewGate`. | Python reuses the **same** `ReviewGate`. |

The gate is identical on both sides — that is the point of keeping it in
`pattern.py`.

## Setup

```python
from __future__ import annotations

import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.getcwd(), "..")))

from claude_agent_sdk import AgentDefinition, ClaudeAgentOptions, query
from pattern import Objection, ReviewGate, Severity

print("claude-agent-sdk imports ready:", AgentDefinition.__name__)
```

    claude-agent-sdk imports ready: AgentDefinition

## Step 1 — the independent critic subagent

The three isolations are all in this one definition. `You did NOT build this
itinerary` is context isolation. `Find every way it can fail` is objective isolation
— its job is to attack, not approve. A separate `model` is identity isolation. And
`You may NOT approve` is the "objections, never endorsement" rule.

```python
itinerary_critic = AgentDefinition(
    description="Independently reviews a travel itinerary for conflicts before booking.",
    prompt=(
        "You are an independent trip auditor. You did NOT build this itinerary. "
        "Find every way it can fail: a taxi that arrives after boarding closes, a "
        "hotel check-in on the wrong day, a layover too short to make the connection. "
        "Return a JSON list of objections, each with severity (blocker/warning/info) "
        "and the leg it refers to. You may NOT approve the plan; only list objections."
    ),
    model="sonnet",          # a different model from the planner = identity isolation
)

print("critic ready · model =", itinerary_critic.model)
```

    critic ready · model = sonnet

## Step 2 — the orchestrator options

`"Agent"` in `allowed_tools` lets the orchestrator delegate to the critic subagent.

```python
options = ClaudeAgentOptions(
    model="sonnet",
    agents={"itinerary-critic": itinerary_critic},
    allowed_tools=["Read", "Agent"],   # "Agent" = the delegation tool
)

print("options ready · can delegate to:", list(options.agents))
```

    options ready · can delegate to: ['itinerary-critic']

## Step 3 — the gate stays in Python

The critic returns objections; it does not decide. `ReviewGate` — the same one the
LangGraph version and the unit tests use — decides admission from the objection list.
Here we gate the objections the critic *would* return (mocked, so it runs with no
key).

```python
GATE = ReviewGate()

# What the critic returns for the bad plan (live, this comes from query()).
objections = [Objection(Severity.BLOCKER, "taxi",
                        "taxi arrives 19:40, boarding closes 19:30")]

print("open blockers:", [o.issue for o in GATE.open_blockers(objections)])
print("may confirm?  ", GATE.may_confirm(objections))    # False — a blocker stands
```

    open blockers: ['taxi arrives 19:40, boarding closes 19:30']
    may confirm?   False

## Step 4 — the loop with a live critic

One round: spawn the critic on the current plan, collect its JSON objections, gate
them. If a blocker stands, revise and go again, up to `max_rounds`. This cell needs
a live API key and the Claude Code CLI, so it is not executed in the build.

```python
async def review_until_clean(plan: dict, revise, max_rounds: int = 3) -> dict:
    for _ in range(max_rounds):
        prompt = ("Use the itinerary-critic subagent to audit this itinerary and "
                  f"return its JSON objections verbatim:\n{json.dumps(plan)}")
        text = ""
        async for msg in query(prompt=prompt, options=options):
            for block in getattr(msg, "content", None) or []:
                if getattr(block, "text", None):
                    text = block.text
        objections = [Objection(**o) for o in json.loads(text)]
        if GATE.may_confirm(objections):                 # gate decides, not the critic
            return {"outcome": "confirmed", "plan": plan}
        plan = revise(plan, GATE.open_blockers(objections))
    return {"outcome": "held_for_human", "plan": plan}   # blockers survived → escalate

# asyncio.run(review_until_clean(plan, revise))          # needs a live key + Claude Code CLI
print("review_until_clean defined — call it with a live key to review for real.")
```

    review_until_clean defined — call it with a live key to review for real.

## What the SDK gives you here

1. **Independence for free.** The critic is a fresh conversation on its own model —
   context and identity isolation without wiring.
2. **Declarative critic.** Its whole contract (audit, don't approve) is the prompt.
3. **The gate is still yours.** Admission is deterministic Python (`ReviewGate`),
   unit-tested with no model. The critic finds faults; it does not get a vote on
   whether to book.

## When this breaks

| Failure | With the SDK |
|---|---|
| **Rubber stamp** | Letting the orchestrator "decide" from the critic's prose instead of gating its objections in Python. |
| **Objective leak** | A critic prompt that says "check if this is OK" rather than "find every failure." Objective isolation lives in the wording. |
| **Infinite loop** | No `max_rounds` on the Python loop. Cap it, then escalate. |

Back to the explicit loop: [`../langgraph/tutorial.md`](../langgraph/tutorial.md).
