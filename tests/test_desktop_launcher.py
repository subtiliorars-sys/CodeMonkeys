"""Smoke tests for the desktop launcher helpers (no WebView required)."""

from __future__ import annotations

import os
import socket
from pathlib import Path

from desktop.launcher import _configure_env, _default_data_dir, _free_port, _repo_root


def test_repo_root_points_at_server():
    root = _repo_root()
    assert (root / "server.py").is_file()
    assert (root / "static" / "forge").is_dir()


def test_free_port_binds_loopback():
    port = _free_port(18765)
    assert 18765 <= port < 18805 or port > 0
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", port))


def test_configure_env_sets_desktop_defaults(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("CM_DESKTOP", raising=False)
    monkeypatch.delenv("DATA_DIR", raising=False)
    monkeypatch.delenv("WORKSPACE_DIR", raising=False)
    monkeypatch.delenv("HOST", raising=False)
    data = tmp_path / "data"
    _configure_env(data, 8765)
    assert os.environ["CM_DESKTOP"] == "1"
    assert os.environ["DATA_DIR"] == str(data)
    assert os.environ["WORKSPACE_DIR"] == str(data / "workspace")
    assert os.environ["HOST"] == "127.0.0.1"
    assert os.environ["PORT"] == "8765"
    assert data.is_dir()
    assert (data / "workspace").is_dir()


def test_default_data_dir_is_under_appdata_or_xdg(monkeypatch):
    if os.name == "nt":
        monkeypatch.setenv("APPDATA", r"C:\Users\test\AppData\Roaming")
        assert _default_data_dir() == Path(r"C:\Users\test\AppData\Roaming\codemonkeys\data")
    else:
        monkeypatch.setenv("XDG_CONFIG_HOME", "/tmp/xdg")
        assert _default_data_dir() == Path("/tmp/xdg/codemonkeys/data")
