# a · Approval Gate

> Pattern · Govern × Route
>
> [中文 README](README.zh-CN.md)

## The problem

An accepted payroll artifact proves that upstream work met its contract. It does
not answer whether a bank payment may run. The execution boundary still needs
to decide:

1. auto-allow, human review, or deterministic deny;
2. which roles may approve;
3. whether two signatures came from two people;
4. whether an old approval survives proposal or policy changes;
5. whether claimed roles came from a trusted identity directory.

## The pattern

`ApprovalGate` evaluates an immutable `ActionProposal` and routes it to:

```text
AUTO_ALLOW | HUMAN_REVIEW | DENY
```

Human review creates an expiring `ApprovalTicket`. Attestations record actor,
role, decision, and time. The final `GovernanceReceipt` binds both the proposal
digest and the policy digest. Any change to amount, artifact version, or policy
invalidates the old authority.

`role_resolver` obtains real role membership from IAM or an organizational
directory. Callers cannot gain approval authority by self-asserting a role.
Missing reviewers, expiration, and explicit rejection fail closed. Allowed and
denied tickets are terminal.

## Public interface

| Object | Responsibility |
|---|---|
| `ApprovalPolicy` | Auto, review, and hard-deny boundaries |
| `ApprovalTicket` | Version-bound, expiring review task |
| `ApprovalAttestation` | One reviewer's role and decision |
| `ApprovalEvaluation` | Route, receipt, and optional ticket |
| `ApprovalGate` | Risk routing, maker-checker, and authorization |

Shared governance objects live in
[`../boundary_contract.py`](../boundary_contract.py).

## Run

```bash
uv run python governance/a-approval-gate/example.py
uv run pytest governance/a-approval-gate/test_pattern.py -q
uv run python governance/payroll-lab/approval_gate_lab.py
uv run python governance/payroll-lab/approval_gate_lab.py --changed
```

## Where this pattern sits

Govern × Route. Approval chooses a responsibility path. Blast Radius constrains
impact, Progressive Commitment checks current authority, and Observability keeps
the causal evidence.
