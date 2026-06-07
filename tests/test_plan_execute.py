"""N7 — Plan→Execute handoff.

Tests: GET /api/specs (list), POST /api/specs/{slug}/execute (create session),
jail enforcement (no traversal), auto-mode never used, auth required.

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

_SPECS_DIR = os.path.join(server.WORKSPACE_DIR, ".codemonkeys", "specs")


@pytest.fixture(autouse=True)
def clean_specs():
    shutil.rmtree(_SPECS_DIR, ignore_errors=True)
    yield
    shutil.rmtree(_SPECS_DIR, ignore_errors=True)


def _write_artifact(slug: str, artifact: str, content: str) -> None:
    d = os.path.join(_SPECS_DIR, slug)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, artifact + ".md"), "w") as f:
        f.write(content)


def _auth():
    """Return dependency override dict for verify_user (any authenticated user)."""
    return {server.verify_user: lambda: "testuser"}


# ---- GET /api/specs ----------------------------------------------------------

def test_list_specs_empty():
    server.app.dependency_overrides.update(_auth())
    try:
        r = client.get("/api/specs")
        assert r.status_code == 200
        assert r.json()["specs"] == []
    finally:
        server.app.dependency_overrides.pop(server.verify_user, None)


def test_list_specs_returns_slugs_and_artifacts():
    _write_artifact("my-feature", "plan", "Build the auth flow.")
    _write_artifact("my-feature", "tasks", "1. Write tests\n2. Implement")
    _write_artifact("my-feature", "constitution", "Do not break prod.")

    server.app.dependency_overrides.update(_auth())
    try:
        r = client.get("/api/specs")
        assert r.status_code == 200
        specs = r.json()["specs"]
        assert len(specs) == 1
        s = specs[0]
        assert s["slug"] == "my-feature"
        assert set(s["artifacts"]) >= {"plan", "tasks", "constitution"}
    finally:
        server.app.dependency_overrides.pop(server.verify_user, None)


def test_list_specs_title_from_plan_first_line():
    _write_artifact("alpha", "plan", "# Heading\n\nBuild the login page.\nMore text.")
    server.app.dependency_overrides.update(_auth())
    try:
        r = client.get("/api/specs")
        specs = r.json()["specs"]
        assert specs[0]["title"] == "Build the login page."
    finally:
        server.app.dependency_overrides.pop(server.verify_user, None)


def test_list_specs_multiple_slugs_sorted():
    for slug in ("zz-last", "aa-first", "mm-middle"):
        _write_artifact(slug, "plan", f"Plan for {slug}")
    server.app.dependency_overrides.update(_auth())
    try:
        r = client.get("/api/specs")
        slugs = [s["slug"] for s in r.json()["specs"]]
        assert slugs == sorted(slugs)
    finally:
        server.app.dependency_overrides.pop(server.verify_user, None)


def test_list_specs_requires_auth():
    r = client.get("/api/specs")
    assert r.status_code in (401, 403)


# ---- jailed directory enumeration -------------------------------------------

def test_list_specs_ignores_symlinks_outside_jail(tmp_path):
    """A symlinked dir inside .codemonkeys/specs/ pointing outside is skipped."""
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "plan.md").write_text("secret content")

    os.makedirs(_SPECS_DIR, exist_ok=True)
    link = os.path.join(_SPECS_DIR, "evil-link")
    try:
        os.symlink(str(outside), link)
    except OSError:
        pytest.skip("Cannot create symlink (permissions)")

    # Also create a legit spec so we can verify only it appears
    _write_artifact("legit", "plan", "Legit plan")

    server.app.dependency_overrides.update(_auth())
    try:
        r = client.get("/api/specs")
        slugs = [s["slug"] for s in r.json()["specs"]]
        assert "legit" in slugs
        assert "evil-link" not in slugs
    finally:
        server.app.dependency_overrides.pop(server.verify_user, None)
        try:
            os.unlink(link)
        except OSError:
            pass


# ---- POST /api/specs/{slug}/execute -----------------------------------------

def test_execute_creates_default_mode_session():
    _write_artifact("my-plan", "plan", "Implement the feature.")
    _write_artifact("my-plan", "tasks", "1. Write code\n2. Run tests")

    server.app.dependency_overrides.update(_auth())
    try:
        r = client.post("/api/specs/my-plan/execute", json={})
        assert r.status_code == 200
        body = r.json()
        assert "id" in body
        assert body["slug"] == "my-plan"
        # Non-negotiable: mode is ALWAYS default (never auto)
        assert body["mode"] == "default"

        sid = body["id"]
        assert sid in server.SESSIONS
        sess = server.SESSIONS[sid]
        assert sess["mode"] == "default"

        # The first event in the session should be a user message containing
        # the plan content
        events = sess["events"]
        user_events = [e for e in events if e["type"] == "user"]
        assert user_events, "No user event seeded into session"
        seed_text = user_events[0]["text"]
        assert "my-plan" in seed_text
        assert "Implement the feature." in seed_text
        assert "Write code" in seed_text
    finally:
        server.app.dependency_overrides.pop(server.verify_user, None)
        # Clean up session (background thread may be trying to run — stop it)
        if "id" in locals():
            s = server.SESSIONS.get(locals()["sid"])
            if s:
                s["stop_flag"].set()
                del server.SESSIONS[locals()["sid"]]


def test_execute_auto_mode_never_used():
    """The executing session must be default, not auto — even for Owner calls."""
    _write_artifact("safe-plan", "plan", "Do something safe.")
    _write_artifact("safe-plan", "tasks", "Task 1")

    # Override as Owner — even owners must get default mode from execute
    server.app.dependency_overrides[server.verify_user] = lambda: "owner"
    try:
        r = client.post("/api/specs/safe-plan/execute", json={})
        assert r.status_code == 200
        assert r.json()["mode"] == "default"
        sid = r.json()["id"]
        assert server.SESSIONS[sid]["mode"] == "default"
    finally:
        server.app.dependency_overrides.pop(server.verify_user, None)
        s = server.SESSIONS.get(sid)
        if s:
            s["stop_flag"].set()
            del server.SESSIONS[sid]


def test_execute_requires_auth():
    _write_artifact("any-plan", "plan", "Something")
    r = client.post("/api/specs/any-plan/execute", json={})
    assert r.status_code in (401, 403)


def test_execute_missing_slug_returns_404():
    server.app.dependency_overrides.update(_auth())
    try:
        r = client.post("/api/specs/does-not-exist/execute", json={})
        assert r.status_code == 404
    finally:
        server.app.dependency_overrides.pop(server.verify_user, None)


def test_execute_slug_with_no_plan_artifacts_returns_404():
    """A slug dir exists but only has constitution.md — nothing to execute."""
    _write_artifact("const-only", "constitution", "Be careful.")
    server.app.dependency_overrides.update(_auth())
    try:
        r = client.post("/api/specs/const-only/execute", json={})
        assert r.status_code == 404
    finally:
        server.app.dependency_overrides.pop(server.verify_user, None)


def test_execute_slug_traversal_rejected():
    """A path-traversal slug must not escape the specs jail."""
    server.app.dependency_overrides.update(_auth())
    try:
        # After sanitization, "../../etc/passwd" → "etc-passwd" (harmless slug).
        # The sanitization itself is the defence; ensure it doesn't 500 and
        # that the cleaned slug doesn't unexpectedly resolve to a real dir.
        r = client.post("/api/specs/../../etc/passwd/execute", json={})
        # Either 400 (bad slug) or 404 (no such plan) is acceptable — never 200
        assert r.status_code in (400, 404)
    finally:
        server.app.dependency_overrides.pop(server.verify_user, None)


def test_execute_slug_with_only_dots_rejected():
    server.app.dependency_overrides.update(_auth())
    try:
        r = client.post("/api/specs/.../execute", json={})
        assert r.status_code in (400, 404)
    finally:
        server.app.dependency_overrides.pop(server.verify_user, None)


def test_execute_custom_title_and_budget():
    _write_artifact("titled-plan", "plan", "Build feature X.")
    _write_artifact("titled-plan", "tasks", "Step 1\nStep 2")
    server.app.dependency_overrides.update(_auth())
    try:
        r = client.post("/api/specs/titled-plan/execute",
                        json={"title": "Custom run", "budget_usd": 0.5})
        assert r.status_code == 200
        sid = r.json()["id"]
        s = server.SESSIONS[sid]
        assert s["title"] == "Custom run"
        assert s["budget_usd"] <= 0.5   # clamped but not zero
    finally:
        server.app.dependency_overrides.pop(server.verify_user, None)
        s = server.SESSIONS.get(sid)
        if s:
            s["stop_flag"].set()
            del server.SESSIONS[sid]


# ---- internal helpers --------------------------------------------------------

def test_list_spec_slugs_helper_empty():
    assert server._list_spec_slugs() == []


def test_list_spec_slugs_helper_finds_dir():
    _write_artifact("helper-test", "plan", "Some plan.")
    slugs = [s["slug"] for s in server._list_spec_slugs()]
    assert "helper-test" in slugs


def test_read_spec_for_execution_combines_plan_and_tasks():
    _write_artifact("combo", "plan", "Execute this.")
    _write_artifact("combo", "tasks", "Step A\nStep B")
    seed = server._read_spec_for_execution("combo")
    assert "Execute this." in seed
    assert "Step A" in seed
    assert "combo" in seed


def test_read_spec_for_execution_missing_returns_empty():
    result = server._read_spec_for_execution("nonexistent-slug")
    assert result == ""


def test_jail_specs_helper_rejects_traversal():
    """_jail_specs must raise ValueError for any traversal attempt."""
    with pytest.raises(ValueError):
        server._jail_specs("../../escape", "plan")
    with pytest.raises(ValueError):
        server._jail_specs("legit/../../../escape", "plan")
