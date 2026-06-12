# Fleet Automation — Medallion Governance

This tool is bound by the same **Twelve Steps** (inner alignment) and **Twelve Traditions**
(outer governance) as MeniscusMaximus and CodeMonkeys.

## Hard-coded loop (cannot be disabled except UNSAFE_SKIP_GATES)

| When | Phase | Checkpoints enforced |
|------|-------|---------------------|
| Session start | `startup` | Steps 1,3,4,12 · Traditions 2,12 |
| Every browser action | `pre_action` | Steps 1,3,10 · Traditions 2,5 |
| Save / publish / deploy | `pre_irreversible` | Steps 5,8,9 · Traditions 1,2,6 |

Source of truth in code: `src/governance/medallion-loop.ts`

Canonical paraphrases also live in:

- `MeniscusMaximus/brain/steps.py`
- `MeniscusMaximus/brain/traditions.py`
- `CodeMonkeys/corps/agent-governance.md`

## Mapping to concrete guardrails

| Medallion principle | Fleet-automation enforcement |
|---------------------|------------------------------|
| Step 1 / Tradition 2 — human authority | TTY-only `[Y/N]` gates |
| Step 5 — disclose | `user-data/audit.log` append-only |
| Step 9 — reversible | `--dry-run` default recommendation; no auto-save without Y |
| Tradition 6 — no entanglement | URL HTTPS allowlist |
| Tradition 12 — principles over expedience | Gates cannot be skipped in CI (non-TTY) |

## Operator oath (read at startup)

Automation serves the human operator. Every store mutation requires explicit approval.
If in doubt, type **N** and fix the plan first.
