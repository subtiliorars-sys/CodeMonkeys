"""Tests covering the 5 security findings from AUDIT-2026-06.

C-1 — import re typo fixed (server imports without crashing)
C-2 — must_reset accounts require PIN at login; verify_token blocks them
H-1 — _client_ip returns None when X-Forwarded-For present without Fly-Client-IP
H-2 — Member session budget capped at MEMBER_SESSION_BUDGET_MAX_USD
H-3 — startup warning emitted when CM_MASTER_KEY is unset

Run: ./.venv/Scripts/python.exe -m pytest tests/test_security_remediation.py -q
"""
import importlib
import logging
import os
import sys
import tempfile

os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(prefix="cm_sectest_"))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pyotp   # noqa: E402
import pytest  # noqa: E402

import server  # noqa: E402

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

class _Client:
    def __init__(self, host):
        self.host = host


class FakeReq:
    """Minimal Request stand-in for _client_ip()."""
    def __init__(self, fly_ip=None, client_host=None, xff=None):
        self.headers = {}
        if fly_ip:
            self.headers["Fly-Client-IP"] = fly_ip
        if xff:
            self.headers["x-forwarded-for"] = xff
        self.client = _Client(client_host) if client_host else None


def _make_full_user(username="alice", role="Owner"):
    """Create a fully set-up user with TOTP."""
    mfa = pyotp.random_base32()
    users = server.load_users()
    users[username] = {
        "role": role,
        "mfa_secret": mfa,
        "must_reset": False,
        "created": 1,
    }
    server.save_users(users)
    return mfa


def _make_invited_user(username="invitee"):
    """Create an invited (must_reset) user with pin_hash."""
    setup_pin = "ABCDEF"
    salt = "deadbeef" * 4          # 32 hex chars = 16 bytes
    pin_h = server.hash_pin(setup_pin, salt)
    users = server.load_users()
    users[username] = {
        "role": "Member",
        "mfa_secret": "",
        "must_reset": True,
        "created": 2,
        "pin_hash": pin_h,
        "salt": salt,
    }
    server.save_users(users)
    return setup_pin


@pytest.fixture(autouse=True)
def clean_state():
    server._login_fails.clear()
    server._login_ip_fails.clear()
    server._login_global.clear()
    server.save_users({})
    yield
    server._login_fails.clear()
    server._login_ip_fails.clear()
    server._login_global.clear()
    server.save_users({})


# ---------------------------------------------------------------------------
# C-1 — import re
# ---------------------------------------------------------------------------

def test_c1_server_imports_without_crash():
    """server.py must import without ModuleNotFoundError (C-1: was 'import rehh')."""
    import re as _re
    # If we got here, the module imported. Also confirm `re` is accessible
    # by testing a call that server uses extensively.
    assert _re.fullmatch(r"\w+", "hello")


def test_c1_re_module_used_correctly():
    """Verify server uses re.fullmatch (a call that would fail if re missing)."""
    # register() calls re.fullmatch internally; a valid username must succeed
    result = server.re.fullmatch(r"[A-Za-z0-9_.-]{2,32}", "alice")
    assert result is not None


# ---------------------------------------------------------------------------
# C-2 — must_reset PIN + verify_token gate
# ---------------------------------------------------------------------------

def test_c2_invite_creates_pin_hash():
    """New invites must produce a setup_pin and store pin_hash in users.json."""
    # Need an Owner to call invite
    _make_full_user("boss", role="Owner")
    result = server.invite(
        server.InviteRequest(username="newdev"),
        _="boss",  # dependency override not needed for direct call
    )
    assert "setup_pin" in result, "invite response must include setup_pin"
    assert "username" in result
    uname = result["username"]
    users = server.load_users()
    assert "pin_hash" in users[uname], "pin_hash must be stored for invited user"
    assert "salt" in users[uname], "salt must be stored for invited user"


def test_c2_must_reset_login_requires_pin():
    """Login for a must_reset account must 401 when the setup PIN is missing."""
    _make_invited_user("invitee")
    with pytest.raises(server.HTTPException) as ei:
        server.login(server.LoginRequest(username="invitee", mfa_code=""))
    assert ei.value.status_code == 401
    assert "PIN" in ei.value.detail or "pin" in ei.value.detail.lower()


def test_c2_must_reset_login_rejects_bad_pin():
    """Login for a must_reset account must 401 on a wrong PIN."""
    _make_invited_user("invitee")
    with pytest.raises(server.HTTPException) as ei:
        server.login(server.LoginRequest(username="invitee", mfa_code="ZZZZZZ"))
    assert ei.value.status_code == 401


def test_c2_must_reset_login_accepts_correct_pin():
    """Login for a must_reset account must succeed with the correct setup PIN."""
    pin = _make_invited_user("invitee")
    result = server.login(server.LoginRequest(username="invitee", mfa_code=pin))
    assert "token" in result
    assert result.get("must_reset") is True


def test_c2_verify_token_blocks_must_reset_accounts():
    """verify_token must raise 403 for must_reset accounts (C-2 gate)."""
    _make_invited_user("invitee")
    # Obtain a valid must_reset token
    pin = "ABCDEF"  # matches _make_invited_user default
    token = server.make_token("invitee")
    # verify_token must refuse it
    with pytest.raises(server.HTTPException) as ei:
        server.verify_token(authorization=f"Bearer {token}")
    assert ei.value.status_code == 403
    assert "setup" in ei.value.detail.lower()


