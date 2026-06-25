"""Shared notebook utilities for the reference-implementation tutorials.

Root-level helpers that every pattern's notebooks reuse — the counterpart to
model_config.py (model loading). Imported the same way: the notebook's import
cell adds the repo root to sys.path, then `from nbtools import show_graph`.

Kept deliberately small: only genuinely cross-cutting, framework-agnostic
helpers belong here. Pattern-specific logic (gates, hooks, trace printers,
nodes) stays in each pattern's own `shared.py` or notebook.
"""
from __future__ import annotations

from typing import Any


def show_graph(graph: Any, *, alt: str = "graph") -> None:
    """Render a graph as a PNG via the Mermaid renderer, falling back to
    offline ASCII art if the renderer is unreachable.

    Works for any object exposing `.get_graph()` — a compiled LangGraph
    `StateGraph` or an LCEL `Runnable`. `draw_mermaid_png()` calls a remote
    service; the ASCII fallback (`draw_ascii()`, needs `grandalf`) keeps the
    cell rendering when that service is offline or blocked.
    """
    # Imported lazily so nbtools stays importable outside a notebook/IPython env.
    from IPython.display import Image, display

    g = graph.get_graph()
    try:
        display(Image(data=g.draw_mermaid_png(), alt=alt))
    except Exception as e:  # noqa: BLE001 — renderer offline / network blocked
        print(f"(PNG render unavailable: {type(e).__name__}) — ASCII fallback:\n")
        print(g.draw_ascii())
