"""W11 — two-layer KB (rules + facts) with a secret-leak guard.

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
_KBDIR = os.path.join(server.WORKSPACE_DIR, ".codemonkeys", "kb")


@pytest.fixture(autouse=True)
def clean_and_owner():
    shutil.rmtree(_KBDIR, ignore_errors=True)
    server.app.dependency_overrides[server.verify_owner] = lambda: "owner"
    yield
    server.app.dependency_overrides.pop(server.verify_owner, None)
    shutil.rmtree(_KBDIR, ignore_errors=True)


def test_requires_owner():
    server.app.dependency_overrides.pop(server.verify_owner, None)
    assert client.get("/api/kb").status_code in (401, 403)
    assert client.post("/api/kb/rules", json={"content": "x"}).status_code in (401, 403)


def test_set_and_get_layers():
    assert client.post("/api/kb/rules", json={"content": "always test"}).status_code == 200
    assert client.post("/api/kb/facts", json={"content": "uses fastapi"}).status_code == 200
    body = client.get("/api/kb").json()["layers"]
    assert body["rules"] == "always test" and body["facts"] == "uses fastapi"


def test_unknown_layer_rejected():
    assert client.post("/api/kb/bogus", json={"content": "x"}).status_code == 400


def test_secret_content_is_refused():
    # the build-fails-on-secret guarantee
    r = client.post("/api/kb/facts", json={"content": "key = ghp_" + "z" * 36})
    assert r.status_code == 422
    assert "ghp" not in r.text.lower() or "GitHub token" in r.text  # names kind, not value
    # nothing was written
    assert server._kb_read("facts") == ""


def test_context_injects_clean_layers():
    client.post("/api/kb/rules", json={"content": "principle one"})
    ctx = server._kb_context()
    assert "PROJECT KNOWLEDGE BASE" in ctx and "principle one" in ctx


def test_context_withholds_secret_bearing_layer(monkeypatch):
    # if a secret lands on disk out-of-band, the injector withholds that layer
    os.makedirs(_KBDIR, exist_ok=True)
    with open(server._kb_jail("facts"), "w") as f:
        f.write("token = sk-" + "q" * 40)
    ctx = server._kb_context()
    assert "WITHHELD" in ctx
    assert "sk-" + "q" * 40 not in ctx          # the secret never appears


def test_commander_prompt_includes_kb():
    client.post("/api/kb/rules", json={"content": "ship small PRs"})
    prompt = server._commander_system({"id": "s1"})
    assert "ship small PRs" in prompt
