# c · Progressive Discovery

> Column lecture **02-04** · pattern · perception × loop
>
> [中文 README](README.zh-CN.md)

## The problem

You don't know which files matter. A bug report says "order confirmation
emails sometimes show another customer's order." The codebase is a
15,000-file legacy monolith. The original authors are gone. There is no
documentation that tells you which files implement the order-mail
pipeline.

Three things that don't work:

* **Feed the whole codebase to the agent.** Even a small monolith
  collapses to ~800K tokens, well past any window. Splitting into
  parallel chunks just means every chunk's agent reports "I don't see
  the bug in this slice" — none of them sees the full picture.
* **RAG.** Embed everything, semantic-search the bug description. In
  practice the offending file uses variable names like `merge_user_state`
  and has no comment containing "order" or "email," so the top-K
  retrieval misses it.
* **Read every file in topological order.** Sounds disciplined; turns
  into 15,000 individual reads with no convergence.

You need something closer to how a senior engineer actually navigates an
unfamiliar codebase — grep, read a few, follow the call chain.

## The pattern

Three phases in a bounded loop:

| Phase | What it does | Typical scale |
|---|---|---|
| **FORAGE** | Broad grep / glob for ~30 candidate files | seconds, hundreds of paths |
| **FOCUS** | Read the top 5–8 candidates in full | seconds, ~5K tokens |
| **DEEPEN** | Follow imports / call chains / references | seconds, ~3K tokens |

If signal found, exit. Otherwise refine keywords from what was read and
loop. Bounded by a per-cycle token budget and a max-cycles cap. Every
phase logs a trace event so you can diagnose drift later.

The pattern's invariant: **no pre-embedding of the codebase**. Discovery
is on-demand, structure-aware, and bounded. The total cost is typically
~18K tokens per full cycle, regardless of repository size.

## Quickstart

```bash
python perception/c-progressive-discovery/example.py
pytest perception/c-progressive-discovery/
```

The demo seeds a 200-file synthetic monolith with two bug-relevant files
hidden among the noise. With the right initial keywords, the discoverer
locates the bug in one cycle at ~530 tokens.

```
Codebase: 200 files
Task    : find why order confirmation emails sometimes show another customer's order
Cycles run     : 1
Total tokens   : 529
Final files    : 5
  · app/mailers/order_confirmed.rb ← bug source 1 (mailer)
  · app/services/order_history_emailer.rb       (red herring)
  · ... (3 more)
  · cache/user_state                  ← bug source 2 (cache key)
Bug located    : True
```

## Files in this folder

| File | What it is |
|---|---|
| `pattern.py` | `ProgressiveDiscoverer` + `Phase` + `Candidate` + `DiscoverySession` + `DiscoveryEvent` (~230 lines) |
| `example.py` | 200-file synthetic Rails monolith with a real-shaped bug |
| `test_pattern.py` | 8 invariants: phase order, budget enforcement, success-exit, max-cycles cap, deepen follows imports, health check |

## Engineering references (verified)

* **Boris Cherny** (creator of Claude Code) on [why Claude Code dropped RAG for agentic search](https://x.com/bcherny/status/2017824286489383315):
  > "Early versions of Claude Code used RAG + a local vector db, but we
  > found pretty quickly that agentic search generally works better.
  > Internal benchmarks showed that agentic search outperformed RAG by
  > a lot, which was surprising."
* [Anthropic Effective Context Engineering](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents) for the "smallest high-signal token set" framing
* [Pirolli & Card, *Information Foraging*](https://psycnet.apa.org/record/1999-11644-001) (Psychological Review 106(4), 1999) — the cognitive-science origin of the forage / focus / deepen vocabulary used here
* [Aider's `repomap.py`](https://github.com/Aider-AI/aider/blob/main/aider/repomap.py) — an alternative line that pre-builds a symbol map; complementary to agentic search, not opposite
* [Augment Code Context Engine](https://www.augmentcode.com/context-engine) — the persistent-indexing camp's reference implementation (400K+ files indexed in ~6 min, 45-sec incremental updates)

## When this pattern doesn't apply

* **The agent already knows the file.** Single-file edits, focused
  refactors, anything where the relevant scope is pre-supplied — skip
  the forage and read directly.
* **The data isn't structured for grep.** Natural-language knowledge
  bases, chat logs, unstructured documentation — semantic RAG is the
  right tool there. The two patterns are complementary, not adversarial.
* **The signal is in metadata, not code.** Git blame, commit history,
  CI logs — those are different perception tools, not failures of
  Progressive Discovery.
