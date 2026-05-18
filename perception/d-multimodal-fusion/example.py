"""Runnable demo for the Multi-Modal Fusion pattern.

Scenario: a brokerage's research-report analysis agent. An 80-page PDF
arrives with mixed content — text, tables, charts. The agent must:

  1. Summarise the core thesis
  2. Fact-check every numeric claim in the report
  3. Distil sales talking points for the account managers

The demo compares three engineering approaches with token-cost estimates:

  v1 · all-in-one        — feed entire PDF (~90K tokens, miss-reads chart
                             axes → "5.8B → 58M" three-zero error)
  v2 · all-text          — OCR everything (~35K tokens, lose spatial info
                             → mechanical summary, vague talking points)
  v3 · multi-modal fuse  — TOC + key pages + charts kept as images +
                             tables to markdown (~18K tokens, all checks pass)

Run:
    python perception/d-multimodal-fusion/example.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
sys.modules.pop("pattern", None)

from pattern import (   # noqa: E402
    FusionResult,
    ModalityInput,
    ModalityType,
    MultiModalFuser,
)


# ───────────────────── synthetic tool stubs ─────────────────────

def fake_pdf_extract(pdf_path: str) -> dict:
    """Return a TOC + 3 key pages of a synthetic 80-page research report."""
    return {
        "toc": (
            "1. Executive Summary\n"
            "2. Market Size and Growth\n"
            "3. Competitive Landscape\n"
            "4. Regulatory Outlook\n"
            "5. Investment Thesis\n"
            "Appendix: Data Methodology"
        ),
        "key_pages": [
            {
                "page": 3,
                "text": (
                    "The market is currently valued at RMB 580 billion as of "
                    "FY2025, with a 5-year CAGR of 14.2%. Three key drivers "
                    "are: (a) digital transformation spending in tier-1 banks, "
                    "(b) regulatory push for domestic substitution, and (c) "
                    "open-source middleware adoption reaching 67% of new builds."
                ),
            },
            {
                "page": 47,
                "text": (
                    "Figure 4.2 shows market-size trajectory. Y-axis: RMB "
                    "billion. Key data points: 2020=320, 2023=485, 2025=580 "
                    "(actual), 2028E=895."
                ),
            },
            {
                "page": 71,
                "text": (
                    "Investment thesis: focus on three sub-sectors — "
                    "infrastructure software (35% growth), agentic AI tooling "
                    "(80% growth, smaller base), and compliance automation "
                    "(22% growth, defensive)."
                ),
            },
        ],
    }


def fake_bash_filter(log_text: str, hint: str) -> str:
    """Pretend to grep for ERROR / WARN / 5xx lines."""
    keep = []
    for line in log_text.split("\n"):
        if any(needle in line for needle in ("ERROR", "WARN", "5xx", "TimeoutError")):
            keep.append(line)
    return "\n".join(keep[:200])


def fake_log_subagent(filtered_text: str) -> dict:
    return {
        "total_errors": filtered_text.count("ERROR"),
        "total_warnings": filtered_text.count("WARN"),
        "first_error_at": "2026-05-18T08:14:02Z",
        "dominant_pattern": "TimeoutError: db pool exhausted",
        "affected_services": ["billing-api", "checkout-api"],
    }


# ───────────────────── scenario data ─────────────────────

MARKET_SHARE_TABLE = [
    {"vendor": "Vendor A", "share_2024": "31%", "share_2025": "29%"},
    {"vendor": "Vendor B", "share_2024": "22%", "share_2025": "25%"},
    {"vendor": "Vendor C", "share_2024": "18%", "share_2025": "21%"},
    {"vendor": "Vendor D", "share_2024": "15%", "share_2025": "12%"},
    {"vendor": "Others",   "share_2024": "14%", "share_2025": "13%"},
]

NOISY_LOG = "\n".join(
    [f"2026-05-18T08:{i:02d}:00Z INFO routine ping" for i in range(60)]
    + [f"2026-05-18T08:14:{i:02d}Z ERROR TimeoutError: db pool exhausted" for i in range(5)]
    + [f"2026-05-18T08:15:{i:02d}Z WARN pool size approaching limit" for i in range(3)]
)


# ───────────────────── main ─────────────────────

def main() -> None:
    print("Scenario: 80-page research report + sales-ops dashboard logs")
    print("=" * 64)

    # ─── v3 multi-modal fusion (the right answer) ───
    fuser = MultiModalFuser(
        pdf_extract=fake_pdf_extract,
        bash_filter=fake_bash_filter,
        log_subagent=fake_log_subagent,
    )

    inputs = [
        ModalityInput(
            type=ModalityType.PDF,
            payload="reports/sector-deep-dive-2026Q2.pdf",
            hint="market sizing and competitive share — fact-check every number",
        ),
        ModalityInput(
            type=ModalityType.IMAGE,
            payload=b"\x89PNG-fake-bytes-for-chart-page-47",
            hint="Figure 4.2 market-size trajectory chart (Y-axis = RMB billion)",
            keep_as_image=True,
        ),
        ModalityInput(
            type=ModalityType.TABLE,
            payload=MARKET_SHARE_TABLE,
            hint="competitive share 2024 vs 2025",
        ),
        ModalityInput(
            type=ModalityType.LOG,
            payload=NOISY_LOG,
            hint="dashboard timeout incidents during report ingest",
        ),
        ModalityInput(
            type=ModalityType.TEXT,
            payload="User question: what are the three sub-sectors the report recommends?",
        ),
    ]

    result: FusionResult = fuser.fuse(inputs)

    print(f"v3 multi-modal fusion: {result.total_tokens_estimate:,} tokens "
          f"({len(result.content)} content blocks)")
    print()
    print("Per-modality cost breakdown:")
    for e in result.fusion_trace:
        print(
            f"  {e.modality.value:12s}  method={e.method:24s}  "
            f"tokens={e.tokens_out:>5,}"
        )
    print()

    # ─── Naive comparison: same content, all dumped as fallback text ───
    naive_fuser = MultiModalFuser()
    naive_inputs = [
        ModalityInput(type=ModalityType.TEXT, payload="<entire 80-page PDF as raw text>" + "x" * 350_000),
        ModalityInput(type=ModalityType.IMAGE, payload=b"\x89PNG" * 350),
        ModalityInput(type=ModalityType.TEXT, payload=str(MARKET_SHARE_TABLE)),
        ModalityInput(type=ModalityType.TEXT, payload=NOISY_LOG),
        ModalityInput(type=ModalityType.TEXT, payload="User question: ..."),
    ]
    naive = naive_fuser.fuse(naive_inputs)
    print(f"v1 all-in-one (naive) : {naive.total_tokens_estimate:,} tokens")
    print(f"Savings               : "
          f"{(naive.total_tokens_estimate - result.total_tokens_estimate):,} tokens "
          f"({100 * (1 - result.total_tokens_estimate / naive.total_tokens_estimate):.0f}% reduction)")
    print()

    print("Health check (v3):")
    health = fuser.health_check()
    if health and health.get("status") != "no fusion events":
        for k, v in health.items():
            print(f"  · {k}: {v}")
    else:
        print("  · all modality ratios within healthy band")

    print()
    print("First 3 content blocks emitted to LLM:")
    for i, block in enumerate(result.content[:3]):
        kind = block["type"]
        preview = (
            block.get("text", "")[:80] + "..." if kind == "text"
            else f"[image, base64 length={len(block['source']['data'])}]"
        )
        print(f"  [{i}] type={kind:5s}  {preview}")


if __name__ == "__main__":
    main()
