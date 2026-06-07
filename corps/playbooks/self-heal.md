# Self-Heal Playbook

*Trigger: autonomous loop / self-healing agent hitting repeated failures.*
*Cost: cheap — this is a stop rule, not a fan-out.*

---

## Purpose

An agent operating in a loop (code-fix cycle, test-retry, apply-and-verify) must not spin
forever. This playbook defines the halt conditions and the discipline for targeted fixes.

---

## Protocol

**After every change, verify.** Each iteration ends with a concrete check (test run, lint,
smoke call) — not an assumption. If verification is skipped, the loop is blind.

**Smallest targeted fix only.** Apply the minimum change that could fix the observed
failure. A fix that touches >3 files for a single failure signature is almost certainly
wrong — stop and re-examine the root cause instead.

**HALT conditions (must stop the loop):**

| Condition | Action |
|-----------|--------|
| Same failure signature appears **twice in a row** | HALT immediately — you are in a local minimum. Report the signature and what was tried. |
| **5 cycles** have elapsed without a green verify | HALT — declare blocked regardless of current failure signature. |
| Budget (spawn cap OR USD session cap) exhausted | HALT — reserve may fund the single Treasury-sanctioned retry (`CORPS_TREASURY.md`); beyond that, HALT and report remaining work. |
| Stop-flag present (`~/.claude/fleet/<repo>__<task>.stop`) | HALT — governance override. |

**On HALT:** write a terse summary — failure signature, cycles consumed, last attempted fix,
what would be needed to continue — and surface it to Command/human. Do not retry. Do not
silently switch strategies without reporting.

**Failure signature** = a short stable string identifying the error (e.g. test name +
exit code, exception class + line, lint rule ID). Two consecutive identical signatures =
same failure twice in a row, regardless of what the fix attempted was.

---

## Anti-patterns

- **Loop masking:** catching the error to continue without a real fix. If verify passes
  only because you suppressed the check, it is a false green.
- **Spray-and-pray:** applying multiple unrelated changes in one iteration hoping one
  sticks. Each iteration: one hypothesis, one change, one verify.
- **Silent escalation:** switching to a heavier tool or larger model inside the loop
  without surfacing it. Use `[[ESCALATE]]` (see `CORPS_MODEL_TIERS.md §2b`) — once, visible.

---

## Relationship to other doctrine

- **Repeat-count ≥ 3** in the heartbeat triggers the Governor's self-loop guard
  (`agent-governance.md` Fleet Supervision). This playbook's halt at 2 consecutive same-signature
  fires before the Governor does — it is the internal primitive.
- Budget caps are set at triage per `CORPS_TREASURY.md`; this playbook reads them, never sets them.
