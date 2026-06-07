"""Wave 4 #9 — connector marketplace catalog.

Run: ./.venv/bin/python -m pytest tests/ -q
"""
import os
import sys
import tempfile

os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(prefix="cm_test_"))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import server  # noqa: E402

client = TestClient(server.app)


@pytest.fixture
def as_owner():
    server.app.dependency_overrides[server.verify_owner] = lambda: "owner"
    yield
    server.app.dependency_overrides.pop(server.verify_owner, None)


def test_requires_owner():
    assert client.get("/api/connectors").status_code in (401, 403)


def test_curated_catalog_shape(as_owner):
    body = client.get("/api/connectors").json()
    assert body["source"] == "curated"
    names = {c["name"] for c in body["connectors"]}
    assert {"GitHub", "Filesystem"} <= names
    # every entry carries what the add-form needs
    for c in body["connectors"]:
        assert c["transport"] in ("http", "stdio") and c.get("description")
        if c["transport"] == "http":
            assert c.get("url")
        else:
            assert c.get("command")


def test_registry_failure_falls_back_to_curated(monkeypatch, as_owner):
    def boom(*a, **kw):
        raise OSError("registry down")
    monkeypatch.setattr(server.requests, "get", boom)
    body = client.get("/api/connectors?include_registry=true").json()
    # still returns the curated baseline, never 500s
    assert {c["name"] for c in body["connectors"]} >= {"GitHub", "Filesystem"}


def test_registry_augments_when_up(monkeypatch, as_owner):
    class R:
        status_code = 200

        def json(self):
            return {"servers": [{"name": "Acme", "description": "test server"},
                                {"name": "GitHub", "description": "dup name"}]}
    monkeypatch.setattr(server.requests, "get", lambda *a, **kw: R())
    body = client.get("/api/connectors?include_registry=true").json()
    assert body["source"] == "curated+registry"
    names = [c["name"] for c in body["connectors"]]
    assert "Acme" in names
    assert names.count("GitHub") == 1            # deduped against curated


def test_fetch_registry_helper_is_defensive(monkeypatch):
    monkeypatch.setattr(server.requests, "get",
                        lambda *a, **kw: (_ for _ in ()).throw(ValueError("x")))
    assert server._fetch_registry_connectors() == []
