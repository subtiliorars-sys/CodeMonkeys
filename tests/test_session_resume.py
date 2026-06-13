"""N6: session resume after server restart.

Fly scale-to-zero / deploys kill the in-memory run thread; sessions that were
mid-run on shutdown come back showing stale "running" status that never
completes. Fix:
  - _persist_index() now stores status + mode so restore_sessions() can see
    what was in-flight.
  - restore_sessions() sets interrupted (not stuck "running") for any session
    whose persisted status was running or waiting_approval, and appends a
    marker event to the stream.
  - POST /api/sessions/{sid}/resume re-dispatches the agent on the existing
    history; auth-gated (verify_user); 409 if already running.
  - Normal sessions (idle / done) are unaffected.

Run: ./.venv/bin/python -m pytest tests/ -q
"""
import json
import os
import sys
import tempfile
import threading

os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(prefix="cm_test_"))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

pytest.importorskip("httpx", reason="TestClient needs httpx (dev-only)")
from fastapi.testclient import TestClient  # noqa: E402

import server  # noqa: E402


# ------------------------------------------------------------------ helpers

def _fake_provider():
    return {"name": "p", "kind": "openai", "model": "m",
            "base_url": "http://x", "api_key": "k",
            "input_cost_per_m": 0, "output_cost_per_m": 0}


def _fake_call(*a, **k):
    return {"text": "done", "tool_calls": [], "in_tokens": 1, "out_tokens": 1}


class _InertThread:
    """Never runs the worker — lets us test endpoint sync behavior in isolation."""
    def __init__(self, *a, **k): pass
    def start(self): pass


@pytest.fixture()
def client():
    server.app.dependency_overrides[server.verify_user] = lambda: "u"
    yield TestClient(server.app, raise_server_exceptions=False)
    server.app.dependency_overrides.pop(server.verify_user, None)


# ------------------------------------------------------------------ index persistence

def test_index_persists_status_and_mode():
    """_persist_index must write status + mode so restore can read them."""
    s = server.new_session(title="idx-test")
    s["status"] = "running"
    s["mode"] = "plan"
    server._persist_index()
    idx = server._load_json(server._session_index_path(), {})
    entry = idx.get(s["id"], {})
    assert entry["status"] == "running"
    assert entry["mode"] == "plan"


def test_index_persists_idle_sessions_too():
    """Normal idle sessions must also record status."""
    s = server.new_session(title="idx-idle")
    server._persist_index()
    idx = server._load_json(server._session_index_path(), {})
    assert idx[s["id"]]["status"] == "idle"


# ------------------------------------------------------------------ restore behaviour

def _simulate_restore(sid, persisted_status):
    """Write a fake index entry and events file then call restore_sessions()."""
    # Write index with the requested status
    idx_path = server._session_index_path()
    idx = server._load_json(idx_path, {})
    idx[sid] = {"title": "t", "repo": "", "created": 0, "budget_usd": None,
                "status": persisted_status, "mode": "default"}
    server._save_json(idx_path, idx)
    # Minimal events file
    evt_path = server._events_path(sid)
    with open(evt_path, "w") as f:
        f.write(json.dumps({"i": 0, "ts": 0, "type": "user", "text": "hi"}) + "\n")
    # History
    hist_path = os.path.join(server.SESSIONS_DIR, f"{sid}.history.json")
    server._save_json(hist_path, [{"role": "user", "text": "hi"}])
    # Remove from in-memory dict to force re-load
    server.SESSIONS.pop(sid, None)
    server.restore_sessions()
    return server.SESSIONS.get(sid)


def test_restore_running_becomes_interrupted():
    """A session persisted as 'running' must come back as 'interrupted'."""
    import uuid
    sid = uuid.uuid4().hex[:12]
    s = _simulate_restore(sid, "running")
    assert s is not None
    assert s["status"] == "interrupted", f"expected interrupted, got {s['status']}"


def test_restore_waiting_approval_becomes_interrupted():
    """waiting_approval is also a mid-run state — must become interrupted."""
    import uuid
    sid = uuid.uuid4().hex[:12]
    s = _simulate_restore(sid, "waiting_approval")
    assert s["status"] == "interrupted"


