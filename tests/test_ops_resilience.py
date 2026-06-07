"""Tests for Wave-3 ops/resilience (W1-W4):
  W1 /healthz liveness, W3 model-call retry/backoff, W2 escalation-on-failure,
  W4 usage summary endpoint.

Run: ./.venv/bin/python -m pytest tests/ -q
"""
import os
import sys
import tempfile
import threading

os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(prefix="cm_test_"))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import server  # noqa: E402

client = TestClient(server.app)

OPENAI = {"kind": "openai", "name": "p", "model": "m", "base_url": "http://x",
          "api_key": "k", "input_cost_per_m": 0, "output_cost_per_m": 0}


# ---- W1 /healthz -------------------------------------------------------------

def test_healthz_is_unauthenticated_and_leaks_nothing():
    r = client.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "uptime_s" in body and isinstance(body["sessions"], int)
    # no sensitive keys
    assert not (set(body) & {"users", "keys", "providers", "token", "api_key"})


# ---- W3 retry / backoff ------------------------------------------------------

def test_transient_error_is_retried_then_succeeds(monkeypatch):
    monkeypatch.setattr(server.time, "sleep", lambda s: None)   # no real waiting
    calls = {"n": 0}

    def flaky(provider, system, history, tools, max_tokens, **kw):
        calls["n"] += 1
        if calls["n"] < 3:
            raise server.TransientModelError("429 slow down")
        return {"text": "ok", "tool_calls": [], "in_tokens": 1, "out_tokens": 1}
    monkeypatch.setattr(server, "_call_provider", flaky)
    out = server.call_model(OPENAI, "sys", [], [])
    assert out["text"] == "ok" and calls["n"] == 3


def test_transient_error_exhausts_retries_and_raises(monkeypatch):
    monkeypatch.setattr(server.time, "sleep", lambda s: None)
    n = {"n": 0}

    def always_429(*a, **kw):
        n["n"] += 1
        raise server.TransientModelError("429")
    monkeypatch.setattr(server, "_call_provider", always_429)
    with pytest.raises(server.TransientModelError):
        server.call_model(OPENAI, "sys", [], [])
    assert n["n"] == server._MODEL_RETRIES


def test_non_transient_error_is_not_retried(monkeypatch):
    monkeypatch.setattr(server.time, "sleep", lambda s: None)
    n = {"n": 0}

    def bad_key(*a, **kw):
        n["n"] += 1
        raise RuntimeError("HTTP 401 bad key")
    monkeypatch.setattr(server, "_call_provider", bad_key)
    with pytest.raises(RuntimeError):
        server.call_model(OPENAI, "sys", [], [])
    assert n["n"] == 1                      # no retry on a 4xx auth error


def test_openai_maps_retryable_status_to_transient(monkeypatch):
    class FakeResp:
        status_code = 503
        text = "overloaded"

        def json(self):
            return {}
    monkeypatch.setattr(server.requests, "post", lambda *a, **kw: FakeResp())
    with pytest.raises(server.TransientModelError):
        server._chat_openai(OPENAI, "s", [], [], 100)


# ---- W2 escalation -----------------------------------------------------------

def _cfg(*outs):
    return {"providers": {f"p{i}": {"key": "k", "label": f"p{i}", "kind": "openai",
                                    "model": f"m{i}", "out": o, "base_url": "http://x"}
                          for i, o in enumerate(outs)}}


def test_pricier_provider_picks_next_tier_up():
    cur = {"model": "m0", "output_cost_per_m": 1}
    nxt = server._pricier_provider(_cfg(1, 5, 9), cur)
    assert nxt is not None and nxt["model"] == "m1"   # cheapest strictly pricier


def test_pricier_provider_none_at_top_tier():
    cur = {"model": "m1", "output_cost_per_m": 9}
    assert server._pricier_provider(_cfg(1, 9), cur) is None


# ---- W4 usage summary --------------------------------------------------------

def test_usage_summary_requires_owner():
    assert client.get("/api/usage").status_code in (401, 403)


def test_usage_summary_aggregates_ledger(monkeypatch):
    s = server.new_session(title="led")
    sid = s["id"]
    server.emit(s, "cost", usd=0.01, in_tokens=100, out_tokens=20, model="m")
    server.emit(s, "cost", usd=0.02, in_tokens=50, out_tokens=10, model="m")
    server.app.dependency_overrides[server.verify_owner] = lambda: "owner"
    try:
        r = client.get("/api/usage")
        assert r.status_code == 200
        body = r.json()
        mine = [x for x in body["sessions"] if x["id"] == sid][0]
        assert mine["calls"] == 2
        assert abs(mine["usd"] - 0.03) < 1e-9
        assert mine["in_tokens"] == 150 and mine["out_tokens"] == 30
        assert body["total"]["usd"] >= 0.03
    finally:
        server.app.dependency_overrides.pop(server.verify_owner, None)
        del server.SESSIONS[sid]
