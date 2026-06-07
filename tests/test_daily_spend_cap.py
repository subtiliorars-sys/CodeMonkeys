"""Tests for N2 rolling daily spend cap.

Covers:
  - under-cap: loop runs normally
  - over-cap: loop halts with daily_cap outcome and correct message
  - cap unset (0.0): no daily limit (backward compat)
  - UTC day rollover resets the counter
  - persistence: counter survives a simulated restart (_load_daily_spend)
  - owner override raises the cap for the session
  - GET /api/spend/today requires owner
  - POST /api/spend/cap requires owner; raises limit in-process
  - POST /api/spend/reset requires owner; zeroes counter

Run: ./.venv/bin/python -m pytest tests/ -q
"""
import os
import sys
import json
import tempfile
import threading

os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(prefix="cm_test_daily_"))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import server  # noqa: E402

client = TestClient(server.app)

ZERO_COST_PROVIDER = {
    "name": "p", "kind": "openai", "model": "m",
    "base_url": "http://x", "api_key": "k",
    "input_cost_per_m": 0, "output_cost_per_m": 0,
}


# ---- helpers ------------------------------------------------------------------

def _make_session(**kwargs):
    s = server.new_session(title="dtest", **kwargs)
    return s


def _fake_call_model(resp_text="done"):
    """Return a call_model stub that succeeds once then raises StopIteration
    so agent_loop exits cleanly after one turn."""
    calls = {"n": 0}

    def _call(provider, system, history, tools, **kw):
        calls["n"] += 1
        if calls["n"] > 10:
            raise RuntimeError("too many calls in test")
        return {"text": resp_text, "tool_calls": [], "in_tokens": 1, "out_tokens": 1}

    return _call


def _reset_daily(monkeypatch, usd=0.0, date_str=None):
    """Force _daily_state to a known value without touching disk."""
    today = date_str or server._daily_utc_date()
    with server._DAILY_LOCK:
        server._daily_state["date"] = today
        server._daily_state["usd"] = usd
        server._daily_cap_override = 0.0


def _run(session, monkeypatch, call_model_fn=None):
    """Drive agent_loop synchronously (no background thread) with stubbed provider."""
    if call_model_fn is None:
        call_model_fn = _fake_call_model()
    monkeypatch.setattr(server, "main_provider",
                        lambda cfg: ZERO_COST_PROVIDER)
    monkeypatch.setattr(server, "call_model", call_model_fn)
    monkeypatch.setattr(server, "_pricier_provider", lambda cfg, p: None)
    server.run_session_message(session, "hi")


# ---- under-cap: run proceeds -------------------------------------------------

def test_under_cap_loop_runs(monkeypatch):
    _reset_daily(monkeypatch, usd=0.0)
    monkeypatch.setattr(server, "SPEND_DAILY_CAP_USD", 10.0)
    monkeypatch.setattr(server, "_daily_cap_override", 0.0)

    s = _make_session()
    _run(s, monkeypatch)
    assert s.get("_run_outcome") == "ok", f"expected ok, got {s.get('_run_outcome')}"
    del server.SESSIONS[s["id"]]


# ---- over-cap: loop halts with daily_cap outcome -----------------------------

def test_over_cap_halts_loop(monkeypatch):
    _reset_daily(monkeypatch, usd=5.0)
    monkeypatch.setattr(server, "SPEND_DAILY_CAP_USD", 4.99)  # already over
    monkeypatch.setattr(server, "_daily_cap_override", 0.0)

    s = _make_session()
    # give a high session budget so only the daily cap trips
    s["budget_usd"] = 100.0
    _run(s, monkeypatch)
    assert s.get("_run_outcome") == "daily_cap", \
        f"expected daily_cap, got {s.get('_run_outcome')}"

    # error event must carry the cap message
    errors = [e for e in s["events"] if e.get("type") == "error"]
    assert any("Daily spend cap" in e.get("message", "") for e in errors), \
        f"no daily-cap error event found: {errors}"
    del server.SESSIONS[s["id"]]


def test_over_cap_message_includes_values(monkeypatch):
    _reset_daily(monkeypatch, usd=3.5)
    monkeypatch.setattr(server, "SPEND_DAILY_CAP_USD", 2.0)
    monkeypatch.setattr(server, "_daily_cap_override", 0.0)

    s = _make_session()
    s["budget_usd"] = 100.0
    _run(s, monkeypatch)

    errors = [e for e in s["events"] if e.get("type") == "error"]
    cap_msg = next((e["message"] for e in errors if "Daily spend cap" in e.get("message", "")), "")
    assert "$2.00" in cap_msg, f"cap value missing from message: {cap_msg!r}"
    assert "$3.50" in cap_msg or "3.5" in cap_msg, f"total missing from message: {cap_msg!r}"
    del server.SESSIONS[s["id"]]


