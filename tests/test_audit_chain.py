"""S-3 (issue #68) — hash-chained tamper-evident audit trail.

Every safelisted security event (and every M-7 erasure receipt) is appended to
DATA_DIR/audit_chain.jsonl where each entry commits to the previous entry's
SHA-256.  verify_audit_chain() must pass on an intact chain and fail — saying
why — on mutation, deletion (middle or tail), insertion, or reordering.

Run: ./.venv/bin/python -m pytest tests/ -q
"""
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


# ---- fixtures ------------------------------------------------------------------

@pytest.fixture
def as_owner():
    server.app.dependency_overrides[server.verify_owner] = lambda: "owner"
    yield
    server.app.dependency_overrides.pop(server.verify_owner, None)


@pytest.fixture
def chain(tmp_path, monkeypatch):
    """Point the chain at a fresh per-test file pair and reset the cached tail."""
    chain_path = str(tmp_path / "audit_chain.jsonl")
    head_path = str(tmp_path / "audit_chain.head.json")
    monkeypatch.setattr(server, "AUDIT_CHAIN_FILE", chain_path)
    monkeypatch.setattr(server, "AUDIT_CHAIN_HEAD_FILE", head_path)
    monkeypatch.setattr(server, "_AUDIT_CHAIN_TAIL",
                        {"loaded": False, "seq": -1,
                         "hash": server._AUDIT_CHAIN_GENESIS})
    yield chain_path, head_path


def _append_n(n, prefix="evt"):
    """Append n well-formed entries via the production append path."""
    for i in range(n):
        entry = server.audit_chain_append(
            {"type": "error", "message": f"{prefix}-{i}", "agent": "main"})
        assert entry is not None
    return n


def _read_lines(chain_path):
    with open(chain_path, encoding="utf-8") as f:
        return [l for l in f.read().splitlines() if l.strip()]


def _write_lines(chain_path, lines):
    with open(chain_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + ("\n" if lines else ""))


# ---- happy path ------------------------------------------------------------------

def test_empty_chain_verifies_clean(chain):
    res = server.verify_audit_chain()
    assert res["ok"] is True
    assert res["entries"] == 0
    assert res["head"] is None


def test_happy_path_verifies_clean(chain):
    chain_path, head_path = chain
    _append_n(5)
    res = server.verify_audit_chain()
    assert res["ok"] is True, res
    assert res["entries"] == 5
    assert res["head_checked"] is True
    # head hash matches the last persisted entry
    last = json.loads(_read_lines(chain_path)[-1])
    assert res["head"] == last["hash"]
    # entry 0 links to genesis; every later entry links to its predecessor
    lines = [json.loads(l) for l in _read_lines(chain_path)]
    assert lines[0]["prev"] == server._AUDIT_CHAIN_GENESIS
    for a, b in zip(lines, lines[1:]):
        assert b["prev"] == a["hash"]
        assert b["seq"] == a["seq"] + 1


def test_chain_survives_tail_cache_reset(chain, monkeypatch):
    """A restart (cold tail cache) continues the chain, not a new one."""
    _append_n(2)
    monkeypatch.setattr(server, "_AUDIT_CHAIN_TAIL",
                        {"loaded": False, "seq": -1,
                         "hash": server._AUDIT_CHAIN_GENESIS})
    _append_n(2, prefix="after-restart")
    res = server.verify_audit_chain()
    assert res["ok"] is True, res
    assert res["entries"] == 4


# ---- emit() routing ---------------------------------------------------------------

def test_emit_chains_safelisted_and_skips_noise(chain):
    chain_path, _ = chain
    s = server.new_session(title="chain-test")
    try:
        server.emit(s, "error", message="boom", agent="main")       # safelisted
        server.emit(s, "approval", approval_id="abc", command="rm -rf /")
        server.emit(s, "text", text="the quick brown fox", agent="main")  # noise
        server.emit(s, "user", text="run the tests please")               # noise
        lines = [json.loads(l) for l in _read_lines(chain_path)]
        types = [e["event"]["type"] for e in lines]
        assert types == ["error", "approval"]
        # chained projection carries only safelisted fields (same as /api/audit)
        approval = lines[1]["event"]
        assert set(approval) <= {"sid", "i", "ts", "type", "approval_id", "command"}
        # noise content never reaches the chain file
        raw = "\n".join(_read_lines(chain_path))
        assert "quick brown fox" not in raw
        assert "run the tests please" not in raw
        assert server.verify_audit_chain()["ok"] is True
    finally:
        server.SESSIONS.pop(s["id"], None)


def test_erasure_receipt_is_chained(chain, tmp_path, monkeypatch):
    chain_path, _ = chain
    monkeypatch.setattr(server, "ERASURE_RECEIPTS_FILE",
                        str(tmp_path / "erasure_receipts.jsonl"))
    server._write_receipt("ghost", by="owner", stores=["users.json"], ts=1234)
    lines = [json.loads(l) for l in _read_lines(chain_path)]
    assert len(lines) == 1
    assert lines[0]["event"] == {"type": "erasure", "ts": 1234, "user": "ghost",
                                 "by": "owner", "stores": ["users.json"]}
    assert server.verify_audit_chain()["ok"] is True


