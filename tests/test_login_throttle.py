"""Tests for the login brute-force throttle (server._login_* + /api/login).

Regression coverage for SECURITY.md "no rate limiting on login": /api/login used
to accept unlimited PIN/MFA attempts. After LOGIN_MAX_FAILS failures within
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

GOOD_PIN = "13579"
MFA_SECRET = pyotp.random_base32()


def _make_user(username="alice", must_reset=False):
    salt = server.secrets.token_hex(16)
    users = server.load_users()
    users[username] = {
        "pin_hash": server.hash_pin(GOOD_PIN, salt),
        "salt": salt,
        "role": "Owner",
        "mfa_secret": "" if must_reset else MFA_SECRET,
        "must_reset": must_reset,
        "created": 1,
    }
    server.save_users(users)


@pytest.fixture(autouse=True)
def reset_state(monkeypatch):
    # small, deterministic thresholds; long window/lockout so timing isn't flaky
    monkeypatch.setattr(server, "LOGIN_MAX_FAILS", 3)
    monkeypatch.setattr(server, "LOGIN_WINDOW_SEC", 300)
    monkeypatch.setattr(server, "LOGIN_LOCKOUT_SEC", 900)
    # This file exercises the per-USERNAME dimension only; disable the per-IP and
    # global ceilings (added later) so their thresholds don't trip during the
    # high-volume flood tests here. The IP/global dimensions get their own suite
    # in test_login_ip_ceiling.py. Clear all three stores for isolation.
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


def _login(uname, pin, mfa=""):
    return server.login(server.LoginRequest(username=uname, pin=pin, mfa_code=mfa))


def _expect_status(uname, pin, mfa, status):
    return _expect_status_call(lambda: _login(uname, pin, mfa), status)


def _expect_status_call(fn, status):
    with pytest.raises(server.HTTPException) as ei:
        fn()
    assert ei.value.status_code == status
    return ei.value


def test_lockout_after_threshold():
    _make_user("alice")
    for _ in range(3):                       # LOGIN_MAX_FAILS bad attempts
        _expect_status("alice", "00000", "000000", 401)
    # next attempt is locked out even though we now supply correct credentials
    exc = _expect_status("alice", GOOD_PIN, pyotp.TOTP(MFA_SECRET).now(), 429)
    assert "Retry-After" in exc.headers


def test_success_clears_the_counter():
    _make_user("alice")
    _expect_status("alice", "00000", "000000", 401)   # 1 failure
    _expect_status("alice", "00000", "000000", 401)   # 2 failures (< threshold)
    out = _login("alice", GOOD_PIN, pyotp.TOTP(MFA_SECRET).now())
    assert out["token"] and out["username"] == "alice"
    assert "alice" not in server._login_fails          # counter cleared
    # a fresh failure run does not instantly re-lock
    _expect_status("alice", "00000", "000000", 401)
    assert server._login_locked_for("alice") == 0


def test_unknown_username_is_throttled_no_oracle():
    # An attacker probing a non-existent account is still rate-limited, so the
    # 401 cannot be used as an account-existence oracle by attempt count.
    for _ in range(3):
        _expect_status("ghost", "00000", "000000", 401)
    _expect_status("ghost", "00000", "000000", 429)


def test_bad_mfa_counts_toward_lockout():
    _make_user("alice")
    for _ in range(3):                       # correct PIN, wrong MFA
        _expect_status("alice", GOOD_PIN, "000000", 401)
    _expect_status("alice", GOOD_PIN, pyotp.TOTP(MFA_SECRET).now(), 429)


def test_window_prunes_old_failures():
    _make_user("alice")
    # two stale failures outside the window must not count toward the lockout
    server._login_fails["alice"] = {
        "stamps": [server.time.time() - 400, server.time.time() - 400], "until": 0}
    _expect_status("alice", "00000", "000000", 401)   # only this one is in-window
    assert server._login_locked_for("alice") == 0


def test_correct_login_succeeds_when_unlocked():
    _make_user("alice")
    out = _login("alice", GOOD_PIN, pyotp.TOTP(MFA_SECRET).now())
    assert out["role"] == "Owner" and out["token"]


def test_webauthn_login_paths_share_the_lock():
    # A lock armed by PIN failures must also block the passkey path (shared key),
    # and the 429 is raised before any fido state is touched (request unused).
    server._login_fails["alice"] = {"stamps": [], "until": server.time.time() + 999}
    _expect_status_call(
        lambda: server.webauthn_login_begin(
            server.WebauthnBegin(username="alice"), request=None), 429)
    _expect_status_call(
        lambda: server.webauthn_login_complete({"username": "alice"}, request=None), 429)


def test_must_reset_login_does_not_clear_counter():
    # Invited (MFA-less) accounts: a correct starter-PIN login still authenticates
    # but must NOT wipe the throttle window (the throttle is their only barrier).
    _make_user("invitee", must_reset=True)
    server._login_note_failure("invitee")
    server._login_note_failure("invitee")
    out = _login("invitee", GOOD_PIN, "")
    assert out.get("must_reset") is True and out["token"]
    assert "invitee" in server._login_fails        # counter preserved


def test_account_setup_clears_counter():
    _make_user("invitee", must_reset=True)
    server._login_note_failure("invitee")
    server.account_setup(server.FirstSetup(new_username="", new_pin="9876"),
                         username="invitee")
    assert "invitee" not in server._login_fails


def test_eviction_retains_near_threshold_account(monkeypatch):
    monkeypatch.setattr(server, "LOGIN_TRACK_CAP", 50)
    # victim is one failure away from lockout but not yet locked (until=0)
    server._login_fails.clear()
    server._login_fails["victim"] = {
        "stamps": [server.time.time()] * (server.LOGIN_MAX_FAILS - 1), "until": 0}
    for i in range(300):                             # flood 1-stamp junk keys
        _expect_status(f"junk-{i}", "00000", "000000", 401)
    assert "victim" in server._login_fails           # near-threshold not evicted


def test_tracking_dict_is_bounded(monkeypatch):
    # Username-spam must not grow the in-memory tracker without bound: once at
    # the cap, stale (unlocked, out-of-window) entries are reclaimed.
    monkeypatch.setattr(server, "LOGIN_TRACK_CAP", 50)
    for i in range(200):
        _expect_status(f"spam-{i}", "00000", "000000", 401)
    assert len(server._login_fails) <= server.LOGIN_TRACK_CAP

    # An actively-locked account is never evicted by the pruner.
    server._login_fails.clear()
    server._login_fails["victim"] = {"stamps": [], "until": server.time.time() + 999}
    for i in range(200):
        _expect_status(f"more-{i}", "00000", "000000", 401)
    assert "victim" in server._login_fails
