"""Lecture 38 payroll lab: reserve a nested effect budget before payment."""
from __future__ import annotations

import sys

from governance_payroll_imports import load_local


governance_lab = load_local("governance_lab")
run_blast_radius = governance_lab.run_blast_radius


def main() -> None:
    result = run_blast_radius(include_third="--overflow" in sys.argv)
    policy = result["policy"]
    print("== containment hierarchy ==")
    print(
        f"   root={policy['root_scope']} "
        f"amount_limit={policy['root_amount_limit']:,.0f}"
    )
    print(
        "   leaf=department::* "
        f"amount_limit={policy['leaf_amount_limit']:,.0f} "
        f"subject_limit={policy['leaf_subject_limit']}"
    )
    print("\n== sibling reservations ==")
    for batch in result["batches"]:
        line = (
            f"   {batch['department']}: "
            f"amount={batch['amount']:,.0f} "
            f"subjects={batch['subject_count']} "
            f"leaf_legal={batch['leaf_legal']} "
            f"decision={batch['decision']}"
        )
        print(line)
        if batch["blocked_at"]:
            print(f"      blocked_at={batch['blocked_at']}")
        else:
            print(f"      root_reserved={batch['root_after']:,.0f}")
    print(f"   payment_effects={result['state']['payment_count']}")


if __name__ == "__main__":
    main()
