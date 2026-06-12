# Session Handoff — 2026-06-12 (Fleet Health + Recurring Checks Ready)

## THIS SESSION'S MAJOR CHANGES (2026-06-12)

**Infrastructure Verification & Autonomy Setup:**
1. ✅ **Fleet Health Check** — 68 active projects, 0 blocking issues, all systems GREEN
2. ✅ **Gunny Interface Verified** — nautical aesthetic (navy/cream/brass) fully functional, 5 command buttons responsive, chat live
3. ✅ **FleetDeck Running** — localhost:8787, reading ~/fleet blackboard, no write operations
4. ✅ **30-Minute Recurring Check Scheduled** — `/loop` fires at :07 and :37 every hour, auto-expires in 7 days
5. ✅ **No Blocking Issues** — queue depth = 0, subagents healthy

**Autonomous Operation:** Fleet requires NO user input; all 4 worker types (efficiency, QA, red-team, revenue) monitor and report automatically via blackboard. Recurring checks will continue whether user is present or not.

**Services Live:**
- FleetDeck: http://localhost:8787 (PID 30218, Python app.py)
- Gunny chat interface: /gunny route, all buttons working
- Fleet blackboard: ~/fleet/ (68 project status files tracked)

**Files Modified This Session:**
- Updated HANDOFF.md with current session status

**Next Session:** Continue from /loop recurring check. No immediate action needed. Verify that new instance can access ~/fleet blackboard and resume recurring checks if needed.

---

**Prepared by:** Claude Code (Haiku 4.5)
**Status:** AUTONOMY READY — no human input required, ready for next session

---

## THE MERGE QUEUE (ordered — do these in this sequence)

| # | Repo | PR / Branch | Action | Notes |
|---|------|-------------|--------|-------|
| 1 | CodeMonkeys | PR #74 | **Fly deploy** (already merged) | `fly deploy --remote-only` from `~/CodeMonkeys` |
| 2 | CodeMonkeys | `work/swarm-viz-phase1` | Open PR then merge | Colony visualizer (standalone canvas) |
| 3 | CodeMonkeys | `work/swarm-state-api` | Open PR then merge | Stacks on top of swarm-viz — do AFTER #2 |
| 4 | MeniscusMaximus | PR #37 | Merge first | 12-step API |
| 5 | MeniscusMaximus | PR #38 | Merge after #37 | Steps UI |
| 6 | TradeGame | PR #43 | Merge | W2-3 applyDrillSeed |
| 7 | OmniDesk | PR #1 (blocked) | Fix SSRF → re-cert → merge | See SSRF section below |

**MeniscusMaximus:** merge = deploy (master → Fly auto-deploys). Use `git push origin master` — never force-push.

---

## PROJECT STATES

