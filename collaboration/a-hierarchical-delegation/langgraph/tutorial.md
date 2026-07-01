# Hierarchical Delegation — LangGraph Implementation

> "A manager delegates and reviews. A manager never does the line work."

This notebook builds Hierarchical Delegation as an **explicit LangGraph
`StateGraph`** — a supervisor you can see: a decompose node, a parallel fan-out
to worker nodes, a reducer that fans the artifacts back in, and a supervisor
node that gates the risky ones to a human.

The scenario is the one from column lecture **07-02**: the June payroll run for
**800 employees**. One agent can't hold 800 people in context, so a **settlement
supervisor** splits the roster by client, dispatches each batch to a **worker**
in its own isolated context, reads back only a compact `SalaryBatchArtifact`, and
routes anything risky to human review. The supervisor never computes a single
paycheck itself.

Everything is defined inline:

- the `DelegationState` (with a **reducer** — the fan-in seam)
- a `BatchArtifact` Pydantic schema (what a worker is allowed to return)
- the `worker` node (isolated context, structured output)
- `Send`-based fan-out (parallel dispatch)
- the `supervisor` node (decompose → gate), reusing `SafetyBoundary` from [`pattern.py`](../pattern.py)

Default model: AI Studio + `ernie-5.1` (OpenAI-compatible). See
[`.env.example`](../../../.env.example) and [`model_config.py`](../../../model_config.py).

## Two implementations, two philosophies

| | `langgraph/` (this notebook) | `claude-agent-sdk/` |
|---|---|---|
| **You write** | The orchestration graph — supervisor node, worker nodes, `Send` fan-out, reducer fan-in. Every edge is visible in LangGraph Studio. | Declarative `AgentDefinition`s. The runtime delegates by the subagent's `description` and isolates context for you. |
| **Isolation** | You control it (`output_mode` / subgraph / return only the artifact). | Built in — each subagent runs in a fresh conversation; only its final message returns. |
| **Model** | Provider-agnostic (`model_config`, default `ernie-5.1`). | Claude-native (`opus` / `sonnet` / `haiku` aliases per subagent). |
| **Best for** | Learning the mechanics: isolation + parallel + structured verification, made explicit. | Shipping fast on Claude with minimal orchestration code. |

Same pattern, same `pattern.py` gate, two ways to wire the agents.

## Setup


```python
from __future__ import annotations

import operator
import os
import sys
from typing import Annotated, TypedDict

# Make the pattern folder importable (reuse SafetyBoundary / Verdict from pattern.py)
sys.path.insert(0, os.path.abspath(os.path.join(os.getcwd(), "..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.getcwd(), "../../..")))

from pydantic import BaseModel, Field
from langgraph.graph import START, END, StateGraph
from langgraph.types import Send

from pattern import SafetyBoundary, Verdict   # the deterministic gate, framework-agnostic

print("Imports ready")
```

    Imports ready


## The shape we're filling

The framework-agnostic pattern lives in [`pattern.py`](../pattern.py): a
`WorkerSpec` (what a worker is told), a `SalaryBatchArtifact` (the only thing it
returns), and a `SafetyBoundary` (the gate). This notebook maps that shape onto
LangGraph primitives:

| pattern.py | LangGraph |
|---|---|
| `WorkerSpec` | the `Send(...)` payload handed to a worker node |
| worker runs isolated, returns only the artifact | a `worker` node that writes **only** to a reduced state key |
| parallel dispatch | `Send` fan-out on a conditional edge |
| supervisor reads artifacts, gates | a `supervisor` node + `SafetyBoundary` |

## Step 1 — State with a reducer (the fan-in seam)

When N workers run in parallel and all write to the same state key, LangGraph
needs to know **how to combine** their writes. That is a *reducer*. Without one,
parallel writes to the same key raise `InvalidUpdateError` — LangGraph refuses to
silently drop data. `Annotated[list, operator.add]` says "append, don't
overwrite," which turns N parallel worker outputs into one accumulated list.


```python
class BatchArtifact(BaseModel):
    """What a worker is allowed to return. Pydantic so we can force structured
    output — the supervisor reads these fields, never the worker's raw working."""
    batch_id: str
    verdict: str = Field(description="one of: success | partial | failure")
    employee_count: int
    total_amount: float
    anomalies: list[str] = Field(default_factory=list)
    needs_review: list[str] = Field(default_factory=list)
    confidence: float = 1.0


class DelegationState(TypedDict):
    roster: list[dict]
    batches: list[dict]                              # [{batch_id, rows}], set by decompose
    # The reducer. N workers append here in parallel; no reducer -> InvalidUpdateError.
    artifacts: Annotated[list[dict], operator.add]
    result: dict

print("State ready — note the operator.add reducer on `artifacts`")
```

    State ready — note the operator.add reducer on `artifacts`


## Step 2 — The worker node: isolated context, structured output

A worker gets **only its own batch** (via the `Send` payload), never the full
roster and never the supervisor's state. It returns a single `BatchArtifact`.
Two things make this a real worker and not just a function:

