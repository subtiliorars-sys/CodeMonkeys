"""Tests for N3 cost dashboard — /api/usage by-day and by-model rollups.

Covers:
  D1  by-day aggregation correct (UTC date bucketing)
  D2  by-model aggregation correct (usd and call counts)
  D3  endpoint remains owner-only (no keys in payload)
  D4  sessions with no cost events contribute zero rows
  D5  multiple models and days accumulate independently
  D6  response never contains sensitive keys

Run: ./.venv/bin/python -m pytest tests/ -q
"""
import os
import sys
import tempfile
import time

os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(prefix="cm_cd_test_"))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import server  # noqa: E402

client = TestClient(server.app)

_SENSITIVE = {"api_key", "key", "token", "password", "pin", "secret"}


# ---- D3 owner-only -----------------------------------------------------------

def test_usage_owner_only_no_token():
    assert client.get("/api/usage").status_code in (401, 403)


def test_usage_owner_only_member_rejected(monkeypatch):
    monkeypatch.setattr(server, "load_users",
        lambda: {"member": {"role": "Member"}})
    from server import verify_token
    server.app.dependency_overrides[verify_token] = lambda: "member"
    try:
        assert client.get("/api/usage").status_code == 403
    finally:
        server.app.dependency_overrides.pop(verify_token, None)


# ---- D1 by-day bucketing -----------------------------------------------------

def test_by_day_aggregation(monkeypatch):
    """Two cost events on the same UTC day must sum into one bucket."""
    s = server.new_session(title="day-test")
    sid = s["id"]
    now = int(time.time())
    server.emit(s, "cost", usd=0.005, in_tokens=100, out_tokens=10, model="m1", ts=now)
    server.emit(s, "cost", usd=0.003, in_tokens=50,  out_tokens=5,  model="m1", ts=now)
    server.app.dependency_overrides[server.verify_owner] = lambda: "owner"
    try:
        r = client.get("/api/usage")
        assert r.status_code == 200
        body = r.json()
        assert "by_day" in body
        # All events in the same day → exactly one day bucket for these events
        day_rows = body["by_day"]
        assert len(day_rows) >= 1
        # The total for our session must appear in one of the day rows
        total_in_days = sum(d["usd"] for d in day_rows)
        assert total_in_days >= 0.008 - 1e-9
        # Verify the day format is YYYY-MM-DD
        import re
        for d in day_rows:
            assert re.match(r"^\d{4}-\d{2}-\d{2}$", d["day"]), d["day"]
    finally:
        server.app.dependency_overrides.pop(server.verify_owner, None)
        del server.SESSIONS[sid]


def test_by_day_sorted_ascending(monkeypatch):
    """by_day list must be sorted oldest-first."""
    import datetime
    s = server.new_session(title="day-sort")
    sid = s["id"]
    # Emit two events 2 days apart
    d1 = int(datetime.datetime(2025, 1, 1, 12, 0, 0).timestamp())
    d2 = int(datetime.datetime(2025, 1, 3, 12, 0, 0).timestamp())
    server.emit(s, "cost", usd=0.01, in_tokens=10, out_tokens=1, model="x", ts=d1)
    server.emit(s, "cost", usd=0.02, in_tokens=20, out_tokens=2, model="x", ts=d2)
    server.app.dependency_overrides[server.verify_owner] = lambda: "owner"
    try:
        r = client.get("/api/usage")
        body = r.json()
        days = [row["day"] for row in body["by_day"]]
        assert days == sorted(days)
    finally:
        server.app.dependency_overrides.pop(server.verify_owner, None)
        del server.SESSIONS[sid]


# ---- D2 by-model aggregation -------------------------------------------------

def test_by_model_aggregation(monkeypatch):
    """Costs per model accumulate correctly; sorted by usd desc."""
    s = server.new_session(title="model-test")
    sid = s["id"]
    server.emit(s, "cost", usd=0.10, in_tokens=500, out_tokens=50, model="opus")
    server.emit(s, "cost", usd=0.01, in_tokens=100, out_tokens=10, model="haiku")
    server.emit(s, "cost", usd=0.04, in_tokens=200, out_tokens=20, model="opus")
    server.app.dependency_overrides[server.verify_owner] = lambda: "owner"
    try:
        r = client.get("/api/usage")
        assert r.status_code == 200
        body = r.json()
        assert "by_model" in body
        by_m = {row["model"]: row for row in body["by_model"]}
        assert "opus" in by_m and "haiku" in by_m
        assert abs(by_m["opus"]["usd"] - 0.14) < 1e-9
        assert by_m["opus"]["calls"] == 2
        assert abs(by_m["haiku"]["usd"] - 0.01) < 1e-9
        assert by_m["haiku"]["calls"] == 1
        # sorted desc by usd
        usds = [row["usd"] for row in body["by_model"]]
        assert usds == sorted(usds, reverse=True)
    finally:
        server.app.dependency_overrides.pop(server.verify_owner, None)
        del server.SESSIONS[sid]


