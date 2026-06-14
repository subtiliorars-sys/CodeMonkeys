"""CM-W5 three-card feedback triage: heuristic proposals + owner-only routes."""
import json
import os
import sys
import tempfile

os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(prefix="cm_test_"))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

import feedback_triage as ft  # noqa: E402
import server  # noqa: E402


def test_heuristic_proposals_three_cards():
    props = ft.heuristic_proposals({"category": "bug", "message": "Button broken"})
    assert len(props) == 3
    assert props[0].startswith("[FIX]")
    assert props[1].startswith("[INVESTIGATE]")
    assert props[2].startswith("[DISMISS]")


def test_ensure_proposals_fills_empty():
    report = {"category": "improvement", "message": "Dark mode please"}
    meta = ft.ensure_proposals(report, {"status": "new"})
    assert len(meta["proposals"]) == 3
    assert all(p.strip() for p in meta["proposals"])
    assert meta["recommendedSlot"] == 0


def test_merge_report_with_meta():
    merged = ft.merge_report_with_meta(
        {"id": "abc", "message": "hi"},
        {"status": "planned", "proposals": ["a", "b", "c"], "recommendedSlot": 1,
         "chosenSolution": "do it", "reviewNote": "note"},
    )
    assert merged["status"] == "planned"
    assert merged["proposals"] == ["a", "b", "c"]
    assert merged["recommendedSlot"] == 1
    assert merged["chosenSolution"] == "do it"
    assert merged["reviewNote"] == "note"


def test_list_feedback_generates_proposals(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(server, "FEEDBACK_FILE", str(tmp_path / "feedback.jsonl"))
    monkeypatch.setattr(server, "FEEDBACK_STATUS_FILE", str(tmp_path / "status.json"))
    rid = "a" * 16
    with open(tmp_path / "feedback.jsonl", "w", encoding="utf-8") as f:
        f.write(json.dumps({"id": rid, "ts": "2026-01-01T00:00Z", "category": "bug",
                            "message": "crash"}) + "\n")
    server.app.dependency_overrides[server.verify_owner] = lambda: "owner"
    try:
        from fastapi.testclient import TestClient
        client = TestClient(server.app)
        r = client.get("/api/feedback/list")
        assert r.status_code == 200
        reports = r.json()["reports"]
        assert len(reports) == 1
        assert len(reports[0]["proposals"]) == 3
        assert reports[0]["proposals"][0].startswith("[FIX]")
    finally:
        server.app.dependency_overrides.pop(server.verify_owner, None)


def test_proposal_accept_route(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(server, "FEEDBACK_FILE", str(tmp_path / "feedback.jsonl"))
    monkeypatch.setattr(server, "FEEDBACK_STATUS_FILE", str(tmp_path / "status.json"))
    rid = "b" * 16
    with open(tmp_path / "feedback.jsonl", "w", encoding="utf-8") as f:
        f.write(json.dumps({"id": rid, "ts": "2026-01-01T00:00Z", "category": "bug",
                            "message": "slow"}) + "\n")
    server.app.dependency_overrides[server.verify_owner] = lambda: "owner"
    try:
        from fastapi.testclient import TestClient
        client = TestClient(server.app)
        r = client.post("/api/feedback/proposals/accept",
                        json={"id": rid, "solution": "[FIX] Speed up load", "acceptedSlot": 0})
        assert r.status_code == 200
        item = r.json()["item"]
        assert item["status"] == "planned"
        assert item["chosenSolution"] == "[FIX] Speed up load"
        assert item["acceptedSlot"] == 0
    finally:
        server.app.dependency_overrides.pop(server.verify_owner, None)
