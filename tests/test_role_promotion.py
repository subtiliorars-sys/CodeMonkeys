"""Multi-admin — promote/demote between Member and Owner (2026-07-20).

Owner-only, self-service accounts (open enrollment / invite) land as Member
and can never promote themselves. Covers: happy-path promote/demote, non-owner
rejection (403), unknown user (404), no-op guards (already-Owner /
not-an-Owner), the self-demote lockout guard, and the receipt trail.

Run: ./.venv/bin/python -m pytest tests/test_role_promotion.py -q
"""
import json
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
def role_env(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "USERS_FILE", str(tmp_path / "users.json"))
    monkeypatch.setattr(server, "ROLE_RECEIPTS_FILE", str(tmp_path / "role_receipts.jsonl"))

    server.save_users({
        "boss":  {"role": "Owner",  "salt": "s", "pin_hash": "h",
                  "mfa_secret": "ABCDEF", "created": 1},
        "alice": {"role": "Member", "salt": "s2", "pin_hash": "h2",
                  "mfa_secret": "SECRET-ALICE", "created": 2},
    })
    server.app.dependency_overrides[server.verify_owner] = lambda: "boss"
    yield tmp_path
    server.app.dependency_overrides.pop(server.verify_owner, None)
    server.app.dependency_overrides.pop(server.verify_token, None)


def _receipts(tmp_path):
    path = tmp_path / "role_receipts.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def test_promote_grants_owner(role_env):
    r = client.post("/api/users/alice/promote")
    assert r.status_code == 200
    assert r.json() == {"ok": True, "username": "alice", "role": "Owner"}
    assert server.load_users()["alice"]["role"] == "Owner"
    receipts = _receipts(role_env)
    assert len(receipts) == 1
    assert receipts[0]["user"] == "alice"
    assert receipts[0]["by"] == "boss"
    assert receipts[0]["old_role"] == "Member"
    assert receipts[0]["new_role"] == "Owner"


def test_promote_unknown_user_404(role_env):
    r = client.post("/api/users/ghost/promote")
    assert r.status_code == 404


def test_cannot_promote_unclaimed_invite(role_env):
    """Red-team: a pending invite is an unclaimed username (invite.py's own
    accepted residual risk). Promoting it to Owner would let whoever claims
    that username first walk away with admin, not just Member access."""
    users = server.load_users()
    users["pending-dev"] = {"role": "Member", "mfa_secret": "", "must_reset": True,
                             "created": 3}
    server.save_users(users)
    r = client.post("/api/users/pending-dev/promote")
    assert r.status_code == 400
    assert server.load_users()["pending-dev"]["role"] == "Member"


def test_promote_already_owner_400(role_env):
    r = client.post("/api/users/boss/promote")
    assert r.status_code == 400


def test_demote_revokes_owner(role_env):
    client.post("/api/users/alice/promote")
    r = client.post("/api/users/alice/demote")
    assert r.status_code == 200
    assert r.json()["role"] == "Member"
    assert server.load_users()["alice"]["role"] == "Member"
    receipts = _receipts(role_env)
    assert receipts[-1]["old_role"] == "Owner"
    assert receipts[-1]["new_role"] == "Member"


def test_demote_not_owner_400(role_env):
    r = client.post("/api/users/alice/demote")
    assert r.status_code == 400


def test_demote_unknown_user_404(role_env):
    r = client.post("/api/users/ghost/demote")
    assert r.status_code == 404


def test_cannot_self_demote(role_env):
    r = client.post("/api/users/boss/demote")
    assert r.status_code == 400
    assert server.load_users()["boss"]["role"] == "Owner"


def test_promote_requires_owner_role(role_env):
    server.app.dependency_overrides[server.verify_owner] = lambda: (_ for _ in ()).throw(
        server.HTTPException(403, "Not owner")
    )
    r = client.post("/api/users/alice/promote")
    assert r.status_code == 403


def test_role_changes_list_owner_only(role_env):
    client.post("/api/users/alice/promote")
    r = client.get("/api/role-changes")
    assert r.status_code == 200
    body = r.json()["role_changes"]
    assert len(body) == 1
    assert body[0]["user"] == "alice"
