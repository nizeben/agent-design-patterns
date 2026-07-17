"""Lecture 34 hands-on: before the money moves, someone whose only job is
to attack the pay run.

Runs the pattern from ../c-adversarial-review/pattern.py on the month-end
payroll bench (800 employees, 798 PAID, 2 REVERSED). The artifact under
review is a disbursement run: plain pay lines plus a declared total. The
reviewers are independent of the author by construction -- they read the
ledger themselves and see only the run, never the author's reasoning.

    scene 1  the loop converges: the author computed the run from the
             employees table (the obligation view, lecture 33's mistake,
             now about to move money), so the two REVERSED payslips ride
             along. The review panel raises blockers, the reviser drops
             the two lines and recomputes, round two is clean, the gate
             confirms. 38,444 stays in the bank. The confirmation is
             sealed into a boundary_contract AcceptanceReceipt bound to
             the task contract's digest.
    scene 2  the rubber stamp refused: pass the same callable as reviewer
             and reviser; IndependenceGuard returns NO_REVIEWER instead
             of running a self-review.
    scene 3  run with --blind-spot: a status-clean run carries a
             duplicated pay line (one employee paid twice). The lone
             reviewer only knows the payslip-status rule, so the run is
             CONFIRMED with the double pay still inside. This is G3 in
             collaboration/stress_collab_gaps.py: independent is not
             omniscient. The lab's coverage gate names what nobody
             checked, and a full panel over the same run catches it.

Coverage note: REQUIRED_COVERAGE is a teaching policy, three risk classes
for one bench. The point it makes is structural: CONFIRMED means "no
blockers among the declared checks", never "no problems". What is
declared, and whether the panel covers it, is data the release decision
must read -- the pattern itself cannot know what nobody told it to check.

Everything is deterministic and reads the bench directly; no API key.
Run `python3 adversarial_review_lab.py` (add --blind-spot for scene 3).
"""
from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).parent


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


_rev = _load(HERE.parent / "c-adversarial-review" / "pattern.py", "review_pattern")
AdversarialReview = _rev.AdversarialReview
Itinerary = _rev.Itinerary
Objection = _rev.Objection
Outcome = _rev.Outcome
ReviewGate = _rev.ReviewGate
Severity = _rev.Severity

_bc = _load(HERE.parent / "boundary_contract.py", "collab_contract")

sys.path.insert(0, str(HERE.parent.parent / "reflection" / "payroll-lab"))
import bench  # noqa: E402

# Teaching policy: the risk classes June's release decision requires a
# reviewer for. A run is only releasable when the panel's declared
# coverage includes all three AND the gate confirms.
REQUIRED_COVERAGE = {"payslip-status", "duplicate-line", "total-reconciliation"}


def month_end():
    return bench.month_end_state()


# ---- two authors, two honest mistakes -----------------------------------------

def draft_from_obligation(con) -> Itinerary:
    """Lecture 33's root cause, now about to move money: the run is built
    from the employees table, so the two REVERSED payslips ride along."""
    legs = [{"type": "payline", "emp_id": e, "dept": d, "amount": float(s)}
            for e, d, s in con.execute(
                "SELECT emp_id, dept, base_salary FROM employees ORDER BY emp_id")]
    return Itinerary(legs=legs,
                     total_price=round(sum(l["amount"] for l in legs), 2))


def draft_with_duplicate(con, emp_id: str = "E0100") -> Itinerary:
    """Status-clean (built from PAID payslips only), but a merge bug left
    one employee's line in twice. Internally consistent: the declared
    total is the sum of the lines, double pay included."""
    legs = [{"type": "payline", "emp_id": e, "dept": d, "amount": float(s)}
            for e, d, s in con.execute(
                "SELECT e.emp_id, e.dept, e.base_salary FROM payroll p "
                "JOIN employees e ON e.emp_id = p.emp_id "
                "WHERE p.month = ? AND p.status = 'PAID' ORDER BY e.emp_id",
                (bench.MONTH,))]
    dup = next(l for l in legs if l["emp_id"] == emp_id)
    legs.append(dict(dup))
    return Itinerary(legs=legs,
                     total_price=round(sum(l["amount"] for l in legs), 2))


