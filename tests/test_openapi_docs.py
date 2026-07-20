"""Smoke tests for the OpenAPI/Swagger/ReDoc docs endpoints (#172).

FastAPI serves /docs, /redoc, and /openapi.json unauthenticated by default
(no docs_url/redoc_url override in server.py) - these tests only confirm
they render/parse, they do NOT assert anything about auth on these routes.
Whether that default exposure is intended is a separate owner decision,
tracked in issue #172's discussion, not something this test file decides.
"""
import os
import sys

os.environ.setdefault("DATA_DIR", os.path.join(os.getcwd(), "data"))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient  # noqa: E402

import server  # noqa: E402

client = TestClient(server.app)


def test_openapi_json_is_valid_schema():
    r = client.get("/openapi.json")
    assert r.status_code == 200
    schema = r.json()
    assert schema["openapi"].startswith("3.")
    assert schema["info"]["title"] == "CodeMonkeys"
    assert len(schema["paths"]) > 50


def test_swagger_docs_renders():
    r = client.get("/docs")
    assert r.status_code == 200
    assert "swagger-ui" in r.text.lower()


def test_redoc_renders():
    r = client.get("/redoc")
    assert r.status_code == 200
    assert "redoc" in r.text.lower()
