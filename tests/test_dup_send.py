"""Duplicate-send fixes (live bug, owner repro'd in prod 2026-06-07).

Symptom: the Nth message in a session appeared N times, each copy looking like
a real model call + tool executions. Root cause (frontend): app.js's poll()
ended with startPolling(), whose immediate poll() call made every chain
self-perpetuating, while stopPolling() only cleared the interval timer — so
every send()/openSession() forked one more immortal poller. N sends → N
concurrent pollers fetching the same `after` cursor → each rendered the new
events once → N copies on screen.

Locked in here:
  1. Frontend: poll() never schedules itself; in-flight poll + submit guards.
  2. Server (defense in depth): /message check-and-claims status atomically
     under the session lock, so rapid-fire duplicate POSTs can't both spawn
     a real model run; a failed accept never bricks the session.

Run: ./.venv/bin/python -m pytest tests/ -q
"""
import os
import re
import sys
import tempfile

os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(prefix="cm_test_"))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

pytest.importorskip("httpx", reason="TestClient needs httpx (dev-only)")
from fastapi.testclient import TestClient  # noqa: E402

import server  # noqa: E402

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(rel):
    with open(os.path.join(_ROOT, rel)) as f:
        return f.read()


# ---------------------------------------------------------------- frontend

def _js_func(src, header, stop):
    """Slice a top-level function body out of a vanilla-JS file."""
    start = src.index(header)
    return src[start:src.index(stop, start)]


def test_poll_never_schedules_itself():
    """The root cause: poll() ending in startPolling() forked a new immortal
    poll chain per send. poll() may only adjust cadence (setPollSpeed)."""
    js = _read("static/forge/app.js")
    poll = _js_func(js, "async function poll()", "function setPollSpeed")
    assert "startPolling(" not in poll, "poll() must not fork a new poll chain"
    assert "setPollSpeed(" in poll


def test_set_poll_speed_keeps_single_interval():
    """Cadence changes re-create the ONE interval; same speed is a no-op, and
    setPollSpeed never kicks an immediate poll (only startPolling does)."""
    js = _read("static/forge/app.js")
    sps = _js_func(js, "function setPollSpeed", "function startPolling")
    assert "state.pollMs === ms" in sps        # same-speed no-op
    assert re.search(r"\bpoll\(\)", sps) is None


def test_poll_has_inflight_guard():
    """Overlapping polls re-fetch the same `after` cursor → duplicate render."""
    js = _read("static/forge/app.js")
    poll = _js_func(js, "async function poll()", "function setPollSpeed")
    assert "_pollInflight" in poll
    assert "finally" in poll                    # guard always released


def test_send_has_inflight_submit_guard():
    """Defense in depth: one submission at a time; the Send button is disabled
    until the POST returns, and always re-enabled."""
    js = _read("static/forge/app.js")
    send = _js_func(js, "async function send()", "/* ---------------- mode selector")
    assert "_sendInflight" in send
    assert 'disabled = true' in send and 'disabled = false' in send
    assert "finally" in send


def test_terminal_poll_does_not_chain():
    """Regression guard for the other frontend: terminal.js's poll() must not
    grow the same self-perpetuating-chain bug."""
    js = _read("static/forge/terminal.js")
    poll = _js_func(js, "async function poll()", "function startPolling")
    assert "startPolling(" not in poll


# ---------------------------------------------------------------- server

@pytest.fixture()
def auth_client():
    server.app.dependency_overrides[server.verify_user] = lambda: "u"
    yield TestClient(server.app, raise_server_exceptions=False)
    server.app.dependency_overrides.pop(server.verify_user, None)


class _InertThread:
    """Stand-in for threading.Thread: never actually runs the worker, so the
    endpoint's synchronous behavior can be asserted in isolation."""
    def __init__(self, *a, **k): pass
    def start(self): pass


def test_message_claims_status_synchronously(auth_client, monkeypatch):
    """The race the bare check left open: until the worker thread flipped
    status to 'running', a second duplicate POST also passed and spawned a
    second real model run. The endpoint must claim BEFORE returning."""
    monkeypatch.setattr(server.threading, "Thread", _InertThread)
    s = server.new_session(title="dup-a")
    r = auth_client.post(f"/api/sessions/{s['id']}/message", json={"text": "hi"})
    assert r.status_code == 200
    assert s["status"] == "running"            # claimed synchronously

    # the duplicate (worker hasn't run anything — _InertThread) is rejected
    r2 = auth_client.post(f"/api/sessions/{s['id']}/message", json={"text": "hi"})
    assert r2.status_code == 409


def test_message_on_busy_session_is_409(auth_client):
    s = server.new_session(title="dup-b")
    s["status"] = "running"
    r = auth_client.post(f"/api/sessions/{s['id']}/message", json={"text": "x"})
    assert r.status_code == 409


def test_failed_accept_releases_the_claim(auth_client, monkeypatch):
    """If anything between claim and thread-start blows up, status must roll
    back to idle — otherwise the session 409s forever (bricked)."""
    monkeypatch.setattr(server, "_save_uploads",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("disk")))
    s = server.new_session(title="dup-c")
    r = auth_client.post(f"/api/sessions/{s['id']}/message", json={"text": "x"})
    assert r.status_code == 500
    assert s["status"] == "idle"               # not bricked


def test_user_event_emitted_once_per_post(auth_client, monkeypatch):
    """One accepted POST = exactly one 'user' event in the stream."""
    monkeypatch.setattr(server.threading, "Thread", _InertThread)
    s = server.new_session(title="dup-d")
    auth_client.post(f"/api/sessions/{s['id']}/message", json={"text": "only-once"})
    user_events = [e for e in s["events"]
                   if e["type"] == "user" and "only-once" in e.get("text", "")]
    assert len(user_events) == 1