def test_c2_verify_invite_token_allows_must_reset():
    """verify_invite_token must accept tokens for must_reset accounts."""
    _make_invited_user("invitee")
    token = server.make_token("invitee")
    username = server.verify_invite_token(authorization=f"Bearer {token}")
    assert username == "invitee"


def test_c2_full_user_accepted_by_verify_token():
    """verify_token must still pass for fully set-up (non-must_reset) accounts."""
    _make_full_user("alice")
    token = server.make_token("alice")
    username = server.verify_token(authorization=f"Bearer {token}")
    assert username == "alice"


# ---------------------------------------------------------------------------
# H-1 — _client_ip skips socket-peer fallback when X-Forwarded-For present
# ---------------------------------------------------------------------------

def test_h1_fly_client_ip_trusted():
    """Fly-Client-IP header is always used when present."""
    req = FakeReq(fly_ip="1.2.3.4")
    assert server._client_ip(req) == "1.2.3.4"


def test_h1_xff_without_fly_ip_returns_none():
    """If X-Forwarded-For is present without Fly-Client-IP, return None.
    This prevents throttle bypass via uvicorn's --forwarded-allow-ips=* behaviour."""
    req = FakeReq(xff="5.6.7.8", client_host="5.6.7.8")
    ip = server._client_ip(req)
    assert ip is None, (
        "H-1: _client_ip must return None when XFF is present without Fly-Client-IP "
        "to avoid acting on a potentially-spoofed socket peer."
    )


def test_h1_no_proxy_headers_uses_socket_peer():
    """Without any proxy headers, fall back to the socket peer (correct for direct connections)."""
    req = FakeReq(client_host="10.0.0.1")
    assert server._client_ip(req) == "10.0.0.1"


def test_h1_fly_ip_takes_priority_over_xff():
    """Fly-Client-IP wins even if X-Forwarded-For is also set."""
    req = FakeReq(fly_ip="1.1.1.1", xff="evil.attacker.ip", client_host="evil.attacker.ip")
    assert server._client_ip(req) == "1.1.1.1"


def test_h1_dead_client_ip_definition_removed():
    """Verify there is only ONE definition of _client_ip (the dead one at old line 1136
    read x-forwarded-for directly and is now removed)."""
    import inspect, ast
    src = inspect.getsource(server)
    tree = ast.parse(src)
    defs = [n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)
            and n.name == "_client_ip"]
    assert len(defs) == 1, f"Expected 1 _client_ip definition, found {len(defs)}"


# ---------------------------------------------------------------------------
# H-2 — Member session budget cap
# ---------------------------------------------------------------------------

def test_h2_member_budget_capped():
    """A Member cannot create a session with budget_usd > MEMBER_SESSION_BUDGET_MAX_USD."""
    _make_full_user("boss", role="Owner")
    _make_full_user("member", role="Member")
    cap = server.MEMBER_SESSION_BUDGET_MAX_USD
    with pytest.raises(server.HTTPException) as ei:
        server.session_create(
            server.SessionCreate(title="t", budget_usd=cap + 10.0),
            username="member",
        )
    assert ei.value.status_code == 403
    assert "MEMBER_SESSION_BUDGET_MAX_USD" in ei.value.detail


def test_h2_owner_not_capped_by_member_limit():
    """Owners can still set budget_usd up to SESSION_BUDGET_MAX_USD."""
    _make_full_user("boss", role="Owner")
    cap = server.SESSION_BUDGET_MAX_USD
    # Should not raise
    s = server.session_create(
        server.SessionCreate(title="t", budget_usd=cap),
        username="boss",
    )
    assert "id" in s


def test_h2_member_default_budget_respects_cap(monkeypatch):
    """When a Member omits budget_usd, the effective budget must not exceed the Member cap."""
    _make_full_user("member", role="Member")
    low_cap = 1.0
    monkeypatch.setattr(server, "MEMBER_SESSION_BUDGET_MAX_USD", low_cap)
    monkeypatch.setattr(server, "SESSION_BUDGET_USD", 5.0)  # higher than member cap
    s = server.session_create(
        server.SessionCreate(title="t"),
        username="member",
    )
    sid = s["id"]
    assert server.session_budget(server.SESSIONS[sid]) <= low_cap


# ---------------------------------------------------------------------------
# H-3 — startup warning when CM_MASTER_KEY unset
# ---------------------------------------------------------------------------

def test_h3_startup_warning_when_no_master_key(monkeypatch, caplog):
    """_startup_security_warnings must emit a WARNING when CM_MASTER_KEY is empty."""
    monkeypatch.setattr(server, "CM_MASTER_KEY", "")
    with caplog.at_level(logging.WARNING, logger="server"):
        server._startup_security_warnings()
    assert any(
        "CM_MASTER_KEY" in r.message and r.levelno == logging.WARNING
        for r in caplog.records
    ), "Expected a WARNING log mentioning CM_MASTER_KEY when key is unset"


def test_h3_no_warning_when_master_key_set(monkeypatch, caplog):
    """_startup_security_warnings must NOT emit a warning when CM_MASTER_KEY is set."""
    monkeypatch.setattr(server, "CM_MASTER_KEY", "a-high-entropy-random-key-12345")
    with caplog.at_level(logging.WARNING, logger="server"):
        server._startup_security_warnings()
    assert not any(
        "CM_MASTER_KEY" in r.message
        for r in caplog.records
    ), "No WARNING expected when CM_MASTER_KEY is set"
