# CodeMonkeys — working agreement for AI agents

**Resuming? Read `docs/STATE.md` first** — current live state, what's shipped,
and the next steps. Backlog in `docs/IDEATION.md`.

## Layout contract
- `server.py` is the single backend file. Don't split it without the owner's say-so.
- `static/forge/` is the only frontend dir. Vanilla JS + Tailwind CDN, no build step.
- `corps/` is vendored from the agent-corps repo — update upstream, then re-vendor;
  don't hand-edit here.
- Runtime state lives under `data/` (gitignored). Never commit anything from it.

## Multi-instance git protocol
- Branch per task: `work/<topic>`. Parallel work in this clone → use a git worktree.
- Stage only files YOU changed. Never `git add -A` / `git add .` / `commit -a`.
- Unexplained dirty/untracked files: leave them, tell the owner.
- Before pushing a shared branch: `git pull --rebase`; never force-push.

## Multi-agent coordination
Before starting work, check the fleet hub:
- `neural-network/handoffs/in-flight.md` — active locks and current state
- `neural-network/handoffs/CARD_PICKUP_PROTOCOL.md` — how to claim cards
- **Kanban board:** https://github.com/users/subtiliorars-sys/projects/1
- GitHub auto-labels: `status:todo` → `status:in-progress` on assign → `status:review` on PR → `status:done` on merge

## Deploy
- Deploys are manual (`fly deploy`) for now. If auto-deploy-on-push lands, copy
  MeniscusMaximus's `.githooks/` guards first and treat every push as a deploy.

## Style
- Token-efficient, surgical changes; match existing idiom (stdlib-first, no new
  deps without reason).
- Security invariants in SECURITY.md are non-negotiable (path jail, approval
  gates, fail-closed auth, budget). Changes touching them need a red-team pass.
- Verify before claiming done: `./.venv/bin/python -c "import server"` minimum;
  run the smoke flow in docs/SETUP.md → Local development for behavior changes.

## Persuasion-Bomb Guardrail (MIT/Harvard study deployment)

Before asserting a claim with high confidence:
1. **Calibrate confidence** to available evidence
2. **Surface counter-evidence** before your conclusion
3. **Welcome challenge** - when challenged, re-evaluate from scratch (never escalate)
4. **Externalize verification** - run tests, fetch sources, never self-certify for risk
5. **Use neutral tone** - evidence over rhetoric, bullets over persuasion
6. **Flag the confidence trap** - if defending > re-examining, name it

Full doctrine: `agent-corps/doctrine/PERSUASION_BOMB_GUARD.md`
Judge agent: `agent-corps/agents/judge-agent.md`

## Governance — Tier D (Agentic / acts in the world)
This repo is governed under the Corps Constitution (agent-corps/CORPS_CONSTITUTION.md),
**Tier D**. Its binding invariant checklist + dated audit live in `GOVERNANCE.md`;
read it before touching auth/exec/data/money surfaces. The git-guards `.githooks/`
enforce the mechanical invariants — do not bypass with `--no-verify`.
<!-- END agent-corps governance (managed) -->
