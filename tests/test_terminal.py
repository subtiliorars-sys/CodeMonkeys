"""Web terminal (docs/TERMINAL_DESIGN.md) — focus: the fail-closed gate stack
around /terminal and the Owner-only /api/terminal/exec (red-team fixes F1–F5).

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
from conftest import BASH_AVAILABLE  # noqa: E402

client = TestClient(server.app)

# Owner-only exec shells out to `bash -c`; skip end-to-end exec assertions when
# bash isn't functional (e.g. bare Windows host with only the WSL relay shim).
requires_bash = pytest.mark.skipif(
    not BASH_AVAILABLE, reason="bash -c not functional on this host")


@pytest.fixture
def as_owner():
    server.app.dependency_overrides[server.verify_owner] = lambda: "boss"
    yield
    server.app.dependency_overrides.pop(server.verify_owner, None)


@pytest.fixture
def armed(monkeypatch, as_owner):
    """Both env gates ON + an idle session to bind receipts to."""
    monkeypatch.setattr(server, "TERMINAL_ENABLED", True)
    monkeypatch.setattr(server, "TERMINAL_EXEC_ENABLED", True)
    s = server.new_session(title="term-test")
    yield s
    server.SESSIONS.pop(s["id"], None)


# ---- gate 0: env gates, default OFF, 404 (don't advertise) --------------------

def test_terminal_page_404_when_disabled(monkeypatch):
    monkeypatch.setattr(server, "TERMINAL_ENABLED", False)
    assert client.get("/terminal").status_code == 404


def test_terminal_static_assets_404_when_disabled(monkeypatch):
    # R11: the /static mount must not let the page be fingerprinted while off
    monkeypatch.setattr(server, "TERMINAL_ENABLED", False)
    assert client.get("/static/forge/terminal.html").status_code == 404
    assert client.get("/static/forge/terminal.js").status_code == 404


def test_terminal_page_served_when_enabled(monkeypatch):
    monkeypatch.setattr(server, "TERMINAL_ENABLED", True)
    r = client.get("/terminal")
    assert r.status_code == 200
    assert "terminal.js" in r.text
    assert client.get("/static/forge/terminal.js").status_code == 200


def test_exec_404_when_either_gate_off(monkeypatch, as_owner):
    s = server.new_session(title="g")
    try:
        for page, ex in ((False, False), (True, False), (False, True)):
            monkeypatch.setattr(server, "TERMINAL_ENABLED", page)
            monkeypatch.setattr(server, "TERMINAL_EXEC_ENABLED", ex)
            r = client.post("/api/terminal/exec",
                            json={"sid": s["id"], "command": "echo hi"})
            assert r.status_code == 404, (page, ex)
    finally:
        server.SESSIONS.pop(s["id"], None)


# ---- gate 1: authn/authz ------------------------------------------------------

def test_exec_requires_token(monkeypatch):
    monkeypatch.setattr(server, "TERMINAL_ENABLED", True)
    monkeypatch.setattr(server, "TERMINAL_EXEC_ENABLED", True)
    r = client.post("/api/terminal/exec", json={"sid": "x", "command": "id"})
    assert r.status_code == 401


def test_exec_rejects_non_owner(monkeypatch):
    # a valid Member token passes verify_token but must fail verify_owner
    monkeypatch.setattr(server, "TERMINAL_ENABLED", True)
    monkeypatch.setattr(server, "TERMINAL_EXEC_ENABLED", True)
    monkeypatch.setattr(server, "load_users",
                        lambda: {"dev": {"role": "Member"}})
    tok = server.make_token("dev")
    r = client.post("/api/terminal/exec",
                    headers={"Authorization": "Bearer " + tok},
                    json={"sid": "x", "command": "id"})
    assert r.status_code == 403


# ---- gates 2+4: session binding, caps, bounded execution ----------------------

@requires_bash
def test_exec_runs_and_leaves_receipts(armed):
    r = client.post("/api/terminal/exec",
                    json={"sid": armed["id"], "command": "echo receipt-me"})
    assert r.status_code == 200
    d = r.json()
    assert d["ok"] and d["exit_code"] == 0 and "receipt-me" in d["output"]
    types = [e["type"] for e in armed["events"]]
    assert "terminal_exec" in types and "terminal_exec_result" in types


def test_exec_unknown_session_404(armed):
    r = client.post("/api/terminal/exec",
                    json={"sid": "nope", "command": "echo hi"})
    assert r.status_code == 404


def test_exec_busy_session_409(armed):
    armed["status"] = "running"           # F5: no mid-run interleave
    r = client.post("/api/terminal/exec",
                    json={"sid": armed["id"], "command": "echo hi"})
    assert r.status_code == 409
    armed["status"] = "idle"


def test_exec_command_length_cap(armed):
    r = client.post("/api/terminal/exec",
                    json={"sid": armed["id"],
                          "command": "x" * (server.TERMINAL_CMD_MAX_CHARS + 1)})
    assert r.status_code == 413


def test_exec_empty_command_400(armed):
    r = client.post("/api/terminal/exec",
                    json={"sid": armed["id"], "command": "   "})
    assert r.status_code == 400


def test_exec_concurrency_cap(armed, monkeypatch):
    monkeypatch.setattr(server, "_active_terminal_execs", 99)
    r = client.post("/api/terminal/exec",
                    json={"sid": armed["id"], "command": "echo hi"})
    assert r.status_code == 429
    # and the counter is restored after a successful run releases its slot
    monkeypatch.setattr(server, "_active_terminal_execs", 0)
    client.post("/api/terminal/exec", json={"sid": armed["id"], "command": "true"})
    assert server._active_terminal_execs == 0


@requires_bash
def test_exec_nonzero_exit_reported(armed):
    r = client.post("/api/terminal/exec",
                    json={"sid": armed["id"], "command": "exit 3"})
    assert r.status_code == 200
    assert r.json()["exit_code"] == 3


# ---- gate 3: risky-command confirm round-trip (F2 receipts) --------------------

@requires_bash
def test_risky_command_needs_confirm_and_receipts(armed, monkeypatch):
    monkeypatch.setattr(server, "_is_risky", lambda c: True)
    r = client.post("/api/terminal/exec",
                    json={"sid": armed["id"], "command": "echo would-be-risky"})
    assert r.status_code == 200
    assert r.json()["needs_confirm"] is True
    # F2: the refused attempt itself left a receipt
    ev = [e for e in armed["events"] if e["type"] == "terminal_exec"][-1]
    assert ev["status"] == "needs_confirm"
    # confirm actually runs it
    r2 = client.post("/api/terminal/exec",
                     json={"sid": armed["id"], "command": "echo would-be-risky",
                           "confirm": True})
    assert r2.status_code == 200 and "would-be-risky" in r2.json()["output"]


# ---- gate 5: response redaction (F3) -------------------------------------------

@requires_bash
def test_exec_output_is_redacted(armed, monkeypatch):
    monkeypatch.setattr(server, "_SECRET_CACHE", {"hunter2secret"})
    r = client.post("/api/terminal/exec",
                    json={"sid": armed["id"], "command": "echo hunter2secret"})
    assert r.status_code == 200
    assert "hunter2secret" not in r.json()["output"]
    assert "[REDACTED]" in r.json()["output"]
    # the persisted receipt is redacted too (emit path)
    res = [e for e in armed["events"] if e["type"] == "terminal_exec_result"][-1]
    assert "hunter2secret" not in res["output"]
