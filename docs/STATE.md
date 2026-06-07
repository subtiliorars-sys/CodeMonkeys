# CodeMonkeys — Current State (jumping-off point)

**Read this first when picking the project back up.** Last updated 2026-06-07.

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

## Next up (from docs/IDEATION.md)
1. **Connector marketplace UI** (#9) — poll the MCP Registry, one-click add (now
   that the MCP client exists). Plus **escalation-on-failure** (cheapest→pricier).
2. **Debate-verify gate** (#7) on high-risk changes; **two-layer KB** (#10).

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
- No remove-passkey UI; no per-user workspace isolation; no escalation-on-failure
  (cost governor selects cheapest but doesn't yet retry up a tier on failure);
  Tailwind + QR via CDN (vendor before multi-user); no login rate-limit.
