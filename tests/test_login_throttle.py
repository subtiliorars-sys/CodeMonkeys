"""Tests for the login brute-force throttle (server._login_* + /api/login).

Regression coverage for SECURITY.md "no rate limiting on login": /api/login used
to accept unlimited MFA attempts. After LOGIN_MAX_FAILS failures within
LOGIN_WINDOW_SEC the account is locked for LOGIN_LOCKOUT_SEC (HTTP 429).

Calls the login() handler directly (no HTTP test-client dep) and exercises the
throttle helpers. Run: ./.venv/bin/python -m pytest tests/ -q
"""
import os
import sys
import tempfile

os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(prefix="cm_test_"))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pyotp  # noqa: E402
import pytest  # noqa: E402

import server  # noqa: E402

MFA_SECRET = pyotp.random_base32()


def _make_user(username="alice", must_reset=False):
    users = server.load_users()
    users[username] = {
        "role": "Owner",
        "mfa_secret": "" if must_reset else MFA_SECRET,
        "must_reset": must_reset,
        "created": 1,
    }
    server.save_users(users)


@pytest.fixture(autouse=True)
def reset_state(monkeypatch):
    monkeypatch.setattr(server, "LOGIN_MAX_FAILS", 3)
    monkeypatch.setattr(server, "LOGIN_WINDOW_SEC", 300)
    monkeypatch.setattr(server, "LOGIN_LOCKOUT_SEC", 900)
    monkeypatch.setattr(server, "LOGIN_IP_MAX_FAILS", 0)
    monkeypatch.setattr(server, "LOGIN_GLOBAL_MAX_FAILS", 0)
    server._login_fails.clear()
    server._login_ip_fails.clear()
    server._login_global.clear()
    server.save_users({})
    yield
    server._login_fails.clear()
    server._login_ip_fails.clear()
    server._login_global.clear()
    server.save_users({})


def _login(uname, mfa=""):
    return server.login(server.LoginRequest(username=uname, mfa_code=mfa))


def _expect_status(uname, mfa, status):
    return _expect_status_call(lambda: _login(uname, mfa), status)


def _expect_status_call(fn, status):
    with pytest.raises(server.HTTPException) as ei:
        fn()
    assert ei.value.status_code == status
    return ei.value


def test_lockout_after_threshold():
    _make_user("alice")
    for _ in range(3):
        _expect_status("alice", "000000", 401)
    exc = _expect_status("alice", pyotp.TOTP(MFA_SECRET).now(), 429)
    assert "Retry-After" in exc.headers


def test_success_clears_the_counter():
    _make_user("alice")
    _expect_status("alice", "000000", 401)
    _expect_status("alice", "000000", 401)
    out = _login("alice", pyotp.TOTP(MFA_SECRET).now())
    assert out["token"] and out["username"] == "alice"
    assert "alice" not in server._login_fails
    _expect_status("alice", "000000", 401)
    assert server._login_locked_for("alice") == 0


def test_unknown_username_is_throttled_no_oracle():
    for _ in range(3):
        _expect_status("ghost", "000000", 401)
    _expect_status("ghost", "000000", 429)


def test_bad_mfa_counts_toward_lockout():
    _make_user("alice")
    for _ in range(3):
        _expect_status("alice", "000000", 401)
    _expect_status("alice", pyotp.TOTP(MFA_SECRET).now(), 429)


def test_window_prunes_old_failures():
    _make_user("alice")
    server._login_fails["alice"] = {
        "stamps": [server.time.time() - 400, server.time.time() - 400], "until": 0}
    _expect_status("alice", "000000", 401)
    assert server._login_locked_for("alice") == 0


def test_correct_login_succeeds_when_unlocked():
    _make_user("alice")
    out = _login("alice", pyotp.TOTP(MFA_SECRET).now())
    assert out["role"] == "Owner" and out["token"]


def test_webauthn_login_paths_share_the_lock():
    server._login_fails["alice"] = {"stamps": [], "until": server.time.time() + 999}
    _expect_status_call(
        lambda: server.webauthn_login_begin(
            server.WebauthnBegin(username="alice"), request=None), 429)
    _expect_status_call(
        lambda: server.webauthn_login_complete({"username": "alice"}, request=None), 429)


def test_must_reset_login_does_not_clear_counter():
    _make_user("invitee", must_reset=True)
    server._login_note_failure("invitee")
    server._login_note_failure("invitee")
    out = _login("invitee", "")
    assert out.get("must_reset") is True and out["token"]
    assert "invitee" in server._login_fails


def test_account_setup_clears_counter():
    _make_user("invitee", must_reset=True)
    server._login_note_failure("invitee")
    server.account_setup(server.FirstSetup(new_username=""), username="invitee")
    assert "invitee" not in server._login_fails


def test_eviction_retains_near_threshold_account(monkeypatch):
    monkeypatch.setattr(server, "LOGIN_TRACK_CAP", 50)
    for i in range(49):
        server._login_note_failure(f"user{i}")
    server._login_note_failure("alice")
    server._login_note_failure("alice")
    assert server._login_locked_for("alice") == 0
    server._login_note_failure("alice")
    assert server._login_locked_for("alice") > 0
