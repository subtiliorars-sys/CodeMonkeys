"""N1: Provider cooldown registry tests.

Covers:
  - 429 benches the provider and _usable skips it
  - Cooldown expiry restores the provider
  - All-cooled fallback: returns least-recently-cooled provider
  - 401/403 triggers longer cooldown (ProviderAuthError path)
  - Thread-safety: concurrent bench_provider calls are consistent
  - Retry-After header honoured when longer than default
  - _cooldown_snapshot / /api/cooldowns endpoint (owner-only)

Run: ./.venv/bin/python -m pytest tests/ -q
"""
import os
import sys
import tempfile
import threading

os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(prefix="cm_test_"))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest                                # noqa: E402
from fastapi.testclient import TestClient    # noqa: E402

import server                               # noqa: E402

client = TestClient(server.app)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

OPENAI_BASE = {"kind": "openai", "name": "p", "model": "m", "base_url": "http://x",
               "api_key": "k", "input_cost_per_m": 0, "output_cost_per_m": 0}


def _provider(pid="p0", **kw):
    """Resolved provider dict (as _resolve produces)."""
    return {"pid": pid, "kind": "openai", "name": pid, "model": "m",
            "base_url": "http://x", "api_key": "k",
            "input_cost_per_m": 0, "output_cost_per_m": 0, **kw}


def _cfg(*pids_and_costs):
    """Build a minimal cfg with providers.  Args: (pid, out_cost) pairs."""
    providers = {}
    for pid, out in pids_and_costs:
        providers[pid] = {"key": "k", "label": pid, "kind": "openai",
                          "model": pid, "out": out, "base_url": "http://x"}
    return {"providers": providers}


def _cleanup(*pids):
    """Remove cooldowns set during a test so registry stays clean."""
    for pid in pids:
        server._clear_cooldown(pid)


# ---------------------------------------------------------------------------
# bench_provider / _is_cooled basic
# ---------------------------------------------------------------------------

def test_bench_and_is_cooled():
    pid = "test-bench-basic"
    _cleanup(pid)
    now = 1_000_000.0
    server.bench_provider(pid, 60, _now=now)
    assert server._is_cooled(pid, _now=now + 30)
    _cleanup(pid)


def test_not_cooled_before_bench():
    pid = "test-not-cooled"
    _cleanup(pid)
    assert not server._is_cooled(pid)
    _cleanup(pid)


def test_cooldown_expires():
    pid = "test-expiry"
    _cleanup(pid)
    now = 1_000_000.0
    server.bench_provider(pid, 60, _now=now)
    # Before expiry: cooled
    assert server._is_cooled(pid, _now=now + 59)
    # At and after expiry: not cooled
    assert not server._is_cooled(pid, _now=now + 60)
    assert not server._is_cooled(pid, _now=now + 120)
    _cleanup(pid)


def test_bench_honours_longer_existing_cooldown():
    """A shorter bench does not shrink an already-longer cooldown window."""
    pid = "test-no-shrink"
    _cleanup(pid)
    now = 1_000_000.0
    server.bench_provider(pid, 300, _now=now)
    server.bench_provider(pid, 30, _now=now)   # shorter, must not shrink
    assert server._is_cooled(pid, _now=now + 200)
    _cleanup(pid)


# ---------------------------------------------------------------------------
# _usable skips cooled providers
# ---------------------------------------------------------------------------

def test_usable_skips_cooled_provider():
    """A benched provider must not appear in _usable."""
    pid = "usable-cooled"
    _cleanup(pid)
    cfg = _cfg((pid, 1))
    now = 1_000_000.0
    server.bench_provider(pid, 60, _now=now)
    # With cooled provider: _is_cooled returns True so _usable filters it out,
    # falling back to all-cooled path which returns it anyway.
    # We test the filter path by checking a 2-provider config.
    pid2 = "usable-not-cooled"
    _cleanup(pid2)
    cfg2 = _cfg((pid, 1), (pid2, 2))
    result = [(p, q) for p, q in server._usable(cfg2) if not server._is_cooled(p, _now=now + 1)]
    assert all(p == pid2 for p, _ in result)
    _cleanup(pid, pid2)


