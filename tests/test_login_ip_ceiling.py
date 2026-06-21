"""Tests for the per-IP + global login ceilings and the persistent lock store.

Extends the per-account throttle (test_login_throttle.py / PR #13) with the three
properties required before OPEN_ENROLLMENT:
  * per-IP limiting     — one source IP is bounded across *all* usernames it tries
  * global ceiling      — a system-wide circuit-breaker across all IPs/usernames
  * restart-persistence — locks/counters survive a process restart (write-through
                          to LOGIN_THROTTLE_FILE, reloaded by server._login_load())

Calls the login()/webauthn handlers directly with a fake Request carrying a
Fly-Client-IP header (no HTTP test-client dep). Run:
    ./.venv/bin/python -m pytest tests/ -q
"""
import os
import sys
import tempfile

os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(prefix="cm_test_"))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pyotp  # noqa: E402
import pytest  # noqa: E402

import server  # noqa: E402

GOOD_PIN = "13579"  # legacy — unused after PIN removal
MFA_SECRET = pyotp.random_base32()


class _Client:
    def __init__(self, host):
        self.host = host


class FakeReq:
    """Minimal stand-in for fastapi.Request: a Fly-Client-IP header and/or a
    socket peer, mirroring what server._client_ip() reads."""
    def __init__(self, fly_ip=None, client_host=None):
        self.headers = {}
        if fly_ip:
            self.headers["Fly-Client-IP"] = fly_ip
        self.client = _Client(client_host) if client_host else None


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
    # Long window/lockout so timing never flakes. By default push every threshold
    # out of the way; each test tightens the ONE dimension it is exercising.
    monkeypatch.setattr(server, "LOGIN_WINDOW_SEC", 300)
    monkeypatch.setattr(server, "LOGIN_LOCKOUT_SEC", 900)
    monkeypatch.setattr(server, "LOGIN_MAX_FAILS", 1000)
    monkeypatch.setattr(server, "LOGIN_IP_MAX_FAILS", 1000)
    monkeypatch.setattr(server, "LOGIN_GLOBAL_MAX_FAILS", 1000)
    server._login_fails.clear()
    server._login_ip_fails.clear()
    server._login_global.clear()
    server.save_users({})
    yield
    server._login_fails.clear()
    server._login_ip_fails.clear()
    server._login_global.clear()
    server.save_users({})


def _attempt(uname, ip, mfa="000000"):
    """One /api/login attempt from *ip* (None => no Request, i.e. no IP dim)."""
    req = server.LoginRequest(username=uname, mfa_code=mfa)
    return server.login(req, request=FakeReq(fly_ip=ip) if ip else None)


def _expect(uname, ip, status, **kw):
    with pytest.raises(server.HTTPException) as ei:
        _attempt(uname, ip, **kw)
    assert ei.value.status_code == status, (
        f"expected {status} got {ei.value.status_code}")
    return ei.value


# --------------------------------------------------------------- per-IP ceiling

def test_per_ip_lock_spans_usernames(monkeypatch):
    # One IP gets LOGIN_IP_MAX_FAILS attempts *total*, even spread across many
    # different usernames — distributed-by-username guessing from one source is
    # what the per-account lock alone could not stop.
    monkeypatch.setattr(server, "LOGIN_IP_MAX_FAILS", 3)
    bad_ip = "203.0.113.7"
    for i in range(3):
        _expect(f"user-{i}", bad_ip, 401)        # 3 distinct users, same IP
    # the 4th attempt — a brand-new username from that IP — is IP-locked
    exc = _expect("user-fresh", bad_ip, 429)
    assert "Retry-After" in exc.headers


def test_per_ip_lock_isolated_to_that_ip(monkeypatch):
    monkeypatch.setattr(server, "LOGIN_IP_MAX_FAILS", 3)
    bad_ip, other_ip = "203.0.113.7", "198.51.100.9"
    for i in range(3):
        _expect(f"u-{i}", bad_ip, 401)
    _expect("u-x", bad_ip, 429)                   # locked source
    _expect("u-y", other_ip, 401)                 # a different IP is unaffected


def test_per_ip_lock_blocks_even_correct_credentials(monkeypatch):
    # Like the per-account lock, the IP lock is checked before credential work, so
    # a locked IP can't log in even with a valid TOTP.
    monkeypatch.setattr(server, "LOGIN_IP_MAX_FAILS", 3)
    _make_user("alice")
    bad_ip = "203.0.113.7"
    for i in range(3):
        _expect(f"probe-{i}", bad_ip, 401)
    _expect("alice", bad_ip, 429, mfa=pyotp.TOTP(MFA_SECRET).now())


def test_ip_header_falls_back_to_socket_peer(monkeypatch):
    # No Fly-Client-IP header => use the socket peer (request.client.host).
    monkeypatch.setattr(server, "LOGIN_IP_MAX_FAILS", 2)
    req_factory = lambda: server.LoginRequest(username="z", mfa_code="000000")
    peer = FakeReq(client_host="192.0.2.50")
    for _ in range(2):
        with pytest.raises(server.HTTPException) as ei:
            server.login(req_factory(), request=peer)
        assert ei.value.status_code == 401
    with pytest.raises(server.HTTPException) as ei:
        server.login(req_factory(), request=peer)
    assert ei.value.status_code == 429


