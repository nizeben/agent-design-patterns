"""Lecture 27 hands-on: the monthly report through a Generator-Critic chain.

Uses the pattern from ../a-generator-critic/pattern.py on the payroll bench
(month-end: 798 PAID, 2 REVERSED). Three scenes:

    scene 1  the full chain: round 1 draft carries the two ledger errors
             plus a missing field; three wired checks find them all, one
             evidence-free "vibe" finding is dropped by the meta-gate;
             round 2 is clean (a MINOR style note stays on record without
             blocking)
    scene 2  a rubber-stamp critic: same wrong draft, no external checks,
             approved in one round -- lecture 26's lesson at pattern level
    scene 3  run with --stubborn: the generator ignores one fix, the round
             budget runs out, the draft goes to a human instead of shipping

Run `python3 generator_critic_lab.py` (add --stubborn for scene 3 behaviour
in scene 1's place).
"""
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "a-generator-critic"))
from pattern import Critic, Finding, GeneratorCritic, Severity  # noqa: E402
import bench  # noqa: E402

MONTH = bench.MONTH
STUBBORN = "--stubborn" in sys.argv

con = bench.month_end_state()
PAID_DB = con.execute("SELECT COUNT(*) FROM payroll WHERE month=? AND status='PAID'",
                      (MONTH,)).fetchone()[0]
REVERSED_DB = [r[0] for r in con.execute(
    "SELECT emp_id FROM payroll WHERE month=? AND status='REVERSED'", (MONTH,))]


# ---- the generator: drafts from a belief, revises from findings -------------

belief = {"paid": 800, "reversed": [], "exceptions_field": False}


def generator(brief, blocking_findings):
    for f in blocking_findings:
        if f.check == "reconcile_paid":
            belief["paid"] = PAID_DB
        if f.check == "reconcile_reversed" and not STUBBORN:
            belief["reversed"] = REVERSED_DB
        if f.check == "schema":
            belief["exceptions_field"] = True
    parts = [f"MONTHLY-REPORT month={MONTH}",
             f"paid={belief['paid']}",
             f"reversed={len(belief['reversed'])}"]
    if belief["exceptions_field"]:
        parts.append("exceptions=" + (",".join(belief["reversed"]) or "none"))
    parts.append("conclusion=all-clear" if not belief["reversed"]
                 else "conclusion=exceptions-pending")
    return " ".join(parts)


# ---- the critic: three wired checks, one sloppy one --------------------------

def schema_check(draft):
    missing = [k for k in ("paid=", "reversed=", "exceptions=") if k not in draft]
    if missing:
        return [Finding("schema", Severity.MAJOR,
                        f"required fields missing: {missing}",
                        evidence="report schema v2 requires paid/reversed/exceptions")]
    return []


def reconcile_paid(draft):
    if f"paid={PAID_DB}" not in draft:
        return [Finding("reconcile_paid", Severity.BLOCKER,
                        "paid count disagrees with the ledger",
                        evidence=f"ledger COUNT(status='PAID') = {PAID_DB}")]
    return []


def reconcile_reversed(draft):
    if f"reversed={len(REVERSED_DB)}" not in draft:
        return [Finding("reconcile_reversed", Severity.BLOCKER,
                        "reversed count disagrees with the ledger",
                        evidence=f"ledger REVERSED rows: {', '.join(REVERSED_DB)}")]
    return []


def style_check(draft):
    if "all-clear" in draft:
        return [Finding("style", Severity.MINOR,
                        "prefer explicit residual-risk wording over 'all-clear'",
                        evidence="reporting guideline R-7")]
    return []


def vibe_check(draft):
    # An LLM-ish check that "feels" the report is too short. No evidence.
    return [Finding("vibe", Severity.MAJOR, "report feels thin, expand it")]


def show(trace):
    for r in trace.rounds:
        print(f"   round {r.report.round}: {r.draft}")
        for f in r.report.findings:
            print(f"      [{f.severity.name:7s}] {f.check}: {f.message}"
                  f"  (evidence: {f.evidence})")
        for f in r.report.dropped:
            print(f"      [DROPPED] {f.check}: {f.message}  (no evidence -- logged, not acted on)")
    print(f"   status: {trace.status.upper()} after {len(trace.rounds)} round(s)")


print(f"== ledger truth: paid={PAID_DB}, reversed={REVERSED_DB} ==")

print(f"\n== scene 1: the wired critic (stubborn={STUBBORN}) ==")
critic = Critic({"schema": schema_check, "reconcile_paid": reconcile_paid,
                 "reconcile_reversed": reconcile_reversed, "style": style_check,
                 "vibe": vibe_check})
trace = GeneratorCritic(generator, critic, max_rounds=3).run(f"monthly report {MONTH}")
show(trace)
if trace.status == "rounds_exhausted":
    print("   -> handed to a human with the full findings history. "
          "The last draft is not shipped.")

print("\n== scene 2: the rubber-stamp critic (no external checks) ==")
belief.update({"paid": 800, "reversed": [], "exceptions_field": False})   # reset
stamp = Critic({"vibe": vibe_check})
trace2 = GeneratorCritic(generator, stamp, max_rounds=3).run(f"monthly report {MONTH}")
show(trace2)
print(f"   -> APPROVED a report that says paid=800 while the ledger says {PAID_DB}. "
      f"No external signal, no findings, wrong report ships.")