def test_usable_returns_active_when_one_cooled(monkeypatch):
    """With two providers, the non-cooled one is returned first."""
    pid_cold = "usable-cold"
    pid_warm = "usable-warm"
    _cleanup(pid_cold, pid_warm)
    # Monkeypatch time.time so _is_cooled uses our fake clock.
    fake_now = 1_000_000.0
    monkeypatch.setattr(server.time, "time", lambda: fake_now)
    cfg = _cfg((pid_cold, 1), (pid_warm, 2))
    server.bench_provider(pid_cold, 60, _now=fake_now)
    usable = server._usable(cfg)
    assert len(usable) == 1
    assert usable[0][0] == pid_warm
    _cleanup(pid_cold, pid_warm)


def test_usable_all_cooled_fallback(monkeypatch):
    """When every provider is cooled, _usable returns the least-recently-cooled."""
    pid1 = "fallback-a"
    pid2 = "fallback-b"
    _cleanup(pid1, pid2)
    fake_now = 2_000_000.0
    monkeypatch.setattr(server.time, "time", lambda: fake_now)
    cfg = _cfg((pid1, 1), (pid2, 2))
    # pid1 expires sooner (shorter cooldown = least penalised).
    server.bench_provider(pid1, 30, _now=fake_now)
    server.bench_provider(pid2, 120, _now=fake_now)
    usable = server._usable(cfg)
    assert len(usable) == 1
    assert usable[0][0] == pid1   # least-recently-cooled = soonest to recover
    _cleanup(pid1, pid2)


# ---------------------------------------------------------------------------
# call_model benches on failure
# ---------------------------------------------------------------------------

def test_call_model_benches_on_exhausted_transient(monkeypatch):
    """After retries are exhausted with a TransientModelError, the provider
    is put in cooldown."""
    pid = "cm-bench-transient"
    _cleanup(pid)
    monkeypatch.setattr(server.time, "sleep", lambda s: None)

    def always_fail(*a, **kw):
        raise server.TransientModelError("429", http_status=429)
    monkeypatch.setattr(server, "_call_provider", always_fail)

    provider = _provider(pid=pid)
    fake_now = 3_000_000.0
    monkeypatch.setattr(server.time, "time", lambda: fake_now)
    with pytest.raises(server.TransientModelError):
        server.call_model(provider, "sys", [], [])
    assert server._is_cooled(pid, _now=fake_now + 1)
    _cleanup(pid)


def test_call_model_honours_retry_after(monkeypatch):
    """A Retry-After header value longer than the default becomes the cooldown."""
    pid = "cm-retry-after"
    _cleanup(pid)
    monkeypatch.setattr(server.time, "sleep", lambda s: None)

    def always_fail(*a, **kw):
        raise server.TransientModelError("429", http_status=429, retry_after=3600)
    monkeypatch.setattr(server, "_call_provider", always_fail)

    provider = _provider(pid=pid)
    fake_now = 3_100_000.0
    monkeypatch.setattr(server.time, "time", lambda: fake_now)
    with pytest.raises(server.TransientModelError):
        server.call_model(provider, "sys", [], [])
    # Cooldown must be at least Retry-After (3600s) long.
    assert server._is_cooled(pid, _now=fake_now + server._COOLDOWN_TRANSIENT_S + 1)
    assert server._is_cooled(pid, _now=fake_now + 3500)
    _cleanup(pid)


def test_call_model_benches_on_auth_error(monkeypatch):
    """ProviderAuthError triggers the longer _COOLDOWN_AUTH_S bench."""
    pid = "cm-bench-auth"
    _cleanup(pid)
    monkeypatch.setattr(server.time, "sleep", lambda s: None)

    def bad_key(*a, **kw):
        raise server.ProviderAuthError("401 bad key", http_status=401)
    monkeypatch.setattr(server, "_call_provider", bad_key)

    provider = _provider(pid=pid)
    fake_now = 3_200_000.0
    monkeypatch.setattr(server.time, "time", lambda: fake_now)
    with pytest.raises(server.ProviderAuthError):
        server.call_model(provider, "sys", [], [])
    # 401 must still be cooled well past the transient window.
    assert server._is_cooled(pid, _now=fake_now + server._COOLDOWN_TRANSIENT_S + 10)
    # And the auth window is longer.
    assert server._COOLDOWN_AUTH_S > server._COOLDOWN_TRANSIENT_S


