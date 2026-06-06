# Playbook: Swarm Discovery

*Exotic pattern. Loaded only when triggered from `CORPS_PLAYBOOKS.md`. Default recon is a
small number of directed `recon-scout` spawns Command assigns. Use this only for genuinely
broad coverage where central assignment becomes the bottleneck.*

## Use when
**Broad, READ-ONLY discovery/coverage** across many files/dirs/sites: "find/audit/
inventory every X", map an unfamiliar large codebase, surface all call-sites of a pattern.
The work is embarrassingly parallel and no single scout needs another's result.

## Don't use when
Anything that **edits** (swarms are read-only — no central coordinator to prevent
conflicting writes), small/targeted lookups (just spawn one scout), or when you need a
traceable linear chain (swarms are harder to debug — reconstructing the path is like
debugging an eventually-consistent DB).

## How to run (real primitives)
1. Partition the ground by a cheap axis (by directory / by file-glob / by subsystem /
   by entity). Each partition = one **T0 `recon-scout`** (cheapest tier — this is volume).
2. Give them a **shared scratchpad file** (the "environment") to append findings to —
   stigmergic coordination: they leave marks, not messages. No scout waits on another.
   **Write-safety:** filesystem has no locking and appends arrive in non-deterministic
   order. Each scout must therefore write exclusively under its own unit-namespaced block
   header (`## <unit-id>`) and never touch another unit's block. Command stamps every
   scout a unique `unit-id` at spawn. The reconciler merges the per-unit blocks at the
   end — interleave-corruption becomes impossible because blocks are identity-fenced.
3. Run them as one parallel wave (respect the per-wave cap; queue the rest).
4. Command reads the scratchpad once and synthesizes — the orchestrator touches the work
   *once at the end*, not once per scout (that's what removes the bottleneck + per-level latency).

## Payoff vs cost
Payoff: full parallel coverage with no central planning bottleneck; cheap (all T0). Cost:
many spawns (watch the cap) and a noisier trace — mitigated by the shared scratchpad as the
single source of findings.

## Exit
A deduped, synthesized findings list. AAR line: `PLAYBOOK: swarm-discovery · N scouts ·
helped? yes/no/partial`.