1. **Isolation** — it reads `payload["rows"]`, nothing else. Its intermediate
   reasoning never lands in the supervisor's state.
2. **Structured output** — `model.with_structured_output(BatchArtifact)` forces
   the model to return the schema. The supervisor gets fields, not prose.


```python
WORKER_PROMPT = """You are a payroll worker. Compute the June payroll for ONLY \
the employees in this batch, applying base pay plus ~30% loading. Do NOT touch \
any other batch. Return a BatchArtifact:
- total_amount: sum of all pay in this batch
- anomalies: any row that looks wrong (e.g. commission far above the mean)
- needs_review: employee ids you are not confident about
- confidence: 0-1
- verdict: "success" if clean, "partial" if any needs_review, "failure" if you couldn't compute

Batch {batch_id}, {n} employees:
{rows}
"""

def make_worker(worker_model):
    """worker_model is a cheap model in production. structured_worker forces schema."""
    structured_worker = worker_model.with_structured_output(BatchArtifact)

    def worker(payload: dict) -> dict:            # payload = {"batch_id", "rows"}
        art = structured_worker.invoke(WORKER_PROMPT.format(
            batch_id=payload["batch_id"], n=len(payload["rows"]), rows=payload["rows"],
        ))
        art.batch_id = payload["batch_id"]        # trust our id, not the model's
        return {"artifacts": [art.model_dump()]}  # write ONLY to the reduced key
    return worker

print("Worker factory ready")
```

    Worker factory ready


## Step 3 — Fan out with `Send` (parallel dispatch)

`Send(node, payload)` schedules an independent run of a node with its own input.
Return a **list** of `Send`s from a routing function and LangGraph runs them all
in parallel, each with a different batch. This is the fan-out.


```python
def decompose(state: DelegationState) -> dict:
    """Supervisor step 1: split the roster into per-client batches."""
    by_client: dict[str, list[dict]] = {}
    for row in state["roster"]:
        by_client.setdefault(row["client"], []).append(row)
    batches = [{"batch_id": f"batch::{c}", "rows": rows} for c, rows in by_client.items()]
    return {"batches": batches}


def fan_out(state: DelegationState) -> list[Send]:
    """Conditional-edge router: one Send per batch -> N workers in parallel."""
    return [Send("worker", b) for b in state["batches"]]

print("Fan-out ready")
```

    Fan-out ready


## Step 4 — The supervisor: gate the artifacts

The supervisor node runs *after* the fan-in. By the time it runs, the reducer has
collected every worker's `BatchArtifact` into `state["artifacts"]`. The
supervisor reads those artifacts — never a worker's raw trace — and applies the
deterministic `SafetyBoundary` from `pattern.py`. High-amount, low-confidence, or
flagged batches go to human review.


```python
BOUNDARY = SafetyBoundary(amount_threshold=5_000_000, min_confidence=0.85)

def supervisor(state: DelegationState) -> dict:
    """Supervisor step 2: synthesize + gate. Reads artifacts only."""
    arts = state["artifacts"]

    def escalate(a: dict) -> bool:
        return (
            a["total_amount"] > BOUNDARY.amount_threshold
            or a["confidence"] < BOUNDARY.min_confidence
            or bool(a["needs_review"])
            or a["verdict"] != Verdict.SUCCESS.value
        )

    clean = [a for a in arts if not escalate(a)]
    human = [a for a in arts if escalate(a)]
    return {"result": {
        "total": round(sum(a["total_amount"] for a in clean), 2),
        "employee_count": sum(a["employee_count"] for a in arts),
        "auto_approved": [a["batch_id"] for a in clean],
        "human_review": [a["batch_id"] for a in human],
    }}

print("Supervisor ready")
```

    Supervisor ready


## Step 5 — Wire the graph

`decompose → (fan_out) → worker ×N → supervisor → END`. The conditional edge from
`decompose` to `worker` carries the `Send` fan-out; the plain edge from `worker`
to `supervisor` is the fan-in (the reducer merges the parallel writes).


```python
def build_graph(worker_model):
    g = StateGraph(DelegationState)
    g.add_node("decompose", decompose)
    g.add_node("worker", make_worker(worker_model))
    g.add_node("supervisor", supervisor)
    g.add_edge(START, "decompose")
    g.add_conditional_edges("decompose", fan_out, ["worker"])  # fan-out
    g.add_edge("worker", "supervisor")                         # fan-in (reducer merges)
    g.add_edge("supervisor", END)
    return g.compile()

print("Graph builder ready")
```

    Graph builder ready


## Step 6 — Run it

### Mock run (no API key) — prove the wiring

A tiny mock model returns a deterministic `BatchArtifact` so you can watch the
fan-out/fan-in/gate work without a key. One batch (`stark`) comes back with low
confidence to show the gate discriminating.


