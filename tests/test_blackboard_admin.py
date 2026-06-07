"""W8 — Owner-only blackboard management (list / read / delete).

Run: ./.venv/bin/python -m pytest tests/ -q
"""
import os
import shutil
import sys
import tempfile

os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(prefix="cm_test_"))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import server  # noqa: E402

client = TestClient(server.app)
_CMDIR = os.path.join(server.WORKSPACE_DIR, ".codemonkeys")


@pytest.fixture(autouse=True)
def clean_and_owner():
    shutil.rmtree(_CMDIR, ignore_errors=True)
    server.app.dependency_overrides[server.verify_owner] = lambda: "owner"
    yield
    server.app.dependency_overrides.pop(server.verify_owner, None)
    shutil.rmtree(_CMDIR, ignore_errors=True)


def test_requires_owner():
    server.app.dependency_overrides.pop(server.verify_owner, None)
    assert client.get("/api/blackboard").status_code in (401, 403)
    assert client.delete("/api/blackboard/x").status_code in (401, 403)


def test_list_and_get(monkeypatch):
    server.t_blackboard_write({"slug": "proj-a", "section": "FACTS", "content": "alpha"})
    server.t_blackboard_write({"slug": "proj-b", "section": "NEXT", "content": "beta"})
    body = client.get("/api/blackboard").json()
    slugs = {b["slug"] for b in body["blackboards"]}
    assert slugs == {"proj-a", "proj-b"}
    assert all(b["bytes"] > 0 for b in body["blackboards"])
    got = client.get("/api/blackboard/proj-a").json()
    assert got["slug"] == "proj-a" and "alpha" in got["content"]


def test_get_unknown_is_friendly():
    got = client.get("/api/blackboard/ghost").json()
    assert "no blackboard yet" in got["content"]


def test_delete_removes_file():
    server.t_blackboard_write({"slug": "doomed", "section": "FACTS", "content": "x"})
    full = server._jail_blackboard("doomed")
    assert os.path.exists(full)
    r = client.delete("/api/blackboard/doomed")
    assert r.status_code == 200 and r.json()["removed"] == "doomed"
    assert not os.path.exists(full)


def test_delete_unknown_404():
    assert client.delete("/api/blackboard/never").status_code == 404


def test_delete_traversal_slug_is_sanitized_not_escaping():
    # a traversal-flavored slug is sanitized; it can't escape .codemonkeys.
    # After sanitization it names no existing board → 404 (never touches /etc).
    r = client.delete("/api/blackboard/..%2f..%2fetc%2fpasswd")
    assert r.status_code in (400, 404)
