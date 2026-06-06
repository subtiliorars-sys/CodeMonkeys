# Corps model tiers — cheap-first routing

*Companion to `CORPS_COMMANDER.md`. Every unit and every Task spawn starts at the
**lowest capable tier** and escalates **max +1 tier per retry** — never starts heavy.*

---

## 1. Four tiers (abstract)

| Tier | Name | When | Claude Code | Cursor (see map) |
|------|------|------|-------------|-------------------|
| **T0** | Light | Search, history, docs, trivial edits, skirmish solo | `haiku` | `gemini-3.5-flash`, `composer-2.5-fast`, `gpt-5.4-nano-low` |
| **T1** | Standard | Line work, most implementation, verify | `sonnet` | `claude-4.5-sonnet`, `gpt-5-mini`, `composer-2.5` |
| **T2** | Heavy | Complex debug, multi-file reasoning, failed T1 once | `sonnet` (+ thinking) | `claude-4.6-sonnet-medium-thinking`, `gpt-5.2-high` |
| **T3** | Critical | Campaign planner, adversarial red-team **only** | `opus` | `claude-4.5-opus-high-thinking`, `gpt-5.3-codex-high` |

**Default Command (main thread):** T0 on Skirmish, T1 on Operation/Campaign orchestration.
Escalate Command to T2 only if stuck after one full pass. **Never T3 for Command** — spawn
`staff-planner` / `red-team` at T3 instead.

Prefs override slug picks: `~/.config/agent-corps/model-prefs.env` (see `model-prefs.example.env`).

---

## 2. Unit default tiers

| Tier | Units |
|------|-------|
| **T0** | `recon-scout`, `historian`, `scribe` |
| **T1** | `field-engineer`, `logistics-engineer`, `medic`, `provost-qa`, `intel-analyst`, `forward-observer`, `quartermaster`, `cartographer`, `interrogator`, `sapper` |
| **T3** | `staff-planner`, `red-team` (**always** — never spawn these at T0/T1/T2) |

---

## 3. Model escalation scoring (within a task)

Start at the unit's default tier. Add:

| Signal | Effect |
|--------|--------|
| Task succeeded at current tier | Stay / de-escalate next task |
| Failed, vague, or incomplete **once** at current tier | **+1 tier**, retry once |
| Failed **twice** at T2 | Report blocked; ask user — do **not** auto-T3 except red-team/planner |
| High-risk correctness (auth, money, data isolation) | Buddy at **same tier** first; red-team at T3 only if adversarial pass needed |
| User mentions cost / credits / cheap | **Lock T0–T1** (no T2/T3 unless safety) |
| User says "best model" / "think hard" | Floor at T2 for that task |

**Hard caps:** max **+1 tier per retry**; max **one tier escalation per user message** for Command.

---

## 4. Spawn rules (all hosts)

1. **Always set model** on Task/subagent spawn — never leave default to platform auto if a tier is known.
2. **Read slug** from `cursor/model-tier-map.json` + `model-prefs.env` (Cursor) or agent `model:` frontmatter (Claude Code).
3. **Announce** optional one-line: `[Model · T1 · claude-4.5-sonnet]` when escalating tiers.
4. **No thinking/opus** for recon, history, or scribe — ever.
5. **Gemini Flash** (T0) is valid for read-only recon when user has Gemini credits — prefer for volume search.

---

## 5. What is enforceable where

| Host | Enforcement |
|------|-------------|
| **Claude Code** | Agent `model:` frontmatter is **hard** at spawn |
| **Cursor Task tool** | Pass `model: <slug>` on every spawn — **you must do this** |
| **Cursor main thread** | `agent --model <slug>` or in-session `/model`; default stays `composer-2.5-fast` unless prefs say otherwise |
| **Cursor subagent `.md`** | `model:` frontmatter may be ignored — **Command passes model on Task** |

Doctrine + commander rules handle what the platform cannot hard-enforce.

---

## 5a. Prompt-cache doctrine

`cache_control` is an **Anthropic Messages API field on content blocks** — not a markdown
header, not a model setting, and not a knob Command can turn from most hosts.

**Host availability:**

| Host | cache_control usable? |
|------|-----------------------|
| Direct API / SDK callers | Yes — attach to content blocks explicitly |
| Claude Code SDK spawn path | Yes — available via SDK |
| Cursor / Windsurf / Copilot / Cline / Roo | **N/A** — harness-injected; not a configurable knob |

**When to cache (and when not to):**

The only viable cache target is the **Command main-thread static doctrine block** in an
active session. Apply `cache_control` there ONLY IF both conditions hold:

1. The block exceeds **~1,024 tokens** (minimum useful cache granularity).
2. It will be **replayed within 5 minutes** — meaning the session has a high message
   density (roughly >10 messages per window).

Cache writes cost a **1.25× write premium**. Below that token threshold or message rate,
caching costs more than it saves.

**What caching does NOT help:**

- **Single-shot subagent system prompts** — the 5-minute TTL expires before any reuse
  occurs. Do not route subagent spawns through cache expecting a hit.
- **Quartermaster / logistics / scribe outputs** — those are output tokens; output is
  uncacheable. Do not claim output-heavy units benefit from prompt caching.

---

## 6. Quick examples

| Request | Echelon | Command model | Spawns |
|---------|---------|---------------|--------|
| Fix typo | Skirmish | T0 | none |
| Find all usages of X | Skirmish | T0 | optional recon-scout @ T0 |
| Implement endpoint + tests | Operation | T1 | field-engineer T1, provost-qa T1 |
| Full security audit | Campaign | T1 | staff-planner **T3**, recon T0, red-team **T3** |