# ---- cap unset → no daily limit (backward compat) ----------------------------

def test_no_cap_when_zero(monkeypatch):
    """SPEND_DAILY_CAP_USD=0 (default) means no daily cap at all."""
    _reset_daily(monkeypatch, usd=9999.0)
    monkeypatch.setattr(server, "SPEND_DAILY_CAP_USD", 0.0)
    monkeypatch.setattr(server, "_daily_cap_override", 0.0)

    s = _make_session()
    _run(s, monkeypatch)
    # should not hit daily_cap (session budget may trip first, but not daily_cap)
    assert s.get("_run_outcome") != "daily_cap", \
        "daily_cap triggered with no cap configured — backward compat broken"
    del server.SESSIONS[s["id"]]


def test_no_cap_when_env_unset(monkeypatch):
    """Same as above: the feature is inert when the env var was never set."""
    _reset_daily(monkeypatch, usd=9999.0)
    monkeypatch.setattr(server, "SPEND_DAILY_CAP_USD", 0.0)
    monkeypatch.setattr(server, "_daily_cap_override", 0.0)

    s = _make_session()
    _run(s, monkeypatch)
    assert s.get("_run_outcome") != "daily_cap"
    del server.SESSIONS[s["id"]]


# ---- UTC day rollover resets counter -----------------------------------------

