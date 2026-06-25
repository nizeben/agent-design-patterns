"""Shared gate factories for the Prompt Chaining reference implementations.

Both langgraph/ and langchain/ notebooks import from here, so the gate
definitions stay in sync between the two frameworks. These are a
notebook-friendly variant of the gates in pattern.py: same checks, but each
factory returns a config **dict** `{"name", "fn", "description"}` (rather than
a bare callable) so the trace can print a stable name and description.

Gate-fn contract: (output: str) -> bool
  True  = output accepted, pass to next step
  False = output rejected, retry or fail
A gate's callable lives at `gate["fn"]`; call it as `gate["fn"](output)`.

This is a small gate *library* — the tutorials demo `length_gate` and
`starts_with_gate`; `keys_gate`, `json_gate`, `regex_gate`, `any_gate`, and
`all_gate` are here as ready-to-use building blocks for your own steps.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Callable

GateFn = Callable[[str], bool]


class StepStatus(str, Enum):
    SUCCESS = "success"
    GATE_FAILED = "gate_failed"
    RETRY_EXHAUSTED = "retry_exhausted"
    LLM_ERROR = "llm_error"


# ---------------------------------------------------------------------------
# Gate factories — notebook-friendly dict variants of the pattern.py gates
# ---------------------------------------------------------------------------


def length_gate(min_chars: int, max_chars: int, *, name: str | None = None) -> dict[str, Any]:
    """Length-bound gate. Most common; also most prone to gate tyranny.

    Measures `len(output)` (not stripped) to match pattern.py.length_gate.
    """
    def fn(output: str) -> bool:
        return min_chars <= len(output) <= max_chars

    return {
        "name": name or f"length[{min_chars}-{max_chars}]",
        "fn": fn,
        "description": f"output length between {min_chars} and {max_chars} chars",
    }


def keys_gate(required_keys: list[str], *, name: str | None = None) -> dict[str, Any]:
    """Output must contain all required substrings (substring match anywhere).

    For an anchored verdict like "starts with 'verified'", use starts_with_gate
    — substring matching would let 'unverified' satisfy a 'verified' check.
    """
    def fn(output: str) -> bool:
        return all(key in output for key in required_keys)

    return {
        # Name lists every key (no truncation) so two gates that differ only in
        # later keys stay distinguishable in the trace.
        "name": name or f"keys[{','.join(required_keys)}]",
        "fn": fn,
        "description": f"output must contain: {required_keys}",
    }


def starts_with_gate(prefixes: list[str], *, name: str | None = None) -> dict[str, Any]:
    """Output (stripped, case-insensitive) must START with one of `prefixes`.

    Use for one-word verdicts where a substring match would be wrong:
    keys_gate(['verified']) accepts 'unverified', but
    starts_with_gate(['verified', 'discrepancy']) rejects it.
    """
    lowered = [p.lower() for p in prefixes]

    def fn(output: str) -> bool:
        head = output.strip().lower()
        return any(head.startswith(p) for p in lowered)

    return {
        "name": name or f"starts_with[{','.join(prefixes)}]",
        "fn": fn,
        "description": f"output must start with one of: {prefixes}",
    }


def json_gate(required_fields: list[str] | None = None, *, name: str | None = None) -> dict[str, Any]:
    """Output must be valid JSON; optionally must contain required top-level keys.

    When required_fields is given, the JSON must be an object that contains
    them — a non-object (array/scalar) fails, since it has no top-level keys.
    """
    import json as _json

    def fn(output: str) -> bool:
        try:
            data = _json.loads(output.strip())
        except (ValueError, TypeError):
            return False
        if required_fields:
            return isinstance(data, dict) and all(k in data for k in required_fields)
        return True

    return {
        "name": name or f"json[{','.join(required_fields or [])}]",
        "fn": fn,
        "description": "valid JSON" + (f" with keys: {required_fields}" if required_fields else ""),
    }


def regex_gate(pattern: str, *, name: str | None = None) -> dict[str, Any]:
    """Output must match a regex pattern."""
    import re
    compiled = re.compile(pattern, re.DOTALL)

    def fn(output: str) -> bool:
        return bool(compiled.search(output))

    return {
        "name": name or f"regex[{pattern[:30]}]",
        "fn": fn,
        "description": f"output matches /{pattern}/",
    }


def any_gate(*gates: dict[str, Any], name: str | None = None) -> dict[str, Any]:
    """OR composition — accept if any sub-gate passes."""
    fns = [g["fn"] for g in gates]

    def fn(output: str) -> bool:
        return any(f(output) for f in fns)

    return {
        "name": name or f"any[{','.join(g['name'] for g in gates)}]",
        "fn": fn,
        "description": f"any of: {[g['name'] for g in gates]}",
    }


def all_gate(*gates: dict[str, Any], name: str | None = None) -> dict[str, Any]:
    """AND composition — accept only if every sub-gate passes."""
    fns = [g["fn"] for g in gates]

    def fn(output: str) -> bool:
        return all(f(output) for f in fns)

    return {
        "name": name or f"all[{','.join(g['name'] for g in gates)}]",
        "fn": fn,
        "description": f"all of: {[g['name'] for g in gates]}",
    }
