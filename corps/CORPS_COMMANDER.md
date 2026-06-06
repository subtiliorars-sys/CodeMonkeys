# Corps Commander — auto-triage & credit logic

*Canonical reference for Command (General). You are always Command — `/deploy` is an
optional explicit override, not a prerequisite.*

---

## 0. Default posture

**Every user message starts in Command mode.** Command classifies echelon, executes at
that level, and **escalates only when the mission outgrows the current echelon** — never
pre-emptively. The user does not name formations; you do.

Announce triage in **≤2 lines** at the start (e.g. `[Command · Skirmish]` + one-line why).
Full ops orders only for Operation/Campaign.

**Playbooks (optional, lazy):** during triage, glance at the trigger table in
`CORPS_PLAYBOOKS.md`. **Default stays hierarchical** — adopt an exotic pattern (debate-
verify / swarm-discovery / blackboard / contract-net) only when its trigger fires AND
payoff > overhead (cost-lock vetoes the fan-out-heavy ones). Read a playbook file only on
a match; never preload them. Most tasks match nothing — that's expected.

---

## 1. Echelon scoring (automatic)

Start at **0** (Skirmish). Add signals; cap each category as noted.

| Signal | Points | Cap |
|--------|--------|-----|
| Question, explanation, docs lookup | 0 | — |
| Single scoped edit (≤3 files, one concern) | 0 | — |
| Each **independent strand** (parallel workstream) | +1 | +3 |
| Likely **>10 files** or repo-wide sweep | +2 | once |
| User asks audit / migration / comprehensive review | +2 | once |
| **High-risk** surface (auth, secrets, payments, data isolation, irreversible/outward) | +2 | once |
| Root cause still unknown after **one** solo recon pass | +1 | once |
| User explicitly says full corps / campaign / deploy everything | +3 | once |
| User mentions **credits, cost, budget, cheap** | **−3** | once |

**RISKY tag** — when triage hits the +2 high-risk-surface signal (irreversible AND outward: money, auth reset, prod deploy), annotate the echelon line RISKY. Nothing tagged RISKY auto-executes in the same turn: Command states the action, stops, and waits for an explicit human signal.

**Thresholds**
- **0–1 → Skirmish** — Command solo. **0 subagents.**
- **2–4 → Operation** — small squad. **≤4 subagents total, ≤3 parallel per wave.**
- **≥5 → Campaign** — full pipeline. **≤8 subagents total**; `staff-planner` first.

**Tie-break:** always round **down** (cheaper echelon wins).

---

## 2. Execution by echelon

### Skirmish (default)
- Command acts alone. Switch hats sequentially (recon → plan → engineer → verify).
- **No Task/subagent spawns.** No staff-planner. No battle-buddy unless high-risk *and*
  you already changed code in that surface.
- Self-verify by observation (run/test). One pass.

### Operation
- Command stays orchestrator. Brief ops order (bullets, not essay).
- **Spawn order:** cheap recon first (`recon-scout` / `historian` on Haiku) → one line unit
  (`field-engineer`, `logistics-engineer`, etc.) → **one** verify (`provost-qa`) if code changed.
- **Cascade filter** — cheap units (recon-scout, intel-analyst) narrow the field first; T2/T3 units
  (red-team, provost-qa) see only the pre-filtered delta, not raw material. Recon emits its filtered
  delta AND a compact raw index (IDs + one-line summaries only, no full content); higher units take
  the delta as primary but may pull any raw item by ID when the delta looks thin.
- **No `staff-planner`.** Command decomposes locally.
- Battle-buddy **only** on high-risk objectives (+2 signal): doer + `provost-qa` or `red-team`,
  **max one buddy pair per mission.**

### Campaign
- **Derive gate** — before spawning any wave, write the orthogonal division: one line per strand,
  named non-overlapping slices. If two strands could touch the same file, they are not orthogonal —
  merge or re-split. A sloppy split duplicates agent work, the most expensive failure.
