"""Tests for GET /readyz — N10 readiness probe.

Checks implemented
------------------
  data_writable       write + delete a temp file under DATA_DIR  (503-required)
  crypto_ok           CM_MASTER_KEY set → _FERNET_AVAILABLE must be True        (503-required)
  provider_configured at least one callable provider exists        (warning-only, never 503s alone)

Run: ./.venv/bin/python -m pytest tests/ -q
"""
import os
import sys
import tempfile
import stat

_TEST_DATA_DIR = tempfile.mkdtemp(prefix="cm_readyz_test_")
os.environ.setdefault("DATA_DIR", _TEST_DATA_DIR)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import server  # noqa: E402
from conftest import IS_WINDOWS  # noqa: E402


client = TestClient(server.app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Happy path — all checks green
# ---------------------------------------------------------------------------

def test_readyz_all_green(monkeypatch, tmp_path):
    """200 + status ready when every check passes."""
    monkeypatch.setattr(server, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(server, "_FERNET_AVAILABLE", True)
    monkeypatch.setattr(server, "CM_MASTER_KEY", "")  # unset → crypto_ok N/A = True
    monkeypatch.setattr(server, "_usable", lambda cfg, username=None: [("p1", {"key": "k"})])
    monkeypatch.setattr(server, "load_models", lambda: {"providers": {}})

    r = client.get("/readyz")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ready"
    assert body["checks"]["data_writable"] is True
    assert body["checks"]["crypto_ok"] is True
    assert body["checks"]["provider_configured"] is True


# ---------------------------------------------------------------------------
# data_writable = False → 503
# ---------------------------------------------------------------------------

@pytest.mark.skipif(IS_WINDOWS, reason="POSIX chmod read-only dir has no "
                      "reliable equivalent in Windows ACLs")
def test_readyz_data_not_writable(monkeypatch, tmp_path):
    """503 + data_writable False when DATA_DIR is not writable."""
    # Make the dir non-writable
    no_write = tmp_path / "ro"
    no_write.mkdir()
    no_write.chmod(stat.S_IRUSR | stat.S_IXUSR)

    monkeypatch.setattr(server, "DATA_DIR", str(no_write))
    monkeypatch.setattr(server, "_FERNET_AVAILABLE", True)
    monkeypatch.setattr(server, "CM_MASTER_KEY", "")
    monkeypatch.setattr(server, "_usable", lambda cfg, username=None: [("p1", {"key": "k"})])
    monkeypatch.setattr(server, "load_models", lambda: {"providers": {}})

    r = client.get("/readyz")
    assert r.status_code == 503
    body = r.json()
    assert body["status"] == "not ready"
    assert body["checks"]["data_writable"] is False


# ---------------------------------------------------------------------------
# crypto_ok = False → 503
# ---------------------------------------------------------------------------

def test_readyz_crypto_mismatch(monkeypatch, tmp_path):
    """503 when CM_MASTER_KEY is set but _FERNET_AVAILABLE is False."""
    monkeypatch.setattr(server, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(server, "CM_MASTER_KEY", "some-high-entropy-master-key-32b!")
    monkeypatch.setattr(server, "_FERNET_AVAILABLE", False)
    monkeypatch.setattr(server, "_usable", lambda cfg, username=None: [("p1", {"key": "k"})])
    monkeypatch.setattr(server, "load_models", lambda: {"providers": {}})

    r = client.get("/readyz")
    assert r.status_code == 503
    body = r.json()
    assert body["status"] == "not ready"
    assert body["checks"]["crypto_ok"] is False


def test_readyz_crypto_ok_when_key_unset(monkeypatch, tmp_path):
    """crypto_ok is True (N/A) when CM_MASTER_KEY is empty regardless of Fernet."""
    monkeypatch.setattr(server, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(server, "CM_MASTER_KEY", "")
    monkeypatch.setattr(server, "_FERNET_AVAILABLE", False)  # irrelevant when key unset
    monkeypatch.setattr(server, "_usable", lambda cfg, username=None: [("p1", {"key": "k"})])
    monkeypatch.setattr(server, "load_models", lambda: {"providers": {}})

    r = client.get("/readyz")
    assert r.status_code == 200
    assert r.json()["checks"]["crypto_ok"] is True


# ---------------------------------------------------------------------------
# provider_configured = False — warning-only, required checks still pass → 200
# ---------------------------------------------------------------------------

def test_readyz_no_provider_still_200(monkeypatch, tmp_path):
    """provider_configured=False is warning-only: 200 but status 'not ready'."""
    monkeypatch.setattr(server, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(server, "CM_MASTER_KEY", "")
    monkeypatch.setattr(server, "_FERNET_AVAILABLE", True)
    monkeypatch.setattr(server, "_usable", lambda cfg, username=None: [])       # no providers
    monkeypatch.setattr(server, "load_models", lambda: {"providers": {}})

    r = client.get("/readyz")
    # Required checks pass → NOT 503
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "not ready"
    assert body["checks"]["provider_configured"] is False
    assert body["checks"]["data_writable"] is True
    assert body["checks"]["crypto_ok"] is True


def test_readyz_no_provider_load_exception_still_200(monkeypatch, tmp_path):
    """Exception in load_models → provider_configured False, but still 200."""
    monkeypatch.setattr(server, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(server, "CM_MASTER_KEY", "")
    monkeypatch.setattr(server, "_FERNET_AVAILABLE", True)

    def _boom(_):
        raise RuntimeError("disk error")

    monkeypatch.setattr(server, "load_models", lambda: (_ for _ in ()).throw(RuntimeError("disk error")))
    monkeypatch.setattr(server, "_usable", _boom)

    r = client.get("/readyz")
    assert r.status_code == 200
    assert r.json()["checks"]["provider_configured"] is False


# ---------------------------------------------------------------------------
# No secrets in the response body
# ---------------------------------------------------------------------------

def test_readyz_no_secrets_in_body(monkeypatch, tmp_path):
    """Response must not contain API keys, paths, usernames, or config values."""
    secret_key = "super-secret-master-key-do-not-leak"
    monkeypatch.setattr(server, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(server, "CM_MASTER_KEY", secret_key)
    monkeypatch.setattr(server, "_FERNET_AVAILABLE", True)
    monkeypatch.setattr(server, "_usable", lambda cfg, username=None: [("p1", {"key": "sk-12345"})])
    monkeypatch.setattr(server, "load_models", lambda: {"providers": {}})

    r = client.get("/readyz")
    raw = r.text
    assert secret_key not in raw
    assert "sk-12345" not in raw
    # path components must not appear
    assert str(tmp_path) not in raw
    # only boolean values for checks — no stringified keys/config
    checks = r.json()["checks"]
    for v in checks.values():
        assert isinstance(v, bool), f"Expected bool, got {type(v)}: {v!r}"


# ---------------------------------------------------------------------------
# Standard fields present
# ---------------------------------------------------------------------------

def test_readyz_has_standard_fields(monkeypatch, tmp_path):
    """Response includes status, uptime_s, sessions, and checks."""
    monkeypatch.setattr(server, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(server, "CM_MASTER_KEY", "")
    monkeypatch.setattr(server, "_FERNET_AVAILABLE", True)
    monkeypatch.setattr(server, "_usable", lambda cfg, username=None: [("p1", {"key": "k"})])
    monkeypatch.setattr(server, "load_models", lambda: {"providers": {}})

    r = client.get("/readyz")
    body = r.json()
    assert "status" in body
    assert "uptime_s" in body
    assert "sessions" in body
    assert "checks" in body
    assert isinstance(body["uptime_s"], int)
    assert isinstance(body["sessions"], int)
