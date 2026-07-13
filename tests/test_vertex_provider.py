"""Vertex provider wiring — ADC readiness and URL builder."""
import os
import sys
import tempfile

os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(prefix="cm_vertex_test_"))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import server


def test_vertex_provider_in_defaults():
    assert "vertex-gemini" in server.DEFAULT_PROVIDERS
    p = server.DEFAULT_PROVIDERS["vertex-gemini"]
    assert p["kind"] == "vertex"
    assert p["model"].startswith("google/")


def test_openai_base_url_vertex():
    prov = server._resolve(server.DEFAULT_PROVIDERS["vertex-gemini"], pid="vertex-gemini")
    url = server._openai_base_url(prov)
    assert "aiplatform.googleapis.com" in url
    assert server.VERTEX_PROJECT in url
    assert url.endswith("/endpoints/openapi")


def test_callable_vertex_when_adc_present(monkeypatch):
    monkeypatch.setattr(server, "_user_can_use_vertex", lambda username=None: True)
    assert server._callable_provider(server.DEFAULT_PROVIDERS["vertex-gemini"])
