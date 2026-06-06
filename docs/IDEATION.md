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
| ~~2~~ | ~~**Self-heal loop**~~ ✅ **SHIPPED 2026-06-06** (auto-mode run→read-failure→patch→rerun-until-green doctrine in `MODE_GUIDANCE["auto"]`; caps 5 iters / repeat-signature=blocked / budget; guidance-only, model keeps tool-control). | M |
| 3 | **Spec-first plan mode** ← **NEXT** | Constitution / Spec / Plan / Tasks artifacts saved in the workspace; each task carries its own verification step. Structured PRD spine for the corps. (Ref: GitHub Spec Kit.) | S–M |
| 4 | **Blackboard cross-session memory** | `.codemonkeys/blackboard-<task>.md` with FACTS/DECISIONS/NEXT that survives session resets. Owner's own corps pattern; near-zero infra. | S |
| 5 | **Issue/webhook-triggered background runs** | Assign an issue / hit a webhook → background session opens a PR. Pair with notify-on-done (OmniVerse pattern). Cron via existing `/loop`. | M |
| 6 | **Tiered / "fractal" memory + theme-token compaction** | Per-session raw → scrubbed working memory → curated pattern library; compact by extracting structured theme tokens, not lossy LLM summaries. (Owner's memory-engine spec.) | L |
| 7 | **Debate-verify gate** on high-risk changes | 3 heterogeneous verifiers, majority-refute = don't-ship (~30% fewer errors). Use the existing corps; trigger only on auth/money/irreversible. | S |
| 8 | **apply_patch tool** (unified-diff edits) | Edit big files without full rewrites; the one file primitive Cursor/Aider have that we lack. | S |
| 9 | **Connector marketplace UI** | Poll the MCP Registry, one-click add servers — the realistic "self-healing connectors." Depends on #1 (now shipped). | M |
| 10 | **Two-layer KB** | Hand-authored rules + deterministically-generated project facts; build fails if secrets would leak into context. (OmniVerse pattern.) | S |

## MCP follow-ups (carved out of #1) — ALL SHIPPED 2026-06-06

- ~~**#1a — OAuth 2.1 client flow**~~ ✅ auth-code + PKCE S256; tokens in
  `mcp_tokens.json` (0600, never returned/logged); refresh; Google Drive / M365
  presets. **Owner-gated:** register a Google/Azure OAuth app (redirect
  `https://<host>/api/mcp/oauth/callback`) before a live round-trip. A5
  red-teamed (refresh-rotation lock, use-time https re-validation +
  `allow_redirects=False`, atomic 0600 write, pinned redirect_uri).
- ~~**#1b — stdio transport**~~ ✅ local MCP servers over newline JSON-RPC;
  `Popen` no shell=True; Node added to the Dockerfile. Red-teamed (select-based
  deadline, stderr=DEVNULL, per-sid connect lock). **Docker build + real `npx`
  unverified locally** (no Docker/Node on dev host) — confirm on first deploy.
- ~~**#1c — startup auto-connect**~~ ✅ background warm of enabled servers on boot.

**Still open (owner expects eventually):** OAuth secrets-envelope — `client_secret`
+ `refresh_token` are plaintext on `/data`, readable by the unsandboxed `bash`
tool (the conceded kernel-sandbox residual, now higher-value). Consider before
opening OAuth widely. Preset MCP endpoint URLs for Drive/M365 are placeholders —
verify against current Google/Microsoft remote-MCP docs.

## Recommended next session

#1 (MCP client, +v2 stdio/OAuth/auto-connect) and #2 (self-heal) are **shipped &
merged to main** (undeployed — owner runs `fly deploy`). Next: **#3 spec-first
plan mode**, then **#4 blackboard memory** and **#8 apply_patch** (both S). For
reference, #2 wires `ruff`/`tsc`/test output back
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
