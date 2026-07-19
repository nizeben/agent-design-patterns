# Payroll Governance Lab

Unified teaching lab for governance lectures 36-40. It receives a real
collaboration-boundary artifact and compares two bridges:

```text
naive: AcceptanceReceipt -> Payment

governed: Accepted Artifact
       -> ActionProposal
       -> Approval Gate
       -> Blast Radius Reservation
       -> Progressive Authority
       -> Payment Adapter
       -> Trace Audit
```

The first bridge demonstrates a real interface error: treating artifact
acceptance as action authority. The governed bridge makes the payment adapter
recheck three proposal-bound control receipts.

Lecture 36 also keeps the accepted 798-person, 13,706,097 payroll artifact
fixed while widening one portfolio policy from 13 million to 30 million. The
raw acceptance receipt does not identify the policy version that judged it;
the governance contract makes that change visible through `PolicyRef` and
`policy_digest`.

Lecture 39 adds an evidence-bound authority chain. Five real payroll department
slices support each one-level promotion. Shadow execution remains non-live, a
20-person canary fits LIMITED authority, the full payroll does not, and the
variant records an immediate critical-incident demotion.

Sibling modules are loaded through `governance_payroll_imports.py` under unique
module names. This keeps teaching-friendly filenames such as `bench.py` without
colliding with the payroll labs in other pattern modules during a full test run.

## Run

```bash
uv run python governance/payroll-lab/run_governance_module.py --mode naive
uv run python governance/payroll-lab/run_governance_module.py --mode governed
uv run python governance/payroll-lab/run_governance_module.py --mode changed
uv run python governance/payroll-lab/run_governance_module.py --mode policy-drift
uv run python governance/payroll-lab/progressive_commitment_lab.py
uv run python governance/payroll-lab/progressive_commitment_lab.py --variant
uv run pytest governance -q
```

Start the teaching console:

```bash
uv sync --extra ui
uv run python governance/payroll-lab/web_app.py --port 8767
```

Open `http://127.0.0.1:8767`.
