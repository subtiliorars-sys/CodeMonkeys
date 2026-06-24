import os
import sys
import tempfile
import shutil
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import server
from server import app, t_glob, t_grep

client = TestClient(app, raise_server_exceptions=False)


def test_bash_timeout_configurable():
    """Verify BASH_TIMEOUT is configured from environment."""
    assert server.BASH_TIMEOUT == 180 or os.environ.get("CM_BASH_TIMEOUT")


def test_readyz_disk_space(monkeypatch, tmp_path):
    """Verify readyz includes disk_space_ok in response checks."""
    monkeypatch.setattr(server, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(server, "_FERNET_AVAILABLE", True)
    monkeypatch.setattr(server, "CM_MASTER_KEY", "")
    monkeypatch.setattr(server, "_usable", lambda cfg, username=None: [("p1", {"key": "k"})])
    monkeypatch.setattr(server, "load_models", lambda: {"providers": {}})

    r = client.get("/readyz")
    assert r.status_code == 200
    body = r.json()
    assert "disk_space_ok" in body["checks"]
    assert body["checks"]["disk_space_ok"] is True


def test_grep_glob_exclusions(tmp_path, monkeypatch):
    """Verify that t_glob and t_grep ignore excluded dirs."""
    monkeypatch.setattr(server, "WORKSPACE_DIR", str(tmp_path))

    # Create dummy directories
    (tmp_path / ".venv").mkdir()
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / ".pytest_cache").mkdir()
    (tmp_path / "src").mkdir()

    # Create dummy files
    (tmp_path / ".venv" / "bad.txt").write_text("should_exclude")
    (tmp_path / "node_modules" / "bad.txt").write_text("should_exclude")
    (tmp_path / "src" / "good.txt").write_text("should_find")

    # Test glob tool
    glob_res = t_glob({"pattern": "*.txt"})
    assert "good.txt" in glob_res
    assert "bad.txt" not in glob_res

    # Test grep tool
    grep_res = t_grep({"pattern": "should", "path": "."})
    assert "good.txt" in grep_res
    assert "bad.txt" not in grep_res


def test_session_tagging(monkeypatch, tmp_path):
    """Test session tags creation, listing, filtering, and updating."""
    monkeypatch.setattr(server, "SESSIONS_DIR", str(tmp_path))
    monkeypatch.setattr(server, "SESSIONS", {})
    
    # 1. Create session with tags
    # Mock user auth dependency via dependency_overrides
    server.app.dependency_overrides[server.verify_user] = lambda: "testuser"

    try:
        # POST to create session
        payload = {
            "title": "Sweep Session",
            "repo": "",
            "budget_usd": 10.0,
            "tags": ["sweep", "high-roi"]
        }
        r = client.post("/api/sessions", json=payload, headers={"Authorization": "Bearer test"})
        assert r.status_code == 200
        sid = r.json()["id"]

        # Create another session without tags
        r2 = client.post("/api/sessions", json={"title": "Empty Session"}, headers={"Authorization": "Bearer test"})
        assert r2.status_code == 200
        sid2 = r2.json()["id"]

        # 2. List all sessions (no filter)
        r_list = client.get("/api/sessions", headers={"Authorization": "Bearer test"})
        assert r_list.status_code == 200
        sessions = r_list.json()["sessions"]
        assert len(sessions) == 2
        
        # Check tags are returned
        sweep_sess = next(s for s in sessions if s["id"] == sid)
        assert sweep_sess["tags"] == ["sweep", "high-roi"]

        # 3. Filter by tag
        r_filter = client.get("/api/sessions?tag=sweep", headers={"Authorization": "Bearer test"})
        assert r_filter.status_code == 200
        filt_sessions = r_filter.json()["sessions"]
        assert len(filt_sessions) == 1
        assert filt_sessions[0]["id"] == sid

        # 4. PATCH update tags and title
        r_patch = client.patch(f"/api/sessions/{sid}", json={"title": "Updated Title", "tags": ["new-tag"]}, headers={"Authorization": "Bearer test"})
        assert r_patch.status_code == 200
        assert r_patch.json()["title"] == "Updated Title"
        assert r_patch.json()["tags"] == ["new-tag"]

        # Verify updated session status in-memory
        assert server.SESSIONS[sid]["title"] == "Updated Title"
        assert server.SESSIONS[sid]["tags"] == ["new-tag"]
    finally:
        server.app.dependency_overrides.pop(server.verify_user, None)
