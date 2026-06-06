# CodeMonkeys — Ideation & Build Backlog

Living backlog from two research passes (2026-06-06): a web landscape survey of
autonomous "build it for me" systems (111 agents, 28 sources, 20 claims
confirmed / 5 refuted) + a mining of the owner's own repos (MeniscusMaximus
memory-engine spec, OpenClaw design, agent-corps doctrine, OmniVerse).

## The field has converged on one loop

Every serious autonomous coder (OpenHands, Devin, Cursor, Copilot coding agent)
runs: **spec → decompose into isolated testable tasks → code → run tests/lint →
read failure → fix → repeat until green or genuinely blocked → then ask the
human.** That loop is the thing to own.

## Ranked backlog (value / effort)

| # | Feature | Why | Effort |
|---|---------|-----|--------|
| ~~1~~ | ~~**MCP client**~~ ✅ **SHIPPED 2026-06-06** (v1: sync Streamable-HTTP JSON-RPC over `requests`, remote servers only, per-server bearer/PAT, Owner-only `/api/mcp`, ⚙ MCP panel). Red-teamed: readOnlyHint not trusted for gating, slowloris-capped, https-only, tool-count capped. See follow-ups #1a/#1b below. | M |
| 2 | **Self-heal loop** + lint/LSP feedback | Run → parse failure → patch → rerun until green; the engine under every autonomous builder. Turns "generate & hope" into reliable. | M |
| 3 | **Spec-first plan mode** | Constitution / Spec / Plan / Tasks artifacts saved in the workspace; each task carries its own verification step. Structured PRD spine for the corps. (Ref: GitHub Spec Kit.) | S–M |
| 4 | **Blackboard cross-session memory** | `.codemonkeys/blackboard-<task>.md` with FACTS/DECISIONS/NEXT that survives session resets. Owner's own corps pattern; near-zero infra. | S |
| 5 | **Issue/webhook-triggered background runs** | Assign an issue / hit a webhook → background session opens a PR. Pair with notify-on-done (OmniVerse pattern). Cron via existing `/loop`. | M |
| 6 | **Tiered / "fractal" memory + theme-token compaction** | Per-session raw → scrubbed working memory → curated pattern library; compact by extracting structured theme tokens, not lossy LLM summaries. (Owner's memory-engine spec.) | L |
| 7 | **Debate-verify gate** on high-risk changes | 3 heterogeneous verifiers, majority-refute = don't-ship (~30% fewer errors). Use the existing corps; trigger only on auth/money/irreversible. | S |
| 8 | **apply_patch tool** (unified-diff edits) | Edit big files without full rewrites; the one file primitive Cursor/Aider have that we lack. | S |
| 9 | **Connector marketplace UI** | Poll the MCP Registry, one-click add servers — the realistic "self-healing connectors." Depends on #1. | M |
| 10 | **Two-layer KB** | Hand-authored rules + deterministically-generated project facts; build fails if secrets would leak into context. (OmniVerse pattern.) | S |

## MCP follow-ups (carved out of #1)

- **#1a — OAuth 2.1 client flow** (M–L). v1 is bearer/PAT only, which covers
  GitHub + most self-hosted/registry servers. **Google Drive and Microsoft 365
  official remote MCP servers require full OAuth 2.1** (authorize redirect,
  dynamic client registration, token store + refresh) — owner flagged this as
  needed eventually. Build the redirect/callback + token store, then Drive/MS
  connect. Microsoft additionally needs an Azure Entra app registration (org
  process, not code).
- **#1b — stdio transport** (M). v1 is remote-HTTP only. Local `npx`/stdio MCP
  servers need a transport + **Node added to the Docker image** (current image is
  python:3.12-slim, no node). Do alongside the connector marketplace (#9).
- **#1c — startup auto-connect** (S). Enabled servers currently lazy-connect on
  first tool use after a process restart; add a startup hook to reconnect + warm
  the tool list so the model sees MCP tools on the first message.

## Recommended next session

Start with **#1 (MCP client)** then **#2 (self-heal loop)** — together they move
CodeMonkeys from "a chat that can code" to "a system that builds and verifies on
its own." #1 is ~80 lines wiring the `mcp` Python SDK into the agent loop +
a server-config entry per MCP server; #2 wires `ruff`/`tsc`/test output back
into the loop and adds an iterate-until-green wrapper in auto mode.

## Notes / caveats from the research

- Ignore Devin's "67% of PRs merged" marketing — that claim was **refuted**;
  don't cite vendor autonomy/quality numbers.
- File-tree scaffolding needs **no special primitive** — Cursor/Windsurf/OpenHands
  just call write_file + mkdir in a loop, which we already do.
- Microsoft 365 is the one connector with real friction (Azure Entra app
  registration), not code — code is S, the org approval is the slow part.
- Web dive under-covered app-builder UX, memory frameworks, and multi-agent
  debate (budget ran out) — those were filled from the owner's own repos.
- Sources skew vendor-primary (GitHub, Cursor, Cognition, OpenHands); treat
  advertised behavior as advertised capability, not measured reliability.
