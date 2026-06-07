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
| ~~3~~ | ~~**Spec-first plan mode**~~ ✅ **SHIPPED 2026-06-06** (plan mode writes Constitution/Spec/Plan/Tasks to `.codemonkeys/specs/<slug>/` via the jailed `save_spec` tool; each task carries a verify step. Red-teamed: closed a pre-existing hole where plan-mode `spawn_agent` could escalate to a write-capable subagent — plan is now read-only end to end). | S–M |
| ~~4~~ | ~~**Blackboard cross-session memory**~~ ✅ **SHIPPED 2026-06-06/07** (cross-session half: `.codemonkeys/blackboard-<slug>.md` FACTS/DECISIONS/NEXT, jailed tools + commander-prompt injection, PR #14. Multi-AGENT half 2026-06-07: every Daystrom subagent gets `blackboard_read`, Edit/Write-capable units get `blackboard_write`, plan mode stays read-only end to end; write path serialized + atomic-rename; untrusted-DATA framing on prompt injection. Red-teamed GO-WITH-FIXES, fixes applied.) | S |
| 5 | **Issue/webhook-triggered background runs** | Assign an issue / hit a webhook → background session opens a PR. Pair with notify-on-done (OmniVerse pattern). Cron via existing `/loop`. | M |
| 6 | **Tiered / "fractal" memory + theme-token compaction** | Per-session raw → scrubbed working memory → curated pattern library; compact by extracting structured theme tokens, not lossy LLM summaries. (Owner's memory-engine spec.) | L |
| ~~7~~ | ~~**Debate-verify gate**~~ ✅ **SHIPPED 2026-06-07** (auto-mode risky *bash* commands — the path with NO human gate — now pass a 3-lens verifier panel (intent/safety/security, no tools), run on distinct providers when 3+ keyed else cheapest-repeated; majority refute = BLOCKED, fail closed on errors/garbled verdicts/no provider; metered into the ledger + `debate_verify` events; default/plan human gate unchanged. Damage-reduction not an auth boundary; bash-only (auto MCP still ungated). Red-teamed GO-WITH-FIXES, fixes applied. See SECURITY.md.) | S |
| ~~8~~ | ~~**apply_patch tool**~~ ✅ **SHIPPED 2026-06-06** (`git apply` unified diffs, atomic, every diff target path jail-checked before apply; in FULL_TOOLS + corps `Edit`). | S |
| 9 | **Connector marketplace UI** | Poll the MCP Registry, one-click add servers — the realistic "self-healing connectors." Depends on #1 (now shipped). | M |
| 10 | **Two-layer KB** | Hand-authored rules + deterministically-generated project facts; build fails if secrets would leak into context. (OmniVerse pattern.) | S |

## Wave 3 — safe self-contained items (ideated 2026-06-07, owner-requested)

All Tier-A safe: docs/tests/own-branch code, no deploy, no owner secrets, no
irreversible/external actions. Each ships as `work/<topic>` + an UNMERGED PR
(owner merges). Security-touching items get a red-team pass. Grouped into PRs
to keep review sane and limit single-file (`server.py`) merge pain.

| # | Item | Group / PR | Risk |
|---|------|-----------|------|
| ~~W1~~ | ✅ **`/healthz` liveness endpoint** — unauthenticated, leaks nothing (status/uptime/session-count). PR A. | A (ops) | low |
| ~~W2~~ | ✅ **Escalation-on-failure** — `agent_loop` retries one tier up (`_pricier_provider`) before dying; sticks with the working tier. PR A. | A (ops) | low |
| ~~W3~~ | ✅ **Model-call retry w/ backoff** — `call_model` retries transient 429/5xx/network (`TransientModelError`, 3 tries, fixed 1/3/8s); 4xx not retried. PR A. | A (ops) | low |
| ~~W4~~ | ✅ **Usage/cost summary** — Owner-only `/api/usage` rollup from `cost` events. PR A. | A (ops) | low |
| W5 | **Harden `_is_risky`** — add `dd`/`mkfs`/`chmod -R`/`chown -R`/`> /dev/…`/`curl\|sh`/`git push --force`/`truncate` to the approval gate + tests. | B (sec) | low |
| W6 | **Secret-scan write guard** — flag/log when `write_file`/`apply_patch` would persist an obvious secret (API key/token/PEM) into the workspace. | B (sec) | low |
| W7 | **Extend debate-verify to risky auto-mode MCP calls** — MED-2 follow-up; stacks on #22. | E (sec) | low |
| W8 | **Blackboard management API + ⚙ panel** — Owner-only list/read/delete of boards; stacks on #21. | F (ux) | low |
| W9 | **Session transcript export** — download a session as Markdown/JSON. | C (ux) | low |
| W10 | **Per-session budget override** — set the USD budget at session creation (today only the global `SESSION_BUDGET_USD`). | C (ux) | low |
| W11 | **Two-layer KB (#10)** — hand-authored rules + deterministically-generated project facts injected into context, with a secret-leak guard on generation. | C (ux) | low |
| W12 | **Remove-passkey UI + endpoint** — close the known gap (passkeys can be added but not revoked); Owner-gated. | D (auth) | med — red-team |

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

#1 (MCP client, +v2 stdio/OAuth/auto-connect), #2 (self-heal), #3 (spec-first
plan mode), #4 (blackboard memory, incl. multi-agent half) and #8 (apply_patch)
are **shipped & merged to main**. Next candidates: **#9 connector marketplace**,
**#7 debate-verify gate**, **#10 two-layer KB**, plus escalation-on-failure in
the cost governor (cheapest→pricier retry).

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
