# CodeMonkeys — Wave Registry

One wave = one PR. Verify: `pytest` (full CI suite). Branch: `automation/wave-*`.
Read `docs/STATE.md` + `docs/IDEATION.md` before each wave. Never merge your own PR.

## Pickup rules
1. Open automation PR → stop (wave in flight).
2. Else → first pending wave below (one N-item at a time).
3. Never ask owner to restart.

## Active queue

### Wave CM-W1 — N5 Streaming output
**Status:** `active`  
**Spec:** `docs/IDEATION.md` N5  
**Branch:** `automation/wave-cm-w1-streaming`

**Acceptance:**
- [ ] Stream partial model text to console UI
- [ ] Red-team: no secret leakage in stream path
- [ ] `pytest` green (472+ tests)

### Wave CM-W2 — N8 Context auto-compaction
**Status:** `pending`  
**Spec:** `docs/IDEATION.md` N8  
**Branch:** `automation/wave-cm-w2-compaction`

### Wave CM-W3 — N12 Model catalog refresh
**Status:** `pending`  
**Spec:** `docs/IDEATION.md` N12  
**Branch:** `automation/wave-cm-w3-model-catalog`

## Blocked / owner-gated (queue only)
- OAuth app registration, webhook secrets, terminal activation
- `fly deploy` / production config changes
- SECURITY.md substantive changes

## Completed
See `docs/STATE.md` — Waves 1–4, N1–N4, N6–N11 shipped.
