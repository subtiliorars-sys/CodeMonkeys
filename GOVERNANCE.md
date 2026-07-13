# GOVERNANCE — CodeMonkeys

**Tiers A + B + D** — Universal + Holds-people's-data + Agentic/acts-in-the-world.
(Installer header below renders the primary tier "D"; CM also carries Tier B because
it holds user data — see the full A/B/D checklist below.) Rendered by
`install-governance.sh` from `agent-corps/templates/GOVERNANCE.md.tmpl` on 2026-06-07.

This repo is governed under the **Corps Constitution**
(`agent-corps/CORPS_CONSTITUTION.md`). That file defines WHAT each invariant and
tier mean; this file records WHICH invariants bind THIS repo and the dated state
of each. Higher tiers add to lower; every repo is at least Tier A.

> A rule with no mechanism is just a wish (Constitution §0.3). Every box below
> names its mechanism class — **hook** (git/CI), **gate** (runtime refusal/
> approval), **test** (regression guard), **middleware** (per-request), or
> **receipt** (tamper-evident audit). Prose-only compliance is non-compliance.

## Binding invariant checklist (Tier D)

Check a box only when its named mechanism is PRESENT and PASSING in this repo —
not when you intend to add it.

### Tier A — Universal (binds every repo)
- [x] **S-4 Verify before done** — risky work (auth/data/irreversible/money/security) gets a recorded RED-TEAM pass before merge. _(test + receipt; PR-checklist line)_
- [x] **S-6 Post-incident amends** — a shipped defect's fix lands with a regression test that would have caught it; lesson recorded. _(test)_
- [x] **S-8 Branch per task; stage only your own** — no `git add -A`/`-a`; parallel work uses worktrees. _(hook: advisory pre-commit add-all detector + doctrine)_
- [x] **T-4 No endorsement entanglement** — brands stay separate; no implied AA/program affiliation on public surfaces. _(hook: brand-string CI lint + PR checklist)_
- [x] **T-5 Principles before personalities** — access is role/permission-based; honorary labels carry zero permissions. _(test)_
- [x] **M-1 Fail-closed auth** — privileged endpoints deny by default; missing/invalid creds => 401/403; root-singleton reads use the strict verifier. _(gate + test; A-tier: if any auth)_
- [x] **M-2 No secrets in code** — creds in env/config only; pre-commit secret-scan hook blocks token/key patterns; leaks are revoked. _(hook)_
- [ ] **M-3 Protected default branch** — direct pushes to the deploy/default branch blocked unless explicitly overridden; deploy-pushes treated as deploys. _(hook)_
- [x] **M-9 Confirm before deploy** — no automated deploy without a human approval or CI test gate in front; deploys observable (healthcheck + smoke). _(hook + gate)_

