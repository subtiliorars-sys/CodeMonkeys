# CodeMonkeys — Wave Registry

One wave = one PR. Verify: `pytest` (full CI suite). Branch: `automation/wave-*`.
Read `docs/STATE.md` + `docs/IDEATION.md` before each wave. Never merge your own PR.

## Pickup rules
1. Open automation PR → stop (wave in flight).
2. Else → first pending wave below (one N-item at a time).
3. Never ask owner to restart.

## Active queue

_(none — safe automation backlog exhausted; next items are owner-gated below.)_

**N-backlog status (2026-07-18):** CM-W1–W7 shipped, and S5 notify-on-done
shipped earlier via PR #45 (inert until `NOTIFY_WEBHOOK_URL` is set).
Automation must **not** pick up new waves until Owner adds a `pending` entry
here or unblocks an item below. Maintainer checklist: `docs/FORGE_HYGIENE.md` §6.

## Parallel track — Windows desktop (manual)

**Docs:** `docs/DESKTOP.md` · **Run:** `python -m desktop` · **Package:** `pwsh scripts/build-windows.ps1`

| Wave | Status | Scope |
|------|--------|--------|
| CM-DESK-W1 | `shipped` | Loopback launcher + pywebview shell + PyInstaller onedir build |
| CM-DESK-W2 | pending | Installer polish (Start Menu shortcut, optional NSIS/MSIX), icon |
| CM-DESK-W3 | pending | Linux packaging (AppImage/build-linux.sh) |
| CM-DESK-W4 | pending | Public BYOK web tier (after desktop is solid) |

## Parallel track — Forge UI / Cursor parity (manual)

**Branch:** `work/frontend-polish` · deploy: owner runs `fly deploy` (not automation PR).  
**Verify:** `pytest` + spot-check Forge at `/`.

| Wave | Status | Scope |
|------|--------|--------|
| CM-UI-W1 | ✅ done | Provider rotation → playful wait banner (no error spam) |
| CM-UI-W2 | ✅ done | Agents hub — sessions, automations, personas, rules (`agents-hub.js`) |
| CM-UI-W3 | `done` | Hooks + Skills tabs + API; live fleet job detail in Automations |

**Coordination:** Automation waves CM-W2/W3 may touch `server.py` (N8 compaction, N12 catalog).
UI track stays in `static/forge/*` unless explicitly merged. If an open `automation/wave-*`
PR exists, finish or pause before overlapping server changes.

See `OFFICE_HOURS.md` for the 5-min PR checklist.

## Blocked / owner-gated (queue only)
- OAuth app registration, webhook secrets, terminal activation
- `fly deploy` / production config changes
- SECURITY.md substantive changes
- S6 Layers 2–4 (workspace jail, per-user secrets, shell sandbox) — owner decision

## Completed

### Wave CM-W7 — S6 Layer 1 session ownership ✅
**Branch:** `automation/wave-cm-w7-session-ownership` (merged via #122)  
**Shipped:** Session→user binding on all `/api/sessions/{sid}/*` routes; members
see/mutate only their sessions; Owner sees all with `read_only` flag on others';
legacy `username=None` sessions (webhook) bind to Owner. Forge sidebar `ro` badge
hides mutate controls on read-only rows. `tests/test_session_ownership.py` (8 tests).

### Wave CM-W6 — Feedback triage list proposals ✅
**Branch:** `automation/wave-cm-w6-feedback-tests`  
**Shipped:** `list_feedback` auto-generates heuristic proposals on first load;
`tests/test_feedback_triage.py` (5 tests for proposals, merge, list, accept).

### Wave CM-W5 — Three-card Field Report triage ✅
**Branch:** `automation/wave-cm-w5-three-card-triage` (merged via #84)  
**Shipped:** `feedback_triage.py` heuristic `[FIX]`/`[INVESTIGATE]`/`[DISMISS]`
proposals; owner-only `/api/feedback/proposals/*` routes; Field Report inbox wired
to `three-card-triage.js` + CSS.

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

### Wave S5 — Notify-on-done ✅
**Branch:** merged via PR #45 (pre-automation registry)  
**Shipped:** Best-effort outbound POST on run completion when `NOTIFY_WEBHOOK_URL`
is set; ops-metadata only (no prompts/code/secrets); `NOTIFY_ON=all|error` filter;
optional HMAC via `NOTIFY_WEBHOOK_SECRET`. Default-off preserves pre-S5 behaviour.
`tests/test_notify_on_done.py`.

See `docs/STATE.md` — Waves 1–4, N1–N4, N6–N11, S5 shipped.