def test_ip_dimension_disabled_when_zero(monkeypatch):
    monkeypatch.setattr(server, "LOGIN_IP_MAX_FAILS", 0)   # disabled
    bad_ip = "203.0.113.7"
    for i in range(50):
        _expect(f"u-{i}", bad_ip, 401)            # never escalates to 429
    assert server._login_ip_fails == {}           # nothing even recorded


def test_success_clears_ip_counter(monkeypatch):
    monkeypatch.setattr(server, "LOGIN_IP_MAX_FAILS", 5)
    _make_user("alice")
    good_ip = "198.51.100.20"
    _expect("alice", good_ip, 401)                # 1 failure on this IP
    _expect("alice", good_ip, 401)                # 2 failures
    out = _attempt("alice", good_ip, mfa=pyotp.TOTP(MFA_SECRET).now())
    assert out["token"]
    assert good_ip not in server._login_ip_fails  # IP counter wiped on success


def test_ip_tracking_dict_is_bounded(monkeypatch):
    # Spoofing a fresh Fly-Client-IP per request must not grow the IP tracker
    # without bound — the same prune/evict cap that protects the username store.
    monkeypatch.setattr(server, "LOGIN_IP_MAX_FAILS", 3)
    monkeypatch.setattr(server, "LOGIN_TRACK_CAP", 50)
    for i in range(200):
        _expect("victim", f"10.0.{i // 256}.{i % 256}", 401)
    assert len(server._login_ip_fails) <= server.LOGIN_TRACK_CAP


# --------------------------------------------------------------- global ceiling

def test_global_ceiling_trips_across_ips_and_users(monkeypatch):
    # The global bucket counts every failure regardless of IP/username. Once it
    # arms, even a never-before-seen IP+username is refused — the system-wide
    # circuit-breaker for a distributed attack.
    monkeypatch.setattr(server, "LOGIN_GLOBAL_MAX_FAILS", 3)
    for i in range(3):
        _expect(f"user-{i}", f"203.0.113.{i}", 401)   # 3 distinct IPs & users
    exc = _expect("totally-new-user", "198.51.100.250", 429)
    assert "Retry-After" in exc.headers


def test_global_ceiling_disabled_when_zero(monkeypatch):
    monkeypatch.setattr(server, "LOGIN_GLOBAL_MAX_FAILS", 0)
    for i in range(50):
        _expect(f"user-{i}", f"203.0.113.{i % 200}", 401)
    assert server._login_global == {}


# ----------------------------------------------------------- restart persistence

def test_lock_survives_restart(monkeypatch):
    # Arm a per-IP lock, then simulate a process restart by dropping all in-memory
    # state and reloading from disk. The lock must still be in force.
    monkeypatch.setattr(server, "LOGIN_IP_MAX_FAILS", 3)
    bad_ip = "203.0.113.77"
    for i in range(3):
        _expect(f"u-{i}", bad_ip, 401)
    assert server._locked_for_dim(server._login_ip_fails, bad_ip,
                                  server.time.time()) > 0
    assert os.path.exists(server.LOGIN_THROTTLE_FILE)     # written through

    # --- restart ---
    server._login_fails.clear()
    server._login_ip_fails.clear()
    server._login_global.clear()
    server._login_load()

    assert server._locked_for_dim(server._login_ip_fails, bad_ip,
                                  server.time.time()) > 0
    _expect("anyone", bad_ip, 429)                # still refused after "restart"


def test_global_lock_survives_restart(monkeypatch):
    monkeypatch.setattr(server, "LOGIN_GLOBAL_MAX_FAILS", 3)
    for i in range(3):
        _expect(f"u-{i}", f"203.0.113.{i}", 401)

    server._login_fails.clear()
    server._login_ip_fails.clear()
    server._login_global.clear()
    server._login_load()

    _expect("fresh-user", "198.51.100.1", 429)    # global lock reloaded


def test_username_counter_persists_and_reloads(monkeypatch):
    # The original per-account dimension is now persistent too.
    monkeypatch.setattr(server, "LOGIN_MAX_FAILS", 3)
    _make_user("alice")
    for _ in range(3):
        _expect("alice", "198.51.100.5", 401)  # bad MFA, not a successful login
    server._login_fails.clear()
    server._login_ip_fails.clear()
    server._login_global.clear()
    server._login_load()
    assert server._login_locked_for("alice") > 0

    # also confirm a never-locked key is NOT resurrected by the reload
    assert server._login_locked_for("nobody") == 0


def test_restart_prunes_expired_locks(monkeypatch):
    # A lock whose `until` is already in the past must not be revived on reload.
    server._login_ip_fails["1.2.3.4"] = {
        "stamps": [], "until": server.time.time() - 1}
    server._login_persist()
    server._login_ip_fails.clear()
    server._login_load()
    assert "1.2.3.4" not in server._login_ip_fails


def test_persist_failure_does_not_break_login(monkeypatch):
    # A disk error in the throttle write-through must never surface as a login
    # failure — the throttle degrades to in-memory-only, login still works.
    monkeypatch.setattr(server, "LOGIN_IP_MAX_FAILS", 3)

    def _boom(*a, **k):
        raise OSError("disk full")
    monkeypatch.setattr(server, "_save_json", _boom)
    try:
        # failure path persists -> swallows the OSError, still 401 (not 500)
        _expect("u", "203.0.113.9", 401)
        # the in-memory counter still advanced despite the persist failure
        assert "203.0.113.9" in server._login_ip_fails
    finally:
        monkeypatch.undo()      # restore _save_json before fixture teardown saves
