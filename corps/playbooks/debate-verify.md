# Playbook: Debate Verify Gate

*Exotic pattern. Loaded only when triggered from `CORPS_PLAYBOOKS.md`. Default verify is a
single `provost-qa` / `red-team` pass — use this only on the deltas where being wrong is
expensive.*

## Use when
A **high-risk delta is about to be trusted**: auth, multi-user data isolation, money,
irreversible/outward actions, security boundaries, correctness-critical logic.

## Don't use when
Low/medium-risk changes (single checker is fine), or when cost-locked and there is no
safety reason — debate costs N× the verifiers.

## How to run (real primitives)
1. Spawn **3 verifiers in parallel**, each with a **different lens** (not 3 clones):
   e.g. `correctness` · `security/abuse` · `does-it-actually-reproduce`. Heterogeneous
   beats homogeneous majority-vote (ICML 2024; ~30% fewer factual errors, diverse > same).
2. Each returns a verdict + evidence, prompted to **refute** the change, not bless it.
3. **Reconcile:** Command (or one extra pass) reads all three.
   - **Majority-refute → DO-NOT-SHIP** (primary kill signal; majority rules).
   - **CRITICAL finding** counts only if at least one *other* verifier independently
     confirms or fails to rebut it; a lone CRITICAL is not auto-decisive.
   - **Solo CRITICAL (others silent):** before Command decides, run ONE cheap T0
     confirming read targeted at that specific claim. If the confirming read validates
     it, treat as confirmed-CRITICAL (block); if it doesn't, treat as noise (proceed
     with fixes at discretion).
4. These verifiers come from the **Treasury reserve** (they ARE the verify gate) — they
   don't eat the maneuver budget.

## Payoff vs cost
Payoff: large error/​hallucination reduction on exactly the changes that matter. Cost: 3
verifier spawns instead of 1 — acceptable because it's the reserve and the surface is
high-risk by definition.

## Exit
Decision: SHIP / SHIP-WITH-FIXES / DO-NOT-SHIP, with the dissent recorded.
AAR line: `PLAYBOOK: debate-verify · helped? yes/no/partial`.
