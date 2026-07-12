"""Generator-Critic pattern.

Reference implementation from column lecture 06-02 (27). The claim:
**a critic is only as good as the external signals wired into it.**
A critic that re-reads the draft can check format and consistency; only
a critic wired to reconciliation tests, schemas, and databases can check
truth. And "no changes needed" must be a legal verdict -- a critic that
is not allowed to approve will invent problems, and the revisions then
degrade a correct draft.

Chain topology, not a loop: generate -> critique -> revise, bounded by
`max_rounds` (Aider hardcodes 3 in base_coder.py and stops with a warning).
Exhausted rounds hand the draft to a human; the last draft is never
silently shipped.

Three roles:

* `Finding` — one critique finding: which check produced it, severity,
  message, and **evidence**. The meta-gate drops findings that carry no
  evidence (they are logged, not acted on). This is "who checks the
  critic": a critic hallucinating a problem cannot trigger a revision.
* `Critic` — a bundle of named checks. Each check is deterministic code
  or a tool / database call. LLM-based checks are allowed, but they must
  attach evidence like everyone else.
* `GeneratorCritic` — runs the chain, records the full trace, stops on a
  clean verdict or exhausted rounds. Severity matters: findings below
  `block_at` are recorded but do not trigger another round, which is
  what closes the nitpick spiral.

Named failure modes:

* **Rubber stamp** — a critic with no external signal approves anything
  that reads well. Lecture 26's introspection demo, at pattern level.
* **Invented problems** — a critic that may not approve always finds
  something. Closed by making the clean verdict legal and by the
  evidence gate.
* **Nitpick spiral** — style findings trigger endless revision. Closed
  by `block_at` + the round budget.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import IntEnum
from typing import Callable


class Severity(IntEnum):
    MINOR = 1      # style, wording — recorded, never blocks
    MAJOR = 2      # wrong structure, missing required parts
    BLOCKER = 3    # contradicts an external source of truth


@dataclass
class Finding:
    """One critique finding. `evidence` is what the check actually saw —
    a ledger count, a schema key, a policy clause. Empty evidence means
    the finding is an opinion, and opinions do not trigger revisions."""

    check: str
    severity: Severity
    message: str
    evidence: str = ""


@dataclass
class CritiqueReport:
    round: int
    findings: list[Finding] = field(default_factory=list)
    dropped: list[Finding] = field(default_factory=list)   # failed the evidence gate

    def blocking(self, block_at: Severity) -> list[Finding]:
        return [f for f in self.findings if f.severity >= block_at]


# A check inspects the draft and returns findings (possibly none).
CheckFn = Callable[[str], list[Finding]]
# A generator takes the brief + the blocking findings from the last round
# and returns a (possibly revised) draft.
GeneratorFn = Callable[[str, list[Finding]], str]


class Critic:
    """A bundle of named external checks + the evidence meta-gate."""

    def __init__(self, checks: dict[str, CheckFn]) -> None:
        self.checks = checks

    def review(self, draft: str, round_no: int) -> CritiqueReport:
        report = CritiqueReport(round=round_no)
        for name, check in self.checks.items():
            for finding in check(draft):
                if finding.evidence:
                    report.findings.append(finding)
                else:
                    report.dropped.append(finding)
        return report


@dataclass
class GCRound:
    draft: str
    report: CritiqueReport


@dataclass
class GCTrace:
    brief: str
    rounds: list[GCRound] = field(default_factory=list)
    final_draft: str = ""
    status: str = "pending"        # clean | rounds_exhausted
    started_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat())


class GeneratorCritic:
    """The bounded generate -> critique -> revise chain."""

    def __init__(
        self,
        generator: GeneratorFn,
        critic: Critic,
        max_rounds: int = 3,
        block_at: Severity = Severity.MAJOR,
    ) -> None:
        self.generator = generator
        self.critic = critic
        self.max_rounds = max_rounds
        self.block_at = block_at

    def run(self, brief: str) -> GCTrace:
        trace = GCTrace(brief=brief)
        blocking: list[Finding] = []
        for round_no in range(1, self.max_rounds + 1):
            draft = self.generator(brief, blocking)
            report = self.critic.review(draft, round_no)
            trace.rounds.append(GCRound(draft=draft, report=report))
            blocking = report.blocking(self.block_at)
            if not blocking:
                trace.final_draft = draft
                trace.status = "clean"
                return trace
        # Rounds exhausted: never silently ship the last draft.
        trace.final_draft = trace.rounds[-1].draft
        trace.status = "rounds_exhausted"
        return trace