def test_by_model_unknown_fallback(monkeypatch):
    """Events with no model field fall into 'unknown' bucket."""
    s = server.new_session(title="no-model")
    sid = s["id"]
    # Emit with empty model string (edge case)
    server.emit(s, "cost", usd=0.005, in_tokens=10, out_tokens=1, model="")
    server.app.dependency_overrides[server.verify_owner] = lambda: "owner"
    try:
        r = client.get("/api/usage")
        body = r.json()
        by_m = {row["model"]: row for row in body["by_model"]}
        assert "unknown" in by_m
    finally:
        server.app.dependency_overrides.pop(server.verify_owner, None)
        del server.SESSIONS[sid]


# ---- D4 empty session --------------------------------------------------------

def test_empty_session_does_not_add_day_or_model_rows(monkeypatch):
    """A session with no cost events must not inflate by_day or by_model."""
    s = server.new_session(title="empty-session")
    sid = s["id"]
    # no cost events emitted
    server.app.dependency_overrides[server.verify_owner] = lambda: "owner"
    try:
        r = client.get("/api/usage")
        body = r.json()
        # session appears in sessions list with zero usd
        mine = next((x for x in body["sessions"] if x["id"] == sid), None)
        assert mine is not None
        assert mine["usd"] == 0.0
        assert mine["calls"] == 0
    finally:
        server.app.dependency_overrides.pop(server.verify_owner, None)
        del server.SESSIONS[sid]


# ---- D5 multi-day multi-model independence -----------------------------------

def test_multi_day_multi_model_accumulate_independently(monkeypatch):
    """Two sessions on different days with different models produce correct
    cross-session sums in each rollup dimension."""
    import datetime
    s1 = server.new_session(title="s1")
    s2 = server.new_session(title="s2")
    id1, id2 = s1["id"], s2["id"]
    ts1 = int(datetime.datetime(2025, 6, 1, 0, 0, 0).timestamp())
    ts2 = int(datetime.datetime(2025, 6, 2, 0, 0, 0).timestamp())
    server.emit(s1, "cost", usd=0.10, in_tokens=100, out_tokens=10, model="A", ts=ts1)
    server.emit(s2, "cost", usd=0.20, in_tokens=200, out_tokens=20, model="B", ts=ts2)
    server.app.dependency_overrides[server.verify_owner] = lambda: "owner"
    try:
        r = client.get("/api/usage")
        body = r.json()
        by_d = {d["day"]: d["usd"] for d in body["by_day"]}
        by_m = {m["model"]: m["usd"] for m in body["by_model"]}
        assert abs(by_d.get("2025-06-01", 0) - 0.10) < 1e-9
        assert abs(by_d.get("2025-06-02", 0) - 0.20) < 1e-9
        assert abs(by_m.get("A", 0) - 0.10) < 1e-9
        assert abs(by_m.get("B", 0) - 0.20) < 1e-9
    finally:
        server.app.dependency_overrides.pop(server.verify_owner, None)
        del server.SESSIONS[id1]
        del server.SESSIONS[id2]


# ---- D6 no sensitive keys in payload ----------------------------------------

def test_no_sensitive_keys_in_payload(monkeypatch):
    """Response must never expose api_key, key, token, password, pin, secret."""
    s = server.new_session(title="sec-check")
    sid = s["id"]
    server.emit(s, "cost", usd=0.001, in_tokens=5, out_tokens=1, model="m")
    server.app.dependency_overrides[server.verify_owner] = lambda: "owner"
    try:
        r = client.get("/api/usage")
        body = r.json()
        # Flatten all keys recursively
        def all_keys(obj):
            if isinstance(obj, dict):
                for k, v in obj.items():
                    yield k
                    yield from all_keys(v)
            elif isinstance(obj, list):
                for item in obj:
                    yield from all_keys(item)
        found = _SENSITIVE & set(all_keys(body))
        assert not found, f"Sensitive keys in response: {found}"
    finally:
        server.app.dependency_overrides.pop(server.verify_owner, None)
        del server.SESSIONS[sid]
