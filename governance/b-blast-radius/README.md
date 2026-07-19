# b · Blast Radius Control

> Pattern · Govern × Hierarchy
>
> [中文 README](README.zh-CN.md)

## The problem

Each department payment may fit its local limit while concurrent siblings exceed
the company portfolio. Counting quota after a tool call is too late because the
external effect already happened.

## The pattern

`BlastRadiusController` organizes amount, subjects, effect count, actions, and
resources into a parent-child budget tree. A child may narrow its parent but
must never widen it. Capacity is reserved across the complete leaf-to-root path
before execution:

```text
reserve -> effect -> commit
              \-> cancel / revoke
```

Sibling actions therefore compete for the same parent capacity. Stable
idempotency keys prevent duplicate reservations. An independent kill switch
revokes active leases and blocks new ones.

A child resource prefix may narrow a parent prefix. For example, a parent that
allows `payroll:` can delegate only
`payroll:2026-06:department:Engineering` to one leaf. Lease IDs also include
the proposal digest so changed proposals cannot overwrite one another under
the same business ID.

## Public interface

| Object | Responsibility |
|---|---|
| `BlastBudget` | Amount, subject, count, action, and resource limits |
| `ContainmentScope` | One node in the parent-child control tree |
| `ContainmentLease` | Capacity reserved before an effect |
| `BlastRadiusController` | Register, reserve, commit, cancel, and stop |
| `GovernanceReceipt` | Pre-effect reservation and post-effect commit evidence |

## Run

```bash
python3 governance/b-blast-radius/example.py
pytest governance/b-blast-radius/test_pattern.py -q
python3 governance/payroll-lab/blast_radius_lab.py
python3 governance/payroll-lab/blast_radius_lab.py --overflow
```

The payroll lab reads real Engineering, Finance, and Ops totals from SQLite.
The first two sibling batches reserve successfully. The third remains legal in
its leaf but is rejected because their aggregate crosses the shared parent
window.

## Where this pattern sits

Govern × Hierarchy. Every level narrows the level above it, so local validity
must also satisfy the portfolio budget.
