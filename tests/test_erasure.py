"""M-7 real erasure — cascade + tombstone + receipt (closes #66).

Verifies the OWNER-RATIFIED Option A: DELETE /api/users hard-deletes the record
AND every derived per-user store, writes a tombstone that blocks reactivation on
every reuse path, and emits an owner-auditable receipt carrying only the subject
id (no pin/salt/secret material). Also covers the red-team cases: non-owner
trigger, Owner/self protection, crafted/traversal names, and double-erase.

Run: ./.venv/bin/python -m pytest tests/test_erasure.py -q
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
def erase_env(tmp_path, monkeypatch):
    """Point every per-user store at an isolated tmp dir and seed an Owner +
    a Member 'alice' with a login-throttle counter and a WebAuthn challenge.
    Authed as the Owner unless a test overrides it."""
    monkeypatch.setattr(server, "USERS_FILE", str(tmp_path / "users.json"))
    monkeypatch.setattr(server, "ERASED_FILE", str(tmp_path / "erased_accounts.json"))
    monkeypatch.setattr(server, "ERASURE_RECEIPTS_FILE", str(tmp_path / "erasure_receipts.jsonl"))
    monkeypatch.setattr(server, "LOGIN_THROTTLE_FILE", str(tmp_path / "login_throttle.json"))

    server.save_users({
        "boss":  {"role": "Owner",  "salt": "s", "pin_hash": "h",
                  "mfa_secret": "ABCDEF", "created": 1},
        "alice": {"role": "Member", "salt": "s2", "pin_hash": "h2",
                  "mfa_secret": "SECRET-ALICE", "created": 2,
                  "webauthn_credentials": ["blob"]},
    })
    # Seed the derived stores keyed to alice.
    with server._LOGIN_LOCK:
        server._login_fails.clear()
        server._login_fails["alice"] = {"stamps": [1, 2, 3], "until": 0}
        server._login_persist()
    server._webauthn_states["alice"] = object()

    server.app.dependency_overrides[server.verify_owner] = lambda: "boss"
    yield tmp_path
    server.app.dependency_overrides.pop(server.verify_owner, None)
    server.app.dependency_overrides.pop(server.verify_token, None)
    with server._LOGIN_LOCK:
        server._login_fails.clear()
    server._webauthn_states.pop("alice", None)


def _receipts(tmp_path):
    p = tmp_path / "erasure_receipts.jsonl"
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text().splitlines() if l.strip()]


# ----------------------------------------------------------------- cascade

def test_cascade_clears_every_per_user_store(erase_env):
    tmp_path = erase_env
    r = client.delete("/api/users/alice")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] and body["erased"] == "alice"
    assert set(body["stores"]) == {"users.json", "login_throttle", "webauthn_state"}

    # 1. primary record gone
    assert "alice" not in server.load_users()
    # 2. login-throttle counter gone (memory AND disk)
    assert "alice" not in server._login_fails
    disk = json.loads((tmp_path / "login_throttle.json").read_text())
    # the throttle file persists multiple dimensions; alice must not appear anywhere
    assert "alice" not in json.dumps(disk)
    # 3. transient WebAuthn challenge gone
    assert "alice" not in server._webauthn_states
    # 4. no residue of alice's secret anywhere on disk in the data dir
    blob = "".join((tmp_path / f).read_text() for f in os.listdir(tmp_path)
                   if (tmp_path / f).is_file())
    assert "SECRET-ALICE" not in blob


def test_cascade_minimal_when_no_derived_stores(erase_env):
    """A user with no throttle counter / no challenge still erases cleanly."""
    server.save_users({**server.load_users(),
                       "bob": {"role": "Member", "created": 3}})
    r = client.delete("/api/users/bob")
    assert r.status_code == 200
    assert r.json()["stores"] == ["users.json"]
    assert server._is_erased("bob")


# ----------------------------------------------------------------- tombstone

def test_tombstone_written(erase_env):
    tmp_path = erase_env
    client.delete("/api/users/alice")
    tomb = json.loads((tmp_path / "erased_accounts.json").read_text())
    assert "alice" in tomb
    assert tomb["alice"]["by"] == "boss"
    assert isinstance(tomb["alice"]["erased_at"], int)
    assert server._is_erased("alice")


def test_tombstone_blocks_reregister(erase_env):
    monkey_open = server.OPEN_ENROLLMENT
    client.delete("/api/users/alice")
    r = client.post("/api/register", json={"username": "alice", "pin": "1234"})
    assert r.status_code == 403
    assert "erased" in r.json()["detail"].lower()
    assert server.OPEN_ENROLLMENT == monkey_open  # untouched


def test_tombstone_blocks_invite(erase_env):
    client.delete("/api/users/alice")
    r = client.post("/api/invite", json={"username": "alice"})
    assert r.status_code == 403
    assert "erased" in r.json()["detail"].lower()


def test_tombstone_blocks_rename_into_erased(erase_env):
    """account_setup must refuse renaming a live account onto a tombstoned id."""
    client.delete("/api/users/alice")
    # carol is a fresh invited member finishing setup; she tries to grab 'alice'
    server.save_users({**server.load_users(),
                       "carol": {"role": "Member", "salt": "s", "pin_hash": "h",
                                 "must_reset": False, "created": 5}})
    server.app.dependency_overrides[server.verify_token] = lambda: "carol"
    r = client.post("/api/account/setup",
                    json={"new_username": "alice", "new_pin": "9999"})
    assert r.status_code == 403
    assert "erased" in r.json()["detail"].lower()
    assert "carol" in server.load_users()   # rename did not go through


# ----------------------------------------------------------------- receipt

def test_receipt_emitted_no_pii(erase_env):
    tmp_path = erase_env
    client.delete("/api/users/alice")
    rec = _receipts(tmp_path)
    assert len(rec) == 1
    e = rec[0]
    assert e["event"] == "erasure" and e["user"] == "alice" and e["by"] == "boss"
    assert isinstance(e["ts"], int)
    # only the id (+ non-PII store names) appears — no credential material. The
    # store list legitimately names "webauthn_state"; what must NOT leak is the
    # actual secret/pin/salt VALUES or the hashed-credential field names.
    line = json.dumps(e)
    assert e["stores"]  # store names are fine to record
    for forbidden in ("pin_hash", "mfa_secret", "SECRET-ALICE", "h2", "blob"):
        assert forbidden not in line


def test_erasures_audit_endpoint(erase_env):
    client.delete("/api/users/alice")
    r = client.get("/api/erasures")
    assert r.status_code == 200
    erased = r.json()["erased"]
    assert any(x["username"] == "alice" and x["by"] == "boss" for x in erased)


# ----------------------------------------------------------------- red-team

def test_non_owner_cannot_erase(erase_env):
    # drop the owner override; authenticate as the Member instead → real
    # verify_owner must 403, and nothing must be erased/tombstoned.
    server.app.dependency_overrides.pop(server.verify_owner, None)
    server.app.dependency_overrides[server.verify_token] = lambda: "alice"
    r = client.delete("/api/users/alice")
    assert r.status_code == 403
    assert "alice" in server.load_users()
    assert not server._is_erased("alice")
    assert _receipts(erase_env) == []


def test_cannot_erase_owner(erase_env):
    # add a second owner and try to erase them
    server.save_users({**server.load_users(),
                       "boss2": {"role": "Owner", "created": 9}})
    r = client.delete("/api/users/boss2")
    assert r.status_code == 400
    assert "boss2" in server.load_users()
    assert not server._is_erased("boss2")     # no tombstone on a refused erase


def test_cannot_self_delete(erase_env):
    r = client.delete("/api/users/boss")
    assert r.status_code == 400
    assert "boss" in server.load_users()


def test_crafted_name_no_residue(erase_env):
    """A traversal-shaped / unknown id never matches (no path is built from the
    id), 404s, and writes neither tombstone nor receipt."""
    before = sorted(os.listdir(erase_env))
    r = client.delete("/api/users/..%2f..%2fetc%2fpasswd")
    assert r.status_code in (404, 400)
    r2 = client.delete("/api/users/ghost")
    assert r2.status_code == 404
    assert not server._is_erased("ghost")
    assert _receipts(erase_env) == []
    assert not (erase_env / "erased_accounts.json").exists() \
        or "ghost" not in (erase_env / "erased_accounts.json").read_text()
    assert sorted(os.listdir(erase_env)) == before  # no stray files created


def test_double_erase_is_idempotent(erase_env):
    """API double-delete 404s the 2nd time (record gone); the tombstone helper
    itself keeps the first timestamp but still appends a receipt."""
    client.delete("/api/users/alice")
    r2 = client.delete("/api/users/alice")
    assert r2.status_code == 404
    # unit-level idempotency of the tombstone writer
    first = json.loads((erase_env / "erased_accounts.json").read_text())["alice"]["erased_at"]
    server._record_erasure("alice", by="boss", stores=["users.json"])
    after = json.loads((erase_env / "erased_accounts.json").read_text())["alice"]["erased_at"]
    assert after == first   # original erased_at preserved
    assert len(_receipts(erase_env)) == 2   # but every call still receipts
