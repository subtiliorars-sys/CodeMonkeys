# Review briefing — git-guards rollout + agent-corps improvement swarm
**Date:** 2026-06-05 · prepared for your return

---

## Part 1 — git-guards: automatic multi-instance + secret-leak protection

**Problem it solves (a real one, today):** you run several Claude instances against the *same*
clone. One sibling ran `git reset --hard` + `clean` on the shared MeniscusMaximus tree and **wiped
~300 lines of my uncommitted work** (recovered via `git fsck` dangling objects). The shared dirty
tree is the hazard.

**The architecture (synthesis, not a copy):**
- **MeniscusMaximus** had the best *hook logic*; **agent-corps** had the best *distribution mechanism*
  (`install.sh` + global `git init.templatedir` + multi-host). I folded the hooks into agent-corps so
  it propagates everywhere — agent-corps is the single source of truth.
- **`git-guards/githooks/pre-commit`** — universal secret scanner (GH/Google/OpenAI/Slack tokens, PEM keys).
- **`git-guards/githooks/pre-push`** — *opt-in* deploy-branch gate (`.githooks/deploy-branch`): a push to
  the deploy branch becomes deliberate (`ALLOW_DEPLOY_PUSH=1`) and is refused if the remote moved.
  **No-op in repos that don't auto-deploy** (so it's safe everywhere).
- **`git-guards/claude-enable-githooks.sh`** — the "automatic" piece. Git deliberately won't run a
  committed hook on clone (security), so a global **Claude `SessionStart` hook** runs
  `git config core.hooksPath .githooks` in any repo shipping `.githooks/` — covering **existing** clones
  too, not just fresh ones. (`install.sh` installs it via an idempotent `settings.json` merge.)
- **`git-guards/PROTOCOL.md`** — the portable CLAUDE.md protocol (branch-per-task, worktrees,
  stage-only-your-files, fsck-recovery).

**Tested:** `bash -n` clean on all scripts; pre-commit blocks a fake `ghp_…` token and allows clean
commits; settings.json merge is idempotent (added → already-present).

## Part 2 — Distribution status (all via branch + PR, per your call)
| Repo | Auto-deploys? | PR |
|---|---|---|
| agent-corps (source of truth) | no | https://github.com/subtiliorars-sys/agent-corps/pull/1 |
| Cairn | no | https://github.com/subtiliorars-sys/Cairn/pull/1 |
| OmniTender | no | https://github.com/subtiliorars-sys/OmniTender/pull/1 |
| OmniVerse | no | https://github.com/subtiliorars-sys/OmniVerse/pull/1 |
| omnitender-web | no | https://github.com/subtiliorars-sys/omnitender-web/pull/1 |
| MeniscusMaximus | **yes (Fly)** | already has `.githooks/` on master (a sibling built it); left to them |

Preview repos (Cairn---Preview, MeniscusMaximus-Preview) intentionally **skipped**.

## Part 3 — How to activate on a machine (one time)
```bash
cd ~/agent-corps && git pull && ./install.sh   # idempotent; adds the Claude SessionStart hook
```
After that, every Claude session in any repo with committed `.githooks/` auto-enables the guards.
I did **not** silently edit your global `~/.claude/settings.json` — that's the one machine-level change
I left for you to run/approve. (Reversible: remove the SessionStart entry from settings.json.)

---

