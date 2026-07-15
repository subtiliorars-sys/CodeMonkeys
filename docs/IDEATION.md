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
(inert until webhook secrets). Separate workstream: **#37 web terminal** — also
MERGED 2026-06-07 (stays OFF: double env gate, owner enables post-deploy).

## Standing list (current — pick from here, one wave per PR)

| # | Item | Why | Risk |
|---|------|-----|------|
| ~~S1~~ | ~~**BUG: blank-base_url provider**~~ ✅ **PR #39** (also folded into **#42**; config-load repair + selection fail-fast + non-transient call guard; 11 tests). | correctness | low |
| ~~S2~~ | ~~**Fleet Deck `GET /fleet-status.json`**~~ ✅ **PR #41** (read-only Bearer `FLEET_TOKEN` ops feed; fail-closed no-route-when-unset; red-teamed; deploy owner-gated). | fleet integration | med — red-team |
| ~~S3~~ | ~~**Fractal memory phase 2**~~ ✅ **PR #43** (scrubbed tier-1 digest + cross-session pattern library `GET /api/memory/patterns`, owner-only; red-teamed, broadened `_scan_secrets`). | memory | low |
| S4 | **Secrets-at-rest / bash sandbox.** Part A ✅ **PR #44** (strip secret-named env vars from bash/terminal/MCP subprocesses — defense-in-depth). Part B (encrypt `/data` secrets at rest incl. the original OAuth `client_secret`/`refresh_token` + `session_secret.key`; sandbox bash) is **OWNER-GATED** — red-team found the bash exfil surface is broader than env (see `SECURITY.md` + questions.md). | security | high — owner decision |
| ~~S5~~ | ~~**Notify-on-done** — webhook/run completion ping (OmniVerse pattern); pairs with #5.~~ ✅ **PR #45** (off until owner sets `NOTIFY_WEBHOOK_URL`; HMAC supported via `NOTIFY_WEBHOOK_SECRET`). | ux/ops | low |
| S6 | **Per-user workspace isolation** — biggest known gap; large, design-first. | security | high — design+red-team |

**Standing-list status (consolidation Wave 14, 2026-06-07 ~11:16 UTC):** S1–S5 all
shipped as PRs; S6 design'd (#46, no code); S4-B owner-gated. **Safe build→PR
backlog exhausted** — remaining work is owner-gated/needs an owner decision.
**Integration verified:** the 6 code PRs (#40/#41/#42/#43/#44/#45; #39 superseded
by #42; #38/#46 docs) merge together cleanly in the suggested order — **integrated
suite 338/338 green**.

## New backlog "N" — 12 ideas (ideated 2026-06-07 PM; owner greenlit Wave 1)

| # | Item | Status | Risk |
|---|------|--------|------|
| ~~N1~~ | **Smart provider failover + cooldown** (skip 429'd/quota-dead providers) | ✅ **PR #52** (red-teamed, fixed) | med |
| ~~N2~~ | **Daily spend cap** across all sessions + kill-switch/override | ✅ **PR #51** (red-teamed, fixed) | med |
| N3 | **Cost/usage dashboard** (by-day/by-model, UI) | ✅ **PR #53** | low |
| ~~N4~~ | **Diff preview** of file writes in the console | ✅ **PR #50** | low |
| N5 | **Streaming output** — stream partial model text to the console | ✅ **CM-W1** | med |
| ~~N6~~ | **Session resume after restart** (survive Fly scale-to-zero/deploy mid-run) | ✅ **PR #60** | med |
| N7 | **Plan→execute handoff** (run a saved spec-mode plan) | ✅ **PR #55** | low |
| ~~N8~~ | **Context auto-compaction** via the fractal digest near token limit | ✅ **CM-W2** | med |
| ~~N9~~ | **Structured tool-error retry/repair** (bounded, signature-aware) | ✅ **PR #59** | low |
| N10 | **Readiness probe** `/readyz` (deep health vs liveness) | ✅ **PR #49** | low |
| N11 | **Owner audit-log viewer** (security-event UI) | ✅ **PR #54** (red-team GO) | low |
| ~~N12~~ | **Model catalog/pricing refresh** (no code edits to add models) | ✅ **CM-W3** | med |

**Wave 1+2 (N1–N4/N7/N10/N11) = PRs #49–#56 — MERGED + DEPLOYED v15.**
**Wave 3 = S4-B #58 + N9 #59 + N6 #60 — built/reviewed, merge-ready, unmerged**
(integration-tested: merge #58→#59→#60 clean, 535 green; see `docs/RELEASE_NOTES.md`).
**Next buildable:** see `docs/IDEATION.md` backlog beyond N-backlog.
— build ONE at a time (shared agent_loop/call_model/load_models regions).
*(legacy note below predates Wave 3)* N5/N6/N8 touch the
agent loop / call_model — sequence them to limit `server.py` merge churn.

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
