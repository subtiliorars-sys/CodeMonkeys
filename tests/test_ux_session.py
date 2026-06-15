"""Tests for Wave-3 UX/session (W9 transcript export, W10 per-session budget).

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


@pytest.fixture
def as_user():
    server.app.dependency_overrides[server.verify_user] = lambda: "u"
    yield
    server.app.dependency_overrides.pop(server.verify_user, None)


# ---- W10 per-session budget --------------------------------------------------

def test_clamp_budget_rules():
    assert server._clamp_budget(None) is None
    assert server._clamp_budget(0) is None            # non-positive ignored
    assert server._clamp_budget(-5) is None
    assert server._clamp_budget("nan") is None
    assert server._clamp_budget(2.5) == 2.5
    # capped at the ceiling
    assert server._clamp_budget(10_000) == server.SESSION_BUDGET_MAX_USD


def test_session_budget_falls_back_to_global():
    s = server.new_session(title="a", username="u")            # no override
    assert server.session_budget(s) == server.SESSION_BUDGET_USD
    del server.SESSIONS[s["id"]]


def test_session_budget_uses_override():
    s = server.new_session(title="b", budget_usd=3.0, username="u")
    assert server.session_budget(s) == 3.0
    del server.SESSIONS[s["id"]]


def test_create_endpoint_accepts_budget(as_user):
    r = client.post("/api/sessions", json={"title": "c", "budget_usd": 4.0})
    assert r.status_code == 200
    sid = r.json()["id"]
    assert r.json()["budget_usd"] == 4.0
    assert server.session_budget(server.SESSIONS[sid]) == 4.0
    del server.SESSIONS[sid]


def test_create_endpoint_rejects_bad_budget_to_global(as_user):
    r = client.post("/api/sessions", json={"title": "d", "budget_usd": -1})
    sid = r.json()["id"]
    assert r.json()["budget_usd"] == server.SESSION_BUDGET_USD
    del server.SESSIONS[sid]


# ---- W9 transcript export ----------------------------------------------------

def _seed_session():
    s = server.new_session(title="export-me", repo="acme", username="u")
    s["history"] = [
        {"role": "user", "text": "fix the bug"},
        {"role": "assistant", "text": "looking",
         "tool_calls": [{"id": "t1", "name": "read_file", "args": {"path": "a.py"}}]},
        {"role": "tool", "tool_call_id": "t1", "name": "read_file", "content": "x = 1"},
    ]
    s["spent_usd"] = 0.05
    return s


def test_export_markdown(as_user):
    s = _seed_session()
    try:
        r = client.get(f"/api/sessions/{s['id']}/export")
        assert r.status_code == 200
        assert "text/markdown" in r.headers["content-type"]
        assert "attachment" in r.headers["content-disposition"]
        body = r.text
        assert "# export-me" in body
        assert "fix the bug" in body and "read_file" in body and "x = 1" in body
    finally:
        del server.SESSIONS[s["id"]]


def test_export_json(as_user):
    s = _seed_session()
    try:
        r = client.get(f"/api/sessions/{s['id']}/export?format=json")
        assert r.status_code == 200
        body = r.json()
        assert body["id"] == s["id"] and body["title"] == "export-me"
        assert len(body["history"]) == 3
        assert body["budget_usd"] == server.SESSION_BUDGET_USD
    finally:
        del server.SESSIONS[s["id"]]


def test_export_unknown_session_404(as_user):
    assert client.get("/api/sessions/nope/export").status_code == 404


def test_export_requires_auth():
    assert client.get("/api/sessions/x/export").status_code in (401, 403)
