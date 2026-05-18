"""Multi-Modal Fusion pattern.

Reference implementation of the data-form engineering pattern from column
lecture 02-05. The pattern's claim: agents don't fail because the prompt
is wrong — they fail because the data they receive is in the wrong form
for an LLM to digest.

The core idea is to route every input modality to the form most useful to
the model:

* **TEXT**: pass through directly
* **IMAGE**: keep as image only when spatial information is signal (charts,
  diagrams, screenshots with UI text). Otherwise OCR + drop the original.
* **TABLE**: convert to markdown, ~80% cheaper than keeping as image while
  preserving structural information
* **PDF**: extract TOC + key pages + selected figures; rebuild a compact
  representation rather than feeding the whole file
* **LOG**: three-stage pipeline — shell-based pre-filter → sub-agent
  structured extraction → compact summary
* **AUDIO**: STT first, then treat as text
* **SQL_RESULT**: markdown table + top-N sampling with total-rows marker

The pattern emits a fusion trace per input so you can spot ballooning
costs (over-imaged charts, unfiltered logs) before they break production.
"""
from __future__ import annotations

import base64
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable


class ModalityType(Enum):
    TEXT = "text"
    IMAGE = "image"
    TABLE = "table"
    LOG = "log"
    PDF = "pdf"
    AUDIO = "audio"
    VIDEO = "video"
    SQL_RESULT = "sql_result"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ModalityInput:
    """One incoming piece of data to be fused."""

    type: ModalityType
    payload: Any                  # path / bytes / object
    hint: str = ""                # business-side hint, e.g. "market size chart"
    keep_as_image: bool = False   # force-keep as image regardless of default


@dataclass
class FusionEvent:
    """One atomic record of a modality being processed."""

    modality: ModalityType
    bytes_in: int = 0
    tokens_out: int = 0
    method: str = ""
    processing_ms: int = 0
    timestamp: str = field(default_factory=_now_iso)


@dataclass
class FusionResult:
    """The unified content list + trace for downstream LLM call."""

    content: list[dict[str, Any]]
    total_tokens_estimate: int
    fusion_trace: list[FusionEvent]


