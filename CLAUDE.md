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
