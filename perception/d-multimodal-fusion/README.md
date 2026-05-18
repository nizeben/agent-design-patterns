# d · Multi-Modal Fusion

> Column lecture **02-05** · pattern · perception × parallel
>
> [中文 README](README.zh-CN.md)

## The problem

The agent receives an 80-page PDF research report. It must summarise the
thesis, fact-check every numeric claim, and distil sales talking points
for account managers. The first engineer tries each of two natural
approaches and they both fail.

* **All-in-one.** Feed the whole PDF to Claude's PDF API. ~90K tokens,
  $0.27/call on Sonnet 4.6 input pricing. The summary is fine. The fact
  check is broken — the agent reads "market size RMB 580 billion" off a
  chart axis as "RMB 580 million." The Y-axis scale was lost in
  rasterised page tokens.
* **All-text.** OCR every page, drop the images, feed plain text. ~35K
  tokens. Numeric reading is now correct. But every chart's spatial
  signal is gone, so the summary is mechanical and the sales talking
  points read like a generated bullet list.

Three weeks of prompt engineering don't move either failure mode. The
fix isn't a better prompt — **the data is in the wrong form for the
model to digest**.

## The pattern

Route every input modality to its cheapest sufficient form, then merge:

| Modality | What you do | Why |
|---|---|---|
| **TEXT** | pass through | the cheapest token already |
| **IMAGE** | keep only when spatial info is signal (charts, diagrams, screenshots) | a market-size chart's Y-axis is signal; a company logo is not |
| **TABLE** | convert to markdown | ~80% cheaper than rasterising and preserves structure |
| **PDF** | TOC + key pages + selected figures | 80-page → ~3-page distillation, 20K tokens instead of 90K |
| **LOG** | bash pre-filter → sub-agent extraction → compact summary | three stages because raw logs are 95% noise |
| **AUDIO** | STT first, then treat as text | the model can't hear waveforms |
| **SQL_RESULT** | markdown table + top-N sample | rows beyond N rarely add signal |

Every input emits a `FusionEvent` (modality, tokens out, method, ms).
The `health_check()` flags red signals — image tokens > 50% of budget,
log tokens > 40% (the bash pre-filter isn't doing its job).

The pattern's claim: **the right form for the data shrinks the token
budget by an order of magnitude AND increases answer quality at the same
time**. They are not a trade-off.

## Quickstart

```bash
python perception/d-multimodal-fusion/example.py
pytest perception/d-multimodal-fusion/
```

The demo simulates the research-report scenario. Without fusion the same
inputs cost ~90K tokens; with fusion they cost ~1.7K tokens (98%
reduction in the synthetic example, ~80% on real production data).

```
v3 multi-modal fusion : 1,724 tokens (5 content blocks)
v1 all-in-one (naive) : 89,693 tokens
Savings               : 87,969 tokens (98% reduction)
```

## Files in this folder

| File | What it is |
|---|---|
| `pattern.py` | `MultiModalFuser` + 8 `ModalityType` + `ModalityInput` + `FusionEvent` + `FusionResult` (~220 lines) |
| `example.py` | 80-page PDF + chart image + 100-row vendor table + 60-line noisy log + user text |
| `test_pattern.py` | 10 invariants: per-modality routing, PDF extract, bash+subagent log pipeline, SQL compaction, health check, keep_as_image override |

## Engineering references (verified)

* [Anthropic Vision API docs](https://platform.claude.com/docs/en/build-with-claude/vision) — token math: `width × height / 750`, max 1568 tokens/image
* [Claude PDF support](https://docs.claude.com/en/docs/build-with-claude/pdf-support) — 30-page text-dense PDF ≈ 56-60K tokens raw
* [Anthropic Effective Context Engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents) — "smallest high-signal token set" framing
* [Manus Context Engineering blog](https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus) — the 100:1 input-to-output ratio that motivates aggressive shaping
* Log structuring with LLMs: arXiv:2511.18727 (LogSyn) and arXiv:2510.24031 (LLMLogAnalyzer)

## When this pattern doesn't apply

* **One small input.** A 200-line config file or a 5-row API response —
  no fusion needed. Just feed it.
* **The cost of pre-processing exceeds the savings.** OCR-ing 2 pages
  to save 800 tokens isn't worth a 4-second latency hit.
* **The model has native multi-modal that's cheaper than your pipeline.**
  Anthropic, OpenAI, and Google all keep rolling out direct-PDF and
  direct-image support. Re-check pricing every quarter; some of this
  pattern's value migrates into the model itself.
