# Design: N8 — context auto-compaction via the fractal digest

**Status:** SHIPPED (CM-W2). Implementation in `server.py` (`_compact_history`,
agent_loop hook); tests in `tests/test_context_compaction.py`.

## Problem
Long sessions grow `history` until it approaches the model's context window. Today
nothing compacts it — eventually a call fails (context-length error) or the
provider silently truncates, losing the *oldest* turns (often the task framing).
We already build a deterministic, no-LLM session digest (fractal memory #33/#43,
`_extract_theme_tokens` / `_digest_markdown`). N8 = use it to compact in-flight.

## Goal
When history nears the limit, replace the OLDEST turns with one compact synthetic
"context summary" message (built from the digest of those turns), keeping recent
turns verbatim — so the run continues without a context-length failure and without
lossy provider-side truncation. Deterministic, no extra model spend.

## Approach
In `agent_loop`, before each `call_model`:
1. **Estimate tokens** of `system + history`. No `tiktoken` dep — use a cheap
   heuristic (`len(text)/4`, summed over text + tool_calls args + tool contents).
   Conservative (over-estimate) so we compact early rather than overflow.
2. **Threshold:** when estimate > `COMPACT_AT_FRAC` (e.g. 0.7) of the model's
   context limit, compact. Per-model context limit: add a `context_window` field
   to provider/model config (default a safe 128k, override per model); fall back
   to a constant if unknown.
3. **What to compact:** the oldest turns, KEEPING:
   - the first user turn (task framing) — never drop the original ask;
   - the most recent `KEEP_RECENT` turns verbatim (e.g. last 12);
   - **tool-call/result pairing integrity** (see Risks).
4. **Replace** the compacted span with a single `{"role":"user","text": "[earlier
   context, compacted]\n" + _digest_markdown_of(span)}` (or an assistant/system
   note — pick the role the provider accepts mid-history without breaking the
   user/assistant alternation). Emit a `compaction` event (turns compacted,
   est. tokens before/after) so it's visible + auditable.
5. Idempotent-ish: a previously-inserted compaction note is itself cheap; on the
   next compaction, fold it into the new digest (don't stack many notes).

## Risks / hard parts (why design-first)
- **Tool-call/result pairing.** The OpenAI/Anthropic message sequence requires
  every `assistant` message with `tool_calls` to be followed by matching `tool`
  results. If compaction drops an assistant-with-tool_calls but keeps its tool
  result (or vice-versa), the next API call 400s. Rule: compact at **turn-group
  boundaries** — never split an assistant+its tool-results; either compact a whole
  group or none of it. Safest: only compact *complete* older groups, leaving the
  recent verbatim window aligned to a group boundary.
- **System prompt** is separate (not in history) — never compact it.
- **Determinism:** reuse `_extract_theme_tokens` (already deterministic). The
  threshold check must not depend on wall-clock/randomness.
- **Don't double-charge / don't call the model** to summarize — the whole point
  is the no-LLM digest.
- **Recent context fidelity:** keep enough recent verbatim turns that the model
  doesn't lose the thread mid-task; `KEEP_RECENT` tunable.
- **Interaction with N5 streaming / N6 resume / N9 guard:** all touch agent_loop;
  build after they merge and rebase, compacting BEFORE the N9 fail-count logic and
  the call. Re-run the integration test.

## Config (proposed)
- `COMPACT_AT_FRAC=0.7`, `KEEP_RECENT=12`, per-model `context_window` (default 128000).
- A `compaction` event for the audit viewer (N11) + the digest endpoints.

## Tests (when built)
- Estimator monotonic + over-estimates; compaction triggers past threshold;
  first-user-turn preserved; recent window preserved verbatim; **no orphaned
  tool_call/tool_result after compaction** (the critical one); deterministic
  (same history → same compacted result); below-threshold history untouched;
  a compaction event is emitted.

## Owner decisions (none blocking now)
- Acceptable to represent compacted context as a `user`-role synthetic note, or
  prefer a provider-specific system/assistant note? (Default: user-role note,
  simplest + provider-agnostic.)
- Per-model `context_window` values — seed sensible defaults; owner can tune.
