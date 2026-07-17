"""Invariant tests for the lecture-34 adversarial-review lab."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).parent


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


lab = _load(HERE / "adversarial_review_lab.py", "review_lab")
_rev = sys.modules["review_pattern"]
_bc = sys.modules["collab_contract"]

GROSS = 13_744_541.0
NET = 13_706_097.0


def test_reversed_lines_are_blocked_then_the_loop_converges():
    con = lab.month_end()
    draft = lab.draft_from_obligation(con)
    assert draft.total_price == GROSS
    out = lab.run_reviewed(draft, lab.panel(*lab.make_reviewers(con)), lab.revise)
    assert out["outcome"] is _rev.Outcome.CONFIRMED
    assert out["release"] == "release"
    assert out["rounds"][0]["blockers"] >= 2          # E0007, E0012 at least
    ids = [l["emp_id"] for l in out["plan"].legs]
    assert "E0007" not in ids and "E0012" not in ids
    assert out["plan"].total_price == NET             # 38,444 stayed in the bank


def test_gate_is_deterministic_and_a_warning_does_not_hold():
    gate = _rev.ReviewGate()
    warn = _rev.Objection(_rev.Severity.WARNING, "E0001", "note")
    block = _rev.Objection(_rev.Severity.BLOCKER, "E0001", "fault")
    assert gate.may_confirm([]) and gate.may_confirm([warn])
    assert not gate.may_confirm([warn, block])


def test_self_review_is_refused_not_run():
    con = lab.month_end()

    async def self_grader(plan, blockers=None):
        return [] if blockers is None else plan

    out = lab.run_reviewed(lab.draft_from_obligation(con), self_grader, self_grader)
    assert out["outcome"] is _rev.Outcome.NO_REVIEWER
    assert out["release"] == "hold"


def test_blind_spot_confirms_the_double_pay():
    con = lab.month_end()
    status_reviewer, _, _ = lab.make_reviewers(con)
    lone = lab.panel(status_reviewer)
    out = lab.run_reviewed(lab.draft_with_duplicate(con), lone, lab.revise)
    assert out["outcome"] is _rev.Outcome.CONFIRMED   # the gate really confirmed
    dup = [l for l in out["plan"].legs if l["emp_id"] == "E0100"]
    assert len(dup) == 2                              # ... with the double pay inside
    assert out["coverage_gap"] == ["duplicate-line", "total-reconciliation"]
    assert out["release"].startswith("hold")          # coverage gate refuses release


def test_full_panel_catches_the_duplicate_and_reconciles():
    con = lab.month_end()
    out = lab.run_reviewed(lab.draft_with_duplicate(con),
                           lab.panel(*lab.make_reviewers(con)), lab.revise)
    assert out["outcome"] is _rev.Outcome.CONFIRMED
    assert out["release"] == "release"
    ids = [l["emp_id"] for l in out["plan"].legs]
    assert ids.count("E0100") == 1
    assert out["plan"].total_price == NET


def test_blockers_without_a_reviser_are_held_for_a_human():
    con = lab.month_end()
    out = lab.run_reviewed(lab.draft_from_obligation(con),
                           lab.panel(*lab.make_reviewers(con)), reviser=None)
    assert out["outcome"] is _rev.Outcome.HELD_FOR_HUMAN
    assert out["release"] == "hold"


def test_receipt_and_gate_enforce_the_same_invariant():
    con = lab.month_end()
    out = lab.run_reviewed(lab.draft_from_obligation(con),
                           lab.panel(*lab.make_reviewers(con)), lab.revise)
    receipt = lab.seal_receipt(out["plan"], lab.june_contract())
    assert receipt.accepted
    assert receipt.contract_digest == lab.june_contract().digest
    # The contract layer refuses what the gate refuses: an ACCEPTED receipt
    # cannot carry a blocker finding.
    with pytest.raises(ValueError):
        _bc.AcceptanceReceipt(
            receipt_id="rcpt-x", contract_digest=receipt.contract_digest,
            artifact_id="payrun-x", checked_by="adversarial-panel",
            decision=_bc.AcceptanceDecision.ACCEPTED,
            findings=(_bc.Finding(code="REVERSED-IN-RUN", field="E0007",
                                  message="reversed payslip in run",
                                  evidence="payroll.status=REVERSED"),),
        )