### CodeMonkeys — `~/CodeMonkeys`
- **Live:** https://codemonkeys.fly.dev (v17 deployed, /healthz 200, /readyz 200)
- **main** branch is clean; PR #74 (20 model/session improvements) merged + deployed
- **Swarm branches** (not yet PR'd):
  - `work/swarm-viz-phase1` (commit `7433054`) — Colony visualizer
  - `work/swarm-state-api` (commit `37b877f`) — live state feed (`GET /api/swarm/state`)
- **Deploy command:** `fly deploy --remote-only` from `~/CodeMonkeys` (no local Docker on Chromebook)
- **Test suite:** `pytest -q` — must be green before push (600 tests)
- **Next backlog (designed, not built):** N5 streaming, N6 session-resume, N8 context compaction, N9 structured retry, N12 model catalog — specs in `docs/IDEATION.md`

### MeniscusMaximus — `~/MeniscusMaximus`
- **Production branch:** `master` (NOT `main`) → auto-deploys to Fly (app: system32-autumn-tide-1990)
- **Open PRs awaiting owner merge:**
  - PR #37: 12-step API (merge this first)
  - PR #38: Steps UI (depends on #37)
  - PR #28: crisis-net activation runbook (doc, safe to merge anytime)
  - PR #30: crisis-lexicon near-synonym gaps + tests (flagged for clinical review)
  - PR #31: webhook signature-verification tests
- **Incomplete / no PR yet:**
  - M-7 completion: communal-cascade + receipt layer on top of existing `/api/me/delete` — agent died on rate limit, never PR'd. Re-dispatch fresh.
- **Key invariants:**
  - `@serialize_user_writes` on ALL `users.json` mutators (race condition prevention)
  - `users.json` atomic save via `save_users()` only
  - `verify_owner` vs `verify_owner_strict` — use `_strict` only for root-singleton GETs

### OmniDesk — `~/omnidesk`
- **Status:** 14 PRs merged to main, NEVER deployed
- **Blockers before deploy (owner must do all 4):**
  - D1: `openssl rand -hex 32` → `fly secrets set ADMIN_TOKEN="..."`
  - D2: Stripe signup → follow `docs/STRIPE_WIRING.md` (4 secrets to set)
  - D3: Confirm 200 chats/day limit (or set `TENANT_DAILY_CHAT_LIMIT` env var)
  - D4: Confirm `app = "omnidesk"` in `fly.toml` matches Fly app name → `fly deploy --remote-only`
- **2 pre-existing SSRF gaps to fix before prod traffic:**
  - DNS rebinding vulnerability in crawler
  - IPv4-mapped IPv6 bypass in crawler
  - Fix → re-run red-team agent → then merge/deploy
- **Stripe runbook:** `~/fleet/research/runbook-stripe-setup.md`

### TradeGame — `~/TradeGame`
- **Status:** Live-drill arc complete through XP (PRs #34–#39 merged)
- **Open PR:** #43 — W2-3 `applyDrillSeed` + 7 tests (branch `work/drill-build`)
- **Playable:** Drawdown Survival playable + pays (paymaster-grade gated)
- **Hard gates:** entity before public, ANY revenue → attorney first, COPPA before Phase 2 data

### MeniscusMaximus / omniverse — M-7 erasure (TWO incomplete builds)
Both died on rate-limit. Nothing to recover — re-dispatch fresh:
1. **MM M-7 completion:** add communal-cascade + receipt to existing `/api/me/delete` (the basic delete already exists in PR #24; this adds the Tapestry contribution cascade + audit receipt). Owner-reserved: don't guess six-gate/k-anon semantics.
2. **omniverse M-7:** hard-delete contact PII + RETAIN non-PII suppression token (for TCPA opt-out) + generate receipt. omniverse had security hardening #7–#16 shipped but NOT this.

### PixelSports — `~/PixelSports`
- PR #49 MERGED (Wave C+D + Cove Beach). No open PRs.
- Next: art pass (Cove Beach confirmed by owner). Gates: Steam $100 + Win signing + Apple $99 before publish.

### DrivingMeNuts — `~/DrivingMeNuts`
- Bootstrap done (7 docs, PR #1 both repos UNMERGED). Phaser+TS engine ratified.
- 2 owner questions open in fleet (see `~/fleet/inbox/drivingmenuts.md`).

---

## OWNER-GATED DECISIONS (nothing can proceed until these are answered)

| Item | Location | What's needed |
|------|----------|---------------|
| Stripe KYC | OmniDesk | Sign up at stripe.com, follow STRIPE_WIRING.md |
| OmniDesk deploy | omnidesk | D1–D4 above |
| MM M-7 semantics | MeniscusMaximus | Confirm six-gate/k-anon approach before re-dispatch |
| omniverse M-7 | omniverse | Confirm TCPA token retention approach |
| DrivingMeNuts 2 questions | ~/fleet/inbox/drivingmenuts.md | Answer, then re-activate agent |
| PixelSports visual V1–V7 | fleet/questions.md | Art direction answers |
| Ilerioluwa: fee table + schedule + logo | docs/CONTENT_INTAKE.md | Simon's answers (9 items) |
| Clean Sheet: tone/perspective/repo/title | memory | 4 owner decisions before repo creation |

---

## RECURRING SYSTEMS (still running, do NOT stop)

- **R1/R2 WIP-snapshot timers:** systemd --user (every 4m / 5m). Check: `systemctl --user status wip-snapshot.timer staleness-sweep.timer`
- **FleetDeck:** `http://localhost:5000` — local dashboard reading `~/fleet/` blackboard. Check: `systemctl --user status fleetdeck`
- **OmniHerald:** social automation on Zernio (FB+IG). Do not touch.

---

## DEPLOY COMMANDS (cheat sheet)

```bash
# CodeMonkeys
cd ~/CodeMonkeys && fly deploy --remote-only

# MeniscusMaximus (push = deploy)
cd ~/MeniscusMaximus && git push origin master

# OmniDesk (first deploy — do D1-D4 first)
cd ~/omnidesk && fly deploy --remote-only

# omniverse
cd ~/omniverse && fly deploy --remote-only
```

---

## HOW TO VERIFY LIVE SERVICES

```bash
curl https://codemonkeys.fly.dev/healthz         # CodeMonkeys
curl https://system32-autumn-tide-1990.fly.dev/healthz   # MeniscusMaximus
# OmniDesk: not deployed yet
```

---

## CRITICAL CONSTANTS

- **Multi-instance:** Always `git branch --show-current` before committing. Stage ONLY files you changed. Never `git add -A`.
- **MM branch:** `master` is production, not `main`.
- **No local Docker:** always `fly deploy --remote-only`.
- **Credits:** Use Sonnet, no swarms, no parallel agent fans unless explicitly authorized. Check `~/agent-corps/CORPS_MODEL_TIERS.md`.
- **License:** all repos proprietary/all-rights-reserved, owner deliberately UNNAMED. Exception: Ilerioluwa repos are Simon's IP — never touch.
- **Preview repos:** nothing confidential ever in `---Preview` repos.

---

*Last updated: 2026-06-09 by Claude Sonnet 4.6 (handoff consolidation)*
