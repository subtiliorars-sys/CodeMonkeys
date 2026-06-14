# CodeMonkeys — Wave Registry

One wave = one PR. Verify: `pytest` (full CI suite). Branch: `automation/wave-*`.
Read `docs/STATE.md` + `docs/IDEATION.md` before each wave. Never merge your own PR.

## Pickup rules
1. Open automation PR → stop (wave in flight).
2. Else → first pending wave below (one N-item at a time).
3. Never ask owner to restart.

## Active queue

*(none)*

## Blocked / owner-gated (queue only)
- OAuth app registration, webhook secrets, terminal activation
- `fly deploy` / production config changes
- SECURITY.md substantive changes

## Completed

### Wave CM-W4 — Lint feedback loop ✅
**Branch:** `automation/wave-cm-w4-lint-feedback`  
**Shipped:** Auto-inject lint diagnostics after `write_file`/`edit_file`/`apply_patch`
(`LINT_AFTER_EDIT=1` default); `run_lint` tool (ruff → py_compile fallback for Python,
`tsc --noEmit` when installed); `lint` session events + forge UI rendering.

### Wave CM-W3 — N12 Model catalog refresh ✅
**Branch:** `automation/wave-cm-w3-model-catalog`  
**Shipped:** Per-model catalog costs via `PUT /api/models/{pid}/models/{mid}`
(manual flag preserved on OpenRouter refresh); cost validation (finite ≥ 0);
`_resolve` uses catalog costs for call_cost; forge UI add-model in/out inputs +
double-click cost edit; refresh merge keeps manual/pinned entries.

### Wave CM-W2 — N8 Context auto-compaction ✅
**Branch:** `automation/wave-cm-w2-compaction`  
**Shipped:** Deterministic in-loop compaction via fractal digest when estimated
tokens exceed `COMPACT_AT_FRAC` of per-model `context_window`; first user turn +
recent `KEEP_RECENT` window preserved; tool-call/result pairing intact;
`compaction` audit events; 17-test suite in `tests/test_context_compaction.py`.

### Wave CM-W1 — N5 Streaming output ✅
**Branch:** `automation/wave-cm-w1-streaming`  
**Shipped:** SSE streaming via `STREAM_ENABLED=1`; `text_delta` events redacted
server-side; forge + terminal UIs render live partial text; non-streaming
fallback on error; default-off preserves pre-N5 behaviour.

See `docs/STATE.md` — Waves 1–4, N1–N4, N6–N11 shipped.