class MultiModalFuser:
    """Route each modality to its cheapest sufficient form, then merge."""

    def __init__(
        self,
        ocr_tool: Callable[[bytes], str] | None = None,
        stt_tool: Callable[[bytes], str] | None = None,
        pdf_extract: Callable[[str], dict] | None = None,
        log_subagent: Callable[[str], dict] | None = None,
        bash_filter: Callable[[str, str], str] | None = None,
        image_token_estimate: int = 1400,   # 1024×1024 ≈ 1.4K tokens for Claude vision
    ) -> None:
        self.ocr = ocr_tool
        self.stt = stt_tool
        self.pdf_extract = pdf_extract
        self.log_subagent = log_subagent
        self.bash_filter = bash_filter
        self.image_token_estimate = image_token_estimate
        self.events: list[FusionEvent] = []

    # ──────────────── public ────────────────

    def fuse(self, inputs: list[ModalityInput]) -> FusionResult:
        content: list[dict[str, Any]] = []

        for inp in inputs:
            t0 = datetime.now(timezone.utc)
            tokens = 0
            method = ""

            # keep_as_image is an override flag — check it first so callers
            # can force-route any input to the vision path.
            if inp.keep_as_image or inp.type == ModalityType.IMAGE:
                content.append(self._build_image_block(inp.payload))
                tokens = self.image_token_estimate
                method = "vision"

            elif inp.type == ModalityType.TEXT:
                content.append({"type": "text", "text": str(inp.payload)})
                tokens = len(str(inp.payload)) // 4
                method = "direct"

            elif inp.type == ModalityType.TABLE:
                md = self._table_to_markdown(inp.payload)
                content.append({"type": "text", "text": md})
                tokens = len(md) // 4
                method = "table_to_md"

            elif inp.type == ModalityType.PDF and self.pdf_extract:
                extracted = self.pdf_extract(inp.payload)
                summary_text = self._build_pdf_summary(extracted, inp.hint)
                content.append({"type": "text", "text": summary_text})
                tokens = len(summary_text) // 4
                method = "pdf_extract"

            elif inp.type == ModalityType.LOG:
                pre_filtered = (
                    self.bash_filter(inp.payload, inp.hint)
                    if self.bash_filter else inp.payload[:50_000]
                )
                structured = (
                    self.log_subagent(pre_filtered)
                    if self.log_subagent else {"raw_excerpt": pre_filtered[:2000]}
                )
                summary = self._format_log_structured(structured)
                content.append({"type": "text", "text": summary})
                tokens = len(summary) // 4
                method = "bash_filter+subagent"

            elif inp.type == ModalityType.AUDIO and self.stt:
                payload_bytes = inp.payload if isinstance(inp.payload, bytes) else b""
                transcript = self.stt(payload_bytes)
                content.append({"type": "text", "text": transcript})
                tokens = len(transcript) // 4
                method = "stt"

            elif inp.type == ModalityType.SQL_RESULT:
                compact = self._compact_sql_result(inp.payload, max_rows=30)
                content.append({"type": "text", "text": compact})
                tokens = len(compact) // 4
                method = "compact_table"

            else:
                txt = str(inp.payload)[:5000]
                content.append({"type": "text", "text": txt})
                tokens = len(txt) // 4
                method = "fallback_str"

            self.events.append(FusionEvent(
                modality=inp.type,
                bytes_in=len(str(inp.payload)) if isinstance(inp.payload, str) else 0,
                tokens_out=tokens,
                method=method,
                processing_ms=int((datetime.now(timezone.utc) - t0).total_seconds() * 1000),
            ))

        return FusionResult(
            content=content,
            total_tokens_estimate=sum(e.tokens_out for e in self.events),
            fusion_trace=list(self.events),
        )

    def health_check(self) -> dict[str, str]:
        """Flag modality-token imbalances — usually means a wrong form choice."""
        if not self.events:
            return {"status": "no fusion events"}
        per_modality: dict[str, int] = defaultdict(int)
        for e in self.events:
            per_modality[e.modality.value] += e.tokens_out
        total = sum(per_modality.values()) or 1
        report: dict[str, str] = {}
        for mod, t in per_modality.items():
            ratio = t / total
            if mod == "image" and ratio > 0.50:
                report["image_token_overshoot"] = (
                    f"Images = {ratio:.0%} of budget. "
                    "Check whether some could become tables or markdown."
                )
            if mod == "log" and ratio > 0.40:
                report["log_token_overshoot"] = (
                    f"Logs = {ratio:.0%} of budget. "
                    "The bash pre-filter likely isn't doing its job."
                )
        return report

    # ──────────────── internals ────────────────

    def _build_image_block(self, payload: Any) -> dict[str, Any]:
        if isinstance(payload, bytes):
            img_bytes = payload
        else:
            try:
                with open(payload, "rb") as f:
                    img_bytes = f.read()
            except (FileNotFoundError, TypeError):
                # In tests / examples the payload may be a placeholder string
                img_bytes = str(payload).encode()
        return {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/png",
                "data": base64.b64encode(img_bytes).decode(),
            },
        }

    def _table_to_markdown(self, table_obj: Any) -> str:
        if hasattr(table_obj, "to_markdown"):
            return table_obj.to_markdown(index=False)
        if isinstance(table_obj, list) and table_obj and isinstance(table_obj[0], dict):
            cols = list(table_obj[0].keys())
            header = "| " + " | ".join(cols) + " |"
            sep = "|" + "|".join(["---"] * len(cols)) + "|"
            body = "\n".join(
                "| " + " | ".join(str(r.get(c, "")) for c in cols) + " |"
                for r in table_obj
            )
            return f"{header}\n{sep}\n{body}"
        return str(table_obj)

    def _build_pdf_summary(self, extracted: dict, hint: str) -> str:
        parts: list[str] = []
        if extracted.get("toc"):
            parts.append(f"[PDF TOC]\n{extracted['toc']}")
        if extracted.get("key_pages"):
            for p in extracted["key_pages"]:
                parts.append(
                    f"[Page {p.get('page', '?')}]\n{p.get('text', '')[:1500]}"
                )
        if hint:
            parts.append(f"[Business hint]: {hint}")
        return "\n\n".join(parts) or "[empty PDF extract]"

    def _format_log_structured(self, structured: dict) -> str:
        if not structured:
            return "[no log signal]"
        lines = "\n".join(f"{k}: {v}" for k, v in structured.items())
        return f"[Log structured summary]\n{lines}"

    def _compact_sql_result(self, rows: list[dict], max_rows: int) -> str:
        if not rows:
            return "[empty result]"
        total = len(rows)
        sample = rows[:max_rows]
        cols = list(sample[0].keys())
        header = "| " + " | ".join(cols) + " |"
        sep = "|" + "|".join(["---"] * len(cols)) + "|"
        body = "\n".join(
            "| " + " | ".join(str(r.get(c, "")) for c in cols) + " |"
            for r in sample
        )
        suffix = f"\n_({total} rows total, showing top {len(sample)})_"
        return f"{header}\n{sep}\n{body}{suffix}"
