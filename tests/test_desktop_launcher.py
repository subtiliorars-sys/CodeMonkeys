"""Smoke tests for the desktop launcher helpers (no WebView required)."""

from __future__ import annotations

import os
import socket
import sys
from pathlib import Path

from desktop.launcher import (
    _configure_env,
    _default_data_dir,
    _ensure_tailwind_css,
    _free_port,
    _repo_root,
)


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


def _fake_root(tmp_path: Path) -> Path:
    forge = tmp_path / "static" / "forge"
    forge.mkdir(parents=True)
    (forge / "tailwind.input.css").write_text("@tailwind base;")
    return tmp_path


def test_ensure_tailwind_css_skips_when_frozen(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    calls = []
    monkeypatch.setattr("desktop.launcher.subprocess.run", lambda *a, **k: calls.append(a))
    _ensure_tailwind_css(_fake_root(tmp_path))
    assert calls == []


def test_ensure_tailwind_css_noop_when_already_built(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    root = _fake_root(tmp_path)
    (root / "static" / "forge" / "tailwind.css").write_text("/* built */")
    calls = []
    monkeypatch.setattr("desktop.launcher.subprocess.run", lambda *a, **k: calls.append(a))
    _ensure_tailwind_css(root)
    assert calls == []


def test_ensure_tailwind_css_warns_without_npx(tmp_path: Path, monkeypatch, capsys):
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    monkeypatch.setattr("desktop.launcher.shutil.which", lambda name: None)
    calls = []
    monkeypatch.setattr("desktop.launcher.subprocess.run", lambda *a, **k: calls.append(a))
    _ensure_tailwind_css(_fake_root(tmp_path))
    assert calls == []
    assert "npx" in capsys.readouterr().err


def test_ensure_tailwind_css_builds_when_missing(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    monkeypatch.setattr("desktop.launcher.shutil.which", lambda name: "/usr/bin/npx")
    root = _fake_root(tmp_path)
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        (root / "static" / "forge" / "tailwind.css").write_text("/* built */")

    monkeypatch.setattr("desktop.launcher.subprocess.run", fake_run)
    _ensure_tailwind_css(root)
    assert captured["cmd"][0] == "/usr/bin/npx"
    assert "tailwindcss@3.4.17" in captured["cmd"]
    assert (root / "static" / "forge" / "tailwind.css").exists()
