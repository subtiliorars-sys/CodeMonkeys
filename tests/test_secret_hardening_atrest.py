"""Tests for single-tenant injection hardening (work/secret-hardening).

Covers:
  (1) session_secret.key encrypt-at-rest: Fernet round-trip, plaintext fallback,
      plaintext→encrypted migration when CM_MASTER_KEY is newly set.
  (2) env eviction: _evict_env_secrets() removes CM_MASTER_KEY / WEBHOOK_SECRET
      from os.environ; GITHUB_TOKEN intentionally NOT evicted.
  (3) auto-mode Owner-only: Member requests auto → silently downgraded to default;
      Owner requests auto → allowed.

Run: ./.venv/bin/python -m pytest tests/ -q
"""
import os
import sys
import tempfile
import threading

_TEST_DATA_DIR = tempfile.mkdtemp(prefix="cm_hardening_test_")
os.environ.setdefault("DATA_DIR", _TEST_DATA_DIR)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import server  # noqa: E402 — import after env setup
import pytest   # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _reset_secret_cache():
    """Clear the in-memory session-secret cache so next call re-reads from disk."""
    server._SESSION_SECRET_CACHE = None


def _make_fernet_from_key(master_key: str):
    """Mirror server._make_fernet() logic for assertions."""
    import base64
    import hashlib
    from cryptography.fernet import Fernet
    digest = hashlib.sha256(master_key.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


# ---------------------------------------------------------------------------
# (1a) Encrypt round-trip — CM_MASTER_KEY set
# ---------------------------------------------------------------------------

def test_session_secret_encrypted_roundtrip(tmp_path, monkeypatch):
    """With CM_MASTER_KEY set, the key file on disk must be Fernet ciphertext,
    and _session_secret() must return the same 32 bytes on repeated reads."""
    monkeypatch.setattr(server, "CM_MASTER_KEY", "test-master-passphrase")
    monkeypatch.setattr(server, "SECRET_FILE", str(tmp_path / "session_secret.key"))
    _reset_secret_cache()

    secret1 = server._session_secret()
    assert len(secret1) == 32, "signing secret must be 32 bytes"

    # File on disk must be encrypted (not raw 32-byte plaintext).
    on_disk = (tmp_path / "session_secret.key").read_bytes()
    assert on_disk != secret1, "file on disk must be ciphertext, not plaintext"

    # Decrypt the on-disk blob independently and confirm it matches.
    assert on_disk.startswith(server._ENC_MAGIC), "encrypted file must carry the version header"
    f = _make_fernet_from_key("test-master-passphrase")
    decrypted = f.decrypt(on_disk[len(server._ENC_MAGIC):])
    assert decrypted == secret1

    # Re-read from disk (simulate restart) — same secret returned.
    _reset_secret_cache()
    secret2 = server._session_secret()
    assert secret2 == secret1, "secret must be stable across reads"


def test_session_secret_file_is_mode_600(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "CM_MASTER_KEY", "test-master-key-mode")
    monkeypatch.setattr(server, "SECRET_FILE", str(tmp_path / "session_secret.key"))
    _reset_secret_cache()
    server._session_secret()
    mode = (tmp_path / "session_secret.key").stat().st_mode & 0o777
    assert mode == 0o600, f"expected 0o600, got {oct(mode)}"


# ---------------------------------------------------------------------------
# (1b) Plaintext fallback — CM_MASTER_KEY unset
# ---------------------------------------------------------------------------

def test_session_secret_plaintext_fallback(tmp_path, monkeypatch, caplog):
    """Without CM_MASTER_KEY the file is written as raw bytes (backward compat)
    and a one-time WARNING is logged."""
    import logging
    monkeypatch.setattr(server, "CM_MASTER_KEY", "")
    monkeypatch.setattr(server, "SECRET_FILE", str(tmp_path / "session_secret.key"))
    _reset_secret_cache()

    with caplog.at_level(logging.WARNING, logger="root"):
        secret = server._session_secret()

    assert len(secret) == 32
    on_disk = (tmp_path / "session_secret.key").read_bytes()
    assert on_disk == secret, "plaintext path must write raw bytes"
    assert "UNENCRYPTED" in caplog.text, "must warn about plaintext storage"


# ---------------------------------------------------------------------------
# (1c) Migration — existing plaintext + newly set CM_MASTER_KEY
# ---------------------------------------------------------------------------

def test_session_secret_migration_plaintext_to_encrypted(tmp_path, monkeypatch, caplog):
    """An existing plaintext session_secret.key plus a newly set CM_MASTER_KEY must
    be re-encrypted transparently — sessions must not be invalidated."""
    import logging

    secret_file = tmp_path / "session_secret.key"
    raw_original = os.urandom(32)
    secret_file.write_bytes(raw_original)
    secret_file.chmod(0o600)

    # First: no master key (plaintext era).
    monkeypatch.setattr(server, "CM_MASTER_KEY", "")
    monkeypatch.setattr(server, "SECRET_FILE", str(secret_file))
    _reset_secret_cache()
    plain_secret = server._session_secret()
    assert plain_secret == raw_original

    # Now operator sets CM_MASTER_KEY (simulate restart with key now set).
    monkeypatch.setattr(server, "CM_MASTER_KEY", "newly-set-master-key")
    _reset_secret_cache()

    with caplog.at_level(logging.INFO, logger="root"):
        migrated_secret = server._session_secret()

    # The returned secret must equal the original — no session invalidation.
    assert migrated_secret == raw_original, "migration must preserve the signing secret"

    # On-disk blob must now be ciphertext, not raw bytes.
    on_disk = secret_file.read_bytes()
    assert on_disk != raw_original, "file must now be encrypted after migration"

    assert on_disk.startswith(server._ENC_MAGIC), "migrated file must carry the version header"
    f = _make_fernet_from_key("newly-set-master-key")
    assert f.decrypt(on_disk[len(server._ENC_MAGIC):]) == raw_original, \
        "migrated ciphertext must decrypt correctly"

    # Log must mention migration.
    assert "migrated" in caplog.text.lower() or "encrypted" in caplog.text.lower()

    # Subsequent read (simulate second restart) returns same secret.
    _reset_secret_cache()
    second_read = server._session_secret()
    assert second_read == raw_original


# ---------------------------------------------------------------------------
# (1d) FAIL-CLOSED on wrong/missing key (red-team F1/F2/F3) — the coverage gap
# ---------------------------------------------------------------------------

def test_rotation_fails_closed(tmp_path, monkeypatch):
    """Rotating CM_MASTER_KEY must NOT silently regenerate/substitute the signing
    secret with the on-disk ciphertext (red-team F1). It must raise, and leave the
    file untouched, so the original key can be restored."""
    sf = tmp_path / "session_secret.key"
    monkeypatch.setattr(server, "SECRET_FILE", str(sf))

    monkeypatch.setattr(server, "CM_MASTER_KEY", "KEY-AAAAAAAAAAAAAAAA")
    _reset_secret_cache()
    original = server._session_secret()
    blob_before = sf.read_bytes()

    # rotate to a different key
    monkeypatch.setattr(server, "CM_MASTER_KEY", "KEY-BBBBBBBBBBBBBBBB")
    _reset_secret_cache()
    with pytest.raises(RuntimeError, match="decrypt"):
        server._session_secret()
    assert sf.read_bytes() == blob_before, "file must be left intact on wrong key"

    # restoring the correct key recovers the ORIGINAL secret (proves it wasn't destroyed)
    monkeypatch.setattr(server, "CM_MASTER_KEY", "KEY-AAAAAAAAAAAAAAAA")
    _reset_secret_cache()
    assert server._session_secret() == original


def test_unset_after_encrypted_fails_closed(tmp_path, monkeypatch):
    """An encrypted file with CM_MASTER_KEY now unset must raise, not read the
    ciphertext as the secret / regenerate (red-team F2)."""
    sf = tmp_path / "session_secret.key"
    monkeypatch.setattr(server, "SECRET_FILE", str(sf))
    monkeypatch.setattr(server, "CM_MASTER_KEY", "KEY-CCCCCCCCCCCCCCCC")
    _reset_secret_cache()
    server._session_secret()

    monkeypatch.setattr(server, "CM_MASTER_KEY", "")
    _reset_secret_cache()
    with pytest.raises(RuntimeError, match="encrypted"):
        server._session_secret()


def test_key_set_but_crypto_unavailable_fails_closed(tmp_path, monkeypatch):
    """CM_MASTER_KEY set but cryptography unavailable must fail closed, not degrade
    to reading the file as plaintext (red-team F3)."""
    sf = tmp_path / "session_secret.key"
    monkeypatch.setattr(server, "SECRET_FILE", str(sf))
    monkeypatch.setattr(server, "CM_MASTER_KEY", "KEY-DDDDDDDDDDDDDDDD")
    monkeypatch.setattr(server, "_FERNET_AVAILABLE", False)
    _reset_secret_cache()
    with pytest.raises(RuntimeError, match="cryptography"):
        server._session_secret()


def test_correct_key_reread_no_spurious_migration(tmp_path, monkeypatch):
    """Re-reading with the SAME key returns the same secret and does not rewrite."""
    sf = tmp_path / "session_secret.key"
    monkeypatch.setattr(server, "SECRET_FILE", str(sf))
    monkeypatch.setattr(server, "CM_MASTER_KEY", "KEY-EEEEEEEEEEEEEEEE")
    _reset_secret_cache()
    s1 = server._session_secret()
    blob1 = sf.read_bytes()
    _reset_secret_cache()
    s2 = server._session_secret()
    assert s2 == s1
    # ciphertext is non-deterministic, but the SECRET is stable and a clean decrypt
    # path doesn't rewrite the file
    assert sf.read_bytes() == blob1, "a clean decrypt must not rewrite the file"


# ---------------------------------------------------------------------------
# (1e) BREAK-GLASS recovery — CM_MASTER_KEY_RESET (docs/RECOVERY.md Scenario A)
# ---------------------------------------------------------------------------

def test_breakglass_recovers_rotation_lockout(tmp_path, monkeypatch):
    """The exact recovery path: encrypted under KEY-A, key 'lost' and replaced with
    KEY-B (would normally fail closed) — with CM_MASTER_KEY_RESET=true it boots,
    generating a FRESH secret encrypted under the new key (never reuses old bytes)."""
    sf = tmp_path / "session_secret.key"
    monkeypatch.setattr(server, "SECRET_FILE", str(sf))
    monkeypatch.setattr(server, "CM_MASTER_KEY_RESET", False)
    monkeypatch.setattr(server, "CM_MASTER_KEY", "KEY-AAAAAAAAAAAAAAAA")
    _reset_secret_cache()
    old = server._session_secret()

    # rotate (lost original) + break-glass
    monkeypatch.setattr(server, "CM_MASTER_KEY", "KEY-BBBBBBBBBBBBBBBB")
    monkeypatch.setattr(server, "CM_MASTER_KEY_RESET", True)
    _reset_secret_cache()
    fresh = server._session_secret()           # must NOT raise

    assert len(fresh) == 32 and fresh != old, "must mint a brand-new secret"
    on_disk = sf.read_bytes()
    assert on_disk.startswith(server._ENC_MAGIC)
    # decrypts under the NEW key
    assert _make_fernet_from_key("KEY-BBBBBBBBBBBBBBBB").decrypt(
        on_disk[len(server._ENC_MAGIC):]) == fresh


def test_breakglass_plaintext_mode(tmp_path, monkeypatch):
    """With no master key, break-glass regenerates a fresh plaintext secret."""
    sf = tmp_path / "session_secret.key"
    sf.write_bytes(b"x" * 32)
    monkeypatch.setattr(server, "SECRET_FILE", str(sf))
    monkeypatch.setattr(server, "CM_MASTER_KEY", "")
    monkeypatch.setattr(server, "CM_MASTER_KEY_RESET", True)
    _reset_secret_cache()
    fresh = server._session_secret()
    assert len(fresh) == 32 and fresh != b"x" * 32
    assert sf.read_bytes() == fresh            # plaintext (no header) in keyless mode


def test_breakglass_off_by_default(tmp_path, monkeypatch):
    """Without the flag, the lockout still fails closed (no accidental reset)."""
    sf = tmp_path / "session_secret.key"
    monkeypatch.setattr(server, "SECRET_FILE", str(sf))
    monkeypatch.setattr(server, "CM_MASTER_KEY_RESET", False)
    monkeypatch.setattr(server, "CM_MASTER_KEY", "KEY-AAAAAAAAAAAAAAAA")
    _reset_secret_cache()
    server._session_secret()
    monkeypatch.setattr(server, "CM_MASTER_KEY", "KEY-BBBBBBBBBBBBBBBB")
    _reset_secret_cache()
    with pytest.raises(RuntimeError):
        server._session_secret()


# ---------------------------------------------------------------------------
# (2) Env eviction — test _evict_env_secrets() directly
# ---------------------------------------------------------------------------
# Because pytest imports all test modules into the same process, os.environ
# mutations at module-level in one test file affect others.  We therefore test
# _evict_env_secrets() in isolation by planting values, calling the function,
# and asserting they were removed.

def test_eviction_removes_cm_master_key():
    """_evict_env_secrets() must remove CM_MASTER_KEY from os.environ."""
    os.environ["CM_MASTER_KEY"] = "planted-for-eviction-test"
    server._evict_env_secrets()
    assert "CM_MASTER_KEY" not in os.environ, (
        "CM_MASTER_KEY must be evicted from os.environ"
    )


def test_eviction_removes_webhook_secret():
    """_evict_env_secrets() must remove WEBHOOK_SECRET from os.environ."""
    os.environ["WEBHOOK_SECRET"] = "planted-webhook-secret-for-test"
    server._evict_env_secrets()
    assert "WEBHOOK_SECRET" not in os.environ, (
        "WEBHOOK_SECRET must be evicted from os.environ"
    )


def test_eviction_preserves_github_token():
    """GITHUB_TOKEN must NOT be in _SECRET_ENV_EVICT — git subprocesses need it."""
    token_val = "github_pat_EVICTION_TEST_TOKEN_xyz123"
    os.environ["GITHUB_TOKEN"] = token_val
    server._evict_env_secrets()
    assert os.environ.get("GITHUB_TOKEN") == token_val, (
        "GITHUB_TOKEN must survive _evict_env_secrets() — git auth depends on it"
    )
    # Restore for other tests
    os.environ.pop("GITHUB_TOKEN", None)


def test_eviction_preserves_path_and_home():
    """Operational vars like PATH and HOME must not be touched by eviction."""
    path_before = os.environ.get("PATH", "")
    home_before = os.environ.get("HOME", "")
    server._evict_env_secrets()
    assert os.environ.get("PATH") == path_before
    assert os.environ.get("HOME") == home_before


def test_cm_master_key_in_evict_set():
    """CM_MASTER_KEY must be listed in _SECRET_ENV_EVICT."""
    assert "CM_MASTER_KEY" in server._SECRET_ENV_EVICT


def test_github_token_not_in_evict_set():
    """GITHUB_TOKEN must NOT be in _SECRET_ENV_EVICT (intentionally preserved)."""
    assert "GITHUB_TOKEN" not in server._SECRET_ENV_EVICT


def test_cm_master_key_module_constant_is_string():
    """CM_MASTER_KEY module constant must be a str (captured before eviction)."""
    assert isinstance(server.CM_MASTER_KEY, str)


# ---------------------------------------------------------------------------
# (3) Auto-mode Owner-only via session_message
# ---------------------------------------------------------------------------

def _make_session():
    """Create a fresh in-memory session for testing (no disk I/O)."""
    return {
        "id": "test-session-automode",
        "title": "test",
        "repo": "",
        "created": 0,
        "status": "idle",
        "mode": "default",
        "events": [],
        "history": [],
        "spent_usd": 0.0,
        "budget_usd": 1.0,
        "agents_spawned": 0,
        "stop_flag": threading.Event(),
        "approvals": {},
        "lock": threading.Lock(),
    }


def test_auto_mode_owner_allowed(monkeypatch):
    """Owner must be able to set mode=auto."""
    from fastapi.testclient import TestClient

    sess = _make_session()
    monkeypatch.setitem(server.SESSIONS, sess["id"], sess)

    # Inject owner user.
    users = {"testowner": {"role": "Owner", "must_reset": False}}
    monkeypatch.setattr(server, "load_users", lambda: users)

    # Bypass auth — inject the username directly.
    server.app.dependency_overrides[server.verify_user] = lambda: "testowner"

    # Capture the mode that gets written without spawning a real thread.
    thread_started = []
    monkeypatch.setattr(threading, "Thread",
                        lambda target, args, daemon: type(
                            "T", (), {"start": lambda self: thread_started.append(args[1])})())
    monkeypatch.setattr(server, "emit", lambda *a, **kw: None)
    monkeypatch.setattr(server, "_cap_message", lambda t: t)
    monkeypatch.setattr(server, "_save_uploads", lambda sid, files: [])

    client = TestClient(server.app)
    resp = client.post(
        f"/api/sessions/{sess['id']}/message",
        json={"text": "go", "mode": "auto"},
        headers={"Authorization": "Bearer dummy"},
    )
    server.app.dependency_overrides.clear()
    assert resp.status_code == 200
    assert sess["mode"] == "auto", f"Owner should get auto mode; got {sess['mode']!r}"


def test_auto_mode_member_blocked(monkeypatch):
    """Member requesting auto must silently fall back to default — not 403."""
    from fastapi.testclient import TestClient

    sess = _make_session()
    sess["status"] = "idle"
    monkeypatch.setitem(server.SESSIONS, sess["id"], sess)

    users = {"testmember": {"role": "Member", "must_reset": False}}
    monkeypatch.setattr(server, "load_users", lambda: users)

    server.app.dependency_overrides[server.verify_user] = lambda: "testmember"

    monkeypatch.setattr(threading, "Thread",
                        lambda target, args, daemon: type(
                            "T", (), {"start": lambda self: None})())
    monkeypatch.setattr(server, "emit", lambda *a, **kw: None)
    monkeypatch.setattr(server, "_cap_message", lambda t: t)
    monkeypatch.setattr(server, "_save_uploads", lambda sid, files: [])

    client = TestClient(server.app)
    resp = client.post(
        f"/api/sessions/{sess['id']}/message",
        json={"text": "go", "mode": "auto"},
        headers={"Authorization": "Bearer dummy"},
    )
    server.app.dependency_overrides.clear()
    assert resp.status_code == 200
    assert sess["mode"] == "default", (
        f"Member requesting auto must fall back to default; got {sess['mode']!r}"
    )


def test_plan_mode_member_allowed(monkeypatch):
    """plan mode must remain available to Member (not over-restricted)."""
    from fastapi.testclient import TestClient

    sess = _make_session()
    monkeypatch.setitem(server.SESSIONS, sess["id"], sess)

    users = {"testmember2": {"role": "Member", "must_reset": False}}
    monkeypatch.setattr(server, "load_users", lambda: users)

    server.app.dependency_overrides[server.verify_user] = lambda: "testmember2"

    monkeypatch.setattr(threading, "Thread",
                        lambda target, args, daemon: type(
                            "T", (), {"start": lambda self: None})())
    monkeypatch.setattr(server, "emit", lambda *a, **kw: None)
    monkeypatch.setattr(server, "_cap_message", lambda t: t)
    monkeypatch.setattr(server, "_save_uploads", lambda sid, files: [])

    client = TestClient(server.app)
    resp = client.post(
        f"/api/sessions/{sess['id']}/message",
        json={"text": "go", "mode": "plan"},
        headers={"Authorization": "Bearer dummy"},
    )
    server.app.dependency_overrides.clear()
    assert resp.status_code == 200
    assert sess["mode"] == "plan", (
        f"Member should be allowed plan mode; got {sess['mode']!r}"
    )