```python
class _MockStructured:
    def invoke(self, prompt: str) -> BatchArtifact:
        # crude: pull the batch id out of the prompt
        bid = next((line for line in prompt.splitlines() if line.startswith("Batch")), "Batch batch::x,")
        bid = bid.split()[1].rstrip(",")
        low = bid.endswith("stark")
        return BatchArtifact(
            batch_id=bid, verdict="partial" if low else "success",
            employee_count=10, total_amount=123456.0,
            needs_review=["e_x"] if low else [], confidence=0.6 if low else 1.0,
        )

class _MockModel:
    def with_structured_output(self, schema): return _MockStructured()

roster = (
    [{"id": f"a{i}", "client": "acme", "base": 8000} for i in range(3)]
    + [{"id": f"g{i}", "client": "globex", "base": 7000} for i in range(2)]
    + [{"id": f"s{i}", "client": "stark", "base": 9000} for i in range(2)]
)
app = build_graph(_MockModel())
out = app.invoke({"roster": roster, "batches": [], "artifacts": [], "result": {}})
print(out["result"])
```

    {'total': 246912.0, 'employee_count': 30, 'auto_approved': ['batch::acme', 'batch::globex'], 'human_review': ['batch::stark']}


The graph ran three workers in parallel, the reducer merged their artifacts, and
the supervisor gated `stark` to human review. No worker saw another worker's
work; the supervisor saw only artifacts.

### Real run — plug in a model

Swap the mock for a real model. In production the **worker** model is a cheap one
(the supervisor's judgment is where you spend). With the shared `model_config`
that's a one-line change — point `worker_model` at a cheaper `MODEL_NAME`, or load
a second model with `init_chat_model("openai:gpt-4o-mini")`.


```python
from model_config import get_model      # registers CN providers; reads .env

worker_model = get_model()              # in prod: a cheap model (haiku / gpt-4o-mini)
if worker_model:
    app = build_graph(worker_model)
    out = app.invoke({"roster": roster, "batches": [], "artifacts": [], "result": {}})
    print(out["result"])
else:
    print("No API key — set one in .env to run the real version.")
```


## The library version — the short way

`langgraph-supervisor` (`pip install langgraph-supervisor`) does the wiring for
you: hand it a list of compiled worker agents and it auto-generates a
`transfer_to_<name>` handoff tool for each, mounted on the supervisor. The
crucial knob is `output_mode`:

- `output_mode="last_message"` (default) → the supervisor only ever sees each
  worker's **final** message. This *is* the isolation. Use it.
- `output_mode="full_history"` → every worker's intermediate messages flood the
  supervisor's context. This is the "supervisor drowns in worker traces" failure
  from the lecture. Avoid.


```python
# Sketch (needs real agents + models to run):
#
# from langgraph_supervisor import create_supervisor
# from langchain.agents import create_agent          # LangChain 1.0; old: langgraph.prebuilt.create_react_agent
#
# acme_worker   = create_agent(model=worker_model, tools=[calc_salary], name="acme_worker")
# globex_worker = create_agent(model=worker_model, tools=[calc_salary], name="globex_worker")
#
# workflow = create_supervisor(
#     agents=[acme_worker, globex_worker],
#     model=supervisor_model,          # strong model orchestrates
#     output_mode="last_message",      # <-- isolation: only final messages reach the supervisor
# )
# app = workflow.compile()
print("Library version: create_supervisor + output_mode='last_message' is the isolation knob.")
```

    Library version: create_supervisor + output_mode='last_message' is the isolation knob.


> **Version note.** LangChain / LangGraph 1.0 (Oct 2025) deprecated
> `langgraph.prebuilt.create_react_agent` in favor of
> `langchain.agents.create_agent` (still runnable, with a warning). Pin your
> versions in the repo's `pyproject.toml` and re-run CI, because this API changed
> in 2025-Q4.

## What LangGraph gives you here

Three things map one-to-one onto the pattern's hard parts:

1. **Isolation** → `output_mode="last_message"` (library) or "worker writes only
   to a reduced key" (hand-written). The supervisor never accumulates worker
   traces — the #1 way hierarchical delegation crashes.
2. **Parallel fan-out + safe fan-in** → `Send` + `Annotated[list, operator.add]`.
   The `InvalidUpdateError` you get without a reducer is a *feature*: it refuses to
   silently drop a worker's result.
3. **Structured verification** → `with_structured_output` means the supervisor
   gates on typed fields, not on parsing prose.

## When this breaks

The failure modes from the lecture, and where they live in this graph:

| Failure | In this graph |
|---|---|
| **Context pollution** (supervisor drowns in worker traces) | Using `output_mode="full_history"`, or a worker returning its whole message list instead of one artifact. |
| **Worker failure cascade** | An unhandled exception in a worker node. Wrap the worker body in try/except and return a `failure` artifact (as `pattern.py`'s `_run_one` does). |
| **Decomposition error** | `decompose` splitting batches with overlapping employees. Pin a boundary per batch. |
| **Fan-in data loss** | Forgetting the `operator.add` reducer → `InvalidUpdateError` (loud, not silent — good). |
| **Mesh degeneration** | Adding an edge from one worker to another. Don't — workers only talk to the supervisor. |

Next: the same pattern with the Claude Agent SDK, where isolation is built into
the subagent primitive instead of wired by hand → [`../claude-agent-sdk/tutorial.md`](../claude-agent-sdk/tutorial.md).
