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

## Run it

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
