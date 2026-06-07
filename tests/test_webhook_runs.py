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


def _payload(sender="alice", label="codemonkeys", title="fix the thing",
             action="opened", number=7, comment=None):
    p = {
        "action": action,
        "sender": {"login": sender},
        "repository": {"full_name": "o/r"},
        "issue": {"number": number, "title": title, "body": "details",
                  "labels": [{"name": label}]},
    }
    if comment is not None:
        p["comment"] = comment
    return p


@pytest.fixture
def enabled(monkeypatch):
    # don't actually run the agent — stub the launcher
    monkeypatch.setattr(server, "run_session_message", lambda s, t: None)
    monkeypatch.setattr(server, "WEBHOOK_ENABLED", True)
    monkeypatch.setattr(server, "WEBHOOK_SECRET", "shh")
    monkeypatch.setattr(server, "WEBHOOK_ALLOWED_SENDERS", ["alice"])
    monkeypatch.setattr(server, "WEBHOOK_TRIGGER_LABEL", "codemonkeys")
    monkeypatch.setattr(server, "_webhook_seen", {})   # fresh dedup per test
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


def test_non_trigger_action_does_not_trigger(enabled):
    # GitHub fires edited/assigned/closed etc. with the label still attached
    for action in ("edited", "assigned", "closed", "unlabeled"):
        r = _post(_payload(action=action))
        assert r.status_code == 200 and r.json()["triggered"] is False


def test_duplicate_delivery_deduped(enabled):
    r1 = _post(_payload(action="opened", number=42))
    assert r1.json()["triggered"] is True
    # GitHub fires `labeled` for the same issue right after `opened`
    r2 = _post(_payload(action="labeled", number=42))
    assert r2.status_code == 200 and r2.json()["triggered"] is False
    assert r2.json().get("deduped") is True
    del server.SESSIONS[r1.json()["session"]]


def test_comment_created_triggers_and_redelivery_deduped(enabled):
    c = {"id": 9001, "body": "please also fix the docs"}
    r1 = _post(_payload(action="created", number=43, comment=c))
    assert r1.json()["triggered"] is True
    r2 = _post(_payload(action="created", number=43, comment=c))   # redelivery
    assert r2.json()["triggered"] is False and r2.json().get("deduped") is True
    # a comment with a non-created action (edited/deleted) never triggers
    r3 = _post(_payload(action="edited", number=43,
                        comment={"id": 9002, "body": "x"}))
    assert r3.json()["triggered"] is False
    del server.SESSIONS[r1.json()["session"]]


def test_oversized_body_rejected(enabled, monkeypatch):
    monkeypatch.setattr(server, "WEBHOOK_MAX_BODY_BYTES", 64)
    p = _payload()
    r = _post(p)
    assert r.status_code == 413


def test_non_dict_payload_rejected(enabled):
    body = json.dumps(["not", "a", "dict"]).encode()
    r = client.post("/api/webhook/github", content=body,
                    headers={"X-Hub-Signature-256": _sig(body, "shh")})
    assert r.status_code == 400


def test_concurrency_cap(enabled, monkeypatch):
    monkeypatch.setattr(server, "WEBHOOK_MAX_CONCURRENT", 0)   # no capacity
    r = _post(_payload())
    assert r.status_code == 429
    # a 429'd delivery is NOT marked seen — GitHub's redelivery can succeed later
    monkeypatch.setattr(server, "WEBHOOK_MAX_CONCURRENT", 2)
    r2 = _post(_payload())
    assert r2.json()["triggered"] is True
    del server.SESSIONS[r2.json()["session"]]


def test_verify_helper_fails_closed_without_secret(monkeypatch):
    monkeypatch.setattr(server, "WEBHOOK_SECRET", "")
    assert server._verify_github_sig(b"x", "sha256=anything") is False


def test_signature_is_constant_time_exact_match(monkeypatch):
    monkeypatch.setattr(server, "WEBHOOK_SECRET", "k")
    body = b'{"a":1}'
    good = _sig(body, "k")
    assert server._verify_github_sig(body, good) is True
    assert server._verify_github_sig(body, good[:-1] + "0") is False
