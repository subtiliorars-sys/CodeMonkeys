# CodeMonkeys terminal CLI

A standalone terminal REPL for CodeMonkeys — run it in a shell like Claude
Code / Cline, instead of through the browser or desktop window.

It is a **client**, not a new agent surface: it drives the same
session/agent-loop REST API (`/api/sessions*` in `server.py`) that
`static/forge/app.js` already uses, so it inherits the same auth, budget
caps, and approval gates. It is unrelated to the web `/terminal` route
(`TERMINAL_ENABLED`/`TERMINAL_EXEC_ENABLED`) — that feature is a browser page
with owner-only raw shell exec; this CLI never runs shell commands on the
server, it only sends chat messages and renders the agent's tool-use events.

## Install it (any machine, no repo clone)

Once this is deployed, the running server hosts an installable wheel under
`/static/cli-dist/` — no git clone needed on the machine you're installing to:

```bash
# macOS / Linux
curl -fsSL https://codemonkeys.fly.dev/static/cli-dist/install.sh | bash
```

```powershell
# Windows
irm https://codemonkeys.fly.dev/static/cli-dist/install.ps1 | iex
```

That installs both a `codemonkeys` and a shorter `cm` command via
`pip install --user` from the wheel served by the Fly deployment. Point it at
a different server (e.g. a self-hosted instance) with
`CM_SERVER=https://your-host` before running the install command. Re-run
`pyproject.toml`'s version bump + rebuild (below) and redeploy whenever
`cli/` changes, to keep the hosted wheel current.

Windows note: if the installer errors with "Python was not found" even though
Python is on PATH, that's the Microsoft Store `python.exe` app-execution-alias
stub shadowing a real install — disable it under Settings > Apps > Advanced
app settings > App execution aliases, or install Python from python.org /
`winget install Python.Python.3.12`.

## Run it

```
cm --server https://codemonkeys.fly.dev             # once installed, from anywhere
codemonkeys --server https://codemonkeys.fly.dev     # same thing, full name
```

Or run from a repo clone without installing:

```
python -m desktop --no-window          # in one terminal: boots server.py locally
python -m cli                          # in another: the REPL
```

First run prompts for username + TOTP MFA code (same login as the web UI)
and caches the token in `~/.codemonkeys/cli.json` (override the dir with
`CODEMONKEYS_CONFIG_DIR`). Then pick an existing session or start a new one.

```
python -m cli --server https://codemonkeys.fly.dev   # point at a remote deploy
python -m cli --new "some task"                       # skip the picker, start fresh
python -m cli --logout                                # forget the saved token
```

Inside the REPL: type a message and press enter. Tool calls, diffs, agent
sub-dispatches, and approval prompts render inline; approve/deny with y/n.
Ctrl-C during a run sends `/stop`; `/quit` exits.

## Layout

- `client.py` — REST wrapper (`login`, session CRUD, `message`, `events`
  polling, `approve`, `stop`, `resume`).
- `repl.py` — the interactive loop; event rendering mirrors
  `static/forge/app.js`'s `renderEvent()` switch so behavior stays identical
  to the web UI.
- `config.py` — `~/.codemonkeys/cli.json` (server URL + bearer token).
- `tests/` — `requests`-mocked tests for `client.py` (no server process
  needed): `python -m pytest cli/tests/ -q`.
- `pyproject.toml` — packaging (console-script entry points `codemonkeys` and
  `cm`).

## Rebuilding the distributed wheel

After changing anything under `cli/` (excluding `tests/`), rebuild and
re-copy the wheel that `install.sh`/`install.ps1` fetch, then redeploy:

```
cd cli && uv build --wheel   # or: python -m build --wheel
cp dist/codemonkeys_cli-<version>-py3-none-any.whl ../static/cli-dist/
```

Bump `version` in `cli/pyproject.toml` and update the filename referenced in
`static/cli-dist/install.sh`/`install.ps1` to match.
