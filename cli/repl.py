"""Interactive terminal REPL over the CodeMonkeys session API.

Event rendering mirrors `static/forge/app.js`'s `renderEvent()` switch so the
CLI stays in semantic lockstep with the web UI rather than re-deriving its
own interpretation of each event type.
"""
from __future__ import annotations

import threading
import time

from prompt_toolkit import PromptSession
from prompt_toolkit.key_binding import KeyBindings
from rich.console import Console
from rich.markup import escape
from rich.prompt import Confirm

from .client import ApiError, Client

POLL_INTERVAL = 0.6


SWITCH_SENTINEL = "\x00SWITCH_SESSION\x00"


def _make_key_bindings() -> KeyBindings:
    """Left-arrow opens the session switcher, but only when the input line is
    empty — otherwise it's needed for normal cursor movement while editing."""
    kb = KeyBindings()

    @kb.add("left")
    def _(event):
        buf = event.app.current_buffer
        if buf.cursor_position == 0 and not buf.text:
            event.app.exit(result=SWITCH_SENTINEL)
        else:
            buf.cursor_left()

    return kb


class Repl:
    def __init__(self, client: Client, sid: str, console: Console | None = None):
        self.client = client
        self.sid = sid
        self.console = console or Console()
        self._after = -1
        self._stream_buf = ""
        self._stream_prefix = ""
        self._streaming = False
        self._stop_poll = threading.Event()
        self._prompt_session = PromptSession(key_bindings=_make_key_bindings())

    def _print_stream_flush(self):
        if self._streaming:
            self.console.print()
            self._streaming = False
            self._stream_buf = ""

    def _render_event(self, e: dict) -> None:
        t = e.get("type")
        if t == "user":
            self._print_stream_flush()
            self.console.print(f"[bold cyan]you:[/bold cyan] {escape(e.get('text') or '')}")
        elif t == "text_delta":
            if not self._streaming:
                self._streaming = True
                self._stream_prefix = f"[{e['agent']}] " if e.get("agent") else ""
                self._stream_buf = ""
                self.console.print(f"[bold green]assistant:[/bold green] ", end="")
                if self._stream_prefix:
                    self.console.print(f"[dim]{escape(self._stream_prefix)}[/dim]", end="")
            self._stream_buf += str(e.get("text") or "")
            self.console.print(escape(str(e.get("text") or "")), end="")
        elif t == "text":
            if not self._streaming:
                self.console.print(f"[bold green]assistant:[/bold green] {escape(e.get('text') or '')}")
            self._print_stream_flush()
        elif t == "tool":
            self._print_stream_flush()
            self.console.print(f"[yellow]⚙ {escape(e.get('name') or '')}[/yellow] [dim]{escape(e.get('detail') or '')}[/dim]")
        elif t == "tool_result":
            self._print_stream_flush()
            mark = "[green]ok[/green]" if e.get("ok") else "[red]FAIL[/red]"
            self.console.print(f"  ↳ {mark} [dim]{escape(e.get('detail') or '')}[/dim]")
            if e.get("diff"):
                for line in e["diff"].splitlines():
                    if line.startswith("+") and not line.startswith("+++"):
                        self.console.print(f"[green]{escape(line)}[/green]")
                    elif line.startswith("-") and not line.startswith("---"):
                        self.console.print(f"[red]{escape(line)}[/red]")
                    elif line.startswith("@@"):
                        self.console.print(f"[cyan]{escape(line)}[/cyan]")
                    else:
                        self.console.print(escape(line))
        elif t == "lint":
            self._print_stream_flush()
            style = "dim" if e.get("ok") else "yellow"
            self.console.print(f"[{style}]lint {escape(e.get('linter') or '')} · {escape(e.get('path') or '')} {escape(e.get('detail') or '')}[/{style}]")
        elif t == "agent_start":
            self._print_stream_flush()
            self.console.print(f"[magenta]\U0001f412 deployed {escape(e.get('agent') or '')}[/magenta] [dim][{escape(e.get('tier') or '')} · {escape(e.get('model') or '')}][/dim] — {escape(e.get('task') or '')}")
        elif t == "agent_end":
            self._print_stream_flush()
            self.console.print(f"[dim]\U0001f412 {escape(e.get('agent') or '')} reported back[/dim]")
        elif t == "cost":
            self._print_stream_flush()
            self.console.print(f"[dim]{escape(e.get('model') or '')} · {e.get('in_tokens')}→{e.get('out_tokens')} tok · ${e.get('usd', 0):.4f}[/dim]")
        elif t == "approval":
            self._print_stream_flush()
            self.console.print(f"[bold yellow]⚠ APPROVAL REQUIRED[/bold yellow]")
            self.console.print(f"  {escape(e.get('command') or '')}")
            ok = Confirm.ask("  Approve?", default=False)
            try:
                self.client.approve(self.sid, e["approval_id"], ok)
            except ApiError as exc:
                self.console.print(f"[red]approve failed: {escape(str(exc))}[/red]")
        elif t == "approval_result":
            self._print_stream_flush()
            self.console.print("[green]✓ approved[/green]" if e.get("approved") else "[red]✗ denied[/red]")
        elif t == "error":
            self._print_stream_flush()
            self.console.print(f"[bold red]error:[/bold red] {escape(e.get('message') or '')}")
        elif t == "provider_wait":
            self.console.print(f"[dim]waiting on provider: {escape(e.get('reason') or '')}[/dim]")
        elif t == "done":
            self._print_stream_flush()
            self.console.print("[dim]— done —[/dim]")

    def _drain_events(self) -> str:
        """Fetch and render events since last seen; returns the session status."""
        data = self.client.events(self.sid, after=self._after)
        for e in data.get("events", []):
            self._render_event(e)
        self._after = data.get("next", self._after)
        return data.get("status", "idle")

    def wait_for_turn(self) -> None:
        """Poll until the session returns to idle/interrupted, rendering as we go."""
        with self.console.status("[dim]thinking...[/dim]", spinner="dots") as status:
            while True:
                s = self._drain_events()
                if s in ("idle", "interrupted"):
                    return
                time.sleep(POLL_INTERVAL)

    def _switch_session(self) -> None:
        """Left-arrow was pressed on an empty line — list all sessions (what's
        running, what's idle) and let the user jump into a different one
        without restarting the process."""
        try:
            sessions = self.client.list_sessions()
        except ApiError as exc:
            self.console.print(f"[red]couldn't list sessions: {escape(str(exc))}[/red]")
            return
        if not sessions:
            self.console.print("[dim](no other sessions)[/dim]")
            return
        self.console.print("\n[bold]sessions[/bold] [dim](left-arrow again to cancel)[/dim]")
        for i, s in enumerate(sessions[:20]):
            marker = "*" if s["id"] == self.sid else " "
            self.console.print(f" {marker}{i}: [{s['status']}] {s['title'] or '(untitled)'} — {s['id']}")
        try:
            choice = self._prompt_session.prompt("switch to > ")
        except (EOFError, KeyboardInterrupt):
            return
        if not choice.strip() or choice == SWITCH_SENTINEL:
            return
        try:
            target = sessions[int(choice)]["id"]
        except (ValueError, IndexError):
            self.console.print("[red]invalid choice[/red]")
            return
        if target == self.sid:
            return
        self.sid = target
        self._after = -1
        self.console.print(f"[green]switched to session {self.sid}[/green]")
        self._drain_events()

    def run(self) -> None:
        self.console.print(
            f"[bold]session {self.sid}[/bold] — type a message, left-arrow (on an "
            "empty line) to switch sessions, Ctrl-C to stop a run, /quit to exit\n"
        )
        while True:
            try:
                text = self._prompt_session.prompt([("class:prompt", "> ")])
            except (EOFError, KeyboardInterrupt):
                self.console.print()
                break
            if text == SWITCH_SENTINEL:
                self._switch_session()
                continue
            if not text.strip():
                continue
            if text.strip() in ("/quit", "/exit"):
                break
            try:
                self.client.send_message(self.sid, text)
            except ApiError as exc:
                self.console.print(f"[red]send failed: {escape(str(exc))}[/red]")
                continue
            try:
                self.wait_for_turn()
            except KeyboardInterrupt:
                self.console.print("\n[yellow]stopping...[/yellow]")
                try:
                    self.client.stop(self.sid)
                except ApiError as exc:
                    self.console.print(f"[red]stop failed: {escape(str(exc))}[/red]")
                self._drain_events()
