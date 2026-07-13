# Forge UI — static surface map

**Lane:** `forge-streaming` · **Path:** `static/forge/`  
**Purpose:** Operator-facing CodeMonkeys workbench (streaming, triage, fleet store).

## Entry points

| File | Role |
|------|------|
| `index.html` | Main Forge shell — workbench + nav |
| `terminal.html` | Terminal-style session view |
| `swarm.html` / `swarm_viz.html` | Swarm visualization |
| `audit.html` | Governance audit viewer |

## Core scripts

| Module | Role |
|--------|------|
| `app.js` | Forge bootstrap |
| `workbench.js` | Primary workbench UI |
| `three-card-triage.js` + `.css` | CM-W5 triage flow |
| `feedback.js` | Lint/feedback surfacing |
| `fleet-store.js` | Fleet roster / store integration |
| `field-report.js` | Field report capture |
| `cursor-desk.js` | Cursor desk bridge |
| `agents-hub.js` | Agents hub panel |
| `terminal.js` | Terminal mode |
| `swarm.js` / `swarm-viz.js` | Swarm views |
| `audit.js` | Audit chain UI |
| `pwa.js` / `sw.js` / `manifest.webmanifest` | PWA shell |

## Hygiene rules (executors)

1. **No secrets** in static JS — env via server endpoints only.
2. **Match naming** — new panels get one primary `.js` + optional `.css`; register in `index.html` nav.
3. **Streaming** — UI reads stream state from existing API; do not add second SSE client without brief.
4. **Verify** — `npm run verify` after JS changes; Forge is included in static checks.
5. **Docs** — non-obvious Forge flows get a one-line comment at file top; architecture notes live here.

## Related docs

- `docs/VERTEX_GCP_CREDITS.md` — batch generation jobs
- `WAVES.md` — CM-W* forge streaming waves
- AgentCorps `fleet/kanban/KANBAN_PROTOCOL.md` — executor gates
