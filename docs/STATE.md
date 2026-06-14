# CodeMonkeys — Current State (jumping-off point)

**Read this first when picking the project back up.** Last updated 2026-06-07
(post Wave-4 merges).

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
- **2026-06-07: redeployed at version 10** — everything through Wave 3 is LIVE
  (v0.2 MCP + v0.3 security wave + #21 blackboard + #22 debate-verify + Wave 3
  W1–W12). `/healthz` (W1) is wired as the Fly liveness check (1 passing).
  Smoke-tested live: `/healthz` 200, `/api/usage` + `/api/kb` 401 fail-closed,
  `/` 200.
- **2026-06-07 PM: DEPLOYED at v15** — everything merged to date is LIVE: Wave 1–4,
  web terminal (#37, OFF), secret encrypt-at-rest (#47) + recovery (#48), and the
  N-backlog Wave 1+2 (PRs #49–#56: N1 failover, N2 daily cap, N3 cost dashboard,
  N4 diff preview, N7 plan→execute, N10 `/readyz`, N11 audit viewer). Smoke-green:
  `/healthz` 200, `/readyz` 200 (checks all true), `/` 200, `/api/usage`+`/api/audit`
  401 fail-closed, `/fleet-status.json` 404 (FLEET_TOKEN unset). Suite 472 on main.
- **Inert until owner sets the secret (each = `fly secrets set …` auto-redeploys):**
  `CM_MASTER_KEY` (encrypt session secret at rest — see docs/RECOVERY.md), `FLEET_TOKEN`
  (fleet feed), `NOTIFY_WEBHOOK_URL` (ntfy), webhook + TERMINAL gates. Tailwind
  phase-2 CDN removal is live — eyeball the vendored CSS render.

## Admin & credit-sharing rehab (2026-06-14, branch `claude/sandbox-ux-admin-system-4jnwlz`)
Owner control surface filled in + a credit-sharing master switch:
- **Reset a Member's 2FA** — `POST /api/users/{u}/reset-mfa` (Owner-only): clears
  TOTP + every passkey, flags `must_reset` so the next login is username-only and
  re-routes through first-time authenticator setup; clears the login throttle so a
  prior lockout can't block recovery. Refuses Owners/self (use `reset_access.py`).
- **Rename a Member** — `POST /api/users/{u}/rename` (Owner-only): regex + collision
  + M-7 tombstone guards; migrates the record, login-throttle counter, transient
  WebAuthn challenge, and on-disk Vertex BYO/provisioned cred files.
- **Share my API credits** — global `share_owner_keys` toggle (model config, default
  **OFF / fail-closed**). Enforced at the single chokepoint `_callable_provider`: a
  Member may spend the Owner's non-Vertex keys only while it's ON; Owner + internal
  contexts always pass. Vertex keeps its own per-user gate. Toggle in ⚙ People panel;
  `/api/models` GET + `/api/models/settings` carry it; `/api/me` exposes
  `keys_shared`/`can_run` so a Member sees a clear "ask the owner" banner up front.
- UI: People panel gains the toggle + per-member rename / reset-2FA / remove actions,
  all mobile-friendly; member access banner on no usable model. Tests in
  `tests/test_admin_user_mgmt.py` (12). Suite green (pre-existing root-only readyz
  artifact aside). **Needs an S-4 red-team pass before deploy** (auth/money surface).

## Shipped so far (v0.1)
- Auth: 4-digit+ PIN (PBKDF2) + mandatory TOTP; HMAC tokens; fail-closed.
- WebAuthn passkey/biometric login (login + sidebar "Add passkey"). *No
  remove-passkey UI yet.*
- Invite system: Owner mints starter username+PIN → dev forced through
  first-login setup (new PIN + authenticator) → becomes Member. Members use
  console/sessions/repos; Owner-only = models/keys + invites. `/api/invite`,
  `/api/users`, `/api/account/setup`. **No per-user workspace isolation** — all
  members share workspace + GITHUB_TOKEN + shell.
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

## Shipped so far (v0.2 — 2026-06-06, all merged to `main`, NOT yet deployed)
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

## Shipped since (v0.3 — 2026-06-06/07, merged to `main`, NOT yet deployed)
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

## Shipped since (Wave 4 — 2026-06-07, merged to `main`, NOT yet deployed)
- **Fractal/tiered memory phase 1** (#6, PR #33): deterministic theme-token
  digest per session.
- **Vendored Tailwind phase 1** (#3, PR #34): build pipeline + CI `css` job;
  **CDN still active** — phase 2 (drop CDN + tighten CSP) is OWNER-GATED until
  the owner confirms the vendored page renders.
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

## Open PR stack (2026-06-07 overnight — unmerged, owner reviews)
All build→PR under the overnight order; **integration-verified: the 6 merge
together cleanly, integrated suite 323/323 green.** Suggested order:
1. **#38** docs/consolidation (this PR) — zero code conflict.
2. **#42** dup-send fix + blank-base_url guard → then **close #39** (subset of #42).
3. **#43** fractal memory phase 2 (scrubbed digest + pattern library) — broadens
   `_scan_secrets`; land before #41 so the fleet feed inherits it.
4. **#41** Fleet Deck `/fleet-status.json` (owner sets `FLEET_TOKEN` + deploys to activate).
5. **#44** bash/terminal/MCP env scrub (defense-in-depth).
6. **#40** Tailwind phase-2 / CSP — owner does the post-deploy visual check.

## Next up
- **S5 notify-on-done** (next buildable wave).
- **OWNER-GATED:** Tailwind phase-2 visual check (#40); Fleet Deck activation (#41);
  terminal activation (#37); **bash sandbox / secrets-at-rest** — red-team found bash
  can exfiltrate `session_secret.key` (→ auth bypass), model keys, OAuth tokens via
  `cat ../<file>` + `/proc/<pid>/environ` (see SECURITY.md Known-limitations +
  questions.md). The original "OAuth secrets-envelope" folds into that decision.

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
- **Owner action to use it:** `fly deploy --app codemonkeys`, then open ⚙ MCP:
  add GitHub (preset) + paste a PAT. For Drive/M365: register a Google/Azure
  OAuth app (redirect `https://<host>/api/mcp/oauth/callback`), fill client_id,
  click Connect (OAuth). **Unverified until deploy:** the Node-in-image Docker
  build and any real `npx`/OAuth round-trip (no local Docker/Node on dev host).

## How to work this repo
- Branch per task (`work/<topic>`); the owner runs **concurrent consoles** —
  stage only files YOU changed, never `git add -A`. See `CLAUDE.md`.
- Verify before deploy: `./.venv/bin/python -c "import server"` + a boot smoke
  test (`docs/SETUP.md` → Local development). Deploys are manual.
- Local dev: `python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt`
  then `DATA_DIR=./data ./.venv/bin/uvicorn server:app --reload --port 8080`.

## Known gaps / TODO
- No per-user workspace isolation (all members share workspace + GITHUB_TOKEN +
  shell).
- Tailwind CDN still active (vendored pipeline merged, phase-2 cutover
  owner-gated); CSP tighten rides with it.
- OAuth secrets-envelope: `client_secret`/`refresh_token` plaintext on `/data`,
  readable by the unsandboxed `bash` tool.
- Blank-base_url provider bug (see "Next up" #1).
- Auto-mode MCP calls: debate-verify covers risky bash + MCP (W7), but MCP
  coverage is heuristic — revisit if MCP usage grows.
- *(Closed in Wave 3: remove-passkey UI ✓, escalation-on-failure ✓, login
  throttle/ceilings ✓, local TOTP QR ✓.)*
