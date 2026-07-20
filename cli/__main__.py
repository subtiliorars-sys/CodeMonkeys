"""codemonkeys CLI — a terminal REPL over the CodeMonkeys session API.

    python -m cli                    # connect to last-used server, resume/pick a session
    python -m cli --server URL       # connect to a specific server
    python -m cli --new "title"      # start a fresh session
    python -m cli --logout           # forget the saved token
"""
from __future__ import annotations

import argparse
import os
import sys

from rich.console import Console
from rich.prompt import Prompt

from . import config
from .client import ApiError, Client
from .repl import Repl

# Owner report (2026-07-20): a fresh `monkey` install with no prior config and
# no --server flag tried localhost:8000, which nobody's running, and crashed
# with a raw connection traceback. install.sh/install.ps1 already default
# CM_SERVER to codemonkeys.fly.dev — match that here so the common "download
# and just run monkey" path works out of the box. Local dev / self-host still
# override via $CM_SERVER or --server.
DEFAULT_SERVER = os.environ.get("CM_SERVER", "https://codemonkeys.fly.dev")


def _login(console: Console, client: Client) -> None:
    console.print("[bold]log in[/bold]")
    username = Prompt.ask("username")
    mfa_code = Prompt.ask("MFA code", default="")
    data = client.login(username, mfa_code)
    if data.get("must_reset"):
        console.print("[yellow]account needs first-time setup — finish that in the web UI, then re-run[/yellow]")
        sys.exit(1)
    console.print(f"[green]logged in as {data['username']} ({data['role']})[/green]")


def _pick_or_create_session(console: Console, client: Client, new_title: str | None) -> str:
    if new_title is not None:
        s = client.create_session(title=new_title)
        console.print(f"[green]created session {s['id']}[/green]")
        return s["id"]
    sessions = client.list_sessions()
    if not sessions:
        s = client.create_session(title="")
        console.print(f"[green]created session {s['id']}[/green]")
        return s["id"]
    console.print("[bold]sessions:[/bold]")
    for i, s in enumerate(sessions[:20]):
        console.print(f"  {i}: [{s['status']}] {s['title'] or '(untitled)'} — {s['id']}")
    console.print(f"  n: new session")
    choice = Prompt.ask("pick", default="0")
    if choice.strip().lower() == "n":
        s = client.create_session(title="")
        console.print(f"[green]created session {s['id']}[/green]")
        return s["id"]
    try:
        return sessions[int(choice)]["id"]
    except (ValueError, IndexError):
        console.print("[red]invalid choice[/red]")
        sys.exit(1)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="codemonkeys")
    parser.add_argument("--server", help="server base URL (default: last used, or " + DEFAULT_SERVER)
    parser.add_argument("--new", metavar="TITLE", nargs="?", const="", default=None, help="start a new session")
    parser.add_argument("--logout", action="store_true", help="forget the saved token and exit")
    args = parser.parse_args(argv)

    console = Console()
    cfg = config.load()

    if args.logout:
        config.save({**cfg, "token": None})
        console.print("logged out")
        return 0

    server = args.server or cfg.get("server") or DEFAULT_SERVER
    client = Client(server, token=cfg.get("token"))

    if client.token:
        try:
            client._request("GET", "/api/sessions")
        except ApiError:
            client.token = None

    if not client.token:
        try:
            _login(console, client)
        except ApiError as exc:
            console.print(f"[red]login failed: {exc}[/red]")
            return 1
        config.save({**cfg, "server": server, "token": client.token})
    elif server != cfg.get("server"):
        config.save({**cfg, "server": server})

    try:
        sid = _pick_or_create_session(console, client, args.new)
    except ApiError as exc:
        console.print(f"[red]{exc}[/red]")
        return 1

    Repl(client, sid, console).run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
