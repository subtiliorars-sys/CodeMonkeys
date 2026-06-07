"""Wave 4 #5 — GitHub webhook → background run. Focus: the fail-closed gates.

Run: ./.venv/bin/python -m pytest tests/ -q
"""
import hashlib
import hmac
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


def _sig(body: bytes, secret: str) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _payload(sender="alice", label="codemonkeys", title="fix the thing"):
    return {
        "sender": {"login": sender},
        "repository": {"full_name": "o/r"},
        "issue": {"number": 7, "title": title, "body": "details",
                  "labels": [{"name": label}]},
    }


@pytest.fixture
def enabled(monkeypatch):
    # don't actually run the agent — stub the launcher
    monkeypatch.setattr(server, "run_session_message", lambda s, t: None)
    monkeypatch.setattr(server, "WEBHOOK_ENABLED", True)
    monkeypatch.setattr(server, "WEBHOOK_SECRET", "shh")
    monkeypatch.setattr(server, "WEBHOOK_ALLOWED_SENDERS", ["alice"])
    monkeypatch.setattr(server, "WEBHOOK_TRIGGER_LABEL", "codemonkeys")
    yield


def _post(payload, secret="shh", sig=None):
    body = json.dumps(payload).encode()
    headers = {"X-Hub-Signature-256": sig if sig is not None else _sig(body, secret)}
    return client.post("/api/webhook/github", content=body, headers=headers)


def test_disabled_returns_404(monkeypatch):
    monkeypatch.setattr(server, "WEBHOOK_ENABLED", False)
    r = client.post("/api/webhook/github", content=b"{}",
                    headers={"X-Hub-Signature-256": "sha256=x"})
    assert r.status_code == 404


def test_bad_signature_rejected(enabled):
    r = _post(_payload(), sig="sha256=deadbeef")
    assert r.status_code == 401


def test_missing_signature_rejected(enabled):
    body = json.dumps(_payload()).encode()
    r = client.post("/api/webhook/github", content=body)
    assert r.status_code in (401, 422)


def test_unauthorized_sender_does_not_trigger(enabled):
    r = _post(_payload(sender="mallory"))
    assert r.status_code == 200 and r.json()["triggered"] is False


def test_missing_trigger_label_does_not_trigger(enabled):
    r = _post(_payload(label="bug"))
    assert r.status_code == 200 and r.json()["triggered"] is False


def test_valid_event_triggers_a_session(enabled):
    before = set(server.SESSIONS)
    r = _post(_payload())
    assert r.status_code == 200 and r.json()["triggered"] is True
    sid = r.json()["session"]
    s = server.SESSIONS[sid]
    assert s["mode"] == "auto"                       # unattended → debate-verify guards
    # clean up the created session
    del server.SESSIONS[sid]
    assert before == set(server.SESSIONS)


def test_concurrency_cap(enabled, monkeypatch):
    monkeypatch.setattr(server, "WEBHOOK_MAX_CONCURRENT", 0)   # no capacity
    r = _post(_payload())
    assert r.status_code == 429


def test_verify_helper_fails_closed_without_secret(monkeypatch):
    monkeypatch.setattr(server, "WEBHOOK_SECRET", "")
    assert server._verify_github_sig(b"x", "sha256=anything") is False


def test_signature_is_constant_time_exact_match(monkeypatch):
    monkeypatch.setattr(server, "WEBHOOK_SECRET", "k")
    body = b'{"a":1}'
    good = _sig(body, "k")
    assert server._verify_github_sig(body, good) is True
    assert server._verify_github_sig(body, good[:-1] + "0") is False