## Part 4 — agent-corps improvement recommendations (swarm result)
**Swarm:** 6 repos mined → 36 insights → 15 proposals → 3-lens adversarial audit → **13 survived** →
converged into **9 recommendations**. 53 agents, ~1.14M tokens, tier-routed cheap-first (sonnet for the
read/audit fan-out, top model for synthesis/convergence — dogfooding the corps' own doctrine).

**The audit earned its keep — it cut the over-engineering**, not just the weak ideas: it rejected porting
MeniscusMaximus's `PROCESS_CADENCE.md` as a new file (metaphor-heavy, per-turn cost, no new decision),
killed a `CORPS_QUEUE` (the corps has no runtime/clock to age items), rejected a 6-field AAR schema
(ceremony with no machine consumer), and deferred new governance files as negative-ROI. Almost every
survivor is a **few-sentence edit to an existing doctrine file, and credit-NEGATIVE** (saves burn).

### ✅ Implemented now (in agent-corps PR #1)
- **R4 — git tooling (the only net-new safety gap in the kit).** Added `git-guards/bin/safe-commit`
  (branch-checked commit; replaces the inline one-liner the audit flagged as a *silent-data-loss bomb* —
  a detached HEAD makes `[ … ]` fail, `&&` short-circuits, the whole add+commit silently drops) and
  `git-guards/bin/agent-worktree` (isolate each parallel writing unit — the real fix for the collision,
  which a hook can't do because hooks fire after the agent already has a tree). On PATH via `install.sh`.

### 📋 Recommended — low-effort doctrine edits, await your OK (I can apply on your word)
| # | Edit | Why / credit impact |
|---|---|---|
| **R1** | `CORPS_COMMANDER.md` Campaign: add a **DERIVE GATE** (write the orthogonal one-line-per-strand split before any fan-out) + tighten "pipeline-not-barrier" with an *independence test* + "one writer converges" rule | Stops the two costliest swarm failures — sprawl and **duplicated agent work from a sloppy split** (~15× waste each). Credit-negative. |
| **R2** | `CORPS_COMMANDER.md` §2: state the **cascade filter** explicitly (recon narrows → T3 red-team only sees the pre-filtered delta) + a cheap "raw-echo index" escape hatch. *Dropped* the per-unit schema mandate (unenforceable). | Keeps the most expensive (Opus) units off raw material. Credit-positive. |
| **R3** | Playbooks `blackboard.md` / `swarm-discovery.md`: **namespace each unit's writes** to its own section (no filesystem locking exists → parallel appends race & corrupt shared FACTS) + sharpen the two triggers | Makes the already-built scratchpad concurrency-*safe*; collapses serial round-trips into one parallel wave. |
| **R5** | `CORPS_COMMANDER.md`: a **`RISKY` triage tag** (irreversible + outward) that does **not** auto-execute in-turn + a subagent `HOLD:` rule + conditional `BLOCKED:` AAR line. *No* persistent queue. | Prevents a subagent firing money/auth/deploy actions before Command intercepts. |
| **R6** | `CORPS_TREASURY.md` ledger: add a closed **`verify=RUN\|TEST\|SYNTAX\|NONE`** token + `VERIFIED-BY: provost-qa` — the gate unit, *not the doer*, owns the PASS verdict | Guards the #1 agent lie ("done" = syntax-only). Grep-able, +2 tokens/line. |
| **R7** | `CORPS_MODEL_TIERS.md`: an **honest prompt-cache note** — `cache_control` only applies to direct-API/Claude-Code-SDK hosts (N/A on Cursor/Roo/Copilot/Cline); real target is the Command thread's static block past ~1,024 tokens / 5-min replay | Corrects a partly-false premise; prevents agents chasing a knob that doesn't exist on half the hosts. |
| **R8** | `AGENT_DOCTRINE.md` §4: **fail-safe two-register output** — mark `internal-only` when NOT ready; unmarked = surfaceable (so omission can't *elevate* an intermediate). Red-team exempt. | Lowers Command's verification burden; closes the dangerous direction. |

### ⏸️ Deferred by the audit (don't build yet)
- **R9 / P14** — doctrine split + sync script + `CORPS_VENDORING.md`/`DECISION_LOG.md`: **negative ROI** —
  Claude Code files are already symlinked (no divergence), no automated writer exists to clobber them.
  Take only two cheap bits: a `# SAFETY-CORE — do not auto-sync` header on the core docs, and a one-line
  `install.sh` grep that warns if a deployed repo's "PROJECT-SPECIFIC FACTS" placeholder is still unfilled
  (a real gap found in `omnitender-web`).
- **P9** (continuous weighted risk→tier score) and **P13** (component-freeze flags) — cut in the audit:
  added complexity outweighed payoff for a doc-only, runtime-less framework.

Full machine-readable detail (every insight, proposal, per-lens verdict) is in the workflow output.

---

## Part 5 — Status: ALL DONE (2026-06-06)
1. ✅ **All 6 PRs merged** — agent-corps #1 (git-guards) + #2 (doctrine R1–R8), and Cairn/OmniTender/
   OmniVerse/omnitender-web #1.
2. ✅ **SessionStart hook activated** from the canonical `~/agent-corps` (`git pull && ./install.sh`).
   Verified: hook enables `.githooks` per repo (tested on MeniscusMaximus → `core.hooksPath=.githooks`);
   `safe-commit`/`agent-worktree` on PATH; R1–R8 live via the `~/.claude/*.md` symlinks.
3. ✅ **R1–R8 implemented** and merged (R9/P9/P13 deferred by the audit, as noted above).
4. ✅ Throwaway clones cleaned up; canonical `~/agent-corps` + `~/MeniscusMaximus` retained.

**Note:** other repos' git-guards take full effect for *new* sessions (the SessionStart hook enables
`.githooks` the next time a Claude session opens in each). MeniscusMaximus is the auto-deploy repo — its
`.githooks/deploy-branch` should name `master` if you want the deploy-gate there (a sibling owns that file).
