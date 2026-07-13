"""M-4 cloud-egress consent gate (issue #67).

Every outbound LLM call funnels through `call_model`; it must be gated on a
recorded, revocable, PER-USER consent decision and FAIL CLOSED (nothing sent)
when consent is absent (explicit mode) or revoked (every mode). Covers:

  - grant -> egress allowed; revoke -> egress blocked (the acceptance pair),
  - absent record blocked in explicit mode / allowed in byok-implied mode
    (revocation still blocks in byok-implied — the Owner-reserved question in
    issue #67 only concerns the ABSENT-record default),
  - the provider function is never reached when the gate refuses,
  - self-service API endpoints (grant/revoke/status, auth required),
  - _debate_verify refuses (fail closed) for a revoked user,
  - unknown EGRESS_CONSENT_MODE falls back to strict, never open,
  - M-7 erasure cascades the consent record away.

Run: ./.venv/bin/python -m pytest tests/test_egress_consent.py -q
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

PROVIDER = {"kind": "openai", "name": "p", "model": "m", "base_url": "http://x",
            "api_key": "k", "input_cost_per_m": 0, "output_cost_per_m": 0}


@pytest.fixture
def consent_env(tmp_path, monkeypatch):
    """Isolated consent store + a stub provider backend that records whether
    any bytes would have left the box."""
    monkeypatch.setattr(server, "EGRESS_CONSENT_FILE",
                        str(tmp_path / "egress_consent.json"))
    monkeypatch.delenv("EGRESS_CONSENT_MODE", raising=False)
    sent = {"n": 0}

    def fake_provider(provider, system, history, tools, max_tokens, **kw):
        sent["n"] += 1
        return {"text": "ok", "tool_calls": [], "in_tokens": 1, "out_tokens": 1}
    monkeypatch.setattr(server, "_call_provider", fake_provider)
    return sent


# ------------------------------------------------ record + gate fundamentals

def test_grant_allows_then_revoke_blocks(consent_env, monkeypatch):
    """The acceptance pair: grant -> egress allowed; revoke -> egress blocked."""
    monkeypatch.setenv("EGRESS_CONSENT_MODE", "explicit")
    sent = consent_env
    server._set_egress_consent("alice", True)
    out = server.call_model(PROVIDER, "sys", [], [], username="alice")
    assert out["text"] == "ok" and sent["n"] == 1

    server._set_egress_consent("alice", False)
    with pytest.raises(server.EgressConsentError):
        server.call_model(PROVIDER, "sys", [], [], username="alice")
    assert sent["n"] == 1          # fail closed: nothing left the box


def test_absent_record_blocks_in_explicit_mode(consent_env, monkeypatch):
    monkeypatch.setenv("EGRESS_CONSENT_MODE", "explicit")
    with pytest.raises(server.EgressConsentError):
        server.call_model(PROVIDER, "sys", [], [], username="nobody")
    assert consent_env["n"] == 0


def test_default_mode_is_explicit_when_env_unset(consent_env):
    """Owner-ratified 2026-07-13 (issue #67): with EGRESS_CONSENT_MODE unset,
    the default is "explicit", not the old "byok-implied" — an absent record
    blocks. `consent_env` already deletes the env var; this locks the default
    in so a future change can't silently loosen it."""
    assert server._egress_consent_mode() == "explicit"
    with pytest.raises(server.EgressConsentError):
        server.call_model(PROVIDER, "sys", [], [], username="nobody")
    assert consent_env["n"] == 0


def test_absent_record_allowed_in_byok_implied_mode(consent_env, monkeypatch):
    """Default mode: owner BYO keys read as consent — current behaviour kept
    until the Owner ratifies the issue-#67 reserved question."""
    monkeypatch.setenv("EGRESS_CONSENT_MODE", "byok-implied")
    out = server.call_model(PROVIDER, "sys", [], [], username="nobody")
    assert out["text"] == "ok" and consent_env["n"] == 1


def test_revocation_blocks_even_in_byok_implied_mode(consent_env, monkeypatch):
    """Revocation is honoured in EVERY mode — only the absent-record default
    is Owner-reserved."""
    monkeypatch.setenv("EGRESS_CONSENT_MODE", "byok-implied")
    server._set_egress_consent("bob", False)
    with pytest.raises(server.EgressConsentError):
        server.call_model(PROVIDER, "sys", [], [], username="bob")
    assert consent_env["n"] == 0


def test_unknown_mode_falls_back_to_strict_not_open(consent_env, monkeypatch):
    monkeypatch.setenv("EGRESS_CONSENT_MODE", "wide-open-please")
    assert server._egress_consent_mode() == "explicit"
    with pytest.raises(server.EgressConsentError):
        server.call_model(PROVIDER, "sys", [], [], username="mallory")
    assert consent_env["n"] == 0


def test_gate_uses_session_owner_when_no_explicit_username(consent_env, monkeypatch):
    """agent_loop passes session=..., not username=... — the gate must pick up
    the session owner, and a mid-run revocation blocks the NEXT call."""
    monkeypatch.setenv("EGRESS_CONSENT_MODE", "explicit")
    session = {"username": "carol", "events": []}
    server._set_egress_consent("carol", True)
    out = server.call_model(PROVIDER, "sys", [], [], session=session)
    assert out["text"] == "ok"
    server._set_egress_consent("carol", False)          # revoke mid-run
    with pytest.raises(server.EgressConsentError):
        server.call_model(PROVIDER, "sys", [], [], session=session)
    assert consent_env["n"] == 1


def test_record_is_timestamped_with_history(consent_env):
    server._set_egress_consent("dave", True)
    rec = server._egress_consent_record("dave")
    assert rec["status"] == "granted" and isinstance(rec["updated_at"], int)
    server._set_egress_consent("dave", False)
    rec = server._egress_consent_record("dave")
    assert rec["status"] == "revoked"
    assert [h["status"] for h in rec["history"]] == ["granted", "revoked"]
    assert all(isinstance(h["ts"], int) for h in rec["history"])


# ------------------------------------------------ debate-verify fails closed

def test_debate_verify_refuses_for_revoked_user(consent_env, monkeypatch):
    monkeypatch.setenv("EGRESS_CONSENT_MODE", "byok-implied")
    server._set_egress_consent("eve", False)
    called = {"n": 0}

    # Match test_debate_verify.py's convention: stub load_models so the real
    # (encrypted, on-disk) config path is never touched by this unit test.
    monkeypatch.setattr(server, "load_models", lambda: {})

    def no_call(*a, **kw):
        called["n"] += 1
        raise AssertionError("verifier must not be called without consent")
    monkeypatch.setattr(server, "call_model", no_call)
    session = {"username": "eve", "events": [], "history": [],
               "spent_usd": 0.0, "id": "s1"}
    allowed, summary = server._debate_verify(session, "rm -rf /")
    assert allowed is False
    assert "consent" in summary and called["n"] == 0


# ------------------------------------------------ self-service API

@pytest.fixture
def api_user(consent_env):
    server.app.dependency_overrides[server.verify_user] = lambda: "frank"
    yield "frank"
    server.app.dependency_overrides.pop(server.verify_user, None)


def test_consent_endpoints_grant_and_revoke(api_user, monkeypatch):
    monkeypatch.setenv("EGRESS_CONSENT_MODE", "explicit")
    r = client.get("/api/me/consent/egress")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] is None and body["effective_allowed"] is False

    r = client.post("/api/me/consent/egress", json={"granted": True})
    assert r.status_code == 200
    assert r.json()["status"] == "granted" and r.json()["effective_allowed"] is True

    r = client.post("/api/me/consent/egress", json={"granted": False})
    assert r.status_code == 200
    assert r.json()["status"] == "revoked" and r.json()["effective_allowed"] is False

    r = client.get("/api/me/consent/egress")
    assert r.json()["status"] == "revoked"


def test_consent_endpoints_require_auth(consent_env):
    assert client.get("/api/me/consent/egress").status_code == 401
    assert client.post("/api/me/consent/egress",
                       json={"granted": True}).status_code == 401


# ------------------------------------------------ M-7 erasure cascade

def test_erasure_cascade_deletes_consent_record(consent_env):
    server._set_egress_consent("gina", True)
    assert server._egress_consent_record("gina") is not None
    cleared = server._erase_user_data("gina")
    assert "egress_consent" in cleared
    assert server._egress_consent_record("gina") is None
