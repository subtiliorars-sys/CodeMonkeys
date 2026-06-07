# Daystrom Playbooks — optional exotic coordination patterns (lazy-loaded)

*Companion to `CORPS_COMMANDER.md`. These are NON-DEFAULT coordination paradigms parked
for the rare task where they beat the hierarchical default. This index is the only part
always in context — it is short on purpose. **Do not read a playbook file unless its
trigger fires.***

## The efficiency contract (read once)
1. **Default stays hierarchical mission-command** (Command → units → verify). These
   patterns are the exception, not the menu.
2. **Consult a playbook ONLY when its trigger fires AND expected payoff > its overhead.**
   When unsure, use the default. Most tasks match nothing here — that is correct.
3. **Progressive disclosure:** scan the trigger table below during triage (cheap). On a
   match, read *only* that one `playbooks/<name>.md`. Never preload them.
4. **Cost-lock wins:** if the user signaled cost/credits/cheap (−3), do NOT adopt a
   fan-out-heavier pattern (debate, swarm) unless safety requires it.
5. **Log the call:** if you use a playbook, add one AAR line — `PLAYBOOK: <name> · helped?
   yes/no/partial` — so triggers can be sharpened later.

## Trigger table (the dispatcher — glance, don't deliberate)

| If the task is… | Playbook | One-line payoff | Cost flag |
|---|---|---|---|
| A **high-risk delta about to be trusted** (auth, data isolation, money, irreversible/outward, correctness-critical) | `debate-verify` | ~30% fewer errors vs one checker | spends spawns from the **reserve** |
| **Broad READ-ONLY discovery/coverage**: >=4 files/dirs to scan in parallel, no interdependency | `swarm-discovery` | no orchestrator bottleneck; parallel coverage | many cheap T0 spawns + a scratchpad |
| **Many specialists feeding ONE artifact**: >=3 sequential waves OR >2 specialist units converging on one output | `blackboard` | shared situational awareness; counters info-loss | discipline to maintain one file |
| A **batch of heterogeneous tasks** where unit fit/cost varies a lot | `contract-net` | better assignment than top-down | a bidding round (often not worth it) |
| **Autonomous loop / self-healing agent** hitting repeated failures | `self-heal` | structured halt before infinite loop | cheap — it's a stop rule, not a fan-out |

If nothing matches: **stop here and run the default.** That is the common case.

**Note on staff-planner:** plan mode is enforced by tool allowlist (`Read/Grep/Glob` only — no
`Bash/Write/Edit`), not just by prompt. If a Campaign task description says "plan and execute",
split it: staff-planner plans, line units execute. Never pass execution tools to staff-planner.
