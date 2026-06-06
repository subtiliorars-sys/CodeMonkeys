# CodeMonkeys — Current State (jumping-off point)

**Read this first when picking the project back up.** Last updated 2026-06-06.

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
- Deploy: `fly deploy --app codemonkeys`. Logs: `fly logs -a codemonkeys`.

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

## Next up (from docs/IDEATION.md)
1. ~~MCP client~~ ✅ **SHIPPED 2026-06-06** (branch `work/mcp-client`, not yet
   deployed — owner deploys manually). See "MCP connectors" below.
2. **Self-heal loop** — run → fail → fix → rerun + lint/LSP feedback.
Then spec-first plan mode (#3) and blackboard memory (#4). MCP follow-ups
#1a OAuth (Drive/MS), #1b stdio+Node image, #1c startup auto-connect in IDEATION.

## MCP connectors (v1, shipped 2026-06-06)
- Sync Streamable-HTTP JSON-RPC client over `requests` (no new deps, no SDK,
  remote HTTP servers only). Owner-only `/api/mcp` CRUD + ⚙ MCP panel in
  `static/forge/`. Per-server bearer/PAT (write-only, stored on `/data`).
  GitHub preset: `https://api.githubcopilot.com/mcp/` (owner pastes a PAT).
- Tools merged into the commander loop as `mcp_<slug>_<tool>` (NOT given to corps
  subagents). Red-teamed + hardened: `readOnlyHint` is a UI hint only, never
  trusted for gating — plan mode = no MCP tools, default mode gates every MCP
  call, auto skips; https-only (localhost http ok); slowloris/byte-capped stream;
  ≤128 tools/session; first-writer-wins namespacing. See SECURITY.md "MCP".
- **Owner action to use it:** open ⚙ MCP, add GitHub (preset) + paste a PAT,
  then `fly deploy --app codemonkeys` (this is on a branch, undeployed).

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
