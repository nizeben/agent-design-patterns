# payroll-lab — hands-on bench for the Action module

[简体中文](README.zh-CN.md)

A mock payroll system (single-file SQLite: 800 employees, one month of draft
payslips, two approved-but-unapplied changes) used as the running hands-on
bench for the Action patterns in this directory. Fake data, real schema,
visible side effects. No API key, no cloud — Python 3 only.

## Teaching UI

From the repository root:

```bash
uv sync --extra ui
uv run --extra ui python action/payroll-lab/web_app.py
```

Open `http://127.0.0.1:8765`. The browser console runs the existing CLI
experiments through a fixed FastAPI surface, shows key events and database
changes, and includes a searchable SQLite inspector. Raw CLI output remains
available in a collapsed section. Lecture 21 exposes five isolated controls:
the clean baseline, bank-account injection, payroll-note injection, the combined
scope-creep case, and the 999999 approval case. Every control resets the database
before it runs.

## CLI path

`naked_loop.py` does not call a provider API. It renders a real Agent prompt
boundary and uses `ScriptedModelAdapter` to return a deterministic JSON
proposal. The injected fault therefore lives at the model seam, while the
executor remains generic. This tests containment mechanics and does not
estimate how often a live model follows the same instruction.

```bash
python3 db.py
python3 naked_loop.py --scenario exact
python3 db.py --diff

python3 db.py
python3 naked_loop.py --scenario bank-account
python3 db.py --diff

python3 db.py
python3 naked_loop.py --scenario payroll-note
python3 db.py --diff

python3 db.py
python3 naked_loop.py --scenario scope-creep
python3 db.py --diff
```

The first injected scenario only normalizes bank accounts, the second only wipes
the dissent note, and the combined scenario does both. All three reuse the same
generic executor. Then:

```bash
python3 db.py
python3 db.py --inject-typo                    # a fat-fingered 999999 approval
python3 naked_loop.py --scenario approved-is-valid
```

That failure is what the four Action patterns fix, one layer at a time:

| Pattern (coordinate) | Directory |
|:--|:--|
| Tool Dispatch (Action × Router) | `tool_dispatch_lab.py` here (injected proposal, recovery, quota, and Saga) + [`../a-tool-dispatch/`](../a-tool-dispatch/) |
| Plan-and-Execute (Action × Orchestration) | `plan_execute_lab.py` here (800-person payroll DAG, five acts) + [`../b-plan-and-execute/`](../b-plan-and-execute/) |
| Prompt Chaining (Action × Chain) | `prompt_chain_lab.py` here (an indirect injection carrying a false 270k-yuan delta) + [`../c-prompt-chaining/`](../c-prompt-chaining/) |
| Guardrail Sandwich (Action × Hierarchy) | `guardrail_lab.py` here (the transfer wrapped, six scenes incl. the 999999) + [`../d-guardrail-sandwich/`](../d-guardrail-sandwich/) |

`action_trace.py` is the shared observability layer: the four production
metrics (tool-call success rate, argument repair rate, guardrail block rate,
scope creep ratio) plus a health check. Run it directly for a demo where the
scope-creep alarm fires on the naked loop's behaviour.
