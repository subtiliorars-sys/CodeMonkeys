# Working agreement

These instructions govern how the agent should work in this workspace.

## Execution style
- Prioritize fast, direct execution. Do the task; skip preamble and wordy boilerplate.
- Favor high-specificity, targeted code changes over broad rewrites.
- Be token-efficient: short answers, no restating the question back.

## Scope guardrails
- Do NOT run massive multi-file scans, repo-wide greps, or whole-directory reads
  without explicit permission. Ask first, then scope the search narrowly.
- When unsure how broad an operation will be, state the cost and confirm before running it.

## Multi-instance git protocol (applies in EVERY repo here)
The user runs several Claude instances in parallel, sometimes in the same clone.
Assume you are not alone:
- **Branch per task** (`work/<topic>`); for parallel work in one clone use a git
  worktree (EnterWorktree tool) so instances never share a dirty tree.
- **Stage only files YOU changed.** Never `git add -A` / `git add .` / `commit -a` —
  the tree may hold another instance's WIP. Unexplained dirty/untracked files:
  leave them alone and tell the user.
- **Before pushing a shared branch:** `git pull --rebase` first; never force-push.
- **Repos that auto-deploy on push** (MeniscusMaximus: master → Fly) treat a push
  as a deploy — follow that repo's CLAUDE.md push protocol exactly. MM has
  `.githooks/` guards (pre-push master gate + secret scan) and a CI test gate;
  copy `.githooks/` + `git config core.hooksPath .githooks` to other repos as
  they gain deploy automation.

## Unified Operating System (UOS v2.1)
All autonomous agents (Claude, Gemini, and future agents) follow the multi-agent
collaboration framework at: `~/omnitender-worklog/UNIFIED_OPERATING_SYSTEM_v2.1.md`

This is the canonical coordination protocol for multi-agent work. Read it once, then
reference it in all `.agent-config.json` files for new projects.

## Canonical doctrine (unified — applies to EVERY repo/project here)
This file cascades into every session started under `~`, so new projects never need
bespoke pointers. Read the docs below on demand, not all upfront:
- **Agent corps (Daystrom):** `~/agent-corps/AGENT_DOCTRINE.md` — mission-command
  echelons (Skirmish → Operation → Campaign), auto-triage per `CORPS_COMMANDER.md`.
  Default to the smallest echelon that wins; `/deploy` is an explicit override.
- **Token economy:** `~/agent-corps/CORPS_MODEL_TIERS.md` + `CORPS_TREASURY.md` —
  tier routing (cheap models for recon/scribe work), credit-reserve doctrine.
- **Governance (12-Steps / 12-Traditions loops):** `~/agent-corps/GOVERNANCE_ROLLOUT_PLAN.md`
  — every repo gets a tier (A/B/C/D); apply the tier's safeguards at scaffold time.
- **License policy:** all repos proprietary / all-rights-reserved, owner deliberately
  UNNAMED (never add a name, never an email). Canonical templates:
  `~/agent-corps/templates/LICENSE-private.txt` (HQ repos) and
  `LICENSE-public.txt` (Preview/public repos, no-confidential variant).
  Exception: Ilerioluwa repos are Simon's IP — never touch their licenses.
- **Repo pattern:** each project = private HQ repo (full docs/code) + public
  `---Preview` repo (sanitized). Nothing confidential ever lands in a Preview repo.

## Territory & Ownership Wheelhouse
To prevent overlaps between parallel instances of Gemini and Claude/Cline, we adhere to the following ownership boundaries:
- **Gemini Territory (Do NOT edit with Claude/Cline):**
  - All **Omni** brand repositories: `OmniTender` (repo, web, design), `OmniVerse` (repo, admin, video), `OmniHerald`, `OmniFounder`, and `OmniDesk`.
- **Claude & Cline Territory (Do NOT edit with Gemini):**
  - `MeniscusMaximus` (including Yes Man GDD/prototypes), `CodeMonkeys`, `DrivingMeNuts` (and `DrivingMeNuts---Preview`), and `TradeGame`.
  - `AgentCorps` (`work/constitution` and general core constitution modifications).
- **Shared / Idle Repositories:**
  - `agent-system` and `Sea Games` (e.g., `WhiteWhale`, `Cetacea`, `Tidesung`). Can be picked up by either fleet upon explicit directive.

## Fleet protocol (multi-session coordination)
Blackboard at `~/fleet/` — full rules in `~/fleet/FLEET_PROTOCOL.md`. Every working
session on a project:
1. **Register:** write/refresh `~/fleet/status/<project>.md` (objective, branch,
   state WORKING|BLOCKED|DONE, heartbeat = output of `date -u`).
2. **Check in at natural breakpoints:** re-read `~/fleet/inbox/<project>.md` for
   Governor directives; refresh your heartbeat.
3. **Never-stall rule:** when blocked on a human decision, append the question to
   `~/fleet/questions.md`, set state BLOCKED, then list 5 safe parallel tasks in your
   status file and START the best one. Do not idle waiting for the human.
4. **Heartbeat + stop-flag (shared with the Windows fleet):** also beat via
   `python3 ~/agent-corps/fleet/heartbeat.py beat <repo> <task> --step "..." --iter N
   --cap <sane> --reserve 1` at every breakpoint, `... done` on finish; halt if
   `~/.claude/fleet/<repo>__<task>.stop` appears. Governance: `~/agent-corps/agent-governance.md`.
