"""Progressive Discovery pattern.

Reference implementation of the agentic-search pattern from column lecture
02-04. The pattern is the engineering core of the "Claude Code dropped RAG
for grep + read" industrial reversal of 2025-2026.

Three phases in a bounded loop:

* **FORAGE** — broad scan with grep / glob to surface ~30 candidate paths
  (Pirolli & Card 1999 "information foraging")
* **FOCUS** — pick ~5-8 highest-scoring candidates and read them in full
* **DEEPEN** — follow imports / call chains / references from those files
  to surface secondary candidates

If the first cycle doesn't find sufficient signal, keywords are refined
from what was learned and a new cycle starts. Bounded by a per-cycle
token budget and a max-cycles cap. Every phase logs a trace event for
post-hoc analysis.

The pattern's invariant: **at no point do we pre-embed the entire
codebase**. Discovery is on-demand, structure-aware, and bounded.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Callable


class Phase(Enum):
    FORAGE = "forage"
    FOCUS = "focus"
    DEEPEN = "deepen"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Candidate:
    """A file path that surfaced during foraging."""

    path: str
    score: float = 0.0
    snippet: str = ""        # grep-matched line + small context
    reason: str = ""         # why this candidate is in the pool


@dataclass
class DiscoveryEvent:
    """One atomic record of a phase execution."""

    phase: Phase
    keyword: str = ""
    candidates_in: int = 0
    candidates_out: int = 0
    files_read: int = 0
    tokens_used: int = 0
    wall_time_ms: int = 0
    timestamp: str = field(default_factory=_now_iso)


@dataclass
class DiscoverySession:
    """One full forage-focus-deepen run, possibly multi-cycle."""

    task: str
    events: list[DiscoveryEvent] = field(default_factory=list)
    cycle_count: int = 0
    final_files: list[str] = field(default_factory=list)
    success: bool = False
    total_tokens: int = 0

    def log(self, event: DiscoveryEvent) -> None:
        self.events.append(event)
        self.total_tokens += event.tokens_used


# Sufficient-signal callable: given (file_contents, task) -> bool.
# Default falls back to a coarse heuristic if you don't pass one in.
SignalFn = Callable[[dict[str, str], str], bool]


class ProgressiveDiscoverer:
    """Three-phase bounded loop with trace logging and budget control."""

    def __init__(
        self,
        grep_tool: Callable[[str], list[Candidate]],
        read_tool: Callable[[str], str],
        scorer: Callable[[Candidate, str], float],
        max_cycles: int = 3,
        budget_per_cycle: int = 20_000,
        signal_fn: SignalFn | None = None,
        forage_top_k: int = 30,
        focus_top_k: int = 8,
        deepen_top_k: int = 5,
    ) -> None:
        self.grep = grep_tool
        self.read = read_tool
        self.scorer = scorer
        self.max_cycles = max_cycles
        self.budget = budget_per_cycle
        self.signal_fn = signal_fn or _default_signal
        self.forage_top_k = forage_top_k
        self.focus_top_k = focus_top_k
        self.deepen_top_k = deepen_top_k

    # ──────────────── public ────────────────

    def discover(
        self,
        task: str,
        initial_keywords: list[str],
        refine_keywords: Callable[[dict[str, str], str], list[str]] | None = None,
    ) -> DiscoverySession:
        session = DiscoverySession(task=task)
        keywords = initial_keywords
        file_contents: dict[str, str] = {}

        for cycle in range(self.max_cycles):
            session.cycle_count = cycle + 1
            cycle_tokens = 0

            # FORAGE
            t0 = datetime.now(timezone.utc)
            all_candidates: list[Candidate] = []
            for kw in keywords:
                all_candidates.extend(self.grep(kw))
            for c in all_candidates:
                c.score = self.scorer(c, task)
            all_candidates.sort(key=lambda c: c.score, reverse=True)
            top_candidates = all_candidates[: self.forage_top_k]
            forage_tokens = sum(len(c.snippet) for c in all_candidates) // 4
            cycle_tokens += forage_tokens
            session.log(DiscoveryEvent(
                phase=Phase.FORAGE,
                keyword=" | ".join(keywords),
                candidates_in=len(all_candidates),
                candidates_out=len(top_candidates),
                tokens_used=forage_tokens,
                wall_time_ms=_ms_since(t0),
            ))
            if cycle_tokens > self.budget:
                break

            # FOCUS
            t0 = datetime.now(timezone.utc)
            focused = top_candidates[: self.focus_top_k]
            for c in focused:
                file_contents[c.path] = self.read(c.path)
            focus_tokens = sum(len(v) for v in file_contents.values()) // 4
            cycle_tokens += focus_tokens
            session.log(DiscoveryEvent(
                phase=Phase.FOCUS,
                candidates_in=len(top_candidates),
                candidates_out=len(focused),
                files_read=len(focused),
                tokens_used=focus_tokens,
                wall_time_ms=_ms_since(t0),
            ))
            if cycle_tokens > self.budget:
                session.final_files = list(file_contents.keys())
                session.success = self.signal_fn(file_contents, task)
                break

            # DEEPEN
            t0 = datetime.now(timezone.utc)
            deeper_paths = self._extract_dependencies(file_contents)
            deeper_paths = deeper_paths[: self.deepen_top_k]
            for p in deeper_paths:
                if p not in file_contents:
                    file_contents[p] = self.read(p)
            deepen_tokens = (
                sum(len(file_contents.get(p, "")) for p in deeper_paths) // 4
            )
            cycle_tokens += deepen_tokens
            session.log(DiscoveryEvent(
                phase=Phase.DEEPEN,
                files_read=len(deeper_paths),
                tokens_used=deepen_tokens,
                wall_time_ms=_ms_since(t0),
            ))

            session.final_files = list(file_contents.keys())
            if self.signal_fn(file_contents, task):
                session.success = True
                break
            # Otherwise refine keywords and loop
            if refine_keywords is not None:
                keywords = refine_keywords(file_contents, task)
            else:
                keywords = self._default_refine(file_contents, task)

        return session

    def health_check(self, session: DiscoverySession) -> dict[str, str]:
        """Run on each session to flag drift / over-cost / phase imbalance."""
        report: dict[str, str] = {}
        if session.cycle_count >= self.max_cycles and not session.success:
            report["max_cycles_hit"] = (
                f"Used all {self.max_cycles} cycles without sufficient signal — "
                "keywords too generic"
            )
        if session.total_tokens > self.budget * session.cycle_count:
            report["over_budget"] = (
                f"Used {session.total_tokens} tokens over {session.cycle_count} "
                f"cycles, budget was {self.budget * session.cycle_count}"
            )
        phase_tokens = {Phase.FORAGE: 0, Phase.FOCUS: 0, Phase.DEEPEN: 0}
        for e in session.events:
            phase_tokens[e.phase] += e.tokens_used
        if phase_tokens[Phase.FORAGE] > phase_tokens[Phase.FOCUS]:
            report["forage_too_heavy"] = (
                "Forage out-spent focus — keywords too broad, dropping "
                "useful signal in the noise"
            )
        return report

    # ──────────────── internals ────────────────

    def _extract_dependencies(self, file_contents: dict[str, str]) -> list[str]:
        """Pull import / require / include targets out of read files."""
        deps: set[str] = set()
        for content in file_contents.values():
            for line in content.split("\n")[:80]:
                m = re.match(
                    r"(?:from|import|require|include)\s+['\"]?([\w./-]+)",
                    line.strip(),
                )
                if m:
                    deps.add(m.group(1))
        return sorted(deps)

    def _default_refine(
        self, file_contents: dict[str, str], task: str
    ) -> list[str]:
        """Lightweight refine: pull the most-frequent identifiers from what we read."""
        tokens: dict[str, int] = {}
        for content in file_contents.values():
            for word in re.findall(r"[a-z_][a-z0-9_]{4,}", content.lower())[:200]:
                tokens[word] = tokens.get(word, 0) + 1
        ranked = sorted(tokens.items(), key=lambda kv: kv[1], reverse=True)[:3]
        return [w for w, _ in ranked] or ["TODO"]


def _default_signal(file_contents: dict[str, str], task: str) -> bool:
    """Coarse fallback — production should use an LLM judge."""
    return len(file_contents) >= 5


def _ms_since(t0: datetime) -> int:
    return int((datetime.now(timezone.utc) - t0).total_seconds() * 1000)
