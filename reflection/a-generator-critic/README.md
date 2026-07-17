# Generator-Critic

> Lecture **06-02** · pattern · Reflect × Chain
> [中文 README](README.zh-CN.md)

## Contract

Generator-Critic reviews one artifact in one bounded pass:

```text
generate -> critique -> policy gate -> optional revision draft
```

The critic reports evidence. It does not approve the artifact. A deterministic
`AcceptancePolicy` converts grounded findings and an evidence-backed score into
`ACCEPTED` or `NEEDS_REVISION`. If a reviser creates a new draft, that draft is
explicitly unreviewed. An outer workflow must submit it through another pass
before it can be accepted.

This keeps the topology honest. Repeating repair until a test, lint, build, or
CI signal turns green belongs to the sibling
[Self-Heal Loop](../d-self-heal-loop/README.md).

## Quick start

```bash
python3 reflection/a-generator-critic/example.py
python3 reflection/payroll-lab/generator_critic_lab.py
python3 reflection/payroll-lab/generator_critic_lab.py --rubber-stamp
```

The payroll lab reviews a report that claims 800 paid payslips while SQLite
contains 798 `PAID` and 2 `REVERSED`. The standard critic attaches ledger and
schema evidence, drafts a correction, and accepts it only in an explicit second
pass. The rubber-stamp contrast has no access to those facts and approves the
wrong report.

## Reference interface

The reference implementation in [`pattern.py`](pattern.py) separates four
responsibilities:

- `Critique` records findings and evidence.
- `AcceptancePolicy` owns the shipping decision.
- `ChainResult.reviewed_artifact` identifies what was actually judged.
- `ChainResult.revision_draft` stays unreviewed until another explicit pass.

Run the invariant tests with:

```bash
uv run pytest reflection/a-generator-critic/test_pattern.py -q
```

## Matrix position

This pattern sits at **Reflect × Chain**. See the
[two-axis matrix](../../README.md#the-28-pattern-map) for neighboring patterns.
