# Handoff — session wrap (2026-06-13)

## Pushed to GitHub

| Repo | Branch | Commit | What shipped |
|------|--------|--------|--------------|
| **CodeMonkeys** | `work/frontend-polish` | `b152635` | Vertex GCP provider + burn scripts, Cursor Desk, Code Gremlins, auto `data/master.key` encryption, workbench/fleet-store UI, broken `.claude` submodule cleanup |
| **MeniscusMaximus** | `work/cairn-guided-experiences` | `be0c10d` | Cursor Desk (MM-only, brand-safe) in console |
| **PixelSports** | `work/store-launch-v0.1` | `fdeffd6` | Freak Franchise GDDs, fleet demos (R-06/R-07), Vertex-generated docs |
| **CodeMonkeys** (`~/` repo origin) | `master` | `9055162` | Portable kit at `projects/shared/vertex-credits/` + this handoff file |

PR links (create if needed):
- https://github.com/subtiliorars-sys/CodeMonkeys/compare/main...work/frontend-polish
- https://github.com/subtiliorars-sys/MeniscusMaximus/compare/master...work/cairn-guided-experiences
- https://github.com/subtiliorars-sys/PixelSports/compare/main...work/store-launch-v0.1

## After pull on any machine

1. **CodeMonkeys:** restart server once → `data/master.key` auto-created, keys encrypt at rest, yellow banner gone.
2. **Vertex credits:** `bash projects/shared/vertex-credits/setup.sh` (or `.ps1` on Windows).
3. **GCP burn:** `python3 projects/claude/CodeMonkeys/scripts/vertex_burn.py` (uses ADC, not Cursor billing).

## Local stashes (not pushed — pop when ready)

- `CodeMonkeys` `stash@{0}`: fleet-automation WIP, agent-governance edits, test_session_resume
- `MeniscusMaximus` `stash@{0}`: Cairn/dog UI WIP across home.js, MENISCUS_USAGE, etc.
- `PixelSports` `stash@{0}`: store-launch volleyball/broadside WIP not in franchise commit

## Still local / not committed

- CodeMonkeys `tools/fleet-automation/` (full tree — in stash)
- MeniscusMaximus: large GDD + fleet-demo batch (Broadside, Pool hub, etc.) — separate from Cursor Desk
- PixelSports: volleyball pixel-art docs, release zips, other store-launch edits — in stash
- Fly secrets / `.env` / `data/` volumes — never in git

## Deploy gates (owner)

- **MeniscusMaximus:** merge `work/cairn-guided-experiences` → `master` before Fly deploy (master auto-deploys).
- **CodeMonkeys:** merge `work/frontend-polish` → `main` when ready for prod.
- **PixelSports:** franchise demos live on branch; merge when fleet Pages workflow should pick them up.

## Session features recap

- **Cursor Desk:** browser panel, screenshot→composer, settings hub (CM + MM).
- **Code Gremlins:** deployable roast/red-team agent + UI in CM Settings.
- **Vertex:** `vertex-gemini` provider + portable credits kit; Cursor chat still uses Cursor credits.
- **Encryption:** automatic at-rest API key encryption via `data/master.key`.
