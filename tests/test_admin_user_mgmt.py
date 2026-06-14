"""Owner admin surfaces: credit-sharing toggle, reset-2FA, rename a Member.

Covers the new functional asks:
  - share_owner_keys gates whether a Member may spend the Owner's (non-Vertex)
    provider keys (default OFF / fail-closed; Owner & internal contexts always OK);
  - POST /api/users/{u}/reset-mfa clears the second factor + passkeys and routes
    the Member back through first-login enrollment, without locking out recovery;
  - POST /api/users/{u}/rename moves the record + derived stores, with the M-7
    tombstone + collision guards.
Plus the red-team edges: non-owner blocked, Owner/self refused, bad/taken/erased ids.

Run: ./.venv/bin/python -m pytest tests/test_admin_user_mgmt.py -q
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
def env(tmp_path, monkeypatch):
    """Isolated stores, seeded Owner 'boss' + Member 'alice'; authed as Owner."""
    monkeypatch.setattr(server, "USERS_FILE", str(tmp_path / "users.json"))
    monkeypatch.setattr(server, "MODELS_FILE", str(tmp_path / "model_config.json"))
    monkeypatch.setattr(server, "ERASED_FILE", str(tmp_path / "erased_accounts.json"))
    monkeypatch.setattr(server, "LOGIN_THROTTLE_FILE", str(tmp_path / "login_throttle.json"))
    server.save_users({
        "boss":  {"role": "Owner",  "mfa_secret": "BOSSSECRET", "created": 1},
        "alice": {"role": "Member", "mfa_secret": "ALICESECRET", "created": 2,
                  "webauthn_credentials": ["blob"]},
    })
    server.app.dependency_overrides[server.verify_owner] = lambda: "boss"
    yield tmp_path
    server.app.dependency_overrides.pop(server.verify_owner, None)
    server.app.dependency_overrides.pop(server.verify_token, None)
    with server._LOGIN_LOCK:
        server._login_fails.clear()
    server._webauthn_states.clear()


# --------------------------------------------------- credit-sharing toggle

def test_share_keys_default_off_blocks_member_owner_key(env):
    """A keyed non-Vertex provider is callable for the Owner/internal but NOT for
    a Member while the share switch is off (the default)."""
    prov = {"kind": "anthropic", "key": "sk-real", "model": "claude"}
    assert server._callable_provider(prov, username=None) is True       # internal
    assert server._callable_provider(prov, username="boss") is True     # Owner
    assert server._callable_provider(prov, username="alice") is False   # Member, off


def test_share_keys_on_lets_member_use_owner_key(env):
    server.save_models({**server.load_models(), "share_owner_keys": True})
    prov = {"kind": "anthropic", "key": "sk-real", "model": "claude"}
    assert server._callable_provider(prov, username="alice") is True


def test_settings_endpoint_toggles_and_get_reflects(env):
    r = client.post("/api/models/settings", json={"share_owner_keys": True})
    assert r.status_code == 200 and r.json()["share_owner_keys"] is True
    assert client.get("/api/models").json()["share_owner_keys"] is True
    # auto_cheapest left untouched when omitted
    r2 = client.post("/api/models/settings", json={"share_owner_keys": False})
    assert r2.json()["share_owner_keys"] is False
    assert client.get("/api/models").json()["share_owner_keys"] is False


def test_me_reports_keys_shared_and_can_run(env):
    server.save_models({"selected": "auto", "auto_cheapest": True,
                        "providers": {"anthropic": {"kind": "anthropic",
                                                    "key": "sk-real", "model": "claude"}}})
    server.app.dependency_overrides[server.verify_token] = lambda: "alice"
    off = client.get("/api/me").json()
    assert off["keys_shared"] is False and off["can_run"] is False
    server.save_models({**server.load_models(), "share_owner_keys": True})
    on = client.get("/api/me").json()
    assert on["keys_shared"] is True and on["can_run"] is True


def test_settings_requires_owner(env):
    server.app.dependency_overrides.pop(server.verify_owner, None)
    server.app.dependency_overrides[server.verify_token] = lambda: "alice"
    assert client.post("/api/models/settings", json={"share_owner_keys": True}).status_code == 403


# --------------------------------------------------- reset 2FA

def test_reset_mfa_forces_reenrollment(env):
    with server._LOGIN_LOCK:
        server._login_fails["alice"] = {"stamps": [1, 2], "until": 0}
    r = client.post("/api/users/alice/reset-mfa")
    assert r.status_code == 200, r.text
    u = server.load_users()["alice"]
    assert u["mfa_secret"] == "" and u["must_reset"] is True
    assert "webauthn_credentials" not in u           # passkeys cleared too
    assert "alice" not in server._login_fails         # lockout cleared for recovery


def test_reset_mfa_refuses_owner_and_self(env):
    server.save_users({**server.load_users(), "boss2": {"role": "Owner", "created": 9}})
    assert client.post("/api/users/boss2/reset-mfa").status_code == 400
    assert client.post("/api/users/boss/reset-mfa").status_code == 400   # self
    assert client.post("/api/users/ghost/reset-mfa").status_code == 404


def test_reset_mfa_requires_owner(env):
    server.app.dependency_overrides.pop(server.verify_owner, None)
    server.app.dependency_overrides[server.verify_token] = lambda: "alice"
    assert client.post("/api/users/alice/reset-mfa").status_code == 403


# --------------------------------------------------- rename

def test_rename_moves_record_and_stores(env):
    with server._LOGIN_LOCK:
        server._login_fails["alice"] = {"stamps": [1], "until": 0}
    server._webauthn_states["alice"] = object()
    r = client.post("/api/users/alice/rename", json={"new_username": "alice2"})
    assert r.status_code == 200, r.text
    users = server.load_users()
    assert "alice" not in users and users["alice2"]["role"] == "Member"
    assert "alice" not in server._login_fails and "alice2" in server._login_fails
    assert "alice" not in server._webauthn_states and "alice2" in server._webauthn_states


def test_rename_guards(env):
    server.save_users({**server.load_users(),
                       "bob": {"role": "Member", "created": 3},
                       "boss2": {"role": "Owner", "created": 9}})
    assert client.post("/api/users/alice/rename", json={"new_username": "bob"}).status_code == 409
    assert client.post("/api/users/alice/rename", json={"new_username": "x"}).status_code == 400  # too short
    assert client.post("/api/users/alice/rename", json={"new_username": "a/b"}).status_code == 400
    assert client.post("/api/users/alice/rename", json={"new_username": "alice"}).status_code == 400  # same
    assert client.post("/api/users/boss2/rename", json={"new_username": "boss3"}).status_code == 400  # owner
    assert client.post("/api/users/ghost/rename", json={"new_username": "y2"}).status_code == 404


def test_rename_blocked_into_tombstone(env):
    server._record_erasure("zombie", by="boss", stores=["users.json"])
    r = client.post("/api/users/alice/rename", json={"new_username": "zombie"})
    assert r.status_code == 403
    assert "alice" in server.load_users()       # unchanged


def test_rename_requires_owner(env):
    server.app.dependency_overrides.pop(server.verify_owner, None)
    server.app.dependency_overrides[server.verify_token] = lambda: "alice"
    assert client.post("/api/users/alice/rename",
                       json={"new_username": "alice9"}).status_code == 403
