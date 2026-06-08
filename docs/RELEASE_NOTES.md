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

## ✅ Shipped + DEPLOYED (v15): the N-backlog Wave 1+2 + S4-A
PRs #49–#56 (N1 failover, N2 daily cap, N3 cost dashboard, N4 diff preview, N7
plan→execute, N10 `/readyz`, N11 audit viewer) merged + deployed v15, smoke-green.

## Open PR stack — awaiting your merge (build→PR only; owner away)
| PR | What | Risk / review |
|----|------|---------------|
| #58 | S4-B extend: encrypt `model_config.json`+`mcp_tokens.json` at rest (FAIL-SOFT) + evict `GITHUB_TOKEN` + UI banner | red-teamed **NO-GO→fixed→GO**; data-loss clobber fixed + R3 footguns hardened (ciphertext `.bak`) |
| #59 | N9 tool-error-repeat guard (nudge + abort on stuck loops) | low-risk (no security boundary) |
| #60 | N6 session-resume (survive Fly scale-to-zero/deploy mid-run) | low-risk (session lifecycle) |

### Tested merge order (integration-checked 2026-06-07 ~22:50 UTC)
**All three merge CLEANLY in this order — no conflicts — integrated suite 535 green:**
1. **#58** (S4-B encrypt+evict) → 2. **#59** (N9 guard) → 3. **#60** (N6 resume)

After merging, run `./.venv/bin/python -m pytest tests/ -q` (expect ~535) and
`fly deploy --app codemonkeys --remote-only`. #58 is INERT until you set
`CM_MASTER_KEY` (then model keys/mcp tokens encrypt too; see Scenario E + the
`.undecryptable.bak` safety net in this file).

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
