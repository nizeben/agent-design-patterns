"""Lecture 37 payroll lab: route, attest, and bind a high-risk approval."""
from __future__ import annotations

import sys

from governance_payroll_imports import load_local


bench = load_local("bench")
governance_lab = load_local("governance_lab")
run_approval_gate = governance_lab.run_approval_gate


def main() -> None:
    result = run_approval_gate(changed_after_approval="--changed" in sys.argv)
    print("== approval route ==")
    print(f"   route={result['route']['name']}")
    print(f"   reasons={list(result['route']['reason_codes'])}")
    print(f"   decision={result['timeline'][0]['decision']}")
    print(f"   ticket_expires={result['ticket']['expires_at']}")

    print("\n== two-person review ==")
    print(
        "   approvers="
        + ", ".join(
            f"{item['approver_id']}:{item['role']}"
            for item in result["attestations"]
        )
    )
    print(f"   decision={result['final_receipt']['decision']}")
    print(f"   proposal_digest={result['proposal']['digest']}")

    if "changed" in result:
        print("\n== changed after approval ==")
        print(f"   changed_digest={result['changed']['changed_digest']}")
        print(f"   changed_amount={result['changed']['changed_amount']:,.2f}")
        print(
            "   old_approval_authorizes="
            f"{result['changed']['old_approval_authorizes']}"
        )
        print(f"   adapter={result['changed']['adapter_result']}")


if __name__ == "__main__":
    main()