# ---- tamper detection --------------------------------------------------------------

def test_mutation_detected(chain):
    """Editing a middle entry's content breaks its hash."""
    chain_path, _ = chain
    _append_n(4)
    lines = _read_lines(chain_path)
    entry = json.loads(lines[1])
    entry["event"]["message"] = "history, rewritten"
    lines[1] = json.dumps(entry)
    _write_lines(chain_path, lines)
    res = server.verify_audit_chain()
    assert res["ok"] is False
    assert "mutated" in res["error"]
    assert res["line"] == 2
    assert res["seq"] == 1


def test_middle_deletion_detected(chain):
    chain_path, _ = chain
    _append_n(4)
    lines = _read_lines(chain_path)
    del lines[1]
    _write_lines(chain_path, lines)
    res = server.verify_audit_chain()
    assert res["ok"] is False
    assert "sequence break" in res["error"]
    assert "deleted" in res["error"]
    assert res["line"] == 2


def test_tail_deletion_detected(chain):
    """Dropping the newest entry is caught by the head record cross-check."""
    chain_path, _ = chain
    _append_n(4)
    lines = _read_lines(chain_path)
    _write_lines(chain_path, lines[:-1])
    res = server.verify_audit_chain()
    assert res["ok"] is False
    assert "tail" in res["error"]


def test_whole_chain_truncation_detected(chain):
    """Emptying the chain file while the head record survives is caught."""
    chain_path, _ = chain
    _append_n(3)
    _write_lines(chain_path, [])
    res = server.verify_audit_chain()
    assert res["ok"] is False
    assert "empty or missing" in res["error"]


def test_head_record_deletion_detected(chain):
    """Deleting the head record while entries remain is itself flagged."""
    chain_path, head_path = chain
    _append_n(3)
    os.remove(head_path)
    res = server.verify_audit_chain()
    assert res["ok"] is False
    assert "head record is missing" in res["error"]


def test_insertion_detected(chain):
    """Even a self-consistent forged entry (valid own hash, correct prev link)
    spliced into the middle breaks the chain downstream."""
    chain_path, _ = chain
    _append_n(4)
    lines = _read_lines(chain_path)
    anchor = json.loads(lines[0])
    forged_event = {"type": "error", "message": "i was always here", "agent": "main"}
    forged = {"seq": 1, "prev": anchor["hash"], "event": forged_event}
    forged["hash"] = server._audit_chain_entry_hash(1, anchor["hash"], forged_event)
    lines.insert(1, json.dumps(forged))
    _write_lines(chain_path, lines)
    res = server.verify_audit_chain()
    assert res["ok"] is False
    # the ORIGINAL entry 1 now repeats seq 1 / links past the forgery
    assert "sequence break" in res["error"] or "prev-hash link broken" in res["error"]


def test_reorder_detected(chain):
    chain_path, _ = chain
    _append_n(4)
    lines = _read_lines(chain_path)
    lines[1], lines[2] = lines[2], lines[1]
    _write_lines(chain_path, lines)
    res = server.verify_audit_chain()
    assert res["ok"] is False
    assert res["line"] == 2


def test_malformed_line_detected(chain):
    chain_path, _ = chain
    _append_n(2)
    lines = _read_lines(chain_path)
    lines[0] = "{not json"
    _write_lines(chain_path, lines)
    res = server.verify_audit_chain()
    assert res["ok"] is False
    assert "malformed" in res["error"]
    assert res["line"] == 1


# ---- owner verification surface ------------------------------------------------------

def test_verify_endpoint_requires_auth():
    r = client.get("/api/audit/verify")
    assert r.status_code == 401


def test_verify_endpoint_rejects_member(monkeypatch):
    monkeypatch.setattr(server, "load_users", lambda: {"dev": {"role": "Member"}})
    tok = server.make_token("dev")
    r = client.get("/api/audit/verify", headers={"Authorization": "Bearer " + tok})
    assert r.status_code == 403


def test_verify_endpoint_ok(as_owner, chain):
    _append_n(3)
    r = client.get("/api/audit/verify")
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data["entries"] == 3


def test_verify_endpoint_reports_tamper(as_owner, chain):
    chain_path, _ = chain
    _append_n(3)
    lines = _read_lines(chain_path)
    entry = json.loads(lines[0])
    entry["event"]["message"] = "tampered"
    lines[0] = json.dumps(entry)
    _write_lines(chain_path, lines)
    r = client.get("/api/audit/verify")
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is False
    assert "mutated" in data["error"]


def test_verify_endpoint_exposes_no_event_content(as_owner, chain):
    """The verify surface returns integrity metadata only — never the events."""
    _append_n(2, prefix="sensitive-command")
    r = client.get("/api/audit/verify")
    assert "sensitive-command" not in r.text
