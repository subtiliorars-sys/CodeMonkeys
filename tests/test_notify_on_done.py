"""Notify-on-done (Standing list S5): best-effort outbound ping when a session
run finishes. OFF unless NOTIFY_WEBHOOK_URL is set; ops-metadata only; optional
HMAC; failures never affect the run.

Run: ./.venv/bin/python -m pytest tests/ -q
"""
import hashlib
import hmac
import json
import os
import sys
import tempfile
import threading

os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(prefix="cm_test_"))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

import server  # noqa: E402


class _Capture:
    """Stand-in for requests.post that records the call and waits for it."""
    def __init__(self):
        self.calls = []
        self.event = threading.Event()

    def __call__(self, url, data=None, headers=None, timeout=None, **kw):
        self.calls.append({"url": url, "data": data, "headers": headers or {},
                           "timeout": timeout, "kw": kw})
        self.event.set()
        return None


@pytest.fixture
def cap(monkeypatch):
    c = _Capture()
    monkeypatch.setattr(server.requests, "post", c)
    return c


def _session(title="t", repo="r", spent=0.5):
    s = server.new_session(title=title, repo=repo)
    s["spent_usd"] = spent
    return s


def _wait(cap, timeout=2.0):
    assert cap.event.wait(timeout), "no outbound POST fired"
    # the daemon thread may still be finishing the append; tiny settle
    return cap.calls[0]


# ---- gating ------------------------------------------------------------------

def test_no_url_means_no_call(cap, monkeypatch):
    monkeypatch.setattr(server, "NOTIFY_WEBHOOK_URL", "")
    server._notify_done(_session(), errored=False)
    assert cap.calls == []


def test_notify_on_error_only_skips_ok(cap, monkeypatch):
    monkeypatch.setattr(server, "NOTIFY_WEBHOOK_URL", "https://ntfy.example/x")
    monkeypatch.setattr(server, "NOTIFY_ON", "error")
    server._notify_done(_session(), errored=False)
    # give any (erroneous) thread a moment
    assert not cap.event.wait(0.3)
    assert cap.calls == []


def test_notify_on_error_only_fires_on_error(cap, monkeypatch):
    monkeypatch.setattr(server, "NOTIFY_WEBHOOK_URL", "https://ntfy.example/x")
    monkeypatch.setattr(server, "NOTIFY_ON", "error")
    server._notify_done(_session(), errored=True)
    call = _wait(cap)
    assert json.loads(call["data"])["status"] == "error"


# ---- payload shape -----------------------------------------------------------

def test_payload_is_ops_metadata_only(cap, monkeypatch):
    monkeypatch.setattr(server, "NOTIFY_WEBHOOK_URL", "https://ntfy.example/x")
    monkeypatch.setattr(server, "NOTIFY_ON", "all")
    s = _session(title="build feature", repo="owner/repo", spent=1.2345)
    s["history"].append({"role": "user", "text": "SECRET-PROMPT-CONTENT"})
    server._notify_done(s, errored=False)
    call = _wait(cap)
    body = json.loads(call["data"])
    assert body["source"] == "codemonkeys" and body["event"] == "session_done"
    assert body["title"] == "build feature" and body["repo"] == "owner/repo"
    assert body["status"] == "ok" and body["spent_usd"] == 1.2345
    assert b"SECRET-PROMPT-CONTENT" not in call["data"]     # no history/prompt
    assert set(body) <= {"source", "event", "session", "title", "repo",
                         "status", "outcome", "spent_usd", "ts"}


def test_secret_in_title_is_withheld(cap, monkeypatch):
    monkeypatch.setattr(server, "NOTIFY_WEBHOOK_URL", "https://ntfy.example/x")
    monkeypatch.setattr(server, "NOTIFY_ON", "all")
    s = _session(title="key sk-AAAABBBBCCCCDDDDEEEEFFFF1234567")
    server._notify_done(s, errored=False)
    call = _wait(cap)
    assert b"sk-AAAABBBB" not in call["data"]
    assert json.loads(call["data"])["title"] == "(withheld)"


# ---- HMAC --------------------------------------------------------------------

def test_hmac_signature_present_and_correct(cap, monkeypatch):
    monkeypatch.setattr(server, "NOTIFY_WEBHOOK_URL", "https://ntfy.example/x")
    monkeypatch.setattr(server, "NOTIFY_ON", "all")
    monkeypatch.setattr(server, "NOTIFY_WEBHOOK_SECRET", "topsecret")
    server._notify_done(_session(), errored=False)
    call = _wait(cap)
    sig = call["headers"].get("X-CodeMonkeys-Signature", "")
    assert sig.startswith("sha256=")
    expect = "sha256=" + hmac.new(b"topsecret", call["data"], hashlib.sha256).hexdigest()
    assert hmac.compare_digest(sig, expect)


