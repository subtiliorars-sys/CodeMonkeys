# 🐒 CodeMonkeys

**Your own coding agents. Any model. Any browser. Your server.**

CodeMonkeys is a self-hosted web coding console — a Claude Code-style autonomous
agent you control from any browser (Chromebook included), powered by **any** model
provider via API keys. Built as credit-outage insurance: if one provider runs dry,
switch models in the UI and keep coding.

## Features

- **Agent loop** — read/write/edit/glob/grep/bash tools, jailed to a workspace volume
- **Daystrom agent corps** — 15 specialized subagents (recon, engineering, QA,
  red-team, planning) with military mission-command doctrine, tool allowlists,
  and spawn caps (`corps/`)
- **Any model** — OpenAI-compatible endpoints (Gemini, OpenRouter incl. **$0 free
  models**, DeepSeek, xAI, …) + native Anthropic; add keys at runtime in the UI
- **Cost governor** — providers carry a tier (t0 cheap → t3 strongest); subagents
  route by tier; every call emits a cost ledger event; per-session USD budget halts
  runaways
- **Approval gates** — `git push`, `fly …`, `rm -rf`, `git reset --hard` pause the
  agent until you click APPROVE in the UI. No silent deploys.
- **Auth** — PIN (PBKDF2) + mandatory TOTP; first account becomes Owner, then
  enrollment closes; HMAC session tokens; fail-closed everywhere
- **Voice input** — free, via Chrome's Web Speech API (mic button)
- **File upload** — attach files; they land in the agent's workspace
- **Pixel-art console** — gold-on-black theme + live swarm visualizer
- **No database, no build step** — single-file FastAPI backend, vanilla JS frontend,
  JSON on a volume

## Quickstart

**Windows desktop (recommended on a PC):** see **[docs/DESKTOP.md](docs/DESKTOP.md)**.

```powershell
pip install -r requirements-desktop.txt
python -m desktop          # native window; data in %APPDATA%\codemonkeys
# package:  pwsh scripts/build-windows.ps1
```

Full Fly / Chromebook walkthrough: **[docs/SETUP.md](docs/SETUP.md)**. Short version:

```bash
fly launch --copy-config --no-deploy     # claim an app name
fly volumes create cm_data --size 3
fly secrets set GITHUB_TOKEN=<fine-grained PAT>
fly deploy
# open the app URL → Register (first account = Owner) → scan TOTP QR
# → ⚙ Models & keys → paste a Gemini/OpenRouter/Anthropic key → clone a repo → code
```

Local web (browser against uvicorn):

```bash
python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt
DATA_DIR=./data ./.venv/bin/uvicorn server:app --reload --port 8080
```

**Keys:** paste your own provider keys in the UI (BYOK). Owner can optionally
grant Vertex/GCP credits to invited accounts — that path is the only shared-credit
surface that needs strong auth.
## Repo layout

| Path | What |
|---|---|
| `server.py` | Entire backend: auth, providers, agent loop, corps runtime, sessions, API |
| `static/forge/` | Frontend: console, swarm viz (vanilla JS + vendored Tailwind — see `docs/FORGE_HYGIENE.md`) |
| `desktop/` | Windows desktop shell (pywebview + PyInstaller) — see `docs/DESKTOP.md` |
| `corps/` | Daystrom agent definitions + doctrine (vendored) |
| `scripts/reset_access.py` | Lockout recovery via `fly ssh console` |
| `scripts/build-windows.ps1` | Package `dist/CodeMonkeys/CodeMonkeys.exe` |
| `docs/` | Setup, architecture, desktop, **[docs/README.md](docs/README.md)** index |
| `Dockerfile`, `fly.toml` | Deploy |
## Updating the UI

All UI changes are committed to `main`. The Fly.io deployment **does not auto-deploy** on git push — you must run:

```bash
cd /path/to/CodeMonkeys
fly deploy
```

After running `fly deploy`, hard-refresh your browser (**Ctrl+Shift+R** on Windows/Linux, **Cmd+Shift+R** on Mac) to clear cached assets.

### Keyboard shortcuts (new in jungle redesign)
| Shortcut | Action |
|----------|--------|
| `Ctrl+,` | Open Settings modal |
| `Escape` | Close Settings modal or jungle menu |

## Security

This app **executes code**. Run it as its own Fly app with its own volume — never
co-located with any other app's data. See [SECURITY.md](SECURITY.md).

MIT © 2026
