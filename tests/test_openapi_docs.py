"""Smoke tests for the OpenAPI/Swagger/ReDoc docs endpoints.

Originally written against FastAPI's default /docs, /redoc, /openapi.json
paths (#172). #214 (merged later) moved them to /api/docs, /api/redoc,
/api/openapi.json via an explicit docs_url/redoc_url/openapi_url override in
server.py's FastAPI(...) call - updated here to match. These tests only
confirm the routes render/parse, they do NOT assert anything about auth on
them (still unauthenticated by default; that's an owner decision, not one
this test file makes).
"""
import os
import sys

os.environ.setdefault("DATA_DIR", os.path.join(os.getcwd(), "data"))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient  # noqa: E402

import server  # noqa: E402

client = TestClient(server.app)


def test_openapi_json_is_valid_schema():
    r = client.get("/api/openapi.json")
    assert r.status_code == 200
    schema = r.json()
    assert schema["openapi"].startswith("3.")
    assert schema["info"]["title"] == "CodeMonkeys"
    assert len(schema["paths"]) > 50


def test_swagger_docs_renders():
    r = client.get("/api/docs")
    assert r.status_code == 200
    assert "swagger-ui" in r.text.lower()


def test_redoc_renders():
    r = client.get("/api/redoc")
    assert r.status_code == 200
    assert "redoc" in r.text.lower()


def test_default_paths_are_gone_not_silently_stale():
    """Regression guard: if a future change reverts docs_url to the default
    without updating this file, we want a clear failure here, not a subtly
    wrong assumption baked into the tests above."""
    assert client.get("/docs").status_code == 404
    assert client.get("/redoc").status_code == 404
    assert client.get("/openapi.json").status_code == 404
