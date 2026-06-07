"""Wave 4 #6 — fractal/tiered memory phase 1: deterministic theme-token digest.

Run: ./.venv/bin/python -m pytest tests/ -q
"""
import os
import sys
import tempfile

os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(prefix="cm_test_"))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import server  # noqa: E402

client = TestClient(server.app)


def _history():
    return [
        {"role": "user", "text": "fix it"},
        {"role": "assistant", "text": "ok", "tool_calls": [
            {"id": "1", "name": "read_file", "args": {"path": "a.py"}},
            {"id": "2", "name": "bash", "args": {"command": "pytest -q"}}]},
        {"role": "tool", "tool_call_id": "1", "name": "read_file", "content": "x=1"},
        {"role": "tool", "tool_call_id": "2", "name": "bash", "content": "ERROR: 1 failed"},
        {"role": "assistant", "text": "patching", "tool_calls": [
            {"id": "3", "name": "write_file", "args": {"path": "a.py", "content": "x=2"}},
            {"id": "4", "name": "read_file", "args": {"path": "a.py"}}]},
        {"role": "tool", "tool_call_id": "3", "name": "write_file", "content": "Wrote 3 chars"},
    ]


def test_extract_is_deterministic_and_structured():
    t1 = server._extract_theme_tokens(_history())
    t2 = server._extract_theme_tokens(_history())
    assert t1 == t2                                   # deterministic
    assert t1["user_turns"] == 1 and t1["assistant_turns"] == 2
    assert t1["files_written"] == ["a.py"]
    assert t1["files_read"] == ["a.py"]
    assert t1["tools_used"]["read_file"] == 2
    assert "pytest -q" in t1["commands"]
    assert any("1 failed" in e for e in t1["errors"])


def test_empty_history_is_safe():
    t = server._extract_theme_tokens([])
    assert t["user_turns"] == 0 and t["files_written"] == [] and t["tools_used"] == {}
    assert server._extract_theme_tokens(None)["commands"] == []


def test_digest_markdown_renders():
    s = {"title": "demo", "history": _history()}
    md = server._digest_markdown(s)
    assert "# Digest — demo" in md and "a.py" in md and "pytest -q" in md


def test_digest_endpoint_json_and_md():
    s = server.new_session(title="dg")
    s["history"] = _history()
    sid = s["id"]
    server.app.dependency_overrides[server.verify_user] = lambda: "u"
    try:
        j = client.get(f"/api/sessions/{sid}/digest").json()
        assert j["tokens"]["files_written"] == ["a.py"]
        md = client.get(f"/api/sessions/{sid}/digest?format=md")
        assert md.status_code == 200 and "Digest" in md.text
        assert client.get("/api/sessions/nope/digest").status_code == 404
    finally:
        server.app.dependency_overrides.pop(server.verify_user, None)
        del server.SESSIONS[sid]


def test_digest_requires_auth():
    assert client.get("/api/sessions/x/digest").status_code in (401, 403)
