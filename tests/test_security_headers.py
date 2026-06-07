"""Tests for baseline security response headers.

The console is auth-gated but fronts a shell; the login page handles PIN + TOTP.
Every response should carry anti-clickjacking / no-sniff / no-referrer headers
and a minimal CSP, so a cross-origin page can't frame-and-phish the console.

Uses Starlette's TestClient (httpx); skipped if httpx isn't installed (it is a
dev/test-only dep, not in requirements.txt).
Run: ./.venv/bin/python -m pytest tests/ -q
"""
import os
import sys
import tempfile

os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(prefix="cm_test_"))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

pytest.importorskip("httpx", reason="TestClient needs httpx (dev-only)")
from fastapi.testclient import TestClient  # noqa: E402

import server  # noqa: E402

client = TestClient(server.app)

EXPECTED = {
    "x-frame-options": "SAMEORIGIN",
    "x-content-type-options": "nosniff",
    "referrer-policy": "no-referrer",
}


def _assert_headers(resp):
    for k, v in EXPECTED.items():
        assert resp.headers.get(k) == v, f"{k} missing/wrong: {resp.headers.get(k)!r}"
    csp = resp.headers.get("content-security-policy", "")
    assert "frame-ancestors 'self'" in csp
    assert "object-src 'none'" in csp
    # Tailwind phase 2: every script is a same-origin file (CDN <script> gone)
    assert "script-src 'self'" in csp


def test_headers_on_html_root():
    # "/" serves the console HTML
    _assert_headers(client.get("/"))


def test_headers_on_unauthenticated_401():
    # a fail-closed 401 must still carry the headers (the login page lives here)
    r = client.get("/api/me")
    assert r.status_code == 401
    _assert_headers(r)


def test_headers_on_json_api():
    # any JSON response path
    r = client.post("/api/login", json={"username": "nobody", "pin": "0000", "mfa_code": "000000"})
    assert r.status_code in (401, 429)
    _assert_headers(r)
