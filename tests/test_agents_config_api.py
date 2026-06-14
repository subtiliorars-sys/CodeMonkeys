"""Agents Hub hooks + skills API."""
from __future__ import annotations

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import server  # noqa: E402

pytest.importorskip("httpx", reason="TestClient needs httpx")
from fastapi.testclient import TestClient  # noqa: E402

client = TestClient(server.app)


@pytest.fixture(autouse=True)
def owner_only():
    server.app.dependency_overrides[server.verify_owner] = lambda: "owner"
    yield
    server.app.dependency_overrides.pop(server.verify_owner, None)


@pytest.fixture
def tmp_agents_config(tmp_path, monkeypatch):
    hooks = tmp_path / "hooks.json"
    skills = tmp_path / "skills"
    skills.mkdir()
    monkeypatch.setattr(server, "CORPS_HOOKS_FILE", str(hooks))
    monkeypatch.setattr(server, "CORPS_SKILLS_DIR", str(skills))
    return hooks, skills


def test_hooks_round_trip(tmp_agents_config):
    hooks_file, _ = tmp_agents_config
    payload = json.dumps({"version": 1, "hooks": {"sessionStart": []}}, indent=2)
    r = client.put("/api/agents/hooks", json={"content": payload})
    assert r.status_code == 200
    assert hooks_file.is_file()
    r2 = client.get("/api/agents/hooks")
    assert r2.status_code == 200
    assert r2.json()["doc"]["hooks"]["sessionStart"] == []


def test_hooks_rejects_invalid_json(tmp_agents_config):
    r = client.put("/api/agents/hooks", json={"content": "not-json"})
    assert r.status_code == 400


def test_hooks_rejects_missing_version(tmp_agents_config):
    r = client.put("/api/agents/hooks", json={"content": '{"hooks": {}}'})
    assert r.status_code == 400


def test_skill_create_read_write(tmp_agents_config):
    _, skills = tmp_agents_config
    body = {"id": "test-skill", "content": "# Test\n\nDo the thing."}
    r = client.post("/api/agents/skills", json=body)
    assert r.status_code == 200
    assert (skills / "test-skill" / "SKILL.md").is_file()

    r2 = client.get("/api/agents/skills/test-skill")
    assert r2.status_code == 200
    assert "Do the thing" in r2.json()["content"]

    r3 = client.put("/api/agents/skills/test-skill", json={"content": "# Updated\n\nNew body."})
    assert r3.status_code == 200
    assert "New body" in client.get("/api/agents/skills/test-skill").json()["content"]


def test_skill_list_includes_seeded(tmp_agents_config):
    _, skills = tmp_agents_config
    skill_dir = skills / "alpha"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("# Alpha\n\nFirst skill.", encoding="utf-8")
    r = client.get("/api/agents/skills")
    assert r.status_code == 200
    ids = [s["id"] for s in r.json()["skills"]]
    assert ids == ["alpha"]


def test_skill_rejects_bad_id(tmp_agents_config):
    r = client.get("/api/agents/skills/INVALID")
    assert r.status_code == 400
