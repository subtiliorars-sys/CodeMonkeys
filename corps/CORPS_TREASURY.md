# Corps Treasury — credit stewardship (Treasurer · Auditor · Timer · Prudent Reserve)

*Companion to `CORPS_COMMANDER.md`. Borrowed from the home-group / Oxford House service
roles (Treasurer keeps the funds, the group keeps a **prudent reserve**, a Timer keeps
shares short). Command wears these hats by default; on a Campaign it may name them
explicitly. Like the model tiers, this is **advisory doctrine** — Command self-governs;
the platform does not hand an agent a live token meter (see §5).*

> **The budget unit is the subagent spawn.** A spawn is the ~15× cost event. The existing
> echelon caps bound *how many* you may spawn; the Treasury bounds *how you allocate them* —
> and forces you to **hold some back for verification and one retry**. You may not spend to zero.

---

## 1. The four roles (one Commander, four hats)

| Role | Charge | Behaviour |
|------|--------|-----------|
| **Treasurer** | Owns the budget | At triage, declares the **spawn allocation**: `maneuver / reserve` out of the echelon cap. Allocates the cheapest capable unit at the lowest tier (defers to `CORPS_MODEL_TIERS.md`). |
| **Auditor** | Keeps it honest | Tracks **spawns spent vs. cap vs. reserve** across the mission. Calls the checkpoints in §3. The AAR **must** carry one ledger line (§4). Hiding overspend = a failed mission (Doctrine §4.5). |
| **Timer** | Keeps shares short | Caps each unit's **output**: scope a tight objective + a bounded/structured return; no rambling, no scope-creep. One retry max per unit (Model Tiers §3). A unit that needs a second wave is a re-triage, not a longer share. |
| **Prudent Reserve** | Solvency | A standing rule, not a hat: **never spend the full cap on the maneuver.** Hold the reserve for the **verify gate** (`provost-qa` / `red-team`) and **one** retry. Reserve is untouchable for new feature/maneuver work. |

---

## 2. Budget by echelon (allocation of the spawn cap)

| Echelon | Total cap | Maneuver | **Reserve (held)** | Reserve pays for |
|---------|-----------|----------|--------------------|------------------|
| **Skirmish** | 0 subagents | — | — | Solo; no treasury needed. Self-verify by observation. |
| **Operation** | ≤4 | **≤3** | **≥1** | one `provost-qa` verify (+ the 1 retry budget) |
| **Campaign** | ≤8 | **≤6** (matches the 6/wave cap) | **≥2** | verify gate + `red-team` on high-risk delta + one retry |

Declare it in the triage line, e.g. `[Treasury · Op · spend ≤3, reserve 1 for verify]`.
If the maneuver runs clean and the reserve is untouched, **bank it** — do not spend it for
"extra thoroughness." Unused budget is a win, not a shortfall.

**Reserve-scaling:** when the +2 high-risk signal fires AND debate-verify is the gate, floor the echelon at Campaign (reserve ≥2) so the 3-verifier cost fits the budget.

---

## 3. Audit checkpoints (burn discipline)

- **At triage** — Treasurer sets `maneuver / reserve`. Round the maneuver *down* on doubt.
- **50% of maneuver spent** — Auditor sanity check: still on the intent? Any spawn not
  pulling its weight gets no follow-up.
- **Maneuver exhausted** — **stop spawning for maneuver.** Only the reserve remains, and it
  is for verify/retry **only**. Reaching the maneuver cap without a result = re-triage or
  report blocked; it is **not** a licence to dip into the reserve.
- **Reserve touched** — allowed *only* for the verify gate or one sanctioned retry. If the
  reserve is gone and the mission still is not verified, **stop and report** — do not
  escalate spend without the user. Insolvency is reported, never hidden.

---

## 4. The ledger line (mandatory in every Operation/Campaign AAR)

One line, with a verify token from the closed set `verify=RUN|TEST|SYNTAX|NONE`, e.g.:

`LEDGER: spent 3/4 (2 maneuver +1 verify); reserve 1 banked; verify=RUN; VERIFIED-BY: provost-qa PASS`

The `VERIFIED-BY:` field is set by the gate unit (`provost-qa` / `red-team`) only — **doers never self-certify PASS.** A doer may write `VERIFIED-BY: provost-qa UNVERIFIED` as a placeholder; the gate unit overwrites it with PASS or FAIL on its turn.

When nonzero, add a second ledger line:

`BLOCKED: <n> RISKY items pending human act. The AAR is the queue — the human reads it and replies next turn.`

Skirmishes need no ledger (0 spawns). Keep it to one or two lines — no ceremony tax (Commander §3.6).

---

## 5. What is enforceable where (honesty)

| Host / context | Treasury enforcement |
|----------------|----------------------|
| **Claude Code main thread** | Advisory. Command counts its own spawns and obeys the caps; no live token meter. |
| **Claude Code subagent** | Cannot see the budget — the **Timer** controls it by handing a tight objective + bounded return. |
| **Cursor** | Advisory, same as model tiers; Command tracks spawns against the cap. |
| **Workflow tool** | The **one semi-hard lever**: `budget.total / spent() / remaining()` is real. Guard loops with `while (budget.total && budget.remaining() > <reserve>) {…}` so the reserve survives. |

Doctrine handles what the platform cannot hard-enforce — the same contract as `CORPS_MODEL_TIERS.md §5`.

---

## 5a. USD session budget (when the host exposes cost)

Some hosts (workflow tools, SDK wrappers) expose a running USD cost. When that data is
available:

- Declare a **USD session cap** at triage alongside the spawn cap, e.g. `[Treasury · Op · spawn ≤3 reserve 1 · USD cap $0.50 · USD reserve $0.08]`.
- Guard the main loop: `while cost_usd() < session_cap - reserve_usd: …`
- When cost hits the session cap, **HALT spawning** and report remaining work to the human — identical to hitting the spawn cap. Do not silently continue.
- The ledger line gains `usd:` and `usd_reserve:` fields, and must carry `verify=` + `VERIFIED-BY:` per §4, e.g.:
  `LEDGER: spent 3/4 · $0.34/$0.50 · reserve 1 banked · usd_reserve $0.08; verify=RUN; VERIFIED-BY: provost-qa PASS`

When cost data is NOT available, the spawn-count proxy remains the operative limit.
Advisory-only doctrine (§5) still applies — the agent self-governs; the platform does not
always hand a live meter.

---

## 6. Interaction with existing rules

- **Sits on top of** the echelon caps (Commander §1–2) and model tiers — it does not replace
  them; it sub-allocates the spawn cap and adds the reserve discipline.
- **Cost signal (−3):** when the user mentions credits/cost/cheap, the Treasurer **widens the
  reserve** (Operation reserve → 2, Campaign → 3) and floors model tier per Model Tiers §3.
- **Subsume before spawn** still holds: one solo recon/action pass is free and precedes any
  spend (Commander §3.1).
