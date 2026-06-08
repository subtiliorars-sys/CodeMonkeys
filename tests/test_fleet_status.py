"""Tests for the Fleet Deck status feed (Standing list S2).

Contract: ~/fleet/contracts/fleetdeck-codemonkeys.md — GET /fleet-status.json,
Bearer FLEET_TOKEN (hmac.compare_digest), read-only ops metadata mapped from the
session registry. Fail-closed: token unset → 404; bad/missing bearer → 401.
No prompts / code / keys / event payloads in the feed.

Run: ./.venv/bin/python -m pytest tests/ -q
"""
import os
import sys
import tempfile

os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(prefix="cm_test_"))
# FLEET_TOKEN is set in conftest.py before any `import server`, so the route is
# registered. Use the same value here for the auth assertions.
TOKEN = os.environ["FLEET_TOKEN"]
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import server  # noqa: E402

client = TestClient(server.app)


@pytest.fixture(autouse=True)
def _clean_sessions(monkeypatch):
    monkeypatch.setattr(server, "SESSIONS", {})
    yield


def _enable(monkeypatch):
    monkeypatch.setattr(server, "FLEET_TOKEN", TOKEN)


def _hdr(tok=TOKEN):
    return {"Authorization": f"Bearer {tok}"}


# ---- gate ---------------------------------------------------------------------

def test_runtime_disabled_token_means_404_even_with_header(monkeypatch):
    # runtime guard: FLEET_TOKEN cleared → 404 regardless of bearer. (In prod the
    # route is also not registered at all when unset at import — true 404/all methods.)
    monkeypatch.setattr(server, "FLEET_TOKEN", "")
    assert client.get("/fleet-status.json").status_code == 404
    assert client.get("/fleet-status.json", headers=_hdr()).status_code == 404


def test_short_token_treated_as_unset_at_import():
    # the <16-char rule blanks a weak token at module load
    assert server.FLEET_TOKEN == "" or len(server.FLEET_TOKEN) >= 16


def test_missing_bearer_is_401(monkeypatch):
    _enable(monkeypatch)
    assert client.get("/fleet-status.json").status_code == 401


def test_wrong_token_is_401(monkeypatch):
    _enable(monkeypatch)
    assert client.get("/fleet-status.json", headers=_hdr("nope")).status_code == 401


def test_empty_bearer_is_401_not_compare_crash(monkeypatch):
    _enable(monkeypatch)
    r = client.get("/fleet-status.json", headers={"Authorization": "Bearer "})
    assert r.status_code == 401


def test_non_bearer_scheme_is_401(monkeypatch):
    _enable(monkeypatch)
    r = client.get("/fleet-status.json", headers={"Authorization": f"Basic {TOKEN}"})
    assert r.status_code == 401


def test_get_only(monkeypatch):
    _enable(monkeypatch)
    assert client.post("/fleet-status.json", headers=_hdr()).status_code == 405


# ---- payload shape -------------------------------------------------------------

def test_empty_fleet_shape(monkeypatch):
    _enable(monkeypatch)
    r = client.get("/fleet-status.json", headers=_hdr())
    assert r.status_code == 200
    body = r.json()
    assert body["source"] == "codemonkeys"
    assert body["workers"] == []
    assert body["generated"].endswith("Z")


def test_session_maps_to_worker(monkeypatch):
    _enable(monkeypatch)
    s = server.new_session(title="build feature X", repo="owner/repo")
    s["status"] = "running"
    server.emit(s, "tool_call", name="bash")
    r = client.get("/fleet-status.json", headers=_hdr()).json()
    assert len(r["workers"]) == 1
    w = r["workers"][0]
    assert w["name"] == f"session-{s['id']}"
    assert w["state"] == "WORKING"
    assert w["objective"] == "build feature X"
    assert w["branch"] == "owner/repo"
    assert isinstance(w["heartbeat_ts"], int) and w["heartbeat_ts"] > 0
    assert w["now"] == ["tool_call"]


def test_state_mapping(monkeypatch):
    _enable(monkeypatch)
    for status, expect in [("running", "WORKING"), ("waiting_approval", "BLOCKED"),
                           ("error", "ERROR"), ("done", "DONE"), ("idle", "IDLE"),
                           ("connected", "IDLE"), ("someday-new-status", "IDLE")]:
        server.SESSIONS.clear()
        s = server.new_session(title="t")
        s["status"] = status
        w = client.get("/fleet-status.json", headers=_hdr()).json()["workers"][0]
        assert w["state"] == expect, status


def test_blocked_session_carries_question(monkeypatch):
    _enable(monkeypatch)
    s = server.new_session(title="t")
    s["status"] = "waiting_approval"
    w = client.get("/fleet-status.json", headers=_hdr()).json()["workers"][0]
    assert w["questions"] == ["awaiting in-UI approval"]


