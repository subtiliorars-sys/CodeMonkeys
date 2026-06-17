"""S6 Layer 1 — session→user binding: API access gated by session owner.

Members see and mutate only their sessions. Owner sees all (read-only flag on
others'). Legacy sessions with username=None are Owner-only.
"""
import os
import sys
import tempfile

os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(prefix="cm_own_test_"))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import server  # noqa: E402

client = TestClient(server.app)


def _as(username: str):
    server.app.dependency_overrides[server.verify_user] = lambda: username
    server.app.dependency_overrides[server.verify_token] = lambda: username


def _clear_overrides():
    server.app.dependency_overrides.pop(server.verify_user, None)
    server.app.dependency_overrides.pop(server.verify_token, None)


@pytest.fixture
def users(monkeypatch):
    store = {
        "owner": {"role": "Owner"},
        "alice": {"role": "Member"},
        "bob": {"role": "Member"},
    }
    monkeypatch.setattr(server, "load_users", lambda: store)
    yield store


@pytest.fixture(autouse=True)
def cleanup_sessions():
    created = []
    orig = server.new_session

    def _track(*a, **kw):
        s = orig(*a, **kw)
        created.append(s["id"])
        return s

    server.new_session = _track
    yield
    server.new_session = orig
    for sid in created:
        server.SESSIONS.pop(sid, None)


def test_member_list_sees_only_own_sessions(users):
    sa = server.new_session(title="alice-a", username="alice")
    sb = server.new_session(title="bob-b", username="bob")
    try:
        _as("alice")
        r = client.get("/api/sessions")
        assert r.status_code == 200
        ids = {s["id"] for s in r.json()["sessions"]}
        assert sa["id"] in ids
        assert sb["id"] not in ids
    finally:
        _clear_overrides()


def test_owner_list_sees_all_with_read_only(users):
    sa = server.new_session(title="alice-a", username="alice")
    try:
        _as("owner")
        r = client.get("/api/sessions")
        assert r.status_code == 200
        rows = {s["id"]: s for s in r.json()["sessions"]}
        assert sa["id"] in rows
        assert rows[sa["id"]].get("read_only") is True
    finally:
        _clear_overrides()


def test_member_cannot_read_other_session_events(users):
    sb = server.new_session(title="bob-b", username="bob")
    sb["events"] = [{"i": 0, "ts": 1, "type": "user", "text": "secret"}]
    try:
        _as("alice")
        r = client.get(f"/api/sessions/{sb['id']}/events")
        assert r.status_code == 404
    finally:
        _clear_overrides()


def test_owner_can_read_other_session_events(users):
    sb = server.new_session(title="bob-b", username="bob")
    sb["events"] = [{"i": 0, "ts": 1, "type": "user", "text": "hi"}]
    try:
        _as("owner")
        r = client.get(f"/api/sessions/{sb['id']}/events")
        assert r.status_code == 200
        assert r.json()["events"]
    finally:
        _clear_overrides()


def test_owner_cannot_mutate_other_session(users):
    sb = server.new_session(title="bob-b", username="bob")
    sb["status"] = "idle"
    try:
        _as("owner")
        assert client.post(f"/api/sessions/{sb['id']}/stop").status_code == 403
        assert client.delete(f"/api/sessions/{sb['id']}").status_code == 403
        assert client.patch(f"/api/sessions/{sb['id']}", json={"title": "x"}).status_code == 403
    finally:
        _clear_overrides()


def test_member_can_mutate_own_session(users):
    sa = server.new_session(title="alice-a", username="alice")
    sa["status"] = "idle"
    try:
        _as("alice")
        r = client.patch(f"/api/sessions/{sa['id']}", json={"title": "renamed"})
        assert r.status_code == 200
        assert r.json()["title"] == "renamed"
    finally:
        _clear_overrides()


def test_legacy_session_owner_only(users):
    legacy = server.new_session(title="webhook-run", username=None)
    legacy["status"] = "idle"
    try:
        _as("alice")
        assert client.get(f"/api/sessions/{legacy['id']}/events").status_code == 404
        assert client.delete(f"/api/sessions/{legacy['id']}").status_code == 404
        _clear_overrides()
        _as("owner")
        assert client.get(f"/api/sessions/{legacy['id']}/events").status_code == 200
        assert client.delete(f"/api/sessions/{legacy['id']}").status_code == 200
    finally:
        _clear_overrides()


def test_create_stamps_username(users):
    try:
        _as("alice")
        r = client.post("/api/sessions", json={"title": "new"})
        assert r.status_code == 200
        sid = r.json()["id"]
        assert server.SESSIONS[sid]["username"] == "alice"
    finally:
        _clear_overrides()