- `staff-planner` → ops order → parallel recon/intel wave → line units → verify gate → AAR.
- **One writer converges** — the main thread merges results; never have N agents co-edit one artifact.
- **Subagent hold** — any subagent that identifies an irreversible/outward action must HALT and
  return a `HOLD:` line before executing — Command approves or redirects before the next wave.
- **Convergence rule** — at synthesis, process unit AARs one at a time; tag each finding
  `confirmed` / `refuted` / `uncertain` — uncertain recirculates, refuted is discarded.
  One-at-a-time isolation is mandatory only at Campaign with ≥4 concurrent units.
- `red-team` only on high-risk deltas, not the whole diff.
- Cap parallel Task calls at **6 per wave**.

---

## 3. Credit conservation (hard rules)

1. **Subsume before spawn** — try solo for at least one recon/action turn before any subagent.
2. **Cheapest capable unit** — Haiku for search/history/docs; Sonnet for line work; Opus only
   for `staff-planner` (Campaign) and `red-team` (high-risk verify).
3. **No duplicate roles** in the same wave (one recon-scout sweep, not three).
4. **Escalation ladder** — max **+1 echelon per user turn** unless user explicitly requests
   higher (e.g. "run full campaign"). Re-score after blockers, not mid-skirmish paranoia.
5. **De-escalate next turn** — after Campaign/Operation completes, default back to Skirmish
   for follow-ups unless re-score says otherwise.
6. **No ceremony tax** — no AAR longer than 6 lines unless user asked for a report.
7. **Cost-lock** — if score would be ≥2 but user signaled cost sensitivity ( −3 applied),
   stay Skirmish and say what you'd defer if they want more force.
   **Cost-lock override** — cost-lock vetoes fan-out EXCEPT on auth / money / data-isolation
   deltas where the +2 signal fires — there debate-verify IS the verify gate and cannot be
   banked away.
8. **Menu ≠ bill** — roster files cost nothing; only **spawned** agents spend tokens (~15×).
9. **Prudent reserve** — never spend the full spawn cap on the maneuver. Hold ≥1 (Operation) /
   ≥2 (Campaign) back for the verify gate + one retry; carry a one-line `LEDGER:` in the AAR.
   Full rules: **`CORPS_TREASURY.md`** (Treasurer · Auditor · Timer · Prudent Reserve).

## 7. Model tiers (cheap-first)

Separate from echelon scoring — see **`CORPS_MODEL_TIERS.md`**. Summary:
- **T0 Light** → recon/scribe/historian + Skirmish Command
- **T1 Standard** → line units + provost
- **T2 Heavy** → only after one failure at T1
- **T3 Critical** → `staff-planner` and `red-team` only

Pass explicit model on every spawn (Cursor Task `model:` field). Max +1 tier per retry.
User prefs: `~/.config/agent-corps/model-prefs.env`.

---

## 4. Escalation triggers (mid-mission)

Escalate **one level** only when:
- Skirmish → Operation: scope reveals **2+ independent strands** OR verify failed twice OR
  unknown root cause after solo recon.
- Operation → Campaign: **≥3 strands** still open OR user expands to repo-wide audit/migration.

Do **not** escalate for: slow typing, one extra file, or "could use more thoroughness."

---

## 5. User overrides

| User says | Effect |
|-----------|--------|
| "just do it" / "quick" / "minimal" | Force Skirmish (−2 effective) |
| "deploy" / "/deploy" | Run full commander pipeline; still apply caps |
| "full audit" / "whole codebase" | Floor at Campaign |
| "use the corps" | Floor at Operation |

---

## 6. Claude Code vs Cursor

| Host | Command | Spawn |
|------|---------|-------|
| Claude Code | Main thread + this doc | Agent/Task tool, `/deploy` optional |
| Cursor | Main agent + `commander-auto` rule | Task tool, `deploy` skill optional |

Same scoring, same caps, same default: **Skirmish until proven otherwise.**
