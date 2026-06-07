"""W7 — debate-verify gate extended to auto-mode MCP tool calls.

The executor path for `mcp_*` tools, in auto mode, must run the same
_debate_verify panel as risky bash and BLOCK on majority refute; default mode
keeps the human approval gate.

Run: ./.venv/bin/python -m pytest tests/ -q
"""
import os
import sys
import tempfile
import threading

os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(prefix="cm_test_"))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import server  # noqa: E402


def _session(mode="auto"):
    return {"id": "mcp-dbv", "mode": mode, "lock": threading.Lock(),
            "events": [], "history": [{"role": "user", "text": "do it"}],
            "spent_usd": 0.0, "stop_flag": threading.Event(),
            "approvals": {}, "agents_spawned": 0}


def _make_exec(session, monkeypatch, registry):
    monkeypatch.setattr(server, "_mcp_registry", lambda: dict(registry))
    monkeypatch.setattr(server, "mcp_tool_schemas", lambda: {})
    return server.make_executor(session, ["mcp_drive_delete"], None, 0)


def test_auto_mcp_blocked_when_panel_refutes(monkeypatch):
    monkeypatch.setattr(server, "_debate_verify",
                        lambda s, cmd: (False, "intent: REFUTE; safety: REFUTE"))
    called = {"n": 0}
    monkeypatch.setattr(server, "_mcp_call_tool",
                        lambda *a, **kw: called.__setitem__("n", called["n"] + 1) or "ran")
    s = _session("auto")
    ex = _make_exec(s, monkeypatch, {"mcp_drive_delete": ("srv", "delete", False)})
    out, ok = ex({"id": "1", "name": "mcp_drive_delete", "args": {"path": "x"}})
    assert ok is False and out.startswith("BLOCKED by debate-verify")
    assert called["n"] == 0          # the MCP call never executed


def test_auto_mcp_runs_when_panel_allows(monkeypatch):
    monkeypatch.setattr(server, "_debate_verify", lambda s, cmd: (True, "all allow"))
    monkeypatch.setattr(server, "_mcp_call_tool", lambda *a, **kw: "ran")
    s = _session("auto")
    ex = _make_exec(s, monkeypatch, {"mcp_drive_delete": ("srv", "delete", False)})
    out, ok = ex({"id": "1", "name": "mcp_drive_delete", "args": {"path": "x"}})
    assert ok is True and out == "ran"


def test_default_mode_uses_human_gate_not_debate(monkeypatch):
    def no_debate(*a, **kw):
        raise AssertionError("default mode must not invoke debate-verify for MCP")
    monkeypatch.setattr(server, "_debate_verify", no_debate)
    monkeypatch.setattr(server, "request_approval", lambda s, c: False)   # deny
    monkeypatch.setattr(server, "_mcp_call_tool", lambda *a, **kw: "ran")
    s = _session("default")
    ex = _make_exec(s, monkeypatch, {"mcp_drive_delete": ("srv", "delete", False)})
    out, ok = ex({"id": "1", "name": "mcp_drive_delete", "args": {"path": "x"}})
    assert ok is False and out == "DENIED"