### Tier B — Holds people's data (adds to A)
- [ ] **M-4 Consent before cloud egress** — no user content leaves to a third-party model/service without recorded, revocable consent. _(gate + test)_
- [ ] **M-5 PII gates + scrubbing** — surfaces that publish/share user-derived content refuse high-confidence identifiers (fail-closed), with a scrubber beneath. _(gate + test)_
<<<<<<< HEAD
- [x] **M-7 Real erasure** — `DELETE /api/users/{uname}` (Owner-only) hard-deletes the users.json record AND every derived per-user store (login-throttle counter, transient WebAuthn challenge, egress-consent record, Vertex credentials; the record carries pin/salt/mfa/passkey material), writes a tombstone (`data/erased_accounts.json`) that blocks re-register/invite/rename-into the id, and appends an owner-auditable receipt (`data/erasure_receipts.jsonl`, viewable at `GET /api/erasures`) carrying only the subject id + names of the stores cleared. Message content (issue #70): sessions are single-owner and typed messages are author-tagged at write time, so the cascade also deletes the member's own sessions (event logs + history + index rows) whole, content-scrubs any author-tagged message of theirs inside a session they don't own, and deletes their isolated `user_<uname>/` workspace subtree (uploads, blackboards, per-user KB, clones) — never touching other accounts' data. Residual: pre-attribution records (legacy `username=None` sessions, pre-#70 workspace-root blackboard/KB writes) carry no author and stay; anonymous-by-design feedback reports are not attributable. Backups: CM's only backup notion is the Fly volume snapshot, which ages out of its window naturally (stated retention exception); no backup-deletion is built (Owner-reserved, Phase-4 crypto-shred target). _(gate + test + receipt)_
- [ ] **M-8 Backup posture** — data-holding repos document + verify a backup path (snapshots and/or encrypted off-site vault, keys held by Owner). _(test: restore drill + receipt)_
=======
- [x] **M-7 Real erasure** — `DELETE /api/users/{uname}` (Owner-only) hard-deletes the users.json record AND every derived per-user store (login-throttle counter, transient WebAuthn challenge; the record carries pin/salt/mfa/passkey material), writes a tombstone (`data/erased_accounts.json`) that blocks re-register/invite/rename-into the id, and appends an owner-auditable receipt (`data/erasure_receipts.jsonl`, viewable at `GET /api/erasures`) carrying only the subject id. Sessions/uploads/blackboard/KB are workspace-global (not per-user) so they are out of per-user cascade scope by design — see the architectural note below. Backups: CM's only backup notion is the Fly volume snapshot, which ages out of its window naturally (stated retention exception); no backup-deletion is built (Owner-reserved, Phase-4 crypto-shred target). _(gate + test + receipt)_
- [x] **M-8 Backup posture** — backup path documented (`docs/RECOVERY.md` Scenario G; Fly volume `cm_data` at `/data` + automatic daily volume snapshots) AND verified: a restore drill (`run_backup_drill`) reads back + validates every structured store CM writes under `DATA_DIR` (JSON parse + expected shape, JSONL line-parse, CMENC1 decrypt under the current master key, S-3 chain integrity via `verify_audit_chain`, sessions tree), runnable against the live tree or a restored snapshot copy (Owner-only `POST /api/backup/drill`, or `scripts/backup_drill.py [dir]` via `fly ssh console`), and appends a timestamped pass/fail-per-store receipt to `data/backup_drill_receipts.jsonl` (Owner view: `GET /api/backup/drill-history`; live-run summaries also committed to the S-3 hash chain). An encrypted OFF-SITE vault (keys held by Owner) is NOT built — Owner-reserved infra decision; snapshots satisfy the "snapshots and/or" letter. _(test: restore drill + receipt — `tests/test_backup_drill.py`)_
>>>>>>> c9d94c8 (feat: M-8 backup posture - restore drill + receipt)
- [x] **M-10 Serialized atomic writes** — all mutators of shared user state are serialized (single-writer) and write atomically; no slow I/O in the critical section. _(test)_
- [ ] **M-12 Minors + likeness consent** — no human imagery / minors' data without documented consent; public-surface images need a consent-log entry or a SAMPLE_ prefix (CI filename-check). _(hook + gate + receipt)_
- [ ] **T-2 (spirit)** — where progress mechanics exist, money must not gate or accelerate them. _(test where applicable)_

### Tier D — Agentic / acts in the world (adds to A/B)
- [x] **S-1 Plan before act** — agent exposes a read-only plan mode; plan precedes execution. _(gate + test)_
- [x] **S-2 Approval gate** — every write / send / deploy / spend records explicit human approval before execution. _(gate + receipt)_
- [ ] **S-3 Receipts** — consequential actions append to a hash-chained audit trail; reads gated to strict admin. _(receipt + test)_
- [x] **S-5 Self-heal capped** — retry/self-repair loops carry a hard iteration/spend cap and stop, never escalate silently. _(gate + test)_
- [x] **S-7 Budget/treasury caps** — runs respect per-session/per-task spend caps + a credit reserve; never spend to zero. _(gate)_
- [x] **M-6 Path jails on agent file access** — FS access confined to declared roots; realpath+prefix check resolves symlinks; traversal refused. _(gate + test)_
- [x] **M-11 Risky-command + write guards** — agent shells/exec gate dangerous commands and scan agent-authored writes for secrets before they land. _(gate + test)_

## Verification standard (Constitution §5)

This repo is **governed** only when ALL of:

- [x] `GOVERNANCE.md` present with tier assignment + a dated audit (this file).
- [x] git-guards active — `git config core.hooksPath` returns `.githooks`.
- [ ] Every invariant this tier binds has its named mechanism present and passing
      (hook / gate / test / middleware / receipt) — not prose.  _(15/23 PRESENT;
      4 PARTIAL, 2 MISSING, 2 N/A — see audit log below. NOT yet fully governed.)_
- [ ] Red-team GO recorded for every D-tier surface touched.  _(pilot install is
      additive scaffolding only; no D-tier code surface changed.)_
- [ ] The Owner merged the governance PR.  _(this PR — pending.)_

Re-audit on the Phase 5 cadence (quarterly) and on ANY change to an
auth / exec / data / money surface (Constitution §5).

## Dated audit log

Append a dated entry each audit. Keep the lab-bench standard: a fresh agent should
be able to read the latest entry and know exactly what is and isn't satisfied.

### 2026-06-07 — Phase 1 pilot install + first audit (Tier A + B + D)
- **State: PARTIALLY GOVERNED — 15/23 PRESENT, 4 PARTIAL, 2 MISSING, 2 N/A.**
- Carrier install (this PR): GOVERNANCE.md (this file), CLAUDE.md governance
  stanza, `.githooks/` + `core.hooksPath=.githooks`, `.github/pull_request_template.md`
  S-4 line, pruned `brand-wordlist.txt` (CM is not recovery-adjacent → AA terms
  removed; CM's own name removed to avoid self-block). Test suite: **472 passed**.

- **PRESENT (15):**
  - Tier A: S-4 (red-team convention + new PR-checklist line), S-6 (regression
    tests lock past fixes, e.g. `test_dup_send`, `test_blank_baseurl`,
    `test_bash_env_hardening`), S-8 (new advisory `pre-commit.d/20-add-all-advisory`
    + CLAUDE.md doctrine), T-4 (new `pre-push.d/20-brand-lint` + pruned wordlist +
    PR checklist), T-5 (role-based: `role` Owner/Member, `verify_owner` server.py:687),
    M-1 (fail-closed `verify_token`/`verify_owner`, 401/403 deny-by-default,
    server.py:680-699), M-2 (new `pre-commit.d/10-secret-scan` hook), M-9
    (`.github/workflows/ci.yml` runs pytest + import smoke on every push/PR;
    `/healthz` server.py:271; deploy is manual = human gate).
  - Tier B: M-10 (`_USERS_LOCK`/`_DAILY_LOCK` single-writer + atomic `os.replace`,
    server.py:378-402).
  - Tier D: S-1 (spec-first plan mode, `_PLAN_READONLY_TOOLS` server.py:3300,
    `test_plan_execute`), S-2 (`request_approval` server.py:3905 + `test_approval_gate`;
    auto-mode uses the 3-lens verifier panel as compensating control), S-5
    (MAX_TURNS=60 / SUBAGENT_MAX_TURNS=25 / _MODEL_RETRIES=3 caps), S-7
    (SESSION_BUDGET_USD + SESSION_BUDGET_MAX_USD + N2 daily spend cap;
    `test_daily_spend_cap`), M-6 (`_jail`/`_jail_specs`/`_jail_blackboard` realpath+
    prefix, server.py:2887; canon source), M-11 (RISKY_PATTERNS + `_is_risky` +
    3-lens verifier + W6 secret write-guard + W7 MCP gating, server.py:204-262,3095+).

- **PARTIAL (4):**
  - **M-3** (LOW) — deploy-gate hook installed but inert: no `.githooks/deploy-branch`
    file because CM deploys are manual (no auto-deploy-on-push). `main` is not
    push-protected. Configure `deploy-branch` if/when auto-deploy lands.
  - **M-5** (LOW) — redaction/scrubbers exist for audit + memory surfaces
    (`_scrub_memory_text` server.py:4719, `test_redaction`), but no formal
    fail-closed PII gate on a publish/share surface. Largely mitigated by per-user
    workspace isolation (no cross-user communal publish surface today).
  - **M-8** (LOW/MED) — Fly volume `cm_data` at `/data` + `docs/RECOVERY.md`
    documented, but no encrypted off-site vault and no recorded restore drill/receipt.
  - **S-3** (MED) — owner-only redacted event aggregator (`audit_log` server.py:4662,
    `verify_owner` read gate, `test_audit_viewer`/`test_redaction`) exists, but the
    trail is aggregated from in-memory SESSIONS — NOT a hash-chained, tamper-evident
    persisted audit trail as S-3 specifies.

- **RESOLVED (1):**
  - **M-7 Real erasure (HIGH) — FIXED** (PR "M-7: real erasure cascade + tombstone
    + receipt", closes #66; S-4 red-teamed). `DELETE /api/users/{uname}` now
    cascade-deletes every store keyed to the username (users.json record +
    login-throttle counter + transient WebAuthn challenge), writes a tombstone
    (`data/erased_accounts.json`) that blocks re-register/invite/rename onto the id,
    and appends a receipt (`data/erasure_receipts.jsonl`, `GET /api/erasures`).
    **Architectural note:** CM's sessions (`data/sessions/<sid>`), uploads
    (`<workspace>/uploads/<sid>/`), blackboard and KB are workspace-GLOBAL, not
    attributed to a username — deleting them on one member's erasure would destroy
    other accounts' (incl. the Owner's) data, so they are out of per-user cascade
    scope by design. The one residual: a member's own typed messages live inside
    SHARED session event logs, commingled and unattributed; precise per-user
    erasure there needs per-user session attribution (tracked as follow-up).

- **MISSING (1):**
  - **M-4 Consent before cloud egress (MED)** — user code/prompts are sent to
    third-party LLM providers (Gemini/OpenAI/OpenRouter/DeepSeek/xAI, server.py:1232+)
    with no recorded, revocable per-user cloud-processing consent gate or test.
    Partially mitigated by owner-supplied BYO keys + per-user isolation + log
    redaction, but no mechanism satisfies M-4.

- **N/A (2):**
  - **M-12** — CM ships no human imagery / minors' content; CI filename-check not
    installed. Re-evaluate (install the check) only if an image-bearing public
    surface is added.
  - **T-2 (spirit)** — CM has no progress / gamification mechanics, so money cannot
    gate or accelerate progress (vacuously satisfied).

- Auditor: governance Phase 1 pilot (automated audit vs Constitution §4 checklist).
- Red-team verdict: n/a for this PR (additive scaffolding only — no auth/exec/data/
  money code surface changed). The MISSING/PARTIAL fixes (esp. M-7 erasure) are
  follow-up work that WILL need an S-4 red-team pass when implemented.

<<<<<<< HEAD
### 2026-07-13 — M-7 follow-up: per-user attribution + message-content erasure (issue #70)
- **Scope correction vs the 2026-06-07 note:** since S6 Layer 1/2 (session
  ownership + per-user workspace subdirs) landed, sessions are SINGLE-OWNER
  (`session["username"]`; only the owner can type into one) and uploads/
  blackboards/per-user KB live under `WORKSPACE_DIR/user_<uname>/` — the
  "workspace-global, unattributable" framing no longer matched the code. The
  one true commingling found: the `blackboard_write` tool dispatch dropped the
  session owner and wrote to the workspace-ROOT board (its read path was
  already per-user) — fixed; member boards now land in their own workspace.
- **Mechanism (gate + test + receipt):** typed `user` events are tagged
  `author=<owner>` at write time in `emit()`. The erasure cascade
  (`_erase_user_data`) now also: deletes the member's own sessions whole
  (events JSONL + history + index row; in-flight runs are stopped and can no
  longer re-persist), content-scrubs any author-tagged event of theirs inside
  sessions they do NOT own (other members'/Owner's lines byte-identical),
  and deletes their isolated `user_<uname>/` workspace subtree (realpath-
  guarded to a direct `user_` child — can never reach shared data). Receipt
  `stores` records `sessions` / `session_events_scrubbed` / `workspace` when
  content erasure occurred; absence means no such content existed.
  Tests: `tests/test_erasure_attribution.py`.
- **Remaining residual (disclosed):** records that PRE-DATE attribution —
  legacy `username=None` sessions and pre-#70 writes on the workspace-root
  blackboard/KB — carry no author and cannot be selectively attributed to an
  erased member; deleting those shared records would destroy other accounts'
  data, so they stay. Feedback reports are anonymous by design (no username
  stored) and are not attributable. Fly volume-snapshot retention exception
  unchanged.
- Red-team pass (S-4): recorded in the PR body (spoofed-attribution,
  over-deletion via crafted username/symlink, under-deletion via in-flight
  runs, and cross-account blast-radius cases checked).
=======
### 2026-07-13 — M-8 backup posture: restore drill + receipt
- **M-8 PARTIAL → PRESENT** (PR "M-8: restore drill + receipt"). The 2026-06-07
  gap was the verification half: volume + runbook documented, but "no encrypted
  off-site vault and no recorded restore drill/receipt". The drill/receipt half
  now exists as a mechanism (test + receipt), not prose:
  - `run_backup_drill()` (server.py) reads back + validates every structured
    store CM writes under `DATA_DIR` — JSON parse + expected top-level shape,
    JSONL line-parse, CMENC1 configs must DECRYPT under the current master key
    (strict, unlike the fail-soft runtime readers), S-3 audit chain must VERIFY
    (`verify_audit_chain`), sessions tree read back — plus a generic sweep of
    any unlisted top-level `*.json`/`*.jsonl` so future stores can't silently
    escape coverage. A drill that finds NOTHING to check reports not-ok (an
    empty tree is what restoring the wrong volume looks like).
  - Receipt: every drill appends `{ts, event, by, ok, checked, absent, failed,
    stores[]}` to `data/backup_drill_receipts.jsonl` (append-only JSONL, the
    M-7 receipt idiom); live-tree drills also commit a summary to the S-3 hash
    chain, so "a drill ran and said X" is itself tamper-evident.
  - Triggers: Owner-only `POST /api/backup/drill` (live tree) and
    `scripts/backup_drill.py [data_dir]` for `fly ssh console` / restored-
    snapshot copies (exit 0/1). History: Owner-only `GET /api/backup/drill-history`.
    Runbook: `docs/RECOVERY.md` Scenario G (quick live drill + full
    restore-a-snapshot drill).
  - Drill EXECUTED as part of this audit (2026-07-13, local, via
    `scripts/backup_drill.py` against a seeded /data-shaped tree): healthy tree
    → ok=true, 8 stores checked, receipt appended; deliberately corrupted
    `users.json` → ok=false, `failed=["users.json"]`, exit 1, second receipt
    appended. Tests: `tests/test_backup_drill.py` (12 — healthy pass+receipt,
    corrupted JSON/JSONL/CMENC1/chain/session artifacts each detected,
    wrong-shape detected, unknown-store sweep, 401/403 fail-closed endpoints,
    corrupted-store contents never echoed into result or receipt).
- **Still open on M-8's spirit (disclosed):** no encrypted OFF-SITE vault with
  Owner-held keys — Owner-reserved infra decision (likely aws-infra), NOT built
  here. Fly's automatic daily `cm_data` snapshots + this drill satisfy the
  checklist letter ("snapshots and/or encrypted off-site vault"); a snapshot
  still lives with the same provider as the primary. If the Owner wants the
  off-site half, a candidate shape is an Owner-triggered encrypted export the
  Owner copies off-box — proposal only, separate decision.
- Red-team pass (S-4, low-risk Tier B surface — read-only verification):
  checked that drill failure reasons never carry file bytes (exception class +
  line/column/offset only; locked by test), that both endpoints sit behind
  `verify_owner` (deny-by-default 401/403, locked by tests), that the drill
  writes nothing into user-facing stores (only its own receipt file), and that
  the CMENC1 check is side-effect-free (doesn't flip the fail-soft
  `_DECRYPT_FAILED` UI flag or rewrite configs).
- Auditor: governance M-8 lane (Fable, dispatched session), verified locally:
  full suite green on Linux-equivalent set (Windows-only pre-existing failures
  unchanged vs clean main), `import server` clean.
>>>>>>> c9d94c8 (feat: M-8 backup posture - restore drill + receipt)

## Amendments

Only the Owner ratifies/amends/repeals invariants (Constitution §6). Agents may
PROPOSE amendments via PR against `CORPS_CONSTITUTION.md`; nothing is in force
until the Owner merges it. Decisions reserved to the Owner (six-gate parameters,
erasure-vs-backup semantics, §6 itself) are never guessed — the affected surface
stays closed until ruled.