def test_no_signature_header_when_no_secret(cap, monkeypatch):
    monkeypatch.setattr(server, "NOTIFY_WEBHOOK_URL", "https://ntfy.example/x")
    monkeypatch.setattr(server, "NOTIFY_ON", "all")
    monkeypatch.setattr(server, "NOTIFY_WEBHOOK_SECRET", "")
    server._notify_done(_session(), errored=False)
    call = _wait(cap)
    assert "X-CodeMonkeys-Signature" not in call["headers"]


def test_secret_value_never_in_body_or_headers(cap, monkeypatch):
    monkeypatch.setattr(server, "NOTIFY_WEBHOOK_URL", "https://ntfy.example/x")
    monkeypatch.setattr(server, "NOTIFY_ON", "all")
    monkeypatch.setattr(server, "NOTIFY_WEBHOOK_SECRET", "topsecret")
    server._notify_done(_session(), errored=False)
    call = _wait(cap)
    assert b"topsecret" not in call["data"]
    assert "topsecret" not in json.dumps(call["headers"])


# ---- resilience --------------------------------------------------------------

def test_post_failure_is_swallowed(monkeypatch):
    monkeypatch.setattr(server, "NOTIFY_WEBHOOK_URL", "https://ntfy.example/x")
    monkeypatch.setattr(server, "NOTIFY_ON", "all")

    def boom(*a, **k):
        raise RuntimeError("network down")
    monkeypatch.setattr(server.requests, "post", boom)
    # must not raise out of _notify_done or the spawned thread
    server._notify_done(_session(), errored=False)
    for t in threading.enumerate():
        if t is not threading.current_thread() and t.daemon:
            t.join(timeout=1.0)


def test_redirects_disabled(cap, monkeypatch):
    monkeypatch.setattr(server, "NOTIFY_WEBHOOK_URL", "https://ntfy.example/x")
    monkeypatch.setattr(server, "NOTIFY_ON", "all")
    server._notify_done(_session(), errored=False)
    call = _wait(cap)
    assert call["kw"].get("allow_redirects") is False
    assert call["timeout"] == server.NOTIFY_TIMEOUT_S


def test_outcome_field_carried(cap, monkeypatch):
    monkeypatch.setattr(server, "NOTIFY_WEBHOOK_URL", "https://ntfy.example/x")
    monkeypatch.setattr(server, "NOTIFY_ON", "all")
    server._notify_done(_session(), errored=True, outcome="budget")
    call = _wait(cap)
    body = json.loads(call["data"])
    assert body["outcome"] == "budget" and body["status"] == "error"


# ---- red-team R4: errored reflects real terminal outcome, not just exceptions --

def _run_with_provider(monkeypatch, fake_call):
    """Drive run_session_message synchronously with a stubbed model call."""
    monkeypatch.setattr(server, "main_provider",
                        lambda cfg: {"name": "p", "kind": "openai", "model": "m",
                                     "base_url": "http://x", "api_key": "k",
                                     "input_cost_per_m": 0, "output_cost_per_m": 0})
    monkeypatch.setattr(server, "call_model", fake_call)
    monkeypatch.setattr(server, "_pricier_provider", lambda cfg, p: None)


def test_run_outcome_ok_on_clean_finish(monkeypatch):
    _run_with_provider(monkeypatch,
                       lambda *a, **k: {"text": "done", "tool_calls": [],
                                        "in_tokens": 1, "out_tokens": 1})
    s = _session()
    server.run_session_message(s, "hi")
    assert s["_run_outcome"] == "ok"


def test_run_outcome_model_error_when_call_fails(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("provider down")
    _run_with_provider(monkeypatch, boom)
    s = _session()
    server.run_session_message(s, "hi")
    assert s["_run_outcome"] == "model_error"


def test_error_outcome_fires_notify_in_error_mode(cap, monkeypatch):
    monkeypatch.setattr(server, "NOTIFY_WEBHOOK_URL", "https://ntfy.example/x")
    monkeypatch.setattr(server, "NOTIFY_ON", "error")

    def boom(*a, **k):
        raise RuntimeError("provider down")
    _run_with_provider(monkeypatch, boom)
    s = _session()
    server.run_session_message(s, "hi")
    call = _wait(cap)                         # error-mode MUST fire on a model failure
    body = json.loads(call["data"])
    assert body["status"] == "error" and body["outcome"] == "model_error"


def test_clean_run_does_not_fire_in_error_mode(cap, monkeypatch):
    monkeypatch.setattr(server, "NOTIFY_WEBHOOK_URL", "https://ntfy.example/x")
    monkeypatch.setattr(server, "NOTIFY_ON", "error")
    _run_with_provider(monkeypatch,
                       lambda *a, **k: {"text": "done", "tool_calls": [],
                                        "in_tokens": 1, "out_tokens": 1})
    server.run_session_message(_session(), "hi")
    assert not cap.event.wait(0.3)           # ok run → no page in error mode

