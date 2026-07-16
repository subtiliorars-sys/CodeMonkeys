# CodeMonkeys — Current State (jumping-off point)

**Read this first when picking the project back up.** Last updated 2026-07-16
(post-UI-fix session: viewport, budget removal, username remember, tab-bar offset).

Tests: **769 passed / 16 skipped / 0 failures**. Working tree clean.

## Recent work (this session, all on main / deployed)

| Commit | What |
|---|---|
| `890b2b8` | Remember username checkbox on login form |
| `c7c62e0` | try/catch on _lockViewport + _cmDiag() diagnostic |
| `2a36598` | Offset view-main below 38px tab-bar |
| `280dc35` | inline min-height:0 on #stream + flex-shrink:0 on composer |
| `68382e9` | JS-enforced viewport lock (_lockViewport) |
| `4ad92a8` | Removed spend display from header |
| `fc797c2` | Removed budget alert banner + viewport fixes |
| `7f55e56` | Swarm-viz Phase 2 tree visualization (sub-agent hierarchy) |

## ⚠️ OPEN — Needs attention

### 1. Buttons/UI not fully functional
Some UI buttons reportedly "don't do anything." A diagnostic function `_cmDiag()` was added — open browser console (F12) and run `_cmDiag()` to see which elements exist/are hidden. The `_lockViewport` JS function was wrapped in try/catch to prevent it from breaking other init code. Needs investigation with console open to find root cause.

### 2. Session token may not survive deploys
Session secret is persisted at `/data/session_secret.key` on the Fly volume, but tokens may become invalid after deploys. User needs to re-login after each deploy. May be expected (server restart) or a volume mount issue.

### 3. Docker cache-bust hack
The Dockerfile has a `# cache-bust: YYYY-MM-DD-HHMM` comment at line 2 that gets updated on every deploy to force a clean rebuild of static files. This is a workaround — the Depot builder was caching old `COPY static/` layers. Consider a proper fix (e.g., `--no-cache` flag or build args).

## Key files

| File | Role |
|---|---|
| `server.py` | Entire backend (single file, ~10k lines) |
| `static/forge/index.html` | Main UI + inline CSS (viewport overrides) |
| `static/forge/app.js` | All frontend logic, auth, sessions, viewport lock |
| `static/forge/swarm-viz.js` | Canvas 2D colony visualizer (ring + tree modes) |
| `static/forge/swarm_viz.html` | Swarm viz page with session selector + layout toggle |
| `static/forge/index-shell.js` | Shell UI: tab bar, taskbar, keyboard handling |
| `static/forge/jungle-theme.css` | Theme: tab bar (38px), sidebar (52px), colors, layout |
| `desktop/launcher.py` | PyWebView desktop window (1280x860, may not fit 1280x800 screens) |
| `corps/` | 15+ Daystrom agent definitions |
| `docs/STATE.md` | This file |
| `docs/ARCHITECTURE.md` | Architecture overview |
| `docs/RECOVERY.md` | Lockout/emergency runbook |

## Deploy

```powershell
./scripts/deploy.ps1
```

This wraps `fly deploy --app codemonkeys --remote-only` and always passes a
fresh `--build-arg CACHEBUST=<unix-timestamp>`, which the Dockerfile uses
right before `COPY static/ static/` to force that layer to rebuild every
time (Depot's remote builder was observed serving a stale static/ layer
otherwise — see PR #186 / the old "cache-bust: YYYY-MM-DD" comment this
replaced). No more hand-editing a date comment before each deploy.

Deploy takes ~90s (remote Depot build). The 30s shell timeout may kill it — use `Start-Process pwsh -ArgumentList '-File scripts/deploy.ps1' -WindowStyle Minimized` to detach.

Live at: https://codemonkeys.fly.dev

## Viewport layout (critical context)

The viewport was a recurring issue. Current solution:
- `_lockViewport()` in app.js sets `#view-main` to `position: fixed`, offset below the 38px `#tab-bar`, with `height = innerHeight - tabH`
- `#stream` has inline `min-height:0`, `#composer` has inline `flex-shrink:0`
- These inline styles bypass CSS cascade conflicts
- If the bottom gets cut off again, check that `_lockViewport` is running and the tab bar height is correct

## What it is
Self-hosted web coding console (Claude Code-style agent). Single-file FastAPI
backend (`server.py`), vanilla-JS frontend (`static/forge/`), JSON-on-volume,
Daystrom agent corps in `corps/`. Full overview: `README.md` +
`docs/ARCHITECTURE.md`. Backlog/next steps: `docs/IDEATION.md`.

