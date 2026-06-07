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
| ~~5~~ | ~~**Issue/webhook-triggered background runs**~~ ✅ **SHIPPED 2026-06-07** (PR #36 merged: webhook → background session → PR; fail-closed OFF-by-default + HMAC + sender allow-list + label/action gate + dedup + caps; INERT until owner sets webhook secrets). | M |
| 6 | **Tiered / "fractal" memory + theme-token compaction** — **phase 1 SHIPPED 2026-06-07** (PR #33: deterministic theme-token digest per session). Remaining: scrubbed working memory → curated pattern library tiers. | L |
| ~~7~~ | ~~**Debate-verify gate**~~ ✅ **SHIPPED 2026-06-07** (auto-mode risky *bash* commands — the path with NO human gate — now pass a 3-lens verifier panel (intent/safety/security, no tools), run on distinct providers when 3+ keyed else cheapest-repeated; majority refute = BLOCKED, fail closed on errors/garbled verdicts/no provider; metered into the ledger + `debate_verify` events; default/plan human gate unchanged. Damage-reduction not an auth boundary; bash-only (auto MCP still ungated). Red-teamed GO-WITH-FIXES, fixes applied. See SECURITY.md.) | S |
| ~~8~~ | ~~**apply_patch tool**~~ ✅ **SHIPPED 2026-06-06** (`git apply` unified diffs, atomic, every diff target path jail-checked before apply; in FULL_TOOLS + corps `Edit`). | S |
| ~~9~~ | ~~**Connector marketplace UI**~~ ✅ **SHIPPED 2026-06-07** (PR #35 merged: curated catalog + MCP Registry fallback). | M |
| ~~10~~ | ~~**Two-layer KB**~~ ✅ **SHIPPED 2026-06-07** (Wave 3 W11, PR #30: rules + generated facts with secret-leak guard). | S |

## Wave 3 — safe self-contained items ✅ ALL SHIPPED (merged PRs #23–#30, deployed v10)

W1 `/healthz` · W2 escalation-on-failure · W3 model-call retry/backoff ·
W4 `/api/usage` · W5 `_is_risky` hardening · W6 secret-scan write guard ·
W7 debate-verify→MCP · W8 blackboard admin API+panel · W9 transcript export ·
W10 per-session budget · W11 two-layer KB · W12 remove-passkey (red-teamed).

## Wave 4 ✅ ALL MERGED 2026-06-07 (PRs #33–#36, not yet deployed)

#6 fractal memory phase 1 · #3 vendored Tailwind phase 1 (CDN still active,
phase-2 cutover OWNER-GATED) · #9 connector marketplace · #5 webhook→PR runs
(inert until webhook secrets). Separate workstream: **PR #37 web terminal**
(open, owner-gated, double env gate).

## Standing list (current — pick from here, one wave per PR)

| # | Item | Why | Risk |
|---|------|-----|------|
| S1 | **BUG: blank-base_url provider** — fail-fast at model selection + config-load repair backfilling known provider URLs (defaults near `server.py:876`). Found in 2026-06-07 live smoke (`Invalid URL '/chat/completions'`). | correctness | low |
| S2 | **Fleet Deck `GET /fleet-status.json`** — read-only Bearer-auth ops feed per `~/fleet/contracts/fleetdeck-codemonkeys.md` (maps #21 blackboard registry → `workers[]`; `hmac.compare_digest` on `FLEET_TOKEN`; no prompts/code/keys). Build+PR; deploy owner-gated. | fleet integration | med — red-team |
| S3 | **Fractal memory phase 2** — scrubbed working-memory tier + curated pattern library on top of the #33 digest. | memory | low |
| S4 | **OAuth secrets-envelope** — encrypt `client_secret`/`refresh_token` at rest on `/data` (today plaintext, readable by unsandboxed bash). | security | med — red-team |
| S5 | **Notify-on-done** — webhook/run completion ping (OmniVerse pattern); pairs with #5. | ux/ops | low |
| S6 | **Per-user workspace isolation** — biggest known gap; large, design-first. | security | high — design+red-team |

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

The original ranked backlog (#1–#10) and Waves 3–4 are **fully shipped**. Work
from the **Standing list** above, in order (S1 bug first). Owner-gated items
(Tailwind phase 2 / CSP, terminal activation, webhook secrets, OAuth app
registration) wait for the owner regardless of list position.

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