def test_restore_interrupted_emits_marker_event():
    """restore must append an 'interrupted' event so the stream shows it."""
    import uuid
    sid = uuid.uuid4().hex[:12]
    s = _simulate_restore(sid, "running")
    types = [e["type"] for e in s["events"]]
    assert "interrupted" in types, f"no interrupted event; got types: {types}"


def test_restore_interrupted_marker_written_to_disk():
    """The marker event must also land in the .events.jsonl file."""
    import uuid
    sid = uuid.uuid4().hex[:12]
    _simulate_restore(sid, "running")
    with open(server._events_path(sid)) as f:
        lines = f.readlines()
    events = [json.loads(l) for l in lines if l.strip()]
    types = [e["type"] for e in events]
    assert "interrupted" in types


def test_restore_idle_stays_idle():
    """Sessions persisted as idle must remain idle — not regress to interrupted."""
    import uuid
    sid = uuid.uuid4().hex[:12]
    s = _simulate_restore(sid, "idle")
    assert s["status"] == "idle"


def test_restore_running_reruns_persist_index():
    """restore must re-persist the index with the new 'interrupted' status."""
    import uuid
    sid = uuid.uuid4().hex[:12]
    _simulate_restore(sid, "running")
    idx = server._load_json(server._session_index_path(), {})
    assert idx.get(sid, {}).get("status") == "interrupted"


# ------------------------------------------------------------------ resume endpoint

def test_resume_auth_required():
    """Resume must be auth-gated; no override → 401/403."""
    client_no_auth = TestClient(server.app, raise_server_exceptions=False)
    s = server.new_session(title="auth-gate")
    s["status"] = "interrupted"
    r = client_no_auth.post(f"/api/sessions/{s['id']}/resume")
    assert r.status_code in (401, 403)


def test_resume_404_on_unknown_session(client):
    r = client.post("/api/sessions/doesnotexist123/resume")
    assert r.status_code == 404


def test_resume_409_when_already_running(client, monkeypatch):
    """Resume must return 409 if the session is already running."""
    monkeypatch.setattr(server.threading, "Thread", _InertThread)
    s = server.new_session(title="busy")
    s["status"] = "running"
    r = client.post(f"/api/sessions/{s['id']}/resume")
    assert r.status_code == 409


def test_resume_409_when_waiting_approval(client):
    s = server.new_session(title="busy-wa")
    s["status"] = "waiting_approval"
    r = client.post(f"/api/sessions/{s['id']}/resume")
    assert r.status_code == 409


def test_resume_on_interrupted_launches_thread(client, monkeypatch):
    """Resume on an interrupted session must start a new worker thread."""
    launched = []

    class _CapThread:
        def __init__(self, target=None, args=(), daemon=False, **k):
            self._target = target
            self._args = args
        def start(self):
            launched.append(self._args)

    monkeypatch.setattr(server.threading, "Thread", _CapThread)
    s = server.new_session(title="resume-ok")
    s["status"] = "interrupted"
    r = client.post(f"/api/sessions/{s['id']}/resume")
    assert r.status_code == 200
    assert len(launched) == 1
    assert launched[0][0] is s   # first arg is the session


def test_resume_on_idle_also_allowed(client, monkeypatch):
    """Resume is also valid from idle — user wants to continue a finished run."""
    monkeypatch.setattr(server.threading, "Thread", _InertThread)
    s = server.new_session(title="resume-idle")
    # status already idle from new_session
    r = client.post(f"/api/sessions/{s['id']}/resume")
    assert r.status_code == 200


def test_resume_nudge_is_last_user_text(client, monkeypatch):
    """When the last history turn was user, resume re-dispatches that text."""
    nudges = []

    class _CapThread:
        def __init__(self, target=None, args=(), **k):
            self._args = args
        def start(self):
            nudges.append(self._args[1])   # args = (session, text)

    monkeypatch.setattr(server.threading, "Thread", _CapThread)
    s = server.new_session(title="nudge-test")
    s["status"] = "interrupted"
    s["history"] = [{"role": "user", "text": "build the thing"}]
    client.post(f"/api/sessions/{s['id']}/resume")
    assert nudges and nudges[0] == "build the thing"


