"""N12 — model catalog / pricing refresh tests.

Covers:
  - Manual add/update model with per-model costs (PUT endpoint)
  - Cost validation rejects non-finite/negative on upsert + catalog PUT
  - _resolve uses per-model catalog costs for call_cost
  - OpenRouter refresh preserves manual costs and owner-pinned entries
  - Refresh never alters key/selected; owner-only gates

Run: ./.venv/bin/python -m pytest tests/test_model_catalog.py -v
"""
import json
import os
import sys
import tempfile

os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(prefix="cm_test_"))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient

import server

client = TestClient(server.app)


def _override_owner():
    server.app.dependency_overrides[server.verify_owner] = lambda: "owner"


def _remove_override():
    server.app.dependency_overrides.pop(server.verify_owner, None)


def _reset_or_cooldown():
    server._or_last_refresh = 0.0


def _or_response(data: list) -> bytes:
    return json.dumps({"data": data}).encode()


def _model(mid, prompt, completion, name=None):
    return {"id": mid, "name": name or mid,
            "pricing": {"prompt": str(prompt), "completion": str(completion)}}


# ---------------------------------------------------------------------------
# Manual catalog PUT
# ---------------------------------------------------------------------------

def test_model_entry_upsert_adds_model_with_costs():
    cfg = server.load_models()
    cfg["providers"]["anthropic"]["models"] = ["claude-sonnet-4-6"]
    cfg["providers"]["anthropic"]["catalog"] = []
    server.save_models(cfg)
    _override_owner()
    try:
        r = client.put("/api/models/anthropic/models/claude-haiku-4-5", json={
            "input_cost_per_m": 1.0, "output_cost_per_m": 5.0,
        })
        assert r.status_code == 200
        prov = server.load_models()["providers"]["anthropic"]
        assert "claude-haiku-4-5" in prov["models"]
        entry = server._catalog_lookup(prov, "claude-haiku-4-5")
        assert entry["in"] == 1.0
        assert entry["out"] == 5.0
        assert entry.get("manual") is True
    finally:
        _remove_override()


def test_model_entry_upsert_persists_after_reload():
    _override_owner()
    try:
        client.put("/api/models/openai/models/gpt-4.1-mini", json={"input_cost_per_m": 0.4, "output_cost_per_m": 1.6})
        cfg = server.load_models()
        entry = server._catalog_lookup(cfg["providers"]["openai"], "gpt-4.1-mini")
        assert entry is not None
        assert entry["in"] == 0.4
    finally:
        _remove_override()


def test_model_entry_upsert_rejects_negative_cost():
    _override_owner()
    try:
        r = client.put("/api/models/openai/models/bad-model", json={"input_cost_per_m": -1.0, "output_cost_per_m": 0.0})
        assert r.status_code == 422
    finally:
        _remove_override()


def test_model_entry_upsert_requires_owner():
    r = client.put("/api/models/openai/models/x", json={"input_cost_per_m": 0, "output_cost_per_m": 0})
    assert r.status_code in (401, 403)


def test_models_upsert_rejects_non_finite_cost():
    _override_owner()
    try:
        r = client.post("/api/models", json={
            "id": "openai", "label": "OpenAI", "kind": "openai",
            "base_url": "https://api.openai.com/v1",
            "model": "gpt-4o-mini", "models": ["gpt-4o-mini"],
            "input_cost_per_m": "Infinity", "output_cost_per_m": 0.6, "auto": False,
        })
        assert r.status_code == 422
    finally:
        _remove_override()


# ---------------------------------------------------------------------------
# _resolve uses per-model catalog costs
# ---------------------------------------------------------------------------

def test_resolve_uses_catalog_costs_for_active_model():
    prov = {
        "label": "Test", "kind": "openai", "base_url": "https://x/v1",
        "key": "sk-test", "model": "model-a", "in": 1.0, "out": 2.0,
        "catalog": [
            {"id": "model-a", "in": 0.5, "out": 1.5},
            {"id": "model-b", "in": 3.0, "out": 9.0},
        ],
    }
    resolved = server._resolve(prov, pid="test")
    assert resolved["input_cost_per_m"] == 0.5
    assert resolved["output_cost_per_m"] == 1.5
    cost = server.call_cost(resolved, 1_000_000, 1_000_000)
    assert cost == pytest.approx(2.0)