## Live deployment
- **App:** `codemonkeys` on Fly · **URL:** https://codemonkeys.fly.dev
- Its **own** machine + volume (`cm_data`, dfw, scale-to-zero). NEVER co-locate
  with another app — it executes code. (See `SECURITY.md`.)
- Owner account registered; **enrollment is locked**.
- `GITHUB_TOKEN` secret set. Model API keys are entered in the UI (⚙ Models),
  stored on `/data`, not in Fly secrets.
- Deploy: `fly deploy --app codemonkeys --remote-only` (Chromebook host has no
  local Docker — remote Depot builder). Logs: `fly logs -a codemonkeys`.
- **2026-06-07: redeployed at version 10** — everything through Wave 3 went LIVE
  (v0.2 MCP + v0.3 security wave + #21 blackboard + #22 debate-verify + Wave 3
  W1–W12). `/healthz` (W1) is wired as the Fly liveness check (1 passing).
  Smoke-tested live: `/healthz` 200, `/api/usage` + `/api/kb` 401 fail-closed,
  `/` 200.
- **2026-06-07 PM: DEPLOYED at v15** — last documented production deploy:
  Wave 1–4, web terminal (#37, OFF), secret encrypt-at-rest (#47) + recovery
  (#48), and the N-backlog Wave 1+2 (PRs #49–#56: N1 failover, N2 daily cap,
  N3 cost dashboard, N4 diff preview, N7 plan→execute, N10 `/readyz`, N11 audit
  viewer). Smoke-green:
  `/healthz` 200, `/readyz` 200 (checks all true), `/` 200, `/api/usage`+`/api/audit`
  401 fail-closed, `/fleet-status.json` 404 (FLEET_TOKEN unset). Suite 472 on main.
- **After v15:** main has continued to move (S4-B, N5/N6/N8/N9/N12, CM-W1-CM-W7,
  governance/security follow-ups, Forge UI, desktop). Treat deploy status for
  those later merges as **manual/owner-confirmed only** unless a newer deploy note
  is added here.
- **Inert until owner sets the secret (each = `fly secrets set …` auto-redeploys):**
  `CM_MASTER_KEY` (encrypt session/model/MCP secrets at rest — see
  `docs/RECOVERY.md`), `FLEET_TOKEN` (fleet feed), `NOTIFY_WEBHOOK_URL`
  (+ optional HMAC secret for ntfy), webhook gates, terminal gates, and optional
  streaming (`STREAM_ENABLED`). Tailwind phase-2 CDN removal is merged; eyeball
  the vendored CSS render after any deploy.

## Shipped so far (v0.1)
- Auth: 4-digit+ PIN (PBKDF2) + mandatory TOTP; HMAC tokens; fail-closed.
- WebAuthn passkey/biometric login (login + sidebar "Add passkey") plus
  self-service credential listing/removal.
- Invite system: Owner mints starter username+PIN → dev forced through
  first-login setup (new PIN + authenticator) → becomes Member. Members use
  console/sessions/repos; Owner-only = models/keys + invites. `/api/invite`,
  `/api/users`, `/api/account/setup`. Since CM-W7/#164, sessions are
  user-owned and user data has per-user workspace subdirs; the app process,
  shell blast radius, and repo/GITHUB_TOKEN remain shared until deeper sandbox
  layers land.
- Models: Wayfinder-style **one key per provider, pick any model**, **Auto
  cheapest-first** toggle + per-provider ✓auto. Old config auto-migrates
  (keys preserved). Presets: gemini/openrouter/anthropic/openai/deepseek/xai.
- Modes: **plan / default / auto** (Claude Code-style). plan = read-only tools;
  auto = skip approval gate.
- Sessions: create/list/message/events(poll)/approve/stop/**delete**.
- Agent loop: read/write/edit/list/glob/grep/bash (path-jailed) + spawn_agent
  (corps subagents, tool allowlists, tier routing, spawn cap 8).
- Cost governor: per-call ledger events + per-session USD budget halt.
- Approval gate: push/deploy/destructive bash pauses for in-UI APPROVE.
- Pixel-art console + live swarm view (`static/forge/swarm.html`).

## Shipped so far (v0.2 — 2026-06-06, merged to `main`)
- **MCP client** (#1): sync Streamable-HTTP JSON-RPC over `requests` (no SDK/new
  deps). Owner-only `/api/mcp` CRUD + ⚙ MCP panel. See "MCP connectors" below.
- **MCP stdio transport** (#1b): local MCP servers (`npx …`) over newline JSON-RPC;
  `Popen([cmd,*args])` never shell=True; Node added to the Docker image (~80 MB).
- **MCP startup auto-connect** (#1c): enabled servers warmed in a background
  thread on boot (lazy-connect remains the fallback).
- **MCP OAuth 2.1** (#1a): auth-code + PKCE S256 for Google Drive / Microsoft 365;
  tokens in `mcp_tokens.json` (0600, never returned/logged). **Owner-gated** —
  needs a registered Google/Azure OAuth app before it can complete a round-trip.
- **Self-heal loop** (#2): auto-mode run → read-failure → patch → rerun-until-green
  doctrine in `MODE_GUIDANCE["auto"]` (caps: 5 iters / repeat-signature=blocked /
  budget). plan/default unchanged.

- **Spec-first plan mode** (#3): plan mode persists Constitution/Spec/Plan/Tasks
  to `.codemonkeys/specs/<slug>/` via the jailed `save_spec` tool; each task
  carries a verify step. Plan mode is now read-only **end to end** (spawn_agent
  can't escalate to a write-capable subagent).
- **apply_patch** (#8): `git apply` unified-diff edits, atomic, every diff target
  path jail-checked before apply. In FULL_TOOLS + corps `Edit`.

## Shipped since (v0.3 — 2026-06-06/07, merged to `main`)
- **Security wave** (PRs #12–#20): approval-gate shell-quoting hardening,
  secret redaction in context/UI/audit log, upload/message-input hardening,
  login brute-force throttle + per-IP/global ceilings, security response
  headers, local TOTP QR (no CDN secret leak), pinned requirements + CI.
- **Blackboard memory** (#4, PR #14 + multi-agent extension): persistent
  `.codemonkeys/blackboard-<slug>.md` FACTS/DECISIONS/NEXT per task; jailed
  `blackboard_read`/`blackboard_write` tools; boards injected (bounded, framed
  as untrusted DATA) into the commander prompt at session start. Multi-AGENT
  half: every Daystrom subagent gets `blackboard_read`; Edit/Write-capable
  units also get `blackboard_write`; plan mode read-only end to end
  (`_plan_filter_subagent_tools`). Write path serialized (`_BB_LOCK`,
  single-process assumption) + atomic tmp+rename. Red-teamed GO-WITH-FIXES,
  all fixes applied; tests in `tests/test_blackboard.py`.

## Shipped since (Wave 4 — 2026-06-07, merged to `main`)
- **Fractal/tiered memory phase 1** (#6, PR #33): deterministic theme-token
  digest per session.
- **Vendored Tailwind** (#3, PRs #34/#40): build pipeline + CI `css` job; phase 2
  dropped the runtime CDN and tightened CSP to self-hosted scripts.
- **Connector marketplace** (#9, PR #35): curated catalog + MCP Registry fallback.
- **Webhook → PR runs** (#5, PR #36): GitHub issue/webhook triggers a background
  session that opens a PR. Fail-closed: OFF by default, HMAC sig, sender
  allow-list, label + action gate, delivery dedup, body cap. **INERT until owner
  sets WEBHOOK_ENABLED/WEBHOOK_SECRET/WEBHOOK_ALLOWED_SENDERS + adds the GitHub
  webhook** (steps in PR #36 body).

- **Web terminal** (PR #37, merged 2026-06-07): `/terminal` REPL + Owner-only
  `!cmd` exec behind DOUBLE env gate (`TERMINAL_ENABLED` + `TERMINAL_EXEC_ENABLED`),
  both default OFF → 404 everywhere. Red-teamed GO-WITH-FIXES (raw PTY mode =
  NO-GO). Design: `docs/TERMINAL_DESIGN.md`. **Stays OFF until owner sets both
  gates post-deploy.**

## Shipped since the June state refresh (merged to `main`)
- **S-list/N-list closure:** #58 S4-B encrypts `model_config.json`/`mcp_tokens.json`
  at rest and evicts `GITHUB_TOKEN`; #59 adds structured tool-error repair/abort;
  #60 resumes sessions after restart; #45 notify-on-done is merged and inert until
  `NOTIFY_WEBHOOK_URL` is set.
- **CM-W1-CM-W7 automation waves:** streaming output (default OFF), context
  auto-compaction, model catalog refresh, lint feedback loop, Field Report
  triage/proposals, and session ownership gates are all merged. `WAVES.md` now
  says the safe automation backlog is exhausted.
- **Forge/UI track:** Agents hub, provider-wait UX, hooks/skills tabs, Jungle
  redesign, OTP-secret copy, passkey registration, and hygiene docs are merged.
- **Governance/security/data:** governance pilot (#65), M-7 erasure cascade and
  later per-user attribution/message-content erasure (#69/#164), S-3 hash-chained
  audit receipts (#159), M-4 explicit cloud-egress consent gate (#160), June
  security audit/remediation (#155/#156/#157), and corps resync (#158) are merged.
- **Ideation sweep:** PR #148 (`work/ideation-sweep`) merged 2026-07-13; it no
  longer needs wave-worker review cleanup.
- **Desktop track:** native desktop shell (#167) and Windows installer polish
  (#170) are merged. Parallel desktop items stay manual unless `WAVES.md` moves
  them into the automation queue.

## Current PR / queue snapshot (2026-07-15)
- **Open PRs:** #168 corps resync follow-up (open, currently unstable) and #165
  M-8 backup posture (draft). Treat both as owner/manual lanes unless explicitly
  assigned.
- **Automation wave queue:** `WAVES.md` Active queue is empty. Do **not** invent a
  new automation wave; if PR #148 is already merged and no pending wave appears,
  do docs hygiene only.
- **OWNER-GATED:** deploys, Fly config/secrets, terminal activation, webhook
  activation, OAuth app registration, and deeper shell/kernel sandboxing.

## MCP connectors (v1+v2, merged to main 2026-06-06)
- Sync Streamable-HTTP JSON-RPC client over `requests` (no new deps, no SDK).
  Owner-only `/api/mcp` CRUD + ⚙ MCP panel in `static/forge/`. Transports:
  **http** (bearer/PAT or OAuth) and **stdio** (local process). Per-server token
  write-only on `/data`. GitHub preset `https://api.githubcopilot.com/mcp/`;
  Google Drive / M365 presets (OAuth — owner supplies client_id).
- Tools merged into the commander loop as `mcp_<slug>_<tool>` (NOT given to corps
  subagents). Red-teamed + hardened: `readOnlyHint` is a UI hint only, never
  trusted for gating — plan mode = no MCP tools, default gates every MCP call,
  auto skips; https-only (localhost http ok); wall-clock+byte-capped streams
  (http SSE and stdio); per-sid connect lock; ≤128 tools/session; first-writer
  namespacing; OAuth tokens 0600 + PKCE + state CSRF. See SECURITY.md "MCP".
- **Owner action to use it:** after deploy, open ⚙ MCP: add GitHub (preset) +
  paste a PAT. For Drive/M365: register a Google/Azure OAuth app (redirect
  `https://<host>/api/mcp/oauth/callback`), fill client_id, click Connect
  (OAuth). Real `npx`/OAuth round-trips are still configuration-dependent owner
  validation items.

## How to work this repo
- Branch per task (`work/<topic>`); the owner runs **concurrent consoles** —
  stage only files YOU changed, never `git add -A`. See `CLAUDE.md`.
- Verify before deploy: `./.venv/bin/python -c "import server"` + a boot smoke
  test (`docs/SETUP.md` → Local development). Deploys are manual.
- Local dev: `python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt`
  then `DATA_DIR=./data ./.venv/bin/uvicorn server:app --reload --port 8080`.

## Known gaps / TODO
- Shell is still cwd-jailed, not kernel-sandboxed. A same-uid command can still
  reach app files and `/proc` despite the subprocess env scrub; deeper sandbox
  layers remain owner-gated (see `SECURITY.md` Known limitations).
- Members now have session ownership and per-user data subdirs, but they still
  share the same server process, repo checkout, and scoped `GITHUB_TOKEN` blast
  radius until the remaining S6 isolation layers land.
- OAuth app registration, webhook activation, Fleet Deck activation, terminal
  activation, deploys, and Fly secret/config changes are owner actions.
- M-8 backup posture is still in-flight as draft PR #165; do not treat it as
  shipped until merged.
- Auto-mode MCP/risky-bash debate verification is damage reduction, not an auth
  boundary; keep default-mode human approval gates as the real boundary.
- *(Closed since the old state note: remove-passkey UI, escalation-on-failure,
  login throttle/ceilings, local TOTP QR, Tailwind CDN removal/CSP, blank-base_url
  guard, S5 notify-on-done, N5/N6/N8/N9/N12, session ownership.)*