# ---- the review panel: each reviewer declares what it covers -------------------

def covers(*classes: str):
    def deco(fn):
        fn.covers = set(classes)
        return fn
    return deco


def make_reviewers(con):
    status = {e: s for e, s in con.execute(
        "SELECT emp_id, status FROM payroll WHERE month = ?", (bench.MONTH,))}
    bank_total = float(con.execute(
        "SELECT SUM(e.base_salary) FROM payroll p "
        "JOIN employees e ON e.emp_id = p.emp_id "
        "WHERE p.month = ? AND p.status = 'PAID'", (bench.MONTH,)).fetchone()[0])

    @covers("payslip-status")
    async def status_reviewer(plan: Itinerary) -> list[Objection]:
        return [Objection(Severity.BLOCKER, l["emp_id"],
                          f"REVERSED-IN-RUN: payslip status is "
                          f"{status.get(l['emp_id'], 'MISSING')}, must not be paid")
                for l in plan.legs if status.get(l["emp_id"]) != "PAID"]

    @covers("duplicate-line")
    async def duplicate_reviewer(plan: Itinerary) -> list[Objection]:
        seen: set[str] = set()
        objs = []
        for l in plan.legs:
            if l["emp_id"] in seen:
                objs.append(Objection(Severity.BLOCKER, l["emp_id"],
                                      "DUPLICATE-LINE: employee appears twice, "
                                      "would be paid twice"))
            seen.add(l["emp_id"])
        return objs

    @covers("total-reconciliation")
    async def reconciliation_reviewer(plan: Itinerary) -> list[Objection]:
        line_sum = round(sum(l["amount"] for l in plan.legs), 2)
        objs = []
        if abs(plan.total_price - line_sum) > 0.005:
            objs.append(Objection(Severity.BLOCKER, "TOTAL",
                                  f"TOTAL-MISMATCH: declared {plan.total_price:,.2f} "
                                  f"vs line sum {line_sum:,.2f}"))
        if abs(line_sum - bank_total) > 0.005:
            objs.append(Objection(Severity.BLOCKER, "TOTAL",
                                  f"TOTAL-MISMATCH: line sum {line_sum:,.2f} vs "
                                  f"bank PAID total {bank_total:,.2f}"))
        return objs

    return status_reviewer, duplicate_reviewer, reconciliation_reviewer


def panel(*reviewers):
    """Compose reviewers into one Reviewer; coverage is the union of what
    each member declared. Still identity-isolated from the reviser."""
    async def review(plan: Itinerary) -> list[Objection]:
        objs: list[Objection] = []
        for r in reviewers:
            objs.extend(await r(plan))
        return objs
    review.covers = set().union(*(r.covers for r in reviewers))
    return review


# ---- the reviser: acts on blockers, nothing else --------------------------------

async def revise(plan: Itinerary, blockers: list[Objection]) -> Itinerary:
    drop_all = {o.leg_ref for o in blockers
                if o.issue.startswith("REVERSED-IN-RUN")}
    dedupe = {o.leg_ref for o in blockers
              if o.issue.startswith("DUPLICATE-LINE")}
    seen: set[str] = set()
    legs = []
    for l in plan.legs:
        if l["emp_id"] in drop_all:
            continue
        if l["emp_id"] in dedupe and l["emp_id"] in seen:
            continue
        seen.add(l["emp_id"])
        legs.append(l)
    # TOTAL-MISMATCH is repaired by recomputing from the surviving lines.
    return Itinerary(legs=legs,
                     total_price=round(sum(l["amount"] for l in legs), 2),
                     revision=plan.revision)


# ---- the lab's release decision: gate verdict AND declared coverage -------------

