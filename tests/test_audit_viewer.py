"""N11 — owner-only audit-log viewer (/api/audit).

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


# ---- fixtures ------------------------------------------------------------------

@pytest.fixture
def as_owner():
    server.app.dependency_overrides[server.verify_owner] = lambda: "owner"
    yield
    server.app.dependency_overrides.pop(server.verify_owner, None)


@pytest.fixture
def session_with_events():
    """A fresh session pre-populated with one of each safelisted event type plus
    some noise types that must NOT appear in audit output."""
    s = server.new_session(title="audit-test")
    # safelisted events
    server.emit(s, "approval",          approval_id="aaa", command="rm -rf /")
    server.emit(s, "approval_result",   approval_id="aaa", approved=False)
    server.emit(s, "terminal_exec",     by="owner", command="ls /workspace", status="run")
    server.emit(s, "terminal_exec_result", command="ls /workspace", exit_code=0)
    server.emit(s, "debate_verify",     command="git push --force",
                allowed=False, refutes=2, summary="lens-a: REFUTE; lens-b: REFUTE")
    server.emit(s, "error",             message="Model call failed", agent="main")
    # noise — must NOT appear in audit output
    server.emit(s, "text",              text="the quick brown fox", agent="main")
    server.emit(s, "tool",              name="bash", detail="ls", agent="main")
    server.emit(s, "tool_result",       name="bash", ok=True, result="file.txt")
    server.emit(s, "cost",              usd=0.001, in_tokens=10, out_tokens=5,
                model="claude-3-5-haiku-20241022", agent="main")
    server.emit(s, "user",              text="run the tests please")
    yield s
    server.SESSIONS.pop(s["id"], None)


# ---- auth tests ----------------------------------------------------------------

def test_requires_auth_no_token():
    """No bearer token → 401 (fail-closed)."""
    r = client.get("/api/audit")
    assert r.status_code == 401


def test_requires_owner_member_rejected(monkeypatch):
    """A valid Member token must be rejected (403, not let through)."""
    monkeypatch.setattr(server, "load_users", lambda: {"dev": {"role": "Member"}})
    tok = server.make_token("dev")
    r = client.get("/api/audit", headers={"Authorization": "Bearer " + tok})
    assert r.status_code == 403


# ---- safelist enforcement ------------------------------------------------------

def test_only_safelisted_types_returned(as_owner, session_with_events):
    r = client.get("/api/audit")
    assert r.status_code == 200
    types = {e["type"] for e in r.json()["events"]}
    # all returned types must be in the safelist
    assert types <= server._AUDIT_SAFELIST
    # noise types must be absent
    for noise in ("text", "tool", "tool_result", "cost", "user"):
        assert noise not in types, f"noise type '{noise}' leaked into audit output"


def test_safelisted_types_are_present(as_owner, session_with_events):
    r = client.get("/api/audit")
    types = {e["type"] for e in r.json()["events"]}
    for expected in ("approval", "approval_result", "terminal_exec",
                     "terminal_exec_result", "debate_verify", "error"):
        assert expected in types, f"expected type '{expected}' missing from audit"


# ---- field projection ----------------------------------------------------------

def test_no_prompt_content_in_payload(as_owner, session_with_events):
    """text/tool/user events are filtered; no field carries raw prompt or output."""
    r = client.get("/api/audit")
    payload_str = r.text
    # the prompt text from the noise 'text' and 'user' events must not appear
    assert "quick brown fox" not in payload_str
    assert "run the tests please" not in payload_str


def test_no_secret_marker_in_payload(as_owner, monkeypatch):
    """A secret value that went through _redact() must not appear verbatim."""
    s = server.new_session(title="secret-test")
    try:
        monkeypatch.setattr(server, "_SECRET_CACHE", {"tok_hunter99"})
        server.emit(s, "error", message="auth failure tok_hunter99", agent="main")
        r = client.get(f"/api/audit?session={s['id']}")
        assert r.status_code == 200
        assert "tok_hunter99" not in r.text, "raw secret leaked through audit endpoint"
        assert "[REDACTED]" in r.text or r.json()["total"] == 0
    finally:
        server.SESSIONS.pop(s["id"], None)


def test_approval_event_fields(as_owner, session_with_events):
    """approval events expose approval_id and command, nothing else beyond core."""
    r = client.get(f"/api/audit?type=approval&session={session_with_events['id']}")
    evts = r.json()["events"]
    assert len(evts) >= 1
    evt = evts[0]
    assert "approval_id" in evt
    assert "command" in evt
    # no non-safelisted fields
    extra = set(evt.keys()) - {"sid", "i", "ts", "type", "approval_id", "command"}
    assert not extra, f"unexpected fields in approval event: {extra}"


def test_error_event_fields(as_owner, session_with_events):
    """error events expose message and agent only."""
    r = client.get(f"/api/audit?type=error&session={session_with_events['id']}")
    evts = r.json()["events"]
    assert len(evts) >= 1
    evt = evts[0]
    extra = set(evt.keys()) - {"sid", "i", "ts", "type", "message", "agent"}
    assert not extra, f"unexpected fields in error event: {extra}"


# ---- query param behavior ------------------------------------------------------

def test_limit_default(as_owner, session_with_events):
    r = client.get("/api/audit")
    assert r.status_code == 200
    data = r.json()
    assert "events" in data and "total" in data


def test_limit_cap_enforced(as_owner, session_with_events):
    """A limit larger than the hard cap (1000) is silently clamped."""
    r = client.get("/api/audit?limit=99999")
    assert r.status_code == 200
    # total is bounded by what's in memory, not 99999
    assert r.json()["total"] <= server._AUDIT_LIMIT_CAP


def test_limit_applied(as_owner, session_with_events):
    """limit=1 returns at most 1 event."""
    r = client.get("/api/audit?limit=1")
    assert r.status_code == 200
    assert len(r.json()["events"]) <= 1


def test_type_filter(as_owner, session_with_events):
    r = client.get("/api/audit?type=error")
    assert r.status_code == 200
    for evt in r.json()["events"]:
        assert evt["type"] == "error"


def test_type_filter_unknown_returns_empty(as_owner):
    """An unknown type (not in safelist) returns an empty result, not an error."""
    r = client.get("/api/audit?type=unknown_noise_type")
    assert r.status_code == 200
    data = r.json()
    assert data["events"] == []


def test_session_filter(as_owner, session_with_events):
    other = server.new_session(title="other")
    try:
        server.emit(other, "error", message="other session error", agent="x")
        r = client.get(f"/api/audit?session={session_with_events['id']}")
        assert r.status_code == 200
        sids = {e["sid"] for e in r.json()["events"]}
        assert session_with_events["id"] in sids
        assert other["id"] not in sids
    finally:
        server.SESSIONS.pop(other["id"], None)


def test_newest_first(as_owner):
    """Results are newest-first (descending ts)."""
    s = server.new_session(title="order-test")
    try:
        import time as _time
        server.emit(s, "error", message="first",  agent="a")
        _time.sleep(0.01)   # ensure distinct timestamps (1-s resolution might alias)
        server.emit(s, "error", message="second", agent="a")
        r = client.get(f"/api/audit?session={s['id']}&type=error")
        evts = r.json()["events"]
        assert len(evts) >= 2
        # newest first: the event with a higher 'i' index should come first
        assert evts[0].get("i", 0) > evts[1].get("i", 0)
    finally:
        server.SESSIONS.pop(s["id"], None)


# ---- empty-state ---------------------------------------------------------------

def test_empty_sessions_returns_ok(as_owner, monkeypatch):
    """With no sessions in memory the endpoint returns an empty list cleanly."""
    monkeypatch.setattr(server, "SESSIONS", {})
    r = client.get("/api/audit")
    assert r.status_code == 200
    assert r.json() == {"events": [], "total": 0}


# ---- UI route ------------------------------------------------------------------

def test_audit_page_served():
    """The /audit route serves the HTML page (no auth required for the HTML itself;
    auth is enforced by the API the page calls)."""
    r = client.get("/audit")
    assert r.status_code == 200
    assert "audit" in r.text.lower()