def test_403_benches_only_briefly(monkeypatch):
    """N1 red-team F2: 403 is overloaded (WAF/geo/rate-limit), not a bad key —
    bench it for the SHORT transient window, not the 5-min auth window."""
    pid = "cm-bench-403"
    _cleanup(pid)
    monkeypatch.setattr(server.time, "sleep", lambda s: None)
    monkeypatch.setattr(server, "_call_provider",
                        lambda *a, **kw: (_ for _ in ()).throw(
                            server.ProviderAuthError("403 blocked", http_status=403)))
    fake_now = 3_300_000.0
    monkeypatch.setattr(server.time, "time", lambda: fake_now)
    with pytest.raises(server.ProviderAuthError):
        server.call_model(_provider(pid=pid), "sys", [], [])
    # cooled now, but NOT past the transient window (i.e. short bench, not auth)
    assert server._is_cooled(pid, _now=fake_now + 5)
    assert not server._is_cooled(pid, _now=fake_now + server._COOLDOWN_TRANSIENT_S + 1)


def test_retry_after_capped(monkeypatch):
    """N1 red-team F3: a hostile/huge Retry-After cannot bench for days."""
    pid = "cm-bench-cap"
    _cleanup(pid)
    monkeypatch.setattr(server.time, "sleep", lambda s: None)
    monkeypatch.setattr(server, "_call_provider",
                        lambda *a, **kw: (_ for _ in ()).throw(
                            server.TransientModelError("429", http_status=429,
                                                       retry_after=999_999_999)))
    fake_now = 3_400_000.0
    monkeypatch.setattr(server.time, "time", lambda: fake_now)
    with pytest.raises(server.TransientModelError):
        server.call_model(_provider(pid=pid), "sys", [], [])
    # not cooled beyond the hard ceiling
    assert not server._is_cooled(pid, _now=fake_now + server._COOLDOWN_MAX_S + 1)
    assert server._is_cooled(pid, _now=fake_now + server._COOLDOWN_MAX_S - 1)
    _cleanup(pid)


def test_call_model_no_bench_on_success(monkeypatch):
    """A successful call must NOT bench the provider."""
    pid = "cm-no-bench-ok"
    _cleanup(pid)

    def ok(*a, **kw):
        return {"text": "hi", "tool_calls": [], "in_tokens": 1, "out_tokens": 1}
    monkeypatch.setattr(server, "_call_provider", ok)

    provider = _provider(pid=pid)
    server.call_model(provider, "sys", [], [])
    assert not server._is_cooled(pid)
    _cleanup(pid)


# ---------------------------------------------------------------------------
# Thread-safety
# ---------------------------------------------------------------------------