def run_reviewed(plan: Itinerary, reviewer, reviser=None) -> dict:
    out = asyncio.run(AdversarialReview(reviewer, reviser).run(plan))
    gap = sorted(REQUIRED_COVERAGE - getattr(reviewer, "covers", set()))
    out["coverage_gap"] = gap
    if out["outcome"] is Outcome.CONFIRMED and not gap:
        out["release"] = "release"
    elif out["outcome"] is Outcome.CONFIRMED:
        out["release"] = "hold: confirmed only within declared coverage"
    else:
        out["release"] = "hold"
    return out


def seal_receipt(plan: Itinerary, contract) -> object:
    """Bind the confirmed run to the exact contract version that asked for
    it. An ACCEPTED receipt cannot carry blocker findings by construction,
    so the receipt and the ReviewGate enforce the same invariant twice."""
    return _bc.AcceptanceReceipt(
        receipt_id=f"rcpt-{contract.contract_id}-r{plan.revision}",
        contract_digest=contract.digest,
        artifact_id=f"payrun-{bench.MONTH}-r{plan.revision}",
        checked_by="adversarial-panel",
        decision=_bc.AcceptanceDecision.ACCEPTED,
    )


def june_contract():
    return _bc.TaskContract(
        contract_id=f"disburse-{bench.MONTH}", version=1,
        objective="release the June salary run",
        output_schema="payline[] + declared total",
        accountable_owner="finance-controller",
        boundary="only PAID payslips may be disbursed",
    )


# ---- scenes ----------------------------------------------------------------------

def main() -> None:
    con = month_end()
    reviewers = make_reviewers(con)

    if "--blind-spot" not in sys.argv:
        print("== scene 1: the run that would repay two reversed payslips ==")
        draft = draft_from_obligation(con)
        print(f"   draft: {len(draft.legs)} lines, declared {draft.total_price:,.2f}")
        out = run_reviewed(draft, panel(*reviewers), revise)
        for r in out["rounds"]:
            print(f"   round r{r['revision']}: objections={r['objections']} "
                  f"blockers={r['blockers']}")
        plan = out["plan"]
        print(f"   outcome={out['outcome'].value}  release={out['release']}")
        print(f"   final: {len(plan.legs)} lines, total {plan.total_price:,.2f} "
              f"(38,444 stayed in the bank)")
        receipt = seal_receipt(plan, june_contract())
        print(f"   sealed: {receipt.receipt_id} -> contract {receipt.contract_digest}")

        print("\n== scene 2: reviewer is reviser; the guard refuses to run ==")
        async def self_grader(plan, blockers=None):
            return [] if blockers is None else plan
        out = run_reviewed(draft_from_obligation(con), self_grader, self_grader)
        print(f"   outcome={out['outcome'].value}  release={out['release']}")
        print("   -> a self-review is not a review; refusing beats a rubber stamp")

    else:
        print("== scene 3 (--blind-spot): independent is not omniscient ==")
        draft = draft_with_duplicate(con)
        status_reviewer, duplicate_reviewer, reconciliation_reviewer = reviewers

        lone = panel(status_reviewer)
        out = run_reviewed(draft, lone, revise)
        dup_count = sum(1 for l in out["plan"].legs if l["emp_id"] == "E0100")
        print(f"   lone reviewer covers {sorted(lone.covers)}")
        print(f"   outcome={out['outcome'].value}, E0100 lines in confirmed run: "
              f"{dup_count} (double pay, 11,700 extra)")
        print(f"   coverage gap: {out['coverage_gap']}")
        print(f"   release={out['release']}")
        print("   -> the reviewer really is independent, and the gate really is")
        print("      deterministic. CONFIRMED still only means: no blockers among")
        print("      the checks somebody declared. (G3 in stress_collab_gaps.py.)")

        print("\n   full panel over the same run:")
        out = run_reviewed(draft, panel(*reviewers), revise)
        plan = out["plan"]
        print(f"   round r0 blockers={out['rounds'][0]['blockers']}, "
              f"outcome={out['outcome'].value}, release={out['release']}")
        print(f"   final: {len(plan.legs)} lines, total {plan.total_price:,.2f}")


if __name__ == "__main__":
    main()
