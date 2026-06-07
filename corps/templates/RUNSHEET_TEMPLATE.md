# Runsheet — <operation name>

| Field | Value |
|-------|-------|
| Operation | <name> |
| Owner | <person/unit responsible> |
| Target date | <YYYY-MM-DD> |
| Repo(s) | <list> |
| Go/No-Go authority | <who can halt> |

---

## Week-before checklist

- [ ] All dependencies confirmed (accounts, API keys, feature flags)
- [ ] Restore point created and recorded (`agent-governance.md` Restore Point Protocol)
- [ ] Hard GATES verified (backup exists, policy posted, two-register check passed)
- [ ] Runbook / rollback path documented and tested in staging
- [ ] Comms drafted (owner notification, status page text if applicable)

## Day-before checklist

- [ ] consistency-sweep complete if doc corpus > 10 files (`CORPS_COMMANDER.md §4a`)
- [ ] Risk register reviewed; no open CRITICAL/HIGH findings without accepted mitigations
- [ ] All STALLED owner-queue items resolved or explicitly deferred with owner sign-off
- [ ] Final go/no-go call scheduled

## Day-of checklist

- [ ] Stop-flag absent (`~/.claude/fleet/<repo>__<task>.stop`)
- [ ] Budget declared and reserve set
- [ ] Hard GATES re-verified (not assumed from yesterday)
- [ ] Execute in order; heartbeat updated at each step
- [ ] Verify gate run (`provost-qa` or `red-team`) before declaring done
- [ ] Ledger line written to AAR

---

## Debrief (fill after operation)

**Went well:**

**Went wrong / unexpected:**

**Gate or halt triggered? (Y/N — if Y, which condition and outcome):**

**Changes to this runsheet for next time:**
