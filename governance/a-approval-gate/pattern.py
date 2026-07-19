"""Approval Gate pattern.

The gate routes an immutable ``ActionProposal`` to one of three outcomes:
automatic allow, human review, or deterministic deny. Human approval is a
version-bound receipt, not a chat message or a mutable ``approved`` flag.

The gate must not:

* let the proposal maker approve its own high-risk effect;
* reuse an approval after the proposal or policy changes;
* treat one person wearing two roles as two-person review;
* default to allow when a ticket expires or no approver is available.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Callable


sys.path.insert(0, str(Path(__file__).parent.parent))

from boundary_contract import (  # noqa: E402
    ActionProposal,
    ControlDecision,
    FindingSeverity,
    GovernanceFinding,
    GovernanceReceipt,
    PolicyRef,
    Reversibility,
    RiskLevel,
)


class ApprovalRoute(str, Enum):
    AUTO_ALLOW = "auto_allow"
    HUMAN_REVIEW = "human_review"
    DENY = "deny"


@dataclass(frozen=True)
class ApprovalPolicy:
    policy_id: str = "approval-gate"
    version: int = 1
    auto_allow_max_amount: float = 10_000.0
    auto_allow_max_subjects: int = 10
    deny_above_amount: float = 20_000_000.0
    required_roles: tuple[str, ...] = ("payroll-controller", "treasury-controller")
    denied_actions: tuple[str, ...] = ()
    human_review_risks: tuple[RiskLevel, ...] = (RiskLevel.HIGH, RiskLevel.CRITICAL)
    irreversible_requires_human: bool = True
    ticket_ttl_minutes: int = 30

    def __post_init__(self) -> None:
        if not self.policy_id.strip():
            raise ValueError("policy_id must not be empty")
        if self.version < 1:
            raise ValueError("policy version must be at least 1")
        if self.auto_allow_max_amount < 0:
            raise ValueError("auto_allow_max_amount must not be negative")
        if self.auto_allow_max_subjects < 0:
            raise ValueError("auto_allow_max_subjects must not be negative")
        if self.deny_above_amount <= self.auto_allow_max_amount:
            raise ValueError("deny_above_amount must exceed the auto-allow limit")
        if not self.required_roles or len(set(self.required_roles)) != len(self.required_roles):
            raise ValueError("required_roles must be unique and non-empty")
        if self.ticket_ttl_minutes < 1:
            raise ValueError("ticket_ttl_minutes must be positive")

    @property
    def ref(self) -> PolicyRef:
        return PolicyRef.from_content(
            self.policy_id,
            self.version,
            {
                "auto_allow_max_amount": self.auto_allow_max_amount,
                "auto_allow_max_subjects": self.auto_allow_max_subjects,
                "deny_above_amount": self.deny_above_amount,
                "required_roles": self.required_roles,
                "denied_actions": self.denied_actions,
                "human_review_risks": tuple(level.name for level in self.human_review_risks),
                "irreversible_requires_human": self.irreversible_requires_human,
                "ticket_ttl_minutes": self.ticket_ttl_minutes,
            },
        )


@dataclass(frozen=True)
class ApprovalAttestation:
    approver_id: str
    role: str
    approved: bool
    decided_at: str

    def __post_init__(self) -> None:
        if not self.approver_id.strip() or not self.role.strip():
            raise ValueError("approval identity fields must not be empty")


@dataclass(frozen=True)
class ApprovalTicket:
    ticket_id: str
    proposal_digest: str
    policy_digest: str
    requester_id: str
    required_roles: tuple[str, ...]
    reason_codes: tuple[str, ...]
    created_at: str
    expires_at: str
    attestations: tuple[ApprovalAttestation, ...] = ()

    @property
    def approved_roles(self) -> tuple[str, ...]:
        return tuple(
            attestation.role
            for attestation in self.attestations
            if attestation.approved
        )

    @property
    def complete(self) -> bool:
        return set(self.required_roles) <= set(self.approved_roles)


@dataclass(frozen=True)
class ApprovalEvaluation:
    route: ApprovalRoute
    receipt: GovernanceReceipt
    ticket: ApprovalTicket | None = None


class ApprovalError(RuntimeError):
    """Raised when an approval attempts to cross a version or role boundary."""


ApproverRoleResolver = Callable[[str], tuple[str, ...]]


def _parse(instant: str) -> datetime:
    value = datetime.fromisoformat(instant)
    if value.tzinfo is None:
        raise ValueError("timestamps must include a timezone")
    return value


class ApprovalGate:
    """Risk router plus maker-checker human review."""

    def __init__(
        self,
        policy: ApprovalPolicy | None = None,
        *,
        role_resolver: ApproverRoleResolver | None = None,
    ) -> None:
        self.policy = policy or ApprovalPolicy()
        self._role_resolver = role_resolver
        self._tickets: dict[str, ApprovalTicket] = {}
        self._proposals: dict[str, ActionProposal] = {}
        self._final_receipts: dict[str, GovernanceReceipt] = {}

    def evaluate(self, proposal: ActionProposal, *, now: str) -> ApprovalEvaluation:
        _parse(now)
        self._proposals[proposal.digest] = proposal
        reasons = self._reason_codes(proposal)

        if "action_denied" in reasons or "amount_above_hard_limit" in reasons:
            receipt = self._receipt(
                proposal,
                decision=ControlDecision.DENIED,
                decided_by="approval-router",
                issued_at=now,
                findings=tuple(
                    GovernanceFinding(
                        code,
                        self._message(code),
                        f"policy://{self.policy.policy_id}/v{self.policy.version}",
                    )
                    for code in reasons
                    if code in {"action_denied", "amount_above_hard_limit"}
                ),
            )
            self._final_receipts[proposal.digest] = receipt
            return ApprovalEvaluation(ApprovalRoute.DENY, receipt)

        if reasons:
            expires = (
                _parse(now) + timedelta(minutes=self.policy.ticket_ttl_minutes)
            ).isoformat()
            ticket = ApprovalTicket(
                ticket_id=f"approval::{proposal.proposal_id}::v{proposal.version}",
                proposal_digest=proposal.digest,
                policy_digest=self.policy.ref.digest,
                requester_id=proposal.requested_by,
                required_roles=self.policy.required_roles,
                reason_codes=reasons,
                created_at=now,
                expires_at=expires,
            )
            self._tickets[ticket.ticket_id] = ticket
            receipt = self._receipt(
                proposal,
                decision=ControlDecision.PENDING,
                decided_by="approval-router",
                issued_at=now,
                expires_at=expires,
                findings=tuple(
                    GovernanceFinding(
                        code,
                        self._message(code),
                        f"proposal://{proposal.digest}",
                        FindingSeverity.INFO,
                    )
                    for code in reasons
                ),
                evidence_refs=(f"approval://{ticket.ticket_id}",),
            )
            return ApprovalEvaluation(ApprovalRoute.HUMAN_REVIEW, receipt, ticket)

        receipt = self._receipt(
            proposal,
            decision=ControlDecision.ALLOWED,
            decided_by="approval-router",
            issued_at=now,
            evidence_refs=(f"policy://{self.policy.policy_id}/v{self.policy.version}",),
        )
        self._final_receipts[proposal.digest] = receipt
        return ApprovalEvaluation(ApprovalRoute.AUTO_ALLOW, receipt)

    def attest(
        self,
        ticket_id: str,
        *,
        approver_id: str,
        role: str,
        approved: bool,
        at: str,
    ) -> ApprovalEvaluation:
        ticket = self._tickets.get(ticket_id)
        if ticket is None:
            raise ApprovalError("unknown approval ticket")
        proposal = self._proposals[ticket.proposal_digest]
        if ticket.proposal_digest in self._final_receipts:
            raise ApprovalError("approval ticket is already closed")
        if ticket.policy_digest != self.policy.ref.digest:
            raise ApprovalError("approval ticket belongs to another policy version")
        if _parse(at) > _parse(ticket.expires_at):
            receipt = self._receipt(
                proposal,
                decision=ControlDecision.DENIED,
                decided_by="approval-gate",
                issued_at=at,
                findings=(
                    GovernanceFinding(
                        "approval_expired",
                        "approval ticket expired before all required roles signed",
                        f"approval://{ticket.ticket_id}",
                    ),
                ),
                evidence_refs=(f"approval://{ticket.ticket_id}",),
            )
            self._final_receipts[proposal.digest] = receipt
            return ApprovalEvaluation(ApprovalRoute.DENY, receipt, ticket)
        if role not in ticket.required_roles:
            raise ApprovalError(f"role {role!r} is not required by this ticket")
        if approver_id == ticket.requester_id:
            raise ApprovalError("the proposal maker cannot approve its own effect")
        if self._role_resolver is None:
            raise ApprovalError("a trusted approver role resolver is required")
        if role not in self._role_resolver(approver_id):
            raise ApprovalError(
                f"identity provider does not grant {role!r} to {approver_id!r}"
            )
        if any(item.approver_id == approver_id for item in ticket.attestations):
            raise ApprovalError("one approver cannot satisfy multiple review roles")
        if any(item.role == role for item in ticket.attestations):
            raise ApprovalError(f"role {role!r} has already attested")

        updated = replace(
            ticket,
            attestations=ticket.attestations
            + (ApprovalAttestation(approver_id, role, approved, at),),
        )
        self._tickets[ticket_id] = updated

        if not approved:
            receipt = self._receipt(
                proposal,
                decision=ControlDecision.DENIED,
                decided_by=approver_id,
                issued_at=at,
                findings=(
                    GovernanceFinding(
                        "human_rejected",
                        f"{role} rejected the requested effect",
                        f"approval://{ticket.ticket_id}/{approver_id}",
                    ),
                ),
                evidence_refs=self._attestation_refs(updated),
            )
            self._final_receipts[proposal.digest] = receipt
            return ApprovalEvaluation(ApprovalRoute.DENY, receipt, updated)

        if updated.complete:
            receipt = self._receipt(
                proposal,
                decision=ControlDecision.ALLOWED,
                decided_by="approval-panel",
                issued_at=at,
                expires_at=updated.expires_at,
                evidence_refs=self._attestation_refs(updated),
            )
            self._final_receipts[proposal.digest] = receipt
            return ApprovalEvaluation(ApprovalRoute.HUMAN_REVIEW, receipt, updated)

        receipt = self._receipt(
            proposal,
            decision=ControlDecision.PENDING,
            decided_by=approver_id,
            issued_at=at,
            expires_at=updated.expires_at,
            evidence_refs=self._attestation_refs(updated),
        )
        return ApprovalEvaluation(ApprovalRoute.HUMAN_REVIEW, receipt, updated)

    def authorize(
        self,
        proposal: ActionProposal,
        receipt: GovernanceReceipt,
        *,
        at: str,
    ) -> bool:
        return receipt.authorizes(proposal, self.policy.ref, at=at)

    def _reason_codes(self, proposal: ActionProposal) -> tuple[str, ...]:
        reasons: list[str] = []
        if proposal.action in self.policy.denied_actions:
            reasons.append("action_denied")
        if proposal.amount > self.policy.deny_above_amount:
            reasons.append("amount_above_hard_limit")
        if proposal.amount > self.policy.auto_allow_max_amount:
            reasons.append("amount_requires_review")
        if proposal.subject_count > self.policy.auto_allow_max_subjects:
            reasons.append("subject_count_requires_review")
        if proposal.risk in self.policy.human_review_risks:
            reasons.append("risk_requires_review")
        if (
            self.policy.irreversible_requires_human
            and proposal.reversibility is Reversibility.IRREVERSIBLE
        ):
            reasons.append("irreversible_effect")
        return tuple(dict.fromkeys(reasons))

    @staticmethod
    def _message(code: str) -> str:
        return {
            "action_denied": "the requested action is denied by policy",
            "amount_above_hard_limit": "amount exceeds the deterministic deny limit",
            "amount_requires_review": "amount exceeds the automatic approval limit",
            "subject_count_requires_review": "subject count exceeds the automatic limit",
            "risk_requires_review": "risk level requires human review",
            "irreversible_effect": "an irreversible effect requires human review",
        }[code]

    def _receipt(
        self,
        proposal: ActionProposal,
        *,
        decision: ControlDecision,
        decided_by: str,
        issued_at: str,
        expires_at: str | None = None,
        findings: tuple[GovernanceFinding, ...] = (),
        evidence_refs: tuple[str, ...] = (),
    ) -> GovernanceReceipt:
        return GovernanceReceipt(
            receipt_id=f"approval-receipt::{proposal.proposal_id}::{decision.value}",
            control="approval-gate",
            proposal_digest=proposal.digest,
            policy_digest=self.policy.ref.digest,
            decided_by=decided_by,
            decision=decision,
            issued_at=issued_at,
            expires_at=expires_at,
            findings=findings,
            evidence_refs=evidence_refs,
        )

    @staticmethod
    def _attestation_refs(ticket: ApprovalTicket) -> tuple[str, ...]:
        return tuple(
            f"approval://{ticket.ticket_id}/{item.role}/{item.approver_id}"
            for item in ticket.attestations
        )
