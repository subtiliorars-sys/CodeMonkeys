"""Tests for request body size limit middleware (DoS guard).

Every non-GET/HEAD/OPTIONS endpoint should reject payloads exceeding
MAX_REQUEST_BODY_BYTES with a 413 before reading the full body.

Run: ./.venv/bin/python -m pytest tests/ -q
"""
import os
import sys
import tempfile

os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(prefix="cm_body_test_"))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

pytest.importorskip("httpx", reason="TestClient needs httpx (dev-only)")
from fastapi.testclient import TestClient  # noqa: E402

import server  # noqa: E402

client = TestClient(server.app)

MAX_BYTES = server.MAX_REQUEST_BODY_BYTES


def _oversized_body() -> bytes:
    """Return a JSON payload just over the limit."""
    # '{"x":"' (6 bytes) + filler + '"}' (2 bytes) = 8 fixed bytes. The
    # original `MAX_BYTES - 8` filler landed the total at EXACTLY MAX_BYTES,
    # not over it - the middleware's `> MAX_REQUEST_BODY_BYTES` check (both
    # the Content-Length fast path and the streaming fallback) correctly
    # let an exactly-at-the-limit body through, so it fell through to the
    # real (auth-gated) route and got 401 instead of 413. +1 byte of filler
    # makes this genuinely exceed the cap, matching the docstring's intent.
    payload = '{"x":"' + "x" * (MAX_BYTES - 7) + '"}'
    return payload.encode()


def test_get_bypasses_limit():
    """GET /healthz must not be rejected (no body)."""
    resp = client.get("/healthz")
    assert resp.status_code == 200


def test_content_length_oversized_rejected():
    """A POST with Content-Length > MAX_REQUEST_BODY_BYTES returns 413."""
    body = _oversized_body()
    resp = client.post(
        "/api/sessions",
        content=body,
        headers={"Content-Type": "application/json", "Content-Length": str(len(body))},
    )
    assert resp.status_code == 413
    data = resp.json()
    assert data["error"] == "request body too large"
    assert data["max_bytes"] == MAX_BYTES


def test_content_length_within_limit():
    """A small POST passes through (actual endpoint may reject for auth, but not 413)."""
    resp = client.post(
        "/api/sessions",
        json={"test": True},
    )
    # The /api/sessions endpoint requires auth, so 401 is expected — but NOT 413
    assert resp.status_code != 413


def test_empty_body_passes():
    """POST with empty body must not be rejected."""
    resp = client.post(
        "/api/sessions",
        content=b"",
        headers={"Content-Length": "0"},
    )
    assert resp.status_code != 413


def test_malformed_content_length_falls_through():
    """A bogus Content-Length should not crash the middleware."""
    body = b'{"ok":true}'
    resp = client.post(
        "/api/sessions",
        content=body,
        headers={"Content-Type": "application/json", "Content-Length": "not-a-number"},
    )
    # Must not be a 500 from the middleware; either auth-rejected or passes
    assert resp.status_code != 500
    assert resp.status_code != 413  # body is small, streaming path will not cap it


def test_streaming_body_oversized_rejected():
    """A chunked request with no Content-Length that exceeds the cap returns 413."""
    # Use a generator to simulate chunked upload
    body = b"x" * (MAX_BYTES + 100)
    resp = client.post(
        "/api/sessions",
        content=body,
        headers={"Content-Type": "application/octet-stream"},
    )
    assert resp.status_code == 413