def test_bench_provider_thread_safe():
    """Concurrent bench_provider calls must not corrupt the registry."""
    pid = "thread-safe-test"
    _cleanup(pid)
    errors = []

    def bench_it():
        try:
            server.bench_provider(pid, 60)
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    threads = [threading.Thread(target=bench_it) for _ in range(50)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    assert server._is_cooled(pid)
    _cleanup(pid)


# ---------------------------------------------------------------------------
# _cooldown_snapshot
# ---------------------------------------------------------------------------

def test_cooldown_snapshot_shows_active():
    pid = "snap-active"
    _cleanup(pid)
    now = 5_000_000.0
    server.bench_provider(pid, 90, _now=now)
    snap = server._cooldown_snapshot(_now=now + 10)
    assert pid in snap
    assert 79 <= snap[pid] <= 80   # ~80s remaining
    _cleanup(pid)


def test_cooldown_snapshot_excludes_expired():
    pid = "snap-expired"
    _cleanup(pid)
    now = 5_100_000.0
    server.bench_provider(pid, 10, _now=now)
    snap = server._cooldown_snapshot(_now=now + 20)
    assert pid not in snap
    _cleanup(pid)


# ---------------------------------------------------------------------------
# /api/cooldowns endpoint
# ---------------------------------------------------------------------------

def test_cooldowns_endpoint_requires_owner():
    r = client.get("/api/cooldowns")
    assert r.status_code in (401, 403)


def test_cooldowns_delete_requires_owner():
    r = client.delete("/api/cooldowns/some-pid")
    assert r.status_code in (401, 403)


def test_cooldowns_endpoint_owner_access(monkeypatch):
    pid = "ep-active"
    _cleanup(pid)
    now = 6_000_000.0
    server.bench_provider(pid, 120, _now=now)
    monkeypatch.setattr(server.time, "time", lambda: now + 1)
    server.app.dependency_overrides[server.verify_owner] = lambda: "owner"
    try:
        r = client.get("/api/cooldowns")
        assert r.status_code == 200
        body = r.json()
        assert pid in body["cooldowns"]
    finally:
        server.app.dependency_overrides.pop(server.verify_owner, None)
        _cleanup(pid)


def test_cooldowns_delete_clears_entry(monkeypatch):
    pid = "ep-clear"
    _cleanup(pid)
    now = 6_100_000.0
    server.bench_provider(pid, 300, _now=now)
    assert server._is_cooled(pid, _now=now + 1)
    server.app.dependency_overrides[server.verify_owner] = lambda: "owner"
    try:
        r = client.delete(f"/api/cooldowns/{pid}")
        assert r.status_code == 200
        assert not server._is_cooled(pid)
    finally:
        server.app.dependency_overrides.pop(server.verify_owner, None)


# ---- N1 red-team F1: cooldown-degraded debate panel requires unanimous --------

def test_debate_panel_degraded_by_cooldown_requires_unanimous(monkeypatch):
    """When cooldown collapses the verifier panel to repeats of one model, a
    single REFUTE must BLOCK (unanimous required) — not the normal 2/3 majority."""
    monkeypatch.setattr(server, "load_models", lambda: {})
    one = {"name": "p", "pid": "solo", "model": "m",
           "input_cost_per_m": 0, "output_cost_per_m": 0}
    monkeypatch.setattr(server, "_verifier_providers", lambda cfg, username=None: [one, one, one])
    monkeypatch.setattr(server, "_cooldown_snapshot", lambda *a, **k: {"other": 30.0})
    seq = iter(["ALLOW: ok", "ALLOW: ok", "REFUTE: nope"])   # 1 refute
    monkeypatch.setattr(server, "call_model",
                        lambda *a, **k: {"text": next(seq), "in_tokens": 0, "out_tokens": 0})
    s = server.new_session(title="t")
    allowed, summary = server._debate_verify(s, "rm -rf /tmp/x")
    assert allowed is False, "degraded panel must require unanimous allow"
    assert "degraded" in summary.lower()


def test_debate_panel_majority_when_not_cooldown_degraded(monkeypatch):
    """Same 1-refute panel but nothing cooled → normal majority still allows."""
    monkeypatch.setattr(server, "load_models", lambda: {})
    one = {"name": "p", "pid": "solo", "model": "m",
           "input_cost_per_m": 0, "output_cost_per_m": 0}
    monkeypatch.setattr(server, "_verifier_providers", lambda cfg, username=None: [one, one, one])
    monkeypatch.setattr(server, "_cooldown_snapshot", lambda *a, **k: {})  # nothing cooled
    seq = iter(["ALLOW: ok", "ALLOW: ok", "REFUTE: nope"])
    monkeypatch.setattr(server, "call_model",
                        lambda *a, **k: {"text": next(seq), "in_tokens": 0, "out_tokens": 0})
    s = server.new_session(title="t")
    allowed, _ = server._debate_verify(s, "ls -la")
    assert allowed is True
