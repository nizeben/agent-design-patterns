# c · Adversarial Review

> Column lecture **07-04** · pattern · Collaborate × Loop
>
> [中文 README](README.zh-CN.md)

## The problem

An AI travel assistant assembles an itinerary — a 20:00 flight, a hotel, a Didi to
the airport — and is about to confirm and pay. Every leg is individually fine: the
flight exists, the hotel has rooms, the taxi is booked. But put together, the taxi's
ETA is 19:40 and boarding closes at 19:30. This plan watches your flight leave
without you.

The agent that built the plan can't catch this. It just finished booking three
things and is in a "did well" state; ask it to review its own work and it will say
"looks good, confirm." That isn't stupidity — the author and the reviewer are the
same agent, same context, same self-assessment, with no incentive to reject what it
just produced.

So Adversarial Review adds a second agent for one purpose only: to attack the plan.
The hard part is not adding a reviewer. It is making that reviewer genuinely
**independent** — not a rubber stamp that co-signs.

## The pattern

Two named tools carry it (from the lecture):

**The Three Isolations of Independence (独立性三隔离)** — a reviewer is independent
only if three things are isolated from the author:

- **Context** — it sees the finished plan, not how the planner talked itself into it.
- **Objective** — its job is to *find every way this fails*, not to *decide if it's
  OK*. The wording decides whether it nitpicks or rubber-stamps.
- **Identity** — it is a different agent, ideally on a different model. Self-review
  with a stern prompt is still the same weights grading themselves.

**Objections, never endorsement (只提异议不背书)** — the reviewer returns a list of
objections. There is no "looks good" it can return. Admission is decided by a
deterministic `ReviewGate` — zero open blockers — never by the critic's say-so. A
critic that *can* approve will eventually approve to be agreeable.

A rubber stamp is worse than no review, because it manufactures false confidence. So
`pattern.py` refuses to run a review whose reviewer isn't independent.

## Two runnable implementations

Same pattern, same `pattern.py` gate, two ways to wire the loop:

| | [`langgraph/`](langgraph/tutorial.ipynb) | [`claude-agent-sdk/`](claude-agent-sdk/tutorial.ipynb) |
|---|---|---|
| **The loop** | An explicit back-edge `revise → review`. Visible in LangGraph Studio. | A Python `for` loop that re-spawns the critic each round. |
| **Independence** | You isolate — the review node reads only the plan. | Built in — the critic is a fresh conversation on its own model. |
| **Gate** | `route` reuses `ReviewGate`. | Python reuses the same `ReviewGate`. |
| **Model** | Provider-agnostic (`model_config`). | Claude-native (a `sonnet` critic, distinct from the planner). |

The gate is identical on both sides. The model finds faults; the gate, not the model,
grants passage.

## Files

| File | What |
|---|---|
| [`pattern.py`](pattern.py) | Framework-agnostic reference (~150 lines): `Itinerary`, `Objection`, `IndependenceGuard`, `ReviewGate`, and the `AdversarialReview` loop. A pluggable `Reviewer` is the seam both tutorials fill. |
| [`example.py`](example.py) | Runs the itinerary review with a mock critic — no API key. Round 1 catches the taxi blocker, round 2 confirms. |
| [`test_pattern.py`](test_pattern.py) | 9 tests: independence rejection, the gate's severity rule, converge/revise/escalate, and the never-auto-confirm-with-a-blocker invariant. |
| [`langgraph/tutorial.ipynb`](langgraph/tutorial.ipynb) | Step-by-step: State + round counter → review node → `route` + `revise` → the back-edge loop. |
| [`claude-agent-sdk/tutorial.ipynb`](claude-agent-sdk/tutorial.ipynb) | Step-by-step: an independent critic `AgentDefinition` → `query()` loop → the Python gate. |

## Run

```bash
# framework-agnostic core — no API key
python collaboration/c-adversarial-review/example.py
pytest collaboration/c-adversarial-review/test_pattern.py -v

# the two implementations need a model — see .env.example
```

## Where this pattern sits

Collaborate (cognitive function) × Loop (execution topology). Its nearest neighbor is
Generator-Critic (reflection module): that is one agent reviewing *itself*; this is a
*separate, independent* agent brought in to attack. Its module-mates: Hierarchical
Delegation, Fan-out-Gather (agents that cooperate), and Handoff Chain (a baton down a
pipeline). See the [two-axis matrix](../../README.md).
