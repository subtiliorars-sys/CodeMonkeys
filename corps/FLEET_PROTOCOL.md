# Fleet Protocol — multi-session blackboard

Coordination layer for parallel Claude Code sessions ("the fleet") plus one
**Governor** (fleet boss) session. All coordination is file-based: sessions cannot
message each other directly, so they read/write this directory.

```
~/fleet/
  FLEET_PROTOCOL.md        this file
  status/<project>.md      one per worker — written BY the worker
  inbox/<project>.md       directives TO the worker — written by the Governor
  questions.md             append-only: questions for the human, from any session
  QUESTIONS_FOR_HUMAN.md   Governor-curated digest (dedup, prioritized)
  GOVERNOR_LOG.md          Governor cycle log (stale workers, actions taken)
  prompts/                 saved copy-paste session prompts
```

## Harmonized with the Windows fleet (2026-06-06)
Enforcement layer is shared with the Windows coworker fleet (agent-corps `fleet/`,
governance in `agent-corps/agent-governance.md` — "the Medallion"). On top of the
blackboard duties below, every worker ALSO:
- **Beats:** `python3 ~/agent-corps/fleet/heartbeat.py beat <repo> <task> --step "..."
  --iter N --cap <echelon-appropriate> --reserve 1` on start and at every breakpoint
  (never hand-roll the JSON — Fix A protocol). `... done <repo> <task> --step "..."`
  when finished.
- **Checks its stop-flag** every step: if `~/.claude/fleet/<repo>__<task>.stop`
  exists, halt, report in your status file, await the human. Self-halt anyway if you
  repeat the same move 3× with no repo change (repeat_count >= 3).

## Worker duties (any session doing project work)
1. **Register on start** — write `status/<project>.md`:
   ```
   # <project> — worker status
   state: WORKING | BLOCKED | DONE
   branch: work/<topic>
   objective: <one line>
   heartbeat: <output of `date -u`>
   ## Now
   <current task>
   ## Next / safe parallel queue
   - <5 items you could safely do without human input>
   ## Questions pending
   - <none, or copies of what you put in questions.md>
   ```
2. **Heartbeat + inbox check at every natural breakpoint** (between tasks, after a
   commit, before a big read): refresh `heartbeat:`, re-read `inbox/<project>.md`,
   fold any directives into your plan.
3. **Never-stall rule** — when you need a human decision: append it to
   `questions.md` (prefix with project + date), set `state: BLOCKED` **but keep
   working** — list 5 safe, doctrine-compliant parallel tasks in your status file
   and start the best one. Safe = docs, tests, sanitized Preview content,
   refactors on your own branch, design iteration. NOT safe = pushes to
   deploy-on-push branches, irreversible/external actions, anything the pending
   question gates.
4. **AAR on finish** — set `state: DONE`, summarize done/found/unresolved/recommend.

## Governor duties (fleet boss — runs `/fleet-tick`, e.g. via `/loop 15m /fleet-tick`)
Read-only over project repos; writes ONLY inside `~/fleet/` (plus manual stop-flags
in `~/.claude/fleet/` for confirmed breaches). Each cycle:
1. Read every `status/*.md`. Flag heartbeats older than ~20 min in `GOVERNOR_LOG.md`.
   Also sweep the shared enforcement layer: `python3 ~/agent-corps/fleet/fleet_watch.py`
   **`--enforce` is now safe** — Fix B (watchdog hardening) landed 2026-06-06. Guards
   prevent the false-positive class: STALE-CLOCK, DONE-STALE, SUPERSEDED never trip; FROZEN
   requires 2 consecutive stale sweeps with no iteration advance. Use report-only
   (no `--enforce`) only during high-activity sessions if you prefer a manual review step.
   Run `python3 ~/agent-corps/fleet/ledger_report.py` if a ledger exists.
2. For each BLOCKED worker: write 5 concrete, safe, doctrine-compliant improvement
   tasks into `inbox/<project>.md` and the instruction "proceed on these while the
   human question is pending."
3. For each WORKING worker with a thin "Next" queue: ideate and append candidate
   tasks to its inbox (respect repo scope + governance tier).
4. Curate `questions.md` → `QUESTIONS_FOR_HUMAN.md` (dedup, prioritize, mark which
   block real work).
5. Stay token-lean: read deltas, write tersely, smallest echelon. Never edit a
   project repo, never push, never answer the human's questions on their behalf.

## Owner-intake queue protocol

When a worker is blocked on an owner/founder decision, it does NOT just append a line to
`questions.md` and hope. It maintains a **numbered register** with the following structure,
either inline in its status file or in a dedicated `questions.md` entry:

```
## Owner queue — <project> (as of <date>)
| # | Question | Status | Unlocks | Age | Flag |
|---|----------|--------|---------|-----|------|
| 1 | ... | OPEN | ... | 2h | — |
| 2 | ... | OPEN | ... | 26h | STALLED |
| 3 | ... | PARKED | ambiguous answer received | 4h | — |
```

Rules:
- **STALLED** after 24 h with no response. The Governor surfaces STALLED items first.
- **ONE ready-to-send message** is prepared in the owner's preferred channel — not a
  thread of fragments. The worker drafts it; the Governor curates it into
  `QUESTIONS_FOR_HUMAN.md`; the **HUMAN sends**. The Governor never sends on the human's behalf.
- **Ambiguous answers are PARKED**, never resolved by assumption. The worker writes
  `status: PARKED — answer unclear; see [exact quote]` and treats the item as still open.
  It picks the next safe parallel task and continues.
- **What-each-answer-unlocks** is mandatory — so the owner can triage by impact, not
  by order received.

*Activation:* this register is the live incarnation of the Founder Decision Queue concept
described in `concepts/CONTINUOUS_FLOW.md`.

---

## Fleet observability — alert discipline

*(target discipline for any alerting layer built later; current fleet_watch is per-sweep report-only and exempt)*

- **Alerts fire on state TRANSITIONS only:** `healthy→degraded`, `degraded→recovered`.
  Never alert per-sweep if the state has not changed. Repeated alerts in a stable state
  = noise that trains humans to ignore the channel.
- **Fallback escalation channel must be independent of the primary.** If the primary
  channel (e.g. Slack, email) is itself degraded, the alert still reaches a human via
  an out-of-band path (SMS, a separate endpoint, a file in a watched location).
- **Preferred future architecture:** append-only event JSONL per unit, aggregated on read
  by the Governor or a query tool. File polling of per-sweep snapshots is the current
  fallback; it is not the target architecture.

---

## Honest limits
The Governor cannot inject text into another interactive session. Workers must
poll their inbox (duty 2) — that is the only channel. If a worker session has
truly halted (its turn ended), nothing restarts it except the human; the Governor's
job is to make sure the moment YOU touch that session, its inbox is full of vetted
next moves, and `QUESTIONS_FOR_HUMAN.md` gives you a one-screen catch-up.
