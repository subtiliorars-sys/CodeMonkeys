# CodeMonkeys — Operator Runbook (deploy / rollback / incident)

Scope: this file is the **day-to-day operator's checklist** — deploy a change,
undo one, and triage an incident fast. For the deep step-by-step fixes behind
each incident type (lost master key, lockout, decrypt-failed banners, backup
drills), see **`docs/RECOVERY.md`** — this file routes you there, it doesn't
duplicate it.

App: **`codemonkeys`** on Fly (`fly.toml`) · dashboard:
https://fly.io/apps/codemonkeys · data volume **`cm_data`** at **`/data`**
(survives every deploy/restart/rollback below).

---

## 1. Deploy

Deploys are **manual** — nothing goes live until you run this.

```powershell
./scripts/deploy.ps1
```

What it does (`scripts/deploy.ps1`): wraps
`fly deploy --app codemonkeys --remote-only` and always passes a fresh
`--build-arg CACHEBUST=<unix-timestamp>`, which the `Dockerfile` uses right
before `COPY static/ static/` to force that layer to rebuild every time
(Depot's remote builder was observed serving a stale `static/` layer
otherwise — see PR #186).

Steps:
1. `git status` — confirm you're deploying what you think you are (no stray
   uncommitted changes, correct branch/commit).
2. `./scripts/deploy.ps1` — remote Depot build, ~90s. The 30s default shell
   timeout can kill a foreground run before it finishes; detach it if needed:
   `Start-Process pwsh -ArgumentList '-File scripts/deploy.ps1' -WindowStyle Minimized`.
3. Watch it land: `fly logs -a codemonkeys` (or dashboard → Monitoring), and
   confirm `/healthz` returns `200` — `curl https://codemonkeys.fly.dev/healthz`.
4. Check `/readyz` too if the deploy touches anything `readyz` depends on
   (`data_writable`, `crypto_ok`, `disk_space_ok` — see `docs/SETUP.md` §4b):
   `curl https://codemonkeys.fly.dev/readyz`.

**"Migrate" steps:** CodeMonkeys has no separate DB-migration step — it's
JSON-on-volume (`/data/*.json`, `*.jsonl`), and every schema change the app
makes is a **self-migrating read path** baked into `server.py` (e.g. plaintext
→ Fernet-encrypted config migrates automatically on first read once
`CM_MASTER_KEY`/`data/master.key` is available — see `docs/RECOVERY.md`
Scenario F). There is nothing extra to run before or after a deploy for this.

---

## 2. Rollback

Your data on `/data` is **untouched by deploys or rollbacks** — rolling back
only changes which container image is running.

**Dashboard (easiest):** app `codemonkeys` → **Monitoring / Releases** → find
the last good version → **Rollback** button.

**CLI:**
```powershell
fly releases -a codemonkeys                 # list versions + image refs
fly deploy -a codemonkeys --image <previous-version-image-ref>
```

**Simulated rollback (dry run, safe to do any time, changes nothing):**
```powershell
fly releases -a codemonkeys --json | ConvertFrom-Json | Select-Object -First 5 Version,Status,ImageRef
```
(field names verified live against `codemonkeys` on 2026-07-20 — `fly releases
--json` returns `Version`, `Status`, `ImageRef`, capitalized, among other fields.)
This shows exactly which image a real rollback would deploy without touching
the live app — use it to confirm you know the target *before* you run the
real `fly deploy --image ...` command above.

> An actual rollback (and an actual deploy) both push to the live production
> app. This runbook documents the exact commands; running them for real
> against `codemonkeys` should be a deliberate, confirmed action by whoever is
> operating it, not something automated unattended.

After any rollback: re-check `/healthz` + `/readyz`, and re-run the M-8
backup drill if the rollback followed an incident (`docs/RECOVERY.md`
Scenario G) to confirm the volume is still in a known-good state.

---

## 3. Incident triage checklist

Work top to bottom — first match wins, then jump to the linked
`docs/RECOVERY.md` scenario for the exact fix.

| Symptom | Likely cause | Go to |
|---|---|---|
| App down / restarting after a deploy; logs show `cannot decrypt session_secret.key` or `CM_MASTER_KEY is unset` | Master key wrong/missing/changed | RECOVERY.md **Scenario A** |
| Someone can't log in — lost 2FA device or forgot PIN | Account lockout | RECOVERY.md **Scenario B** |
| App worked before the last deploy, now misbehaves, root cause unclear | Bad deploy | **§2 Rollback** above, then RECOVERY.md **Scenario C** |
| A feature (webhook/notify/fleet-status/terminal) is misbehaving and you need it off *now* | Runaway/broken optional feature | RECOVERY.md **Scenario D** |
| Yellow banner: "could not decrypt saved model API keys" | `CM_MASTER_KEY` rotated/removed since keys were saved | RECOVERY.md **Scenario E** |
| Banner says model keys are unencrypted (old deploys only) | Pre-Scenario-F deploy, needs one restart to migrate | RECOVERY.md **Scenario F** |
| You need to confirm the volume/backups actually restore | Routine or post-incident verification | RECOVERY.md **Scenario G** (M-8 backup drill) |
| None of the above / app is up but behaving wrong in a way not covered here | Unknown | Check `fly logs -a codemonkeys` first, then `SECURITY.md` + `docs/STATE.md` "OPEN — Needs attention" for known issues before treating it as new |

**Fast health check, any time:**
```powershell
curl https://codemonkeys.fly.dev/healthz   # liveness - always 200 while up
curl https://codemonkeys.fly.dev/readyz    # readiness - 503 if a dependency check fails
```

---

## Where everything lives

See `docs/RECOVERY.md` "Where everything lives" for the full data-volume
layout and script list (`scripts/reset_access.py`, `scripts/backup_drill.py`,
`scripts/verify_audit_chain.py`) — not duplicated here.
