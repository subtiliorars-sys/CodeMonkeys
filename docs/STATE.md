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
- **Wave 4 (PRs #33/#34/#35/#36) is merged to `main` but NOT yet deployed** —
  next deploy picks up fractal memory, vendored-Tailwind phase 1, connector
  marketplace, and webhook→PR runs (inert until webhook secrets set).

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

## Open PRs (owner-gated)
- **#37 web terminal** — `/terminal` REPL + Owner-only `!cmd` exec behind DOUBLE
  env gate (`TERMINAL_ENABLED` + `TERMINAL_EXEC_ENABLED`), both default OFF.
  Red-teamed GO-WITH-FIXES (raw PTY mode = NO-GO). Design: `docs/TERMINAL_DESIGN.md`.

## Next up
1. **BUG:** provider entry with blank `base_url` reaches the runtime and errors
   with `Invalid URL '/chat/completions'` before escalation rescues it (found in
   2026-06-07 live smoke). Fix: fail-fast at model selection + config-load repair
   backfilling known provider URLs.
2. **Fleet Deck handoff:** `GET /fleet-status.json` read-only Bearer-auth ops
   feed per `~/fleet/contracts/fleetdeck-codemonkeys.md` (build+PR; deploy
   owner-gated).
3. Fractal memory phase 2+; Tailwind phase 2 (owner-gated); OAuth
   secrets-envelope (see IDEATION "Still open").

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
