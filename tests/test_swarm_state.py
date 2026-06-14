"""Tests for GET /api/swarm/state — swarm visualizer live backend feed.

Contract:
  - No auth required
  - Returns { orchestrator, agents, activity, stats }
  - agents: one entry per session with { id, name, status, tier }
  - stats includes: sessions, running, spend_today_usd, model
  - State mapping from session fields:
      stop_flag set or status=="interrupted"  → "blocked"
      status == "running"                     → "running"
      status == "idle" + prior spend          → "done"
      default                                 → "idle"

Run: ./.venv/bin/python -m pytest tests/ -q
"""
import os
import sys
import tempfile
import threading

os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(prefix="cm_swarm_test_"))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import server  # noqa: E402

client = TestClient(server.app)


def _make_session(sid="abc123", title="test-session", status="idle",
                  stop_set=False, spent_usd=0.0, events=None):
    """Build a minimal SESSIONS entry matching the real new_session() shape."""
    flag = threading.Event()
    if stop_set:
        flag.set()
    return {
        "id": sid,
        "title": title,
        "status": status,
        "stop_flag": flag,
        "spent_usd": spent_usd,
        "events": events or [],
        "lock": threading.Lock(),
    }


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.setattr(server, "SESSIONS", {})
    # Silence model lookup — no provider configured in test env
    monkeypatch.setattr(server, "load_models", lambda: {"providers": {}})
    monkeypatch.setattr(server, "main_provider", lambda cfg, username=None: None)
    monkeypatch.setattr(server, "daily_total_usd", lambda: 0.0)
    yield


# ── No-sessions baseline ──────────────────────────────────────────────────────

def test_empty_sessions_200_agents_empty(monkeypatch):
    r = client.get("/api/swarm/state")
    assert r.status_code == 200
    body = r.json()
    assert body["agents"] == []


def test_empty_sessions_stats_zero(monkeypatch):
    r = client.get("/api/swarm/state")
    stats = r.json()["stats"]
    assert stats["sessions"] == 0
    assert stats["running"] == 0


def test_no_auth_required(monkeypatch):
    """Endpoint must be accessible without an Authorization header."""
    r = client.get("/api/swarm/state")
    assert r.status_code == 200


# ── Shape contract ────────────────────────────────────────────────────────────

def test_response_has_required_top_level_keys(monkeypatch):
    r = client.get("/api/swarm/state")
    body = r.json()
    for key in ("orchestrator", "agents", "activity", "stats"):
        assert key in body, f"missing top-level key: {key}"


def test_stats_has_model_key(monkeypatch):
    r = client.get("/api/swarm/state")
    assert "model" in r.json()["stats"]


def test_model_label_from_provider(monkeypatch):
    monkeypatch.setattr(server, "main_provider",
                        lambda cfg, username=None: {"model": "claude-sonnet-4-6"})
    r = client.get("/api/swarm/state")
    assert r.json()["stats"]["model"] == "claude-sonnet-4-6"


def test_model_empty_when_no_provider(monkeypatch):
    monkeypatch.setattr(server, "main_provider", lambda cfg, username=None: None)
    r = client.get("/api/swarm/state")
    assert r.json()["stats"]["model"] == ""


# ── Meta.total == len(agents) ─────────────────────────────────────────────────

def test_meta_total_matches_agents_len(monkeypatch):
    sessions = {
        "s1": _make_session("s1", "alpha"),
        "s2": _make_session("s2", "beta"),
        "s3": _make_session("s3", "gamma"),
    }
    monkeypatch.setattr(server, "SESSIONS", sessions)
    body = client.get("/api/swarm/state").json()
    assert body["stats"]["sessions"] == len(body["agents"])


# ── State mapping ──────────────────────────────────────────────────────────────

def test_state_running(monkeypatch):
    monkeypatch.setattr(server, "SESSIONS",
                        {"s1": _make_session("s1", status="running")})
    agents = client.get("/api/swarm/state").json()["agents"]
    assert agents[0]["status"] == "running"


def test_state_blocked_via_stop_flag(monkeypatch):
    monkeypatch.setattr(server, "SESSIONS",
                        {"s1": _make_session("s1", stop_set=True)})
    agents = client.get("/api/swarm/state").json()["agents"]
    assert agents[0]["status"] == "blocked"


def test_state_blocked_via_interrupted(monkeypatch):
    monkeypatch.setattr(server, "SESSIONS",
                        {"s1": _make_session("s1", status="interrupted")})
    agents = client.get("/api/swarm/state").json()["agents"]
    assert agents[0]["status"] == "blocked"


def test_state_done_idle_with_spend(monkeypatch):
    """idle + prior spend → done (session ran before, now quiet)."""
    monkeypatch.setattr(server, "SESSIONS",
                        {"s1": _make_session("s1", status="idle", spent_usd=0.05)})
    agents = client.get("/api/swarm/state").json()["agents"]
    assert agents[0]["status"] == "done"


def test_state_idle_no_spend(monkeypatch):
    """idle + zero spend → idle (never ran)."""
    monkeypatch.setattr(server, "SESSIONS",
                        {"s1": _make_session("s1", status="idle", spent_usd=0.0)})
    agents = client.get("/api/swarm/state").json()["agents"]
    assert agents[0]["status"] == "idle"


# ── Agent entry shape ─────────────────────────────────────────────────────────

def test_agent_entry_fields(monkeypatch):
    monkeypatch.setattr(server, "SESSIONS",
                        {"abc": _make_session("abc", "my-job")})
    agent = client.get("/api/swarm/state").json()["agents"][0]
    assert agent["id"]   == "session-abc"
    assert agent["name"] == "my-job"
    assert "status" in agent
    assert "tier"   in agent


# ── Stats running count ───────────────────────────────────────────────────────

def test_stats_running_count(monkeypatch):
    sessions = {
        "r1": _make_session("r1", status="running"),
        "r2": _make_session("r2", status="running"),
        "i1": _make_session("i1", status="idle"),
    }
    monkeypatch.setattr(server, "SESSIONS", sessions)
    stats = client.get("/api/swarm/state").json()["stats"]
    assert stats["running"] == 2
    assert stats["sessions"] == 3


# ── Activity packets ──────────────────────────────────────────────────────────

def test_activity_from_tool_events(monkeypatch):
    events = [
        {"i": 0, "ts": 100, "type": "tool",  "name": "bash",   "text": ""},
        {"i": 1, "ts": 101, "type": "text",  "name": "",       "text": "hello"},
        {"i": 2, "ts": 102, "type": "agent_start", "agent": "x", "tier": "t1"},
    ]
    monkeypatch.setattr(server, "SESSIONS",
                        {"s1": _make_session("s1", events=events)})
    activity = client.get("/api/swarm/state").json()["activity"]
    # Only tool + text events become activity packets; agent_start is excluded
    assert len(activity) == 2
    assert activity[0]["detail"] == "bash"
    assert activity[1]["detail"] == "hello"
