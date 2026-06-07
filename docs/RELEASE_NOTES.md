# CodeMonkeys — Release Notes (2026-06-07)

A big build day. This summarizes what's **already on `main`** (merged) and the
**open PR stack** waiting for your merge, with a tested merge order. **Nothing is
deployed** — deploys are manual (`fly deploy`), your call.

## Already merged to `main` today
- **Wave 1–4 features** (overnight): fractal memory phase 1, vendored Tailwind
  phase 1 (+ phase 2 CDN removal/CSP tighten), connector marketplace, webhook→PR
  runs, web terminal (OFF by default), dup-send fix, blank-base_url provider guard.
- **#43** fractal memory phase 2 (scrubbed digest + cross-session pattern library).
- **#41** Fleet Deck `/fleet-status.json` ops feed (off until `FLEET_TOKEN` set).
- **#44** bash/terminal/MCP subprocess env scrub (defense-in-depth).
- **#45** notify-on-done outbound ping (off until `NOTIFY_WEBHOOK_URL` set).
- **#46** per-user isolation **design doc** (no code).
- **#47** encrypt `session_secret.key` at rest (off until `CM_MASTER_KEY` set) — twice red-teamed.
- **#48** recovery: `CM_MASTER_KEY_RESET` break-glass + `docs/RECOVERY.md`.

## Open PR stack — awaiting your merge (build→PR only; none merged while you were away)
| PR | What | Risk / review |
|----|------|---------------|
| #49 | N10 readiness probe `/readyz` | ops, no secrets |
| #50 | N4 unified diff preview for file writes | display-only |
| #51 | N2 daily spend cap (across sessions) | red-teamed GO-WITH-FIXES → fixed |
| #52 | N1 provider failover + cooldown | red-teamed GO-WITH-FIXES → fixed (debate-verify still fails closed) |
| #53 | N3 cost dashboard (by-day/by-model) | display-only |
| #54 | N11 owner audit-log viewer | red-teamed **GO** (stricter than existing endpoints) |
| #55 | N7 plan→execute handoff | jail verified |

### Tested merge order (integration-checked 2026-06-07)
Merge in this order — the first **5 apply cleanly**, the last **2 need a trivial
`server.py` conflict resolution** (adjacent additions to the single file — keep
both sides):
1. #49 → 2. #50 → 3. #53 → 4. #54 → 5. #51  *(clean)*
6. **#55** — minor `server.py` conflict (adjacent endpoint insertions), keep both
7. **#52** — minor `server.py` conflict (provider/agent_loop region vs #51), keep both

After merging, run `./.venv/bin/python -m pytest tests/ -q` to confirm green.
(Each PR is green on its own branch; the conflicts are textual adjacency, not logic.)

## Owner action items (when you're ready)
- **Merge** the stack above (no deploy happens from merging).
- **Deploy** when ready: `fly deploy --app codemonkeys --remote-only`.
- **Activate (optional), each = `fly secrets set …` + deploy:**
  - `CM_MASTER_KEY` (encrypt session secret at rest) — save it in your password
    manager first; see `docs/RECOVERY.md` (recovery is one env var if ever lost).
  - `FLEET_TOKEN` (Fleet Deck feed) · `NOTIFY_WEBHOOK_URL`(+secret) (ntfy pings).
- **Post-deploy:** eyeball the Tailwind phase-2 vendored CSS render; live LLM smoke.
- **Parked decisions** in `~/fleet/questions.md`: tenancy intent (S6), the
  pre-existing Member-readable `/api/sessions/{sid}/events` (only matters if you
  open to semi-trusted users).