def test_resume_nudge_fallback_when_no_history(client, monkeypatch):
    """With no user history, resume must use the generic continuation nudge."""
    nudges = []

    class _CapThread:
        def __init__(self, target=None, args=(), **k):
            self._args = args
        def start(self):
            nudges.append(self._args[1])

    monkeypatch.setattr(server.threading, "Thread", _CapThread)
    s = server.new_session(title="nudge-empty")
    s["status"] = "interrupted"
    s["history"] = []
    client.post(f"/api/sessions/{s['id']}/resume")
    assert nudges and nudges[0] == "Continue where you left off."


def test_resume_stays_default_mode_for_non_owner(client, monkeypatch):
    """A session with mode=auto must be silently downgraded for non-Owner."""
    monkeypatch.setattr(server.threading, "Thread", _InertThread)
    # Non-owner user (dependency override already returns "u")
    monkeypatch.setattr(server, "load_users", lambda: {"u": {"role": "Member"}})
    s = server.new_session(title="auto-guard")
    s["status"] = "interrupted"
    s["mode"] = "auto"
    client.post(f"/api/sessions/{s['id']}/resume")
    assert s["mode"] == "default"


def test_resume_keeps_auto_for_owner(client, monkeypatch):
    """Owner resumes an auto session — mode must not be downgraded."""
    monkeypatch.setattr(server.threading, "Thread", _InertThread)
    monkeypatch.setattr(server, "load_users", lambda: {"u": {"role": "Owner"}})
    s = server.new_session(title="auto-owner")
    s["status"] = "interrupted"
    s["mode"] = "auto"
    client.post(f"/api/sessions/{s['id']}/resume")
    assert s["mode"] == "auto"


# ------------------------------------------------------------------ run-path persistence

def test_run_persists_running_status(monkeypatch):
    """run_session_message must persist status=running before invoking the agent."""
    persisted_statuses = []

    orig_persist = server._persist_index

    def cap_persist():
        s_statuses = {sid: s["status"] for sid, s in server.SESSIONS.items()}
        persisted_statuses.append(dict(s_statuses))
        orig_persist()

    monkeypatch.setattr(server, "_persist_index", cap_persist)
    monkeypatch.setattr(server, "main_provider", lambda cfg, username=None: _fake_provider())
    monkeypatch.setattr(server, "call_model", _fake_call)
    monkeypatch.setattr(server, "_pricier_provider", lambda cfg, p, username=None: None)

    s = server.new_session(title="persist-run")
    server.run_session_message(s, "go")

    # At least one persist call must have seen "running" for this session
    saw_running = any(snap.get(s["id"]) == "running" for snap in persisted_statuses)
    assert saw_running, "run_session_message never persisted status=running"


def test_run_persists_idle_status_on_finish(monkeypatch):
    """run_session_message must persist status=idle at the end of the run."""
    final_status = {}

    orig_persist = server._persist_index

    def cap_persist():
        for sid, sess in server.SESSIONS.items():
            final_status[sid] = sess["status"]
        orig_persist()

    monkeypatch.setattr(server, "_persist_index", cap_persist)
    monkeypatch.setattr(server, "main_provider", lambda cfg, username=None: _fake_provider())
    monkeypatch.setattr(server, "call_model", _fake_call)
    monkeypatch.setattr(server, "_pricier_provider", lambda cfg, p, username=None: None)

    s = server.new_session(title="persist-idle")
    server.run_session_message(s, "go")

    assert final_status.get(s["id"]) == "idle"


# ------------------------------------------------------------------ normal sessions unaffected

def test_normal_idle_session_sends_message_ok(client, monkeypatch):
    """Regular message send on an idle session must still work (regression)."""
    monkeypatch.setattr(server.threading, "Thread", _InertThread)
    s = server.new_session(title="normal-send")
    r = client.post(f"/api/sessions/{s['id']}/message", json={"text": "hello"})
    assert r.status_code == 200


def test_message_on_interrupted_is_accepted(client, monkeypatch):
    """Sending a new message to an interrupted session unblocks it normally."""
    monkeypatch.setattr(server.threading, "Thread", _InertThread)
    s = server.new_session(title="msg-interrupted")
    s["status"] = "interrupted"
    r = client.post(f"/api/sessions/{s['id']}/message", json={"text": "try again"})
    assert r.status_code == 200
