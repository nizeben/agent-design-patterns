"""Invariant tests for the Generator-Critic reference interface."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest


HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
sys.modules.pop("pattern", None)

from pattern import (  # noqa: E402
    AcceptancePolicy,
    Artifact,
    Critique,
    Decision,
    GeneratorCriticChain,
    Issue,
    Severity,
)


def grounded_blocker(message: str = "missing evidence") -> Issue:
    return Issue(
        Severity.BLOCKER,
        message,
        "report",
        "ledger query returned a conflicting count",
        "ledger_reconciliation",
    )


def test_policy_accepts_clean_high_score_artifact() -> None:
    critique = Critique(score=0.92, issues=[], summary="clear")

    assert AcceptancePolicy().decide(critique) is Decision.ACCEPTED


def test_policy_rejects_grounded_low_score_or_grounded_blocker() -> None:
    low_score = Critique(
        score=0.71,
        issues=[],
        summary="thin",
        score_evidence="rubric completeness=0.71",
    )
    blocked = Critique(score=0.95, issues=[grounded_blocker()], summary="unsafe")

    assert AcceptancePolicy().decide(low_score) is Decision.NEEDS_REVISION
    assert AcceptancePolicy().decide(blocked) is Decision.NEEDS_REVISION


def test_ungrounded_opinion_cannot_trigger_automatic_revision() -> None:
    opinion = Issue(Severity.BLOCKER, "the report feels thin", "body")
    critique = Critique(score=0.5, issues=[opinion], summary="one opinion")

    assert AcceptancePolicy(require_evidence=True).decide(critique) is Decision.ACCEPTED
    assert AcceptancePolicy(require_evidence=False).decide(critique) is Decision.NEEDS_REVISION


def test_critique_score_must_be_unit_interval() -> None:
    with pytest.raises(ValueError, match="score"):
        Critique(score=1.2, issues=[], summary="invalid")


def test_chain_calls_critic_once_and_accepts_reviewed_artifact() -> None:
    calls: list[str] = []

    def generator(prompt: str) -> Artifact:
        calls.append(f"generate:{prompt}")
        return Artifact("sourced report")

    def critic(artifact: Artifact) -> Critique:
        calls.append(f"critic:{artifact.content}")
        return Critique(0.92, [], "ready")

    result = GeneratorCriticChain(generator, critic).run("monthly report")

    assert result.decision is Decision.ACCEPTED
    assert result.reviewed_artifact.content == "sourced report"
    assert result.revision_draft is None
    assert calls == ["generate:monthly report", "critic:sourced report"]
    assert result.trace == ("generated", "critiqued", "accepted")


def test_revision_draft_is_separate_and_never_auto_accepted() -> None:
    critic_calls = 0

    def generator(_prompt: str) -> Artifact:
        return Artifact("paid=800")

    def critic(_artifact: Artifact) -> Critique:
        nonlocal critic_calls
        critic_calls += 1
        return Critique(0.4, [grounded_blocker("paid count mismatch")], "wrong")

    def reviser(artifact: Artifact, _critique: Critique) -> Artifact:
        return artifact.revise("paid=798", note="reconciled with ledger")

    result = GeneratorCriticChain(generator, critic, reviser).run("report")

    assert result.decision is Decision.NEEDS_REVISION
    assert result.reviewed_artifact.content == "paid=800"
    assert result.revision_draft.content == "paid=798"
    assert result.requires_re_review is True
    assert critic_calls == 1
    assert result.trace[-1] == "revision_drafted"


def test_revision_is_accepted_only_by_an_explicit_second_pass() -> None:
    def critic(artifact: Artifact) -> Critique:
        if "paid=798" in artifact.content:
            return Critique(0.95, [], "reconciled")
        return Critique(0.4, [grounded_blocker()], "wrong")

    chain = GeneratorCriticChain(
        generator=lambda _prompt: Artifact("paid=800"),
        critic=critic,
        reviser=lambda artifact, _critique: artifact.revise("paid=798"),
    )

    first = chain.run("report")
    second = chain.review(first.revision_draft)

    assert first.decision is Decision.NEEDS_REVISION
    assert second.decision is Decision.ACCEPTED
    assert second.reviewed_artifact.revision == 1
    assert second.trace == ("artifact_received", "critiqued", "accepted")
