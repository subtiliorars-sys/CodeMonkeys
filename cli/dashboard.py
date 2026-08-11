"""The landing screen: a CodeMonkeys-branded session dashboard.

Mirrors the shape of Claude Code's own multi-session picker (header with
mascot/version/model/cwd, awaiting-input/working/completed counts, a
"Working" list and a "Completed" list of sessions each summarized to one
line with elapsed time) -- restyled with the CodeMonkeys mascot and palette
instead of Anthropic's.
"""
from __future__ import annotations

import time

from rich.console import Console
from rich.table import Table
from rich.text import Text

from . import __version__

# A small pixel-art monkey, banana-yellow on jungle green -- the CodeMonkeys
# answer to Claude Code's clay-orange robot mark.
MONKEY_MASCOT = [
    '  .-"""-.  ',
    ' /  o o  \\ ',
    '|    \u03c9    |',
    ' \\  ---  / ',
    "  '-...-'  ",
]

MONKEY_COLOR = "yellow"
ACCENT_COLOR = "green"

RUNNING_STATUSES = {"running", "working", "streaming"}
AWAITING_STATUSES = {"interrupted", "approval", "awaiting_input"}


def _elapsed(created_epoch: float) -> str:
    secs = max(0, int(time.time() - created_epoch))
    if secs < 60:
        return f"{secs}s"
    mins = secs // 60
    if mins < 60:
        return f"{mins}m"
    hours = mins // 60
    if hours < 24:
        return f"{hours}h"
    return f"{hours // 24}d"


def _one_liner(session: dict) -> str:
    """Best available single-line summary for a session row."""
    title = session.get("title") or "(untitled)"
    repo = session.get("repo")
    return f"{title} -- {repo}" if repo else title


def _bucket(session: dict) -> str:
    status = session.get("status", "idle")
    if status in RUNNING_STATUSES:
        return "working"
    if status in AWAITING_STATUSES:
        return "awaiting"
    return "completed"


def render_dashboard(console: Console, sessions: list[dict], server: str, username: str, model: str = "") -> None:
    working = [s for s in sessions if _bucket(s) == "working"]
    awaiting = [s for s in sessions if _bucket(s) == "awaiting"]
    completed = [s for s in sessions if _bucket(s) == "completed"]

    header = Table.grid(padding=(0, 2))
    header.add_column()
    header.add_column()
    mascot_text = Text("\n".join(MONKEY_MASCOT), style=MONKEY_COLOR)
    info = Text()
    info.append(f"CodeMonkeys CLI v{__version__}\n", style="bold")
    info.append(f"{model or 'multi-model'} \u00b7 {username} \u00b7 {server}\n", style="dim")
    info.append(
        f"{len(awaiting)} awaiting input \u00b7 {len(working)} working \u00b7 {len(completed)} completed",
        style="dim",
    )
    header.add_row(mascot_text, info)
    console.print(header)
    console.print()

    def _section(label: str, rows: list[dict], color: str) -> None:
        if not rows:
            return
        console.print(f"[bold {color}]{label}[/bold {color}]")
        t = Table.grid(padding=(0, 2))
        t.add_column(style="bold")
        t.add_column(overflow="ellipsis", max_width=60)
        t.add_column(justify="right", style="dim")
        for s in rows:
            marker = "\U0001f412" if color == ACCENT_COLOR else "*"
            t.add_row(f"{marker} {s.get('title') or '(untitled)'}", _one_liner(s), _elapsed(s.get("created", time.time())))
        console.print(t)
        console.print()

    _section("Working", working, ACCENT_COLOR)
    _section("Awaiting input", awaiting, "yellow")
    _section("Completed", completed, "dim white")

    if not sessions:
        console.print("[dim](no sessions yet -- describe a task below to start one)[/dim]")
        console.print()
