# b · Fan-out-Gather

> Column lecture **07-03** · pattern · Collaborate × Parallel
>
> [中文 README](README.zh-CN.md)

## The problem

The June settlement is done, every payslip computed — but when the totals roll up,
the ledger is off by a chunk (say **¥370k**), and nobody knows where. Hierarchical
Delegation (the previous pattern) can't answer this: it split 800 people into
batches, each a *different* slice. This is one total, and the fix is to have
several agents recompute the **same** total by different lenses and see where they
disagree.

The obvious first version fans the work out to a dozen workers — that part is
easy, `asyncio` does it in one line — and then writes the gather as a single
`concatenate`. The result is an unreadable report: the same finding restated three
ways, six hundred line items of which sixty percent are duplicates. The reader
gives up two pages in.

That is the whole truth of this pattern: **distribute is easy, merge is hard.**
Fan-out barely needs design. What decides whether the thing works is the gather —
turning N ambiguous, overlapping, possibly contradictory results into one
trustworthy answer. The aggregator is the soul.

## The pattern

Two named tools carry it (from the lecture):

**The Aggregator's Four Questions (聚合器四问)** — answered *before* any fan-out,
because you design the gather first and let it decide how to distribute:

- **Q1 — additive or competing?** Do the workers each see one facet (sum them) or
  answer the same question (reconcile them)? This picks the whole strategy family.
- **Q2 — how are conflicts adjudicated?** Majority, confidence-weighted, a judge
  agent, or human? For high-stakes work the rule must be deterministic.
- **Q3 — how is overlap de-duplicated?** Collapse "对赌条款增加" and "earnout 扩大"
  into one finding — the fix for the 600-item report.
- **Q4 — who reviews the seams?** Some problems live only at the boundary between
  workers' slices; add a reviewer that reads the *assembled* report, not a slice.

**Divergence-to-Root-Cause, three layers (分歧定位三层)** — the specialisation that
makes this case sing. Bind each worker to an *attributable* boundary (one data
source), have them all compute the same total, and their divergence stops being
noise:

- **Agree** → the gap is not here.
- **Attributable divergence** (the values cluster two ways) → the gap *is* located
  to a source. No more guessing.
- **Unexplained divergence** (it doesn't cluster) → human review.

The requirement is one line: *workers must bind to distinct sources.* Resample the
same data and the divergence only flags uncertainty — it can't locate anything.

## Two runnable implementations

Same pattern, same `pattern.py` reconciler, two philosophies of orchestration:

| | [`langgraph/`](langgraph/tutorial.ipynb) | [`claude-agent-sdk/`](claude-agent-sdk/tutorial.ipynb) |
|---|---|---|
| **Fan-out** | Explicit `StateGraph`: `Send` sends the *same* rows to N source workers, a reducer fans their readings back in. Every edge visible. | Declarative `AgentDefinition` per source; the runtime delegates via the Agent tool, or one `query()` per source. |
| **Isolation** | You control it (write only to a reduced key). | Built in — each subagent is a fresh conversation; only its final message returns. |
| **Gather** | A `gather` node calling `Reconciler`. | The **same** `Reconciler`, in Python, after the subagents return. |
| **Model** | Provider-agnostic (`model_config`, default `ernie-5.1`). | Claude-native (`sonnet` orchestrator, `haiku` workers). |

The gather is identical on both sides — that's the point of keeping it in
`pattern.py`. The reconciliation is framework-agnostic and, crucially,
*deterministic*: the model moves the data, it does not get a vote on where the gap
is.

## Files

| File | What |
|---|---|
| [`pattern.py`](pattern.py) | Framework-agnostic reference (~150 lines): `FanOutGather` (parallel dispatch + failure isolation + a `min_success_rate` floor) and `Reconciler` (the three-layer gather). A pluggable `FanoutFn` is the seam both tutorials fill. |
| [`example.py`](example.py) | Runs the June ledger reconciliation with mock workers — no API key. Two gaps locate themselves to a subsystem. |
| [`test_pattern.py`](test_pattern.py) | 11 tests: parallel dispatch, failure isolation, the success floor, all three divergence layers, additive dedup, the seam reviewer, and an end-to-end locate. |
| [`langgraph/tutorial.ipynb`](langgraph/tutorial.ipynb) | Step-by-step: State + reducer → source worker → `Send` fan-out (same rows) → `gather` node. |
| [`claude-agent-sdk/tutorial.ipynb`](claude-agent-sdk/tutorial.ipynb) | Step-by-step: `AgentDefinition` per source → `ClaudeAgentOptions` → `query()` fan-out → Python gather. |

## Run

```bash
# framework-agnostic core — no API key
python collaboration/b-fan-out-gather/example.py
pytest collaboration/b-fan-out-gather/test_pattern.py -v

# the two implementations need a model — see .env.example
```

## Where this pattern sits

Collaborate (cognitive function) × Parallel (execution topology). Its neighbors in
the collaboration module: Hierarchical Delegation (same team, *different* slices),
Adversarial Review (a second agent that only critiques), Handoff Chain (a baton
down a pipeline). The nearest confusion is Iterative Hypothesis Testing
(reasoning × loop): that is one agent digging down a single line; this is many
agents computing in parallel, and the signal is *their divergence*. See the
[two-axis matrix](../../README.md).
