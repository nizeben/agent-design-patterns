# Checklist Benchmark Case

> Lecture **09 Composition** companion case · Composition × mixed topologies
> [中文 README](README.zh-CN.md)

## Status

Document-only. This folder turns a real financial regulatory-document POC into a public, anonymized case. The original regulator, jurisdiction, document title, internal meeting context, and project paths are removed. What remains is the engineering structure.

The task: turn a financial product-disclosure standard into a reviewed checklist. A strong assistant plus human review creates 12 Golden Rules. Then several ordinary-model extraction strategies are compared against the same schema and gold set.

## Why this case matters

The point is not that a model can extract rules. The point is that pattern composition turns a one-shot extraction task into a measurable, replayable, human-reviewable workflow.

| Strategy | Two-axis map | Match |
|---|---|---:|
| `single_pass` | Reasoning × Chain | 6 / 12 |
| `critique_repair` | Reflection × Chain | 7 / 12 |
| `iterative_self_refine` | Reflection × Loop | 7 / 12 |
| `candidate_guided_review` | Governance × Route | 9 / 12 |
| `coverage_preserving_union_queue` | Composite: Parallel -> Route | 10 / 12 |
| `orchestrated_consensus_refine` | Composite: Parallel -> Route -> Loop | 8 / 12 |

The design lesson: one-shot extraction recovers 6 of 12 rules. A candidate-guided review path reaches 9 of 12. A coverage-preserving union queue reaches 10 of 12 by keeping complementary candidate rules for human review. Compressing too early loses coverage.

## Files

| File | Purpose |
|---|---|
| `CODEX_V1.zh-CN.md` | Chinese Codex v1 article draft for the Composition module |
| `anonymized_case.json` | Static public case data |
| `checklist_benchmark.ipynb` | Executed notebook for the column |
| `VERSION_NOTES.zh-CN.md` | Version map from early schema work to public benchmark case |

## Use

This is a document package, not a runnable pattern package. Read `CODEX_V1.zh-CN.md` first, then open `checklist_benchmark.ipynb` for the saved benchmark table.

## Engineering slice

This case aligns with current production-agent practice:

* Anthropic's *Building Effective Agents* recommends simple, composable workflows before adding more autonomy.
* OpenAI Agents SDK tracing and trace grading make agent runs inspectable and evaluable.
* LangGraph durable execution and human-in-the-loop support show why intermediate state must be preserved when humans approve or edit outputs.

The shared principle: a production agent is not a single answer. It is an auditable path.
