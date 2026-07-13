# Forge UI — Maintainer Hygiene Checklist

**Lane:** `forge-streaming` · **Scope:** `static/forge/*` and forge-related docs.  
**Read first:** `docs/STATE.md`, `WAVES.md`, `OFFICE_HOURS.md`.

Use this before editing the Forge console, landing a UI wave, or reviewing an
automation PR that touches streaming or frontend assets.

---

## 1. Path map (`static/forge/`)

| Path | Role |
|------|------|
| `index.html` | Main console shell; links vendored `tailwind.css` |
| `app.js`, `workbench.js` | Session UI, composer, event polling |
| `agents-hub.js` | Agents hub (sessions, automations, personas, rules) |
| `terminal.html`, `terminal.js` | Web terminal (gated OFF by default) |
| `swarm.html`, `swarm.js` | Live swarm view |
| `feedback.js`, `field-report.js`, `three-card-triage.*` | Field Report / triage |
| `push.js`, `pwa.js`, `sw.js`, `manifest.webmanifest` | PWA + push |
| `tailwind.input.css` | Tailwind source directives |
| `tailwind.css` | **Built output** (image build or local `npx`; not hand-edited) |
| `jungle-theme.css` | Theme tokens (CSS variables) |

**Coordination:** Automation waves may touch `server.py` (compaction, catalog, streaming).
UI track stays in `static/forge/*` unless explicitly merged. If an open
`automation/wave-*` PR exists, finish or pause before overlapping server changes.

---

## 2. Vendored Tailwind build

Phase 2 is live: runtime CDN is gone; `index.html` links `/static/forge/tailwind.css`.
The dev host has **no Node** — CI and the Docker image are the verification path.

**Config:** `tailwind.config.js` scans `./static/forge/*.html` and `*.js`.

**Local build (when Node is available):**

```bash
npx --yes tailwindcss@3.4.17 \
  -i static/forge/tailwind.input.css \
  -o static/forge/tailwind.css --minify
```

**CI (`css` job):** same command to `/tmp/tailwind.css`; asserts non-trivial output
and spot-checks `.flex` + `gold` arbitrary-value classes.

**Dockerfile:** runs the identical build at image time into `static/forge/tailwind.css`.

**After CSS changes:** run the build (or rely on CI `css` job). Eyeball Forge at `/`
after deploy — owner confirmed prod render; regressions are owner-visible.

---

## 3. Streaming flags (N5 / CM-W1)

| Env | Default | Effect |
|-----|---------|--------|
| `STREAM_ENABLED` | off (`""`) | When `1` / `true` / `yes`, SSE emits `text_delta` events; forge + terminal render live partial text |

- Default-off preserves pre-N5 behaviour (byte-identical non-stream path).
- Server redacts streamed chunks; errors fall back to non-streaming.
- **Do not flip in production** without owner intent — set via Fly env / secrets policy.

Forge polls session events; no separate frontend flag — behaviour follows server env.

---

## 4. Verify commands

**Full suite (matches CI / office hours):**

```bash
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt pytest
mkdir -p data
DATA_DIR=./data ./.venv/bin/python -c "import server"
DATA_DIR=./data ./.venv/bin/pytest tests/ -q
```

**Focused:**

```bash
DATA_DIR=./data ./.venv/bin/pytest tests/test_streaming.py -q
DATA_DIR=./data ./.venv/bin/pytest tests/test_vendored_tailwind.py -q   # when present
```

**UI spot-check:** Forge at `/` (or `/forge` per `OFFICE_HOURS.md`) — login, composer,
streaming text deltas when `STREAM_ENABLED=1`, mobile drawer ≤767px if touched.

**Import smoke:** `DATA_DIR=./data python -c "import server"` (CI runs this before pytest).

---

## 5. Branch + claim discipline

- Branch per task: `work/<topic>` or `cursor/<topic>-<date>`; never `git add -A`.
- Before multi-file forge edits: `work-check.sh start --area forge-streaming`.
- Claim: `REPO=CodeMonkeys AREA=forge-streaming WHO=<name> BRANCH=<branch> work-claim.sh claim`.
- Deploy is **owner-gated** (`fly deploy`); automation PRs do not deploy.

---

## 6. N-backlog / automation queue status

**As of 2026-07-13:** Safe automation backlog is **exhausted**. `WAVES.md` Active queue
is empty — **do not start blocked automation waves.**

| Category | Status | Next action |
|----------|--------|-------------|
| CM-W1–W7 (N5 streaming, N8 compaction, N12 catalog, lint, triage, session ownership) | ✅ merged | — |
| CM-UI-W1–W3 (Forge parity track) | ✅ done on `work/frontend-polish` | Owner deploy when ready |
| **S5 notify-on-done** | Next buildable wave (per `docs/STATE.md`) | Add to Active queue when lane free |
| OAuth app registration, webhook secrets | **owner-gated** | Owner registers apps + sets Fly secrets |
| Terminal activation (`TERMINAL_ENABLED` + `TERMINAL_EXEC_ENABLED`) | **owner-gated** | Both default OFF → 404 |
| `fly deploy` / prod config | **owner-gated** | Not automation |
| `SECURITY.md` substantive edits | **owner-gated** | Manual merge |
| S6 Layers 2–4 (workspace jail, per-user secrets, shell sandbox) | **owner-gated** | Owner decision |

**Executor rule:** If Active queue is `_(none)_`, document status (this section or
`WAVES.md`) and stop — do not fabricate waves or merge owner-gated work.

See `WAVES.md` § Blocked / owner-gated for the canonical list.