def test_call_cost_falls_back_to_provider_defaults():
    prov = {"in": 2.0, "out": 4.0, "model": "unknown", "catalog": []}
    resolved = server._resolve(prov)
    assert resolved["input_cost_per_m"] == 2.0
    assert resolved["output_cost_per_m"] == 4.0


# ---------------------------------------------------------------------------
# OpenRouter refresh merge policy
# ---------------------------------------------------------------------------

def test_refresh_preserves_manual_costs(monkeypatch):
    _reset_or_cooldown()
    cfg = server.load_models()
    cfg["providers"]["openrouter"]["catalog"] = [
        {"id": "paid/model", "in": 99.0, "out": 88.0, "manual": True},
    ]
    server.save_models(cfg)

    payload = _or_response([_model("paid/model", 0.000003, 0.000015)])
    class _Resp:
        def read(self): return payload
        def __enter__(self): return self
        def __exit__(self, *a): pass
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **kw: _Resp())
    _override_owner()
    try:
        r = client.post("/api/models/openrouter/refresh")
        assert r.status_code == 200
        entry = server._catalog_lookup(
            server.load_models()["providers"]["openrouter"], "paid/model")
        assert entry["in"] == 99.0
        assert entry["out"] == 88.0
        assert entry.get("manual") is True
    finally:
        _remove_override()


def test_refresh_keeps_manual_entries_not_in_api(monkeypatch):
    _reset_or_cooldown()
    cfg = server.load_models()
    cfg["providers"]["openrouter"]["catalog"] = [
        {"id": "owner/custom-model", "in": 1.0, "out": 2.0, "manual": True},
    ]
    server.save_models(cfg)

    payload = _or_response([_model("free/other", 0, 0)])
    class _Resp:
        def read(self): return payload
        def __enter__(self): return self
        def __exit__(self, *a): pass
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **kw: _Resp())
    _override_owner()
    try:
        client.post("/api/models/openrouter/refresh")
        catalog = server.load_models()["providers"]["openrouter"]["catalog"]
        ids = {e["id"] for e in catalog}
        assert "owner/custom-model" in ids
        assert "free/other" in ids
    finally:
        _remove_override()


def test_refresh_never_alters_key_or_selected(monkeypatch):
    _reset_or_cooldown()
    cfg = server.load_models()
    cfg["selected"] = "openrouter"
    cfg["providers"]["openrouter"]["key"] = "sk-or-test-key-12345"
    cfg["providers"]["openrouter"]["model"] = "qwen/qwen3-coder:free"
    server.save_models(cfg)

    payload = _or_response([_model("free/new", 0, 0)])
    class _Resp:
        def read(self): return payload
        def __enter__(self): return self
        def __exit__(self, *a): pass
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **kw: _Resp())
    _override_owner()
    try:
        client.post("/api/models/openrouter/refresh")
        cfg2 = server.load_models()
        assert cfg2["selected"] == "openrouter"
        assert cfg2["providers"]["openrouter"]["key"] == "sk-or-test-key-12345"
        assert cfg2["providers"]["openrouter"]["model"] == "qwen/qwen3-coder:free"
    finally:
        _remove_override()


def test_model_delete_removes_catalog_entry():
    cfg = server.load_models()
    cfg["providers"]["openrouter"]["models"] = ["keep-me", "drop-me"]
    cfg["providers"]["openrouter"]["catalog"] = [
        {"id": "keep-me", "in": 0, "out": 0},
        {"id": "drop-me", "in": 1, "out": 2, "manual": True},
    ]
    server.save_models(cfg)
    _override_owner()
    try:
        r = client.delete("/api/models/openrouter/models/drop-me")
        assert r.status_code == 200
        prov = server.load_models()["providers"]["openrouter"]
        assert "drop-me" not in prov["models"]
        assert server._catalog_lookup(prov, "drop-me") is None
        assert server._catalog_lookup(prov, "keep-me") is not None
    finally:
        _remove_override()


def test_ensure_catalog_entries_fills_gaps():
    prov = {"models": ["a", "b"], "in": 0.3, "out": 1.2, "catalog": [
        {"id": "a", "in": 0.3, "out": 1.2},
    ]}
    server._ensure_catalog_entries(prov)
    assert server._catalog_lookup(prov, "b") == {"id": "b", "in": 0.3, "out": 1.2}