def test_rollover_resets_counter(monkeypatch):
    """daily_total_usd() returns 0 when the stored date is yesterday."""
    # set state to yesterday
    import datetime
    yesterday = (datetime.datetime.utcnow() - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    with server._DAILY_LOCK:
        server._daily_state["date"] = yesterday
        server._daily_state["usd"] = 999.0

    total = server.daily_total_usd()
    assert total == 0.0, f"rollover did not reset: got {total}"

    # restore
    _reset_daily(monkeypatch, usd=0.0)


def test_accrue_rollover_creates_new_entry(monkeypatch):
    """_accrue_daily() switches to today even if stored date is yesterday."""
    import datetime
    yesterday = (datetime.datetime.utcnow() - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    with server._DAILY_LOCK:
        server._daily_state["date"] = yesterday
        server._daily_state["usd"] = 999.0

    server._accrue_daily(0.01)

    today = server._daily_utc_date()
    with server._DAILY_LOCK:
        assert server._daily_state["date"] == today
        # only today's 0.01, not yesterday's 999
        assert abs(server._daily_state["usd"] - 0.01) < 1e-9

    _reset_daily(monkeypatch, usd=0.0)


# ---- persistence: counter survives simulated restart -------------------------

def test_persist_and_reload(tmp_path, monkeypatch):
    """_load_daily_spend reads DAILY_SPEND_FILE; counter persists across restart."""
    today = server._daily_utc_date()
    spend_file = tmp_path / "daily_spend.json"
    spend_file.write_text(json.dumps({"date": today, "usd": 7.5}))

    monkeypatch.setattr(server, "DAILY_SPEND_FILE", str(spend_file))
    # reset in-memory to zero so we can detect the reload
    _reset_daily(monkeypatch, usd=0.0)

    server._load_daily_spend()

    total = server.daily_total_usd()
    assert abs(total - 7.5) < 1e-9, f"reload failed: got {total}"

    # cleanup
    _reset_daily(monkeypatch, usd=0.0)


def test_persist_stale_date_rolls_over(tmp_path, monkeypatch):
    """_load_daily_spend ignores a file whose date is not today."""
    import datetime
    yesterday = (datetime.datetime.utcnow() - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    spend_file = tmp_path / "daily_spend.json"
    spend_file.write_text(json.dumps({"date": yesterday, "usd": 99.0}))

    monkeypatch.setattr(server, "DAILY_SPEND_FILE", str(spend_file))
    server._load_daily_spend()

    total = server.daily_total_usd()
    assert total == 0.0, f"stale date not rolled over: got {total}"

    _reset_daily(monkeypatch, usd=0.0)


# ---- owner override raises the cap -------------------------------------------

def test_owner_override_raises_cap(monkeypatch):
    """_daily_cap_override > 0 overrides SPEND_DAILY_CAP_USD."""
    monkeypatch.setattr(server, "SPEND_DAILY_CAP_USD", 1.0)
    monkeypatch.setattr(server, "_daily_cap_override", 50.0)

    assert server.effective_daily_cap() == 50.0

    monkeypatch.setattr(server, "_daily_cap_override", 0.0)
    assert server.effective_daily_cap() == 1.0


def test_override_allows_run_past_base_cap(monkeypatch):
    """With daily spend already above SPEND_DAILY_CAP_USD but below override, run proceeds."""
    _reset_daily(monkeypatch, usd=3.0)
    monkeypatch.setattr(server, "SPEND_DAILY_CAP_USD", 2.0)
    # owner raised the cap in-memory
    with server._DAILY_LOCK:
        server._daily_cap_override = 10.0

    s = _make_session()
    s["budget_usd"] = 100.0
    _run(s, monkeypatch)
    assert s.get("_run_outcome") == "ok", \
        f"expected ok with override cap, got {s.get('_run_outcome')}"

    with server._DAILY_LOCK:
        server._daily_cap_override = 0.0
    _reset_daily(monkeypatch, usd=0.0)
    del server.SESSIONS[s["id"]]


# ---- endpoints require owner -------------------------------------------------

def test_spend_today_requires_owner():
    r = client.get("/api/spend/today")
    assert r.status_code in (401, 403)


def test_spend_cap_requires_owner():
    r = client.post("/api/spend/cap", json={"usd": 5.0})
    assert r.status_code in (401, 403)


def test_spend_reset_requires_owner():
    r = client.post("/api/spend/reset")
    assert r.status_code in (401, 403)


def test_spend_today_returns_correct_fields(monkeypatch):
    today = server._daily_utc_date()
    _reset_daily(monkeypatch, usd=1.23)
    monkeypatch.setattr(server, "SPEND_DAILY_CAP_USD", 5.0)
    monkeypatch.setattr(server, "_daily_cap_override", 0.0)

    server.app.dependency_overrides[server.verify_owner] = lambda: "owner"
    try:
        r = client.get("/api/spend/today")
        assert r.status_code == 200
        body = r.json()
        assert body["date"] == today
        assert abs(body["usd"] - 1.23) < 1e-4
        assert abs(body["cap"] - 5.0) < 1e-4
        assert abs(body["remaining"] - 3.77) < 1e-4
    finally:
        server.app.dependency_overrides.pop(server.verify_owner, None)
        _reset_daily(monkeypatch, usd=0.0)


def test_spend_today_no_cap_returns_null(monkeypatch):
    _reset_daily(monkeypatch, usd=0.5)
    monkeypatch.setattr(server, "SPEND_DAILY_CAP_USD", 0.0)
    monkeypatch.setattr(server, "_daily_cap_override", 0.0)

    server.app.dependency_overrides[server.verify_owner] = lambda: "owner"
    try:
        r = client.get("/api/spend/today")
        assert r.status_code == 200
        body = r.json()
        assert body["cap"] is None
        assert body["remaining"] is None
    finally:
        server.app.dependency_overrides.pop(server.verify_owner, None)
        _reset_daily(monkeypatch, usd=0.0)


def test_post_spend_cap_updates_override(monkeypatch):
    monkeypatch.setattr(server, "_daily_cap_override", 0.0)

    server.app.dependency_overrides[server.verify_owner] = lambda: "owner"
    try:
        r = client.post("/api/spend/cap", json={"usd": 20.0})
        assert r.status_code == 200
        body = r.json()
        assert abs(body["override_usd"] - 20.0) < 1e-9
        assert server.effective_daily_cap() == 20.0
    finally:
        server.app.dependency_overrides.pop(server.verify_owner, None)
        with server._DAILY_LOCK:
            server._daily_cap_override = 0.0


def test_post_spend_cap_zero_clears_override(monkeypatch):
    with server._DAILY_LOCK:
        server._daily_cap_override = 15.0

    server.app.dependency_overrides[server.verify_owner] = lambda: "owner"
    try:
        r = client.post("/api/spend/cap", json={"usd": 0.0})
        assert r.status_code == 200
        assert server._daily_cap_override == 0.0
    finally:
        server.app.dependency_overrides.pop(server.verify_owner, None)


def test_post_spend_reset_zeroes_counter(monkeypatch):
    _reset_daily(monkeypatch, usd=9.0)

    server.app.dependency_overrides[server.verify_owner] = lambda: "owner"
    try:
        r = client.post("/api/spend/reset")
        assert r.status_code == 200
        assert r.json()["usd"] == 0.0
        assert server.daily_total_usd() == 0.0
    finally:
        server.app.dependency_overrides.pop(server.verify_owner, None)


# ---- thread-safety sanity: concurrent accruals don't lose counts ------------

def test_concurrent_accrue(monkeypatch):
    """Multiple threads accruing simultaneously must not lose updates."""
    _reset_daily(monkeypatch, usd=0.0)
    n_threads, per = 20, 0.1
    threads = [threading.Thread(target=server._accrue_daily, args=(per,))
               for _ in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    total = server.daily_total_usd()
    expected = n_threads * per
    assert abs(total - expected) < 1e-6, \
        f"concurrent accrue lost updates: expected {expected}, got {total}"
    _reset_daily(monkeypatch, usd=0.0)