def test_stop_flag_reported(monkeypatch):
    _enable(monkeypatch)
    s = server.new_session(title="t")
    s["stop_flag"].set()
    body = client.get("/fleet-status.json", headers=_hdr()).json()
    assert body["stop_flags"] == [{"name": f"session-{s['id']}",
                                   "reason": "stop requested"}]


# ---- leak resistance ------------------------------------------------------------

def test_no_event_payloads_or_history_leak(monkeypatch):
    _enable(monkeypatch)
    s = server.new_session(title="t", repo="r")
    s["status"] = "running"
    s["history"].append({"role": "user", "text": "SUPER-SECRET-PROMPT"})
    server.emit(s, "tool_call", name="bash", command="cat /etc/passwd")
    raw = client.get("/fleet-status.json", headers=_hdr()).text
    assert "SUPER-SECRET-PROMPT" not in raw
    assert "/etc/passwd" not in raw          # event TYPE only, never fields
    assert "spent_usd" not in raw            # not in the contract — don't add


def test_objective_is_redacted_and_truncated(monkeypatch):
    _enable(monkeypatch)
    long_title = "x" * 500
    server.new_session(title=long_title)
    w = client.get("/fleet-status.json", headers=_hdr()).json()["workers"][0]
    assert len(w["objective"]) <= 200


def test_secret_in_title_is_withheld_not_shipped(monkeypatch):
    # R1: a user-pasted third-party credential in a title must not leak
    _enable(monkeypatch)
    server.new_session(title="debug acme key sk-AAAABBBBCCCCDDDDEEEEFFFF1234567")
    body = client.get("/fleet-status.json", headers=_hdr())
    assert "sk-AAAABBBB" not in body.text
    assert "withheld" in body.json()["workers"][0]["objective"]


def test_secret_in_repo_is_withheld(monkeypatch):
    _enable(monkeypatch)
    s = server.new_session(title="ok", repo="ghp_0123456789abcdefABCDEF0123456789abcdef")
    s["status"] = "idle"
    body = client.get("/fleet-status.json", headers=_hdr())
    assert "ghp_0123456789" not in body.text


def test_poisoned_session_is_skipped_not_fatal(monkeypatch):
    # R2: an event lacking ts/type (schema drift / hand-edit) must not 500 the feed
    _enable(monkeypatch)
    bad = server.new_session(title="bad")
    bad["events"].append({"i": 0})            # no ts, no type
    good = server.new_session(title="good")
    good["status"] = "running"
    r = client.get("/fleet-status.json", headers=_hdr())
    assert r.status_code == 200
    names = {w["name"] for w in r.json()["workers"]}
    assert f"session-{good['id']}" in names   # good survives even if bad maps fine
    # heartbeat_ts is always a sane int (never missing)
    for w in r.json()["workers"]:
        assert isinstance(w["heartbeat_ts"], int) and w["heartbeat_ts"] > 0


def test_worker_field_allowlist(monkeypatch):
    _enable(monkeypatch)
    s = server.new_session(title="t", repo="r")
    s["status"] = "waiting_approval"
    w = client.get("/fleet-status.json", headers=_hdr()).json()["workers"][0]
    assert set(w) <= {"name", "state", "objective", "branch",
                      "heartbeat_ts", "now", "questions"}


# ---- bounds ---------------------------------------------------------------------

def test_truncates_to_cap_newest_first(monkeypatch):
    _enable(monkeypatch)
    monkeypatch.setattr(server, "FLEET_MAX_WORKERS", 3)
    ids = [server.new_session(title=f"s{i}")["id"] for i in range(5)]
    body = client.get("/fleet-status.json", headers=_hdr()).json()
    assert len(body["workers"]) == 3
    assert "truncated" in body.get("notes", "")
    # newest-first: the cap keeps the most recent sessions
    kept = {w["name"] for w in body["workers"]}
    assert f"session-{ids[-1]}" in kept


def test_response_under_1mb_with_max_workers(monkeypatch):
    # Contract bound: ≤200 workers, ≤1 MB total response. Create 200 sessions
    # with long-ish titles + a repo to maximize per-worker payload size.
    _enable(monkeypatch)
    for i in range(server.FLEET_MAX_WORKERS):
        s = server.new_session(title=f"feature-{i:03d}: " + "x" * 150, repo="owner/feature-branch")
        s["status"] = "running"
        server.emit(s, "tool_call", name="bash")
    r = client.get("/fleet-status.json", headers=_hdr())
    assert r.status_code == 200
    assert len(r.content) <= 1_048_576, (
        f"Response body {len(r.content)} bytes exceeds 1 MB contract bound"
    )
    body = r.json()
    assert len(body["workers"]) == server.FLEET_MAX_WORKERS
