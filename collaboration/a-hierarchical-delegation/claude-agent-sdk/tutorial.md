# Hierarchical Delegation — Claude Agent SDK Implementation

> "A manager delegates and reviews. A manager never does the line work."

This notebook builds Hierarchical Delegation with the **Claude Agent SDK**, where
the supervisor-worker structure is a *native primitive*: you declare **subagents**
as `AgentDefinition`s, and the runtime delegates to them by their `description`
and isolates each one's context for you. Where the [LangGraph version](../langgraph/tutorial.md)
has you wire a graph by hand, here you mostly declare intent.

Same scenario as column lecture **07-02**: the June payroll run for **800
employees**. A **supervisor** (the main `query`) splits the roster by client and
delegates each batch to a **payroll-worker** subagent that runs in its own
isolated context and reports back a compact artifact. The supervisor never
computes a paycheck itself — and, importantly, the **deterministic gate stays in
Python** (`pattern.py`'s `SafetyBoundary`), because a "must this go to a human?"
rule should never be left to a model's judgment.

Verified against the official docs
([code.claude.com/docs/en/agent-sdk/subagents](https://code.claude.com/docs/en/agent-sdk/subagents))
and the installed `claude-agent-sdk` (0.1.81).

## Two implementations, two philosophies

| | `langgraph/` | `claude-agent-sdk/` (this notebook) |
|---|---|---|
| **You write** | An orchestration graph — nodes, `Send` fan-out, reducer fan-in. | Declarative `AgentDefinition`s. The runtime delegates by `description`. |
| **Isolation** | You control it (`output_mode` / return only the artifact). | **Built in** — each subagent runs in a fresh conversation; only its final message returns to the parent. |
| **Model** | Provider-agnostic (`model_config`). | Claude-native — `model="haiku"` per worker, `model="opus"` for the supervisor. |
| **Parallel** | `Send` + reducer. | Multiple subagents run concurrently; for *dozens–hundreds* of batches, the `Workflow` tool. |

## Setup

```bash
pip install claude-agent-sdk        # 0.1.81; also needs the Claude Code CLI + auth
```

The SDK drives the Claude Code backend, so it needs the CLI installed and an
`ANTHROPIC_API_KEY` (or a logged-in Claude Code). The pattern's deterministic
gate is pure Python and needs neither.


```python
from __future__ import annotations

import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.getcwd(), "..")))  # reuse pattern.py

from claude_agent_sdk import query, ClaudeAgentOptions, AgentDefinition
from pattern import SafetyBoundary, Verdict     # the deterministic gate stays in Python

print("Imports ready")
```

    Imports ready


## The shape we're filling

| pattern.py | Claude Agent SDK |
|---|---|
| `WorkerSpec` (objective, tools, boundary) | an `AgentDefinition` (`description`, `prompt`, `tools`, `model`) |
| worker runs isolated, returns only the artifact | **built in** — subagent gets a fresh context; only its final message returns |
| parallel dispatch | the runtime runs subagents concurrently |
| `SafetyBoundary` (the gate) | **still Python** — you apply it to the returned artifacts, in code |

The lecture's rule — *the deterministic gate belongs in the program, not the
prompt* — is why `SafetyBoundary` doesn't move into the model here. The SDK gives
you isolation and delegation for free; the gate you keep.

## Step 1 — Define the worker as a subagent (`AgentDefinition`)

A subagent is declared, not built. Four fields carry the Delegation Kit's *Spec*:
`description` (Claude uses this to decide when to delegate), `prompt` (the
worker's instructions), `tools` (its whitelist), and `model` (cheap for workers).
The worker is told to end with a single JSON artifact line so the supervisor —
and our Python gate — can read structured fields, not prose.


```python
WORKER_PROMPT = """You are a payroll worker. You are given ONE batch of employees.
Compute June pay for each (base + ~30% loading). Do NOT touch any other batch.

End your reply with exactly one JSON line, nothing after it:
{"batch_id": "...", "verdict": "success|partial|failure", "employee_count": N,
 "total_amount": <float>, "anomalies": [...], "needs_review": [...], "confidence": <0-1>}

Set verdict to "partial" if needs_review is non-empty, "failure" if you couldn't compute."""

payroll_worker = AgentDefinition(
    description="Computes June payroll for a single client batch. Use once per batch.",
    prompt=WORKER_PROMPT,
    tools=["Read", "Bash"],     # whitelist: can read the roster + run a calc; cannot write the HR DB
    model="haiku",              # workers are cheap; the supervisor is where you spend
)
print("Worker subagent defined:", payroll_worker.description)
```

    Worker subagent defined: Computes June payroll for a single client batch. Use once per batch.


## Step 2 — The supervisor options

The supervisor is the main `query`. Its `model` is strong (`opus`); its `agents`
map names the worker subagents it may delegate to; and `allowed_tools` **must
include `Agent`** — that is the tool the supervisor uses to spawn a subagent
(auto-approving it so there's no permission prompt).


```python
def supervisor_options() -> ClaudeAgentOptions:
    return ClaudeAgentOptions(
        model="opus",                               # supervisor: strong, orchestrates
        allowed_tools=["Read", "Bash", "Agent"],    # `Agent` = spawn a subagent
        agents={"payroll-worker": payroll_worker},  # the roster of subagents it may use
    )

print("Supervisor options ready — note `Agent` in allowed_tools")
```

    Supervisor options ready — note `Agent` in allowed_tools


## Step 3 — Delegate, and detect the delegation

The supervisor prompt tells it to split the roster and delegate each batch to the
`payroll-worker` subagent, then report back every worker's JSON artifact. Claude
decides to invoke the subagent based on its `description`; you can also force it by
naming the agent ("Use the payroll-worker agent to...").

We stream the messages and watch for the **Agent** tool being used — that is proof
a subagent was spawned rather than the supervisor answering directly. (The tool
was named `Task` before Claude Code v2.1.63 and `Agent` after; match both.)


```python
from claude_agent_sdk import ToolUseBlock

SUPERVISOR_PROMPT = """You are the settlement supervisor for the June payroll run.
The roster has these client batches: acme (3 employees), globex (2), stark (2).
Delegate EACH batch to the payroll-worker subagent, one at a time.
Do not compute any pay yourself. When all workers have reported, output a JSON
array of their artifact objects, and nothing else."""

async def run_supervisor(prompt: str) -> str:
    final = ""
    async for message in query(prompt=prompt, options=supervisor_options()):
        # prove delegation happened: an Agent/Task tool_use block
        for block in getattr(message, "content", None) or []:
            if isinstance(block, ToolUseBlock) and block.name in ("Task", "Agent"):
                print(f"  → delegated to subagent: {block.input.get('subagent_type')}")
        if hasattr(message, "result"):
            final = message.result
    return final

print("Runner ready (call: await run_supervisor(SUPERVISOR_PROMPT))")
```

    Runner ready (call: await run_supervisor(SUPERVISOR_PROMPT))


## Step 4 — Isolation is built in (what the SDK gives you)

You do not wire isolation here — it's the point of a subagent. From the official
docs:

> *"Each subagent runs in its own fresh conversation. Intermediate tool calls and
> results stay inside the subagent; only its final message returns to the parent."*

So when a `payroll-worker` reads the roster and runs its calculation, none of that
working lands in the supervisor's context. The supervisor receives one artifact
per worker — the "supervisor drowns in worker traces" crash from the lecture
simply can't happen through this channel. What a subagent *does* inherit: its own
`prompt`, the Agent tool's prompt string, and (optionally) project `CLAUDE.md`.
What it does **not** inherit: the parent's conversation history or system prompt.
The only parent→child channel is the prompt you pass when delegating, so put any
needed context (file paths, the batch rows) directly in it.

## Step 5 — Keep the gate in Python

The supervisor comes back with the workers' artifacts. Now apply the
**deterministic** `SafetyBoundary` from `pattern.py` — in code, not in the model.
This is the Delegation Kit's *Gate*: high-amount, low-confidence, or flagged
batches go to a human, every time, regardless of what the model "thinks."


```python
def gate_artifacts(artifacts: list[dict]) -> dict:
    boundary = SafetyBoundary(amount_threshold=5_000_000, min_confidence=0.85)

    def escalate(a: dict) -> bool:
        return (
            a["total_amount"] > boundary.amount_threshold
            or a.get("confidence", 1.0) < boundary.min_confidence
            or bool(a.get("needs_review"))
            or a.get("verdict") != Verdict.SUCCESS.value
        )

    clean = [a for a in artifacts if not escalate(a)]
    human = [a for a in artifacts if escalate(a)]
    return {
        "total": round(sum(a["total_amount"] for a in clean), 2),
        "employee_count": sum(a["employee_count"] for a in artifacts),
        "auto_approved": [a["batch_id"] for a in clean],
        "human_review": [a["batch_id"] for a in human],
    }

# Deterministic — runs without any API. Same gate as the LangGraph version.
demo_artifacts = [
    {"batch_id": "batch::acme",   "verdict": "success", "employee_count": 3, "total_amount": 31200.0, "confidence": 1.0, "needs_review": []},
    {"batch_id": "batch::globex", "verdict": "success", "employee_count": 2, "total_amount": 18200.0, "confidence": 1.0, "needs_review": []},
    {"batch_id": "batch::stark",  "verdict": "partial", "employee_count": 2, "total_amount": 23400.0, "confidence": 0.6, "needs_review": ["s0"]},
]
print(gate_artifacts(demo_artifacts))
```

    {'total': 49400.0, 'employee_count': 7, 'auto_approved': ['batch::acme', 'batch::globex'], 'human_review': ['batch::stark']}


## Step 6 — Put it together

```python
async def main():
    raw = await run_supervisor(SUPERVISOR_PROMPT)   # needs ANTHROPIC_API_KEY + Claude Code CLI
    artifacts = json.loads(raw)                     # supervisor returns a JSON array
    print(gate_artifacts(artifacts))                # deterministic gate, in Python

# asyncio.run(main())
```

The division of labor: the SDK delegates and isolates (Steps 1–4), and Python
holds the deterministic gate (Step 5). The worker runs on a cheap model, the
supervisor on a strong one, and the artifact — not the working — is all that
crosses the boundary.

## Scaling up: from a few subagents to hundreds of batches

800 employees split by client is a handful of batches — a good fit for turn-by-turn
subagent delegation. But split 800 people into *fifty* batches and you're past what
one conversation should orchestrate. The docs are explicit:

> *"Subagents work well for a few delegated tasks per turn. For runs that
> coordinate dozens to hundreds of agents, use the `Workflow` tool, which moves the
> orchestration into a script the runtime executes outside the conversation
> context."*

So the scale ladder for hierarchical delegation on Claude is: a few batches →
subagent delegation (this notebook); dozens–hundreds → the `Workflow` tool. Same
pattern, different orchestration substrate.

## What the Claude Agent SDK gives you

| Pattern's hard part | Here |
|---|---|
| **Isolation** | Native. Fresh context per subagent; only the final message returns. Nothing to wire. |
| **Model layering** | `model="haiku"` on the worker, `model="opus"` on the supervisor — one field each. |
| **Tool restriction** | `tools=[...]` per subagent; omit `Agent` from a worker's tools so it can't spawn its own subagents. |
| **Delegation** | Automatic, by `description` — or explicit by naming the agent. |
| **The deterministic gate** | *Not* the SDK's job. You keep `SafetyBoundary` in Python. |

## When this breaks

| Failure | Here |
|---|---|
| **Supervisor drowns in traces** | Can't happen through the subagent channel — only final messages return. (It can still happen if you stuff everything into one agent instead of delegating.) |
| **Worker failure cascade** | A subagent that errors returns its failure as the Agent tool result; catch it and treat as a `failure` artifact, don't let it abort the run. |
| **Gate drift** | Leaving the amount/confidence threshold to the supervisor's prompt. Don't — keep `SafetyBoundary` in Python (Step 5). |
| **Mesh degeneration** | A worker spawning its own workers. Omit `Agent` from the worker's `tools` (or add it to `disallowedTools`) so it can't. |
| **Decomposition error** | The supervisor splitting overlapping batches. Put the boundary in the worker's `prompt` and the delegation prompt ("this batch only"). |

Compare with the hand-wired [LangGraph version](../langgraph/tutorial.md): same
pattern, same `pattern.py` gate — one makes isolation explicit, the other makes it
native.
