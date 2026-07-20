"""M-8 backup posture — restore drill + receipt (GOVERNANCE.md M-8).

The drill must prove the DATA_DIR tree reads back after a restore and leave a
receipt, and it must FAIL LOUDLY (per store, without crashing and without
echoing file contents) when a store is corrupted. Covers:

  - healthy tree -> ok, no failed stores, receipt line appended (the
    acceptance pair for "restore drill + receipt"),
  - corrupted JSON store -> that store reported failed, drill still completes,
    receipt records the failure, raw file bytes never appear in the result
    (S-4: a corrupted store can't leak content through a receipt/response),
  - corrupted JSONL line / undecryptable CMENC1 config / tampered audit chain
    / corrupted session artifact each detected,
  - wrong top-level JSON shape detected (parse alone isn't a round-trip),
  - unknown top-level *.json files still swept (future-proofing),
  - POST /api/backup/drill + GET /api/backup/drill-history are Owner-only
    (401 anonymous, 403 Member — the M-1 fail-closed pattern),
  - the owner endpoints run a live drill / list receipts newest-first.

Run: ./.venv/bin/python -m pytest tests/test_backup_drill.py -q
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

# A marker that must NEVER surface in a drill result — planted inside
# deliberately corrupted stores to prove failures don't echo file contents.
SECRET_MARKER = "SUPER-SECRET-PIN-HASH-abc123xyz"


def _healthy_tree(root) -> str:
    """Lay out a small, valid /data-shaped tree."""
    d = str(root / "restored_data")
    os.makedirs(os.path.join(d, "sessions"))
    with open(os.path.join(d, "users.json"), "w") as f:
        json.dump({"o": {"role": "Owner"}}, f)
    with open(os.path.join(d, "egress_consent.json"), "w") as f:
        json.dump({"o": {"status": "granted", "updated_at": 1, "history": []}}, f)
    with open(os.path.join(d, "erasure_receipts.jsonl"), "w") as f:
        f.write(json.dumps({"ts": 1, "event": "erasure", "user": "x",
                            "by": "o", "stores": ["users.json"]}) + "\n")
    with open(os.path.join(d, "session_secret.key"), "wb") as f:
        f.write(b"k" * 32)
    with open(os.path.join(d, "sessions", "index.json"), "w") as f:
        json.dump({}, f)
    with open(os.path.join(d, "sessions", "s1.events.jsonl"), "w") as f:
        f.write(json.dumps({"type": "note"}) + "\n")
    return d


# ------------------------------------------------ receipt schema contract (#179)

_VALID_STATUSES = {"pass", "fail", "absent"}


def _assert_valid_receipt(rec: dict) -> None:
    """The receipt schema contract: required fields + types. Any drift here
    (a field renamed/dropped/retyped) must fail this assertion, since
    downstream tooling (drill-history, any external consumer) trusts this
    shape."""
    assert isinstance(rec, dict)
    assert rec.get("event") == "backup_drill"
    assert isinstance(rec.get("ts"), int)
    assert isinstance(rec.get("by"), str) and rec["by"]
    assert isinstance(rec.get("ok"), bool)
    assert isinstance(rec.get("checked"), int)
    assert isinstance(rec.get("absent"), int)
    assert isinstance(rec.get("failed"), list)
    assert all(isinstance(s, str) for s in rec["failed"])
    assert isinstance(rec.get("stores"), list) and rec["stores"]
    for entry in rec["stores"]:
        assert isinstance(entry, dict)
        assert isinstance(entry.get("store"), str) and entry["store"]
        assert entry.get("status") in _VALID_STATUSES
        if entry["status"] == "fail":
            assert isinstance(entry.get("reason"), str) and entry["reason"]


def test_receipt_matches_schema_contract(tmp_path):
    """A real receipt from a healthy drill satisfies the contract."""
    d = _healthy_tree(tmp_path)
    server.run_backup_drill(by="owner", data_dir=d)
    with open(os.path.join(d, "backup_drill_receipts.jsonl")) as f:
        rec = json.loads(f.readline())
    _assert_valid_receipt(rec)


@pytest.mark.parametrize("mutation", [
    lambda r: r.pop("ts"),
    lambda r: r.__setitem__("ts", "not-an-int"),
    lambda r: r.pop("event"),
    lambda r: r.__setitem__("event", "wrong_event_name"),
    lambda r: r.pop("ok"),
    lambda r: r.__setitem__("ok", "yes"),
    lambda r: r.pop("checked"),
    lambda r: r.pop("failed"),
    lambda r: r.__setitem__("failed", "users.json"),  # not a list
    lambda r: r.pop("stores"),
    lambda r: r.__setitem__("stores", []),  # empty - nothing was actually checked
    lambda r: r["stores"][0].__setitem__("status", "ok"),  # not a valid status
    lambda r: r["stores"][0].pop("store"),
])
def test_malformed_receipt_fails_the_contract(tmp_path, mutation):
    """Acceptance: a malformed receipt fails the contract test - prove the
    contract actually rejects drift instead of rubber-stamping any dict."""
    d = _healthy_tree(tmp_path)
    server.run_backup_drill(by="owner", data_dir=d)
    with open(os.path.join(d, "backup_drill_receipts.jsonl")) as f:
        rec = json.loads(f.readline())
    mutation(rec)
    with pytest.raises(AssertionError):
        _assert_valid_receipt(rec)


def test_receipt_file_is_append_only_never_truncates(tmp_path):
    """Running the drill repeatedly must only ever grow the receipt file -
    prior lines are byte-for-byte preserved, never rewritten or truncated."""
    d = _healthy_tree(tmp_path)
    path = os.path.join(d, "backup_drill_receipts.jsonl")

    server.run_backup_drill(by="owner", data_dir=d)
    with open(path, "rb") as f:
        first_write = f.read()
    size_after_first = os.path.getsize(path)

    server.run_backup_drill(by="owner", data_dir=d)
    size_after_second = os.path.getsize(path)
    assert size_after_second > size_after_first

    with open(path, "rb") as f:
        after_second = f.read()
    # The bytes from the first write are an unmodified prefix of the file now.
    assert after_second.startswith(first_write)

    # A third drill, this time with a corrupted store - receipt still only
    # appends, even when the drill result itself reports a failure.
    with open(os.path.join(d, "users.json"), "w") as f:
        f.write("{broken")
    server.run_backup_drill(by="owner", data_dir=d)
    with open(path, "rb") as f:
        after_third = f.read()
    assert after_third.startswith(after_second)
    with open(path) as f:
        lines = [json.loads(x) for x in f if x.strip()]
    assert len(lines) == 3
    for rec in lines:
        _assert_valid_receipt(rec)


def test_receipt_never_contains_secret_marker_across_all_failure_modes(tmp_path):
    """Belt-and-suspenders on top of the per-scenario leak checks above: plant
    the marker in several different stores in the same tree, corrupt all of
    them, and assert it never reaches the persisted receipt file."""
    d = _healthy_tree(tmp_path)
    with open(os.path.join(d, "users.json"), "w") as f:
        f.write('{"pin_hash": "' + SECRET_MARKER + '"')  # truncated
    with open(os.path.join(d, "erasure_receipts.jsonl"), "a") as f:
        f.write("not json " + SECRET_MARKER + "\n")
    with open(os.path.join(d, "future_store.json"), "w") as f:
        f.write(SECRET_MARKER + " {not json")

    out = server.run_backup_drill(by="owner", data_dir=d)
    assert out["ok"] is False
    assert SECRET_MARKER not in json.dumps(out)
    with open(os.path.join(d, "backup_drill_receipts.jsonl")) as f:
        contents = f.read()
    assert SECRET_MARKER not in contents
    rec = json.loads(contents.splitlines()[-1])
    _assert_valid_receipt(rec)


# ------------------------------------------------ drill fundamentals

def test_healthy_tree_all_pass_and_receipt_written(tmp_path):
    """The acceptance pair: drill a healthy tree -> ok + receipt appended."""
    d = _healthy_tree(tmp_path)
    out = server.run_backup_drill(by="owner", data_dir=d)
    assert out["ok"] is True and out["failed"] == []
    assert out["checked"] >= 5 and isinstance(out["ts"], int)
    by_store = {r["store"]: r for r in out["stores"]}
    assert by_store["users.json"]["status"] == "pass"
    assert by_store["sessions/"]["status"] == "pass"
    assert by_store["model_config.json"]["status"] == "absent"  # absent is fine
    # Receipt lands in the drilled tree, append-only JSONL, minimal fields.
    with open(os.path.join(d, "backup_drill_receipts.jsonl")) as f:
        lines = [json.loads(x) for x in f if x.strip()]
    assert len(lines) == 1
    rec = lines[0]
    assert rec["event"] == "backup_drill" and rec["ok"] is True
    assert rec["by"] == "owner" and rec["failed"] == []
    # A second drill appends (never truncates) — and drills its own receipts.
    out2 = server.run_backup_drill(by="owner", data_dir=d)
    assert out2["ok"] is True
    with open(os.path.join(d, "backup_drill_receipts.jsonl")) as f:
        assert sum(1 for x in f if x.strip()) == 2


def test_corrupted_json_store_fails_that_store_without_leaking(tmp_path):
    """A truncated/malformed users.json must be reported as THAT store failing
    — not crash the drill, not silently pass, and never echo file bytes."""
    d = _healthy_tree(tmp_path)
    with open(os.path.join(d, "users.json"), "w") as f:
        f.write('{"o": {"pin_hash": "' + SECRET_MARKER + '"')  # truncated JSON
    out = server.run_backup_drill(by="owner", data_dir=d)
    assert out["ok"] is False and out["failed"] == ["users.json"]
    rec = next(r for r in out["stores"] if r["store"] == "users.json")
    assert rec["status"] == "fail" and "JSONDecodeError" in rec["reason"]
    # S-4: neither the returned result nor the persisted receipt carries content.
    assert SECRET_MARKER not in json.dumps(out)
    with open(os.path.join(d, "backup_drill_receipts.jsonl")) as f:
        assert SECRET_MARKER not in f.read()
    # Other stores were still checked (one bad store doesn't abort the drill).
    others = {r["store"]: r["status"] for r in out["stores"]}
    assert others["egress_consent.json"] == "pass"


def test_corrupted_jsonl_line_reports_line_number(tmp_path):
    d = _healthy_tree(tmp_path)
    with open(os.path.join(d, "erasure_receipts.jsonl"), "a") as f:
        f.write("not json " + SECRET_MARKER + "\n")
    out = server.run_backup_drill(by="owner", data_dir=d)
    assert out["failed"] == ["erasure_receipts.jsonl"]
    rec = next(r for r in out["stores"] if r["store"] == "erasure_receipts.jsonl")
    assert rec["reason"].startswith("line 2:")
    assert SECRET_MARKER not in json.dumps(out)


def test_wrong_shape_is_a_failure_not_a_pass(tmp_path):
    """users.json that parses but isn't a dict would break every consumer —
    parseability alone is not a round-trip."""
    d = _healthy_tree(tmp_path)
    with open(os.path.join(d, "users.json"), "w") as f:
        json.dump(["not", "a", "dict"], f)
    out = server.run_backup_drill(by="owner", data_dir=d)
    assert out["failed"] == ["users.json"]
    rec = next(r for r in out["stores"] if r["store"] == "users.json")
    assert "expected dict" in rec["reason"]


def test_undecryptable_encrypted_config_fails(tmp_path):
    """A CMENC1 blob that doesn't decrypt under the current master key is
    exactly what a bad restore looks like — strict FAIL here, even though the
    runtime reader is fail-soft."""
    d = _healthy_tree(tmp_path)
    with open(os.path.join(d, "model_config.json"), "wb") as f:
        f.write(server._ENC_MAGIC + b"garbage-not-a-fernet-token")
    out = server.run_backup_drill(by="owner", data_dir=d)
    assert out["failed"] == ["model_config.json"]
    rec = next(r for r in out["stores"] if r["store"] == "model_config.json")
    assert "decrypt" in rec["reason"]


def test_tampered_audit_chain_fails_the_drill(tmp_path):
    """The S-3 chain isn't just parsed — it's VERIFIED (verify_audit_chain)."""
    d = _healthy_tree(tmp_path)
    entry = {"seq": 0, "prev": "0" * 64, "event": {"type": "x"},
             "hash": "beef" * 16}                       # wrong hash = mutation
    with open(os.path.join(d, "audit_chain.jsonl"), "w") as f:
        f.write(json.dumps(entry) + "\n")
    out = server.run_backup_drill(by="owner", data_dir=d)
    assert "audit_chain" in out["failed"]


def test_corrupted_session_artifact_detected(tmp_path):
    d = _healthy_tree(tmp_path)
    with open(os.path.join(d, "sessions", "s1.events.jsonl"), "a") as f:
        f.write("{broken\n")
    out = server.run_backup_drill(by="owner", data_dir=d)
    assert out["failed"] == ["sessions/"]
    rec = next(r for r in out["stores"] if r["store"] == "sessions/")
    assert "s1.events.jsonl" in rec["reason"]


def test_unknown_top_level_store_is_swept(tmp_path):
    """A store added after this manifest still gets a generic parse check."""
    d = _healthy_tree(tmp_path)
    with open(os.path.join(d, "future_store.json"), "w") as f:
        f.write("{nope")
    out = server.run_backup_drill(by="owner", data_dir=d)
    assert "future_store.json" in out["failed"]


def test_empty_key_file_is_a_failure(tmp_path):
    d = _healthy_tree(tmp_path)
    with open(os.path.join(d, "session_secret.key"), "wb"):
        pass                                            # truncate to zero bytes
    out = server.run_backup_drill(by="owner", data_dir=d)
    assert out["failed"] == ["session_secret.key"]


# ------------------------------------------------ owner-only endpoints (M-1)

@pytest.fixture
def as_owner():
    server.app.dependency_overrides[server.verify_owner] = lambda: "owner"
    yield
    server.app.dependency_overrides.pop(server.verify_owner, None)


@pytest.fixture
def live_tree(tmp_path, monkeypatch):
    """Point every live-path global the drill reads at a hermetic healthy tree
    so the POST endpoint drills (and receipts into) tmp, not the shared test
    DATA_DIR or the live S-3 chain."""
    d = _healthy_tree(tmp_path)
    for name, attr, _kind in server._BACKUP_DRILL_STORES:
        monkeypatch.setattr(server, attr, os.path.join(d, name))
    monkeypatch.setattr(server, "DATA_DIR", d)
    monkeypatch.setattr(server, "SESSIONS_DIR", os.path.join(d, "sessions"))
    monkeypatch.setattr(server, "AUDIT_CHAIN_FILE",
                        os.path.join(d, "audit_chain.jsonl"))
    monkeypatch.setattr(server, "AUDIT_CHAIN_HEAD_FILE",
                        os.path.join(d, "audit_chain.head.json"))
    return d


def test_endpoints_require_auth():
    assert client.post("/api/backup/drill").status_code == 401
    assert client.get("/api/backup/drill-history").status_code == 401


def test_endpoints_reject_member(monkeypatch):
    monkeypatch.setattr(server, "load_users", lambda: {"dev": {"role": "Member"}})
    tok = server.make_token("dev")
    hdr = {"Authorization": "Bearer " + tok}
    assert client.post("/api/backup/drill", headers=hdr).status_code == 403
    assert client.get("/api/backup/drill-history", headers=hdr).status_code == 403


def test_owner_endpoint_runs_drill_and_history_lists_it(as_owner, live_tree):
    r = client.post("/api/backup/drill")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True and body["failed"] == [] and body["by"] == "owner"

    r = client.get("/api/backup/drill-history")
    assert r.status_code == 200
    hist = r.json()
    assert hist["malformed_lines"] == 0 and len(hist["drills"]) == 1
    assert hist["drills"][0]["event"] == "backup_drill"
    assert hist["drills"][0]["ok"] is True

    # Newest first: run a second drill after corrupting one store.
    with open(os.path.join(live_tree, "users.json"), "w") as f:
        f.write("{broken")
    r = client.post("/api/backup/drill")
    assert r.status_code == 200 and r.json()["ok"] is False
    hist = client.get("/api/backup/drill-history").json()
    assert [d["ok"] for d in hist["drills"]] == [False, True]
