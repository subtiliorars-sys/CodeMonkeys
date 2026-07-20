"""#180 - request size limits + malformed-body handling.

Covers: oversized bodies rejected with 413 before reaching a handler
(auth included), malformed JSON rejected with 400 (not FastAPI's default
422), and genuine schema-validation failures still get the standard 422 -
only the JSON-decode case is reclassified.
"""
import os
import sys

os.environ.setdefault("DATA_DIR", os.path.join(os.getcwd(), "data"))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient  # noqa: E402

import server  # noqa: E402

client = TestClient(server.app)


def test_oversized_body_rejected_with_413():
    body = b"x" * (server.MAX_BODY_BYTES + 1)
    r = client.post("/api/mcp", content=body,
                     headers={"content-type": "application/json"})
    assert r.status_code == 413
    assert "detail" in r.json()


def test_body_at_exact_limit_is_not_rejected_by_size_check():
    """The limit is exclusive - exactly MAX_BODY_BYTES must pass the size
    gate (it may still fail downstream for other reasons, e.g. auth/shape,
    but never with 413)."""
    body = b"{" + b" " * (server.MAX_BODY_BYTES - 2) + b"}"
    r = client.post("/api/mcp", content=body,
                     headers={"content-type": "application/json"})
    assert r.status_code != 413


def test_malformed_json_body_rejected_with_400():
    r = client.post("/api/mcp", content=b"{not valid json",
                     headers={"content-type": "application/json"})
    assert r.status_code == 400
    assert "json" in r.json()["detail"].lower()


def test_non_json_garbage_body_rejected_with_400():
    r = client.post("/api/mcp", content=b"plain text, not even braces",
                     headers={"content-type": "application/json"})
    assert r.status_code == 400


def test_valid_json_wrong_shape_keeps_422_not_400():
    """A body that parses fine as JSON but fails pydantic's schema (wrong
    type, missing field) is a semantic error, not a syntax error - the
    reclassification to 400 must NOT swallow this case."""
    r = client.post("/api/mcp", json={"name": 12345})  # name should be str-ish shape
    assert r.status_code in (401, 422)  # auth may short-circuit first
    if r.status_code == 422:
        assert isinstance(r.json()["detail"], list)


def test_healthz_unaffected_by_body_limit_middleware():
    r = client.get("/healthz")
    assert r.status_code == 200
