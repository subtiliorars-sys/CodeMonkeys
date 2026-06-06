# Playbook: Blackboard

*Exotic pattern. Loaded only when triggered from `CORPS_PLAYBOOKS.md`. Default flow passes
results up the hierarchy (and loses some detail at each summarization). Use this when that
information loss hurts, or when many specialists must share one evolving picture.*

## Use when
- **Many specialists contribute to ONE evolving artifact** (a design doc, a migration plan,
  a shared model of a subsystem), each adding their piece opportunistically; or
- A **long / multi-wave** task where context lost between hierarchy levels is costing you
  (the documented weakness of deep hierarchies: info dropped at each summarization).

## Don't use when
A short, linear task — the file is overhead. One unit doing one thing doesn't need a board.

## How to run (real primitives)
1. Create **one shared file** = the blackboard (e.g. `.daystrom/blackboard-<task>.md`), with
   sections: `FACTS` · `OPEN QUESTIONS` · `DECISIONS` · `NEXT`.
2. Each unit, when it finishes, **reads the board and appends/updates its section** — it
   writes findings to the board, not just to its return value. The board is the shared truth.
3. **Concurrency safety — disjoint sections only.** Parallel subagents have independent
   contexts and no filesystem locking; two units appending to a shared flat section can race
   and corrupt it. Rule: each unit writes ONLY to its own unit-namespaced section header
   (e.g. `## FACTS · <unit-id>`); a unit must NOT mutate any other unit's section mid-wave.
   Command must stamp each spawned unit a unique ID at spawn time so suffixes don't collide.
   Disjoint sections make concurrent writes provably safe.
4. Command and later units orient from the board, not from re-deriving prior context. This
   is the "externalize the plan" doctrine made literal + shared (and survives context limits).
5. One unit owns **reconcile** at the end (collapse namespaced sections, resolve
   contradictions, emit a unified `FACTS` / `DECISIONS` / `NEXT` block).

## Payoff vs cost
Payoff: shared situational awareness; counters per-level info-loss; resilient to context
truncation. Cost: the discipline of keeping one file current; a stale board misleads — so
reconcile and date entries.

## Exit
The board is the deliverable (or feeds one). AAR line: `PLAYBOOK: blackboard · helped? yes/no/partial`.
