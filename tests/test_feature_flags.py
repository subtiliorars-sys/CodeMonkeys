"""#182 - config-backed feature-flag store.

GET /api/flags/example is a reference-only demo route gated by
server._KNOWN_FLAGS["example_reference_endpoint"] - it exists purely to
prove the flag store's on/off + runtime-toggle mechanism, not as a real
feature. See server.py's "#182: config-backed feature-flag store" comment
block for the intended lifecycle of a flag.
"""
import os
import sys

os.environ.setdefault("DATA_DIR", os.path.join(os.getcwd(), "data"))
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


@pytest.fixture(autouse=True)
def _clean_flags_store(tmp_path, monkeypatch):
    """Each test gets its own feature_flags.json so toggles from one test
    never leak into another."""
    monkeypatch.setattr(server, "FEATURE_FLAGS_FILE",
                        str(tmp_path / "feature_flags.json"))
    yield


def test_unknown_flag_defaults_to_off():
    assert server.flag_enabled("does_not_exist") is False


def test_example_endpoint_404s_while_flag_is_off():
    r = client.get("/api/flags/example")
    assert r.status_code == 404


def test_list_flags_requires_owner():
    r = client.get("/api/flags")
    assert r.status_code == 401


def test_set_flag_requires_owner():
    r = client.post("/api/flags/example_reference_endpoint", json={"enabled": True})
    assert r.status_code == 401


def test_owner_can_list_flags(as_owner):
    r = client.get("/api/flags")
    assert r.status_code == 200
    names = [f["name"] for f in r.json()["flags"]]
    assert "example_reference_endpoint" in names
    flag = next(f for f in r.json()["flags"] if f["name"] == "example_reference_endpoint")
    assert flag["enabled"] is False


def test_toggle_on_then_off_at_runtime_no_restart(as_owner):
    r_on = client.post("/api/flags/example_reference_endpoint", json={"enabled": True})
    assert r_on.status_code == 200
    assert r_on.json() == {"name": "example_reference_endpoint", "enabled": True}
    assert server.flag_enabled("example_reference_endpoint") is True

    # the gated route now serves 200 with no server restart
    r_get = client.get("/api/flags/example")
    assert r_get.status_code == 200

    r_off = client.post("/api/flags/example_reference_endpoint", json={"enabled": False})
    assert r_off.status_code == 200
    assert server.flag_enabled("example_reference_endpoint") is False
    assert client.get("/api/flags/example").status_code == 404


def test_setting_unknown_flag_name_is_rejected(as_owner):
    r = client.post("/api/flags/not_a_real_flag", json={"enabled": True})
    assert r.status_code == 404
    assert server.flag_enabled("not_a_real_flag") is False


def test_flag_toggle_is_recorded_in_audit_chain(as_owner, monkeypatch):
    recorded = []
    monkeypatch.setattr(server, "audit_chain_append", lambda e: recorded.append(e))
    client.post("/api/flags/example_reference_endpoint", json={"enabled": True})
    assert len(recorded) == 1
    assert recorded[0]["type"] == "feature_flag_set"
    assert recorded[0]["flag"] == "example_reference_endpoint"
    assert recorded[0]["enabled"] is True
    assert recorded[0]["by"] == "owner"

