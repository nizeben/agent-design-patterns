# a · Hierarchical Delegation

> Column lecture **07-02** · pattern · Collaborate × Hierarchy
>
> [中文 README](README.zh-CN.md)

## The problem

A payroll SaaS agent runs the June settlement: **800 employees**, a dozen
clients, several pay schemes. One agent computing all 800 paychecks in a single
context is slow, and one wrong row means starting over. The obvious fix is a team:
a **settlement supervisor** that splits the roster by client and hands each batch
to a **worker**.

The first version delegated, and the first three batches came back fast and
clean. The fourth batch, the supervisor started hallucinating — its output
structure fell apart. The workers were fine. The supervisor had drowned: to
synthesize, it had read each worker's *entire working*, and by the fourth batch
sixty percent of its context was other agents' raw computation. The thing it was
supposed to judge had been squeezed out.

Root cause: the supervisor was accumulating worker **traces** instead of worker
**results**. Delegation isn't "hand the work out." It's "hand it out without
letting the workers' process drown you, and without trusting what they hand
back."

After the rewrite: workers run in isolated contexts and return only a compact,
schema-shaped `SalaryBatchArtifact`. The supervisor reads artifacts, never raw
traces, and admits each through a deterministic gate.

## The pattern

Two named tools carry it (from the lecture):

**The Delegation Kit (委派三件套)** — before dispatching any batch, three things
are pinned:

- **Spec** — the worker's objective, output shape, tool whitelist, and *boundary*
  (what is NOT its job — the #1 defense against overlapping batches).
- **Budget** — the worker starts from a blank context and returns *only* an
  artifact. Its raw computation never reaches the supervisor.
- **Gate** — a deterministic `SafetyBoundary` (amount / confidence / needs-review
  / verdict) admits or escalates. Coded in the program, never left to a prompt.

**Manager-Never-Executes (主管不下场)** — three red lines you can write as asserts:
the supervisor only sees artifacts (not traces), workers never talk to each other
(hub-and-spoke), and the supervisor only decomposes / dispatches / synthesizes /
gates — it never does the line work.

## Two runnable implementations

Same pattern, same `pattern.py` gate, two philosophies of orchestration:

| | [`langgraph/`](langgraph/tutorial.ipynb) | [`claude-agent-sdk/`](claude-agent-sdk/tutorial.ipynb) |
|---|---|---|
| **You write** | An explicit `StateGraph` — decompose node, `Send` fan-out, reducer fan-in, supervisor gate. Every edge visible. | Declarative `AgentDefinition`s. The runtime delegates by `description` and isolates context for you. |
| **Isolation** | You control it (`output_mode="last_message"` / return only the artifact). | Built in — each subagent runs in a fresh conversation; only its final message returns. |
| **Model** | Provider-agnostic (`model_config`, default `ernie-5.1`). | Claude-native (`opus` supervisor, `haiku` workers). |
| **Scale** | `Send` + reducer. | A few batches → subagents; dozens–hundreds → the `Workflow` tool. |

The split mirrors the repo's Guardrail Sandwich (explicit graph vs. invisible
middleware): the LangGraph version makes isolation and parallelism *explicit*, the
Claude Agent SDK version makes them *native*.

## Files

| File | What |
|---|---|
| [`pattern.py`](pattern.py) | Framework-agnostic reference (~130 lines): `WorkerSpec`, `SalaryBatchArtifact`, `SafetyBoundary`, `SettlementSupervisor`. A pluggable `dispatch` callable is the seam both tutorials fill. |
| [`example.py`](example.py) | Runs the 800-employee delegation with a mock worker — no API key. |
| [`test_pattern.py`](test_pattern.py) | 9 tests: decompose/boundary, the four gate triggers, worker-failure isolation, parallel dispatch. |
| [`langgraph/tutorial.ipynb`](langgraph/tutorial.ipynb) | Step-by-step: State + reducer → worker node → `Send` fan-out → supervisor gate. |
| [`claude-agent-sdk/tutorial.ipynb`](claude-agent-sdk/tutorial.ipynb) | Step-by-step: `AgentDefinition` workers → `ClaudeAgentOptions` → `query()` delegation → Python gate. |

## Run

```bash
# framework-agnostic core — no API key
python collaboration/a-hierarchical-delegation/example.py
pytest collaboration/a-hierarchical-delegation/test_pattern.py -v

# the two implementations need a model — see .env.example
```

## Where this pattern sits

Collaborate (cognitive function) × Hierarchy (execution topology). Its neighbors
in the collaboration module: Fan-out-Gather (same batch, different lens),
Adversarial Review (a second agent that only critiques), Handoff Chain (a baton
down a pipeline). See the [two-axis matrix](../../README.md).
