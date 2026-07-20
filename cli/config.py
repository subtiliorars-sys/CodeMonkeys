"""Local CLI config: server URL + auth token, stored per-user under the home dir."""
from __future__ import annotations

import json
import os
import stat
from pathlib import Path

CONFIG_DIR = Path(os.environ.get("CODEMONKEYS_CONFIG_DIR", Path.home() / ".codemonkeys"))
CONFIG_FILE = CONFIG_DIR / "cli.json"


def load() -> dict:
    if not CONFIG_FILE.exists():
        return {}
    try:
        return json.loads(CONFIG_FILE.read_text("utf-8"))
    except (ValueError, OSError):
        return {}


def save(data: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    # Token is a bearer credential — restrict to the owner on POSIX; best-effort
    # on Windows (ACLs aren't set here, but this avoids a world-readable regression
    # if the file is later synced to a POSIX host).
    try:
        os.chmod(CONFIG_FILE, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass
