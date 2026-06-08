"""Layer A: free-model auto-lister tests.

Covers:
  - Free filter selects only price-0 models (pricing.prompt==0 AND pricing.completion==0)
  - Refresh maps per-token → per-1M and rejects null/non-finite pricing
  - Add-all upserts free model IDs at cost 0 (tier t0); doesn't touch key/selected
  - Idempotent: add-all is safe to run multiple times without creating duplicates
  - All three endpoints are owner-only

Run: ./.venv/bin/python -m pytest tests/test_free_models.py -v
"""
import json
import os
import sys
import tempfile
import unittest.mock

os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(prefix="cm_test_"))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient

import server

client = TestClient(server.app)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _override_owner():
    server.app.dependency_overrides[server.verify_owner] = lambda: "owner"

def _remove_override():
    server.app.dependency_overrides.pop(server.verify_owner, None)

def _or_response(data: list) -> bytes:
    """Fake OpenRouter /v1/models response payload."""
    return json.dumps({"data": data}).encode()

def _model(mid, prompt, completion, name=None):
    return {"id": mid, "name": name or mid,
            "pricing": {"prompt": str(prompt), "completion": str(completion)}}

def _reset_or_cooldown():
    """Reset the in-memory OpenRouter refresh cooldown so tests don't block each other."""
    server._or_last_refresh = 0.0

def _set_catalog(catalog: list):
    """Directly write a catalog into the OpenRouter provider entry."""
    cfg = server.load_models()
    cfg["providers"].setdefault("openrouter", {})["catalog"] = catalog
    server.save_models(cfg)

# ---------------------------------------------------------------------------
# Free filter: only price-0 models qualify
# ---------------------------------------------------------------------------

def test_free_filter_zero_price(monkeypatch):
    """GET /api/models/openrouter/free returns only in==0 AND out==0 entries."""
    _set_catalog([
        {"id": "free/model-a", "name": "Free A", "in": 0.0, "out": 0.0},
        {"id": "paid/model-b", "name": "Paid B", "in": 3.0, "out": 15.0},
        {"id": "half-free/model-c", "name": "Half C", "in": 0.0, "out": 0.5},
    ])
    _override_owner()
    try:
        r = client.get("/api/models/openrouter/free")
        assert r.status_code == 200
        data = r.json()
        ids = [m["id"] for m in data["free"]]
        assert "free/model-a" in ids
        assert "paid/model-b" not in ids
        assert "half-free/model-c" not in ids
    finally:
        _remove_override()


def test_free_filter_empty_catalog(monkeypatch):
    """No catalog → empty free list, no error."""
    cfg = server.load_models()
    cfg["providers"]["openrouter"]["catalog"] = []
    server.save_models(cfg)
    _override_owner()
    try:
        r = client.get("/api/models/openrouter/free")
        assert r.status_code == 200
        assert r.json()["free"] == []
    finally:
        _remove_override()


def test_free_filter_requires_owner():
    r = client.get("/api/models/openrouter/free")
    assert r.status_code in (401, 403)


# ---------------------------------------------------------------------------
# Refresh: pricing conversion + bad-data guards
# ---------------------------------------------------------------------------

_OR_SAMPLE = [
    _model("free/qwen3-coder:free",  "0",     "0"),          # free
    _model("paid/claude-sonnet",     "3e-6",  "15e-6"),      # paid: 3$/M in, 15$/M out
    _model("partial/model-x",        None,    "0"),           # null prompt → skip
    _model("bad/model-y",            "inf",   "0"),           # non-finite → skip
    _model("negative/model-z",       "-1e-6", "0"),           # negative → skip
    _model("free/model-b",           "0",     "0"),           # another free
]


def test_refresh_maps_per_token_to_per_million(monkeypatch):
    """Pricing per-token × 1e6 == per-million stored in catalog."""
    _reset_or_cooldown()
    paid = _model("paid/claude-sonnet", "3e-6", "15e-6")
    raw = json.dumps({"data": [paid]}).encode()
    mock_resp = unittest.mock.MagicMock()
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = lambda s, *a: False
    mock_resp.read = lambda: raw
    monkeypatch.setattr(server.urllib.request, "urlopen", lambda *a, **kw: mock_resp)
    _override_owner()
    try:
        r = client.post("/api/models/openrouter/refresh")
        assert r.status_code == 200
        catalog = server.load_models()["providers"]["openrouter"]["catalog"]
        entry = next(e for e in catalog if e["id"] == "paid/claude-sonnet")
        # 3e-6 per token × 1e6 = 3.0 per million
        assert abs(entry["in"] - 3.0) < 1e-9
        assert abs(entry["out"] - 15.0) < 1e-9
    finally:
        _remove_override()


_OR_SAMPLE_RAW = json.dumps({"data": _OR_SAMPLE}).encode()


def test_refresh_skips_null_and_bad_pricing(monkeypatch):
    """Models with null, non-finite, or negative pricing are excluded from catalog."""
    _reset_or_cooldown()
    mock_resp = unittest.mock.MagicMock()
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = lambda s, *a: False
    mock_resp.read = lambda: _OR_SAMPLE_RAW
    monkeypatch.setattr(server.urllib.request, "urlopen", lambda *a, **kw: mock_resp)
    _override_owner()
    try:
        r = client.post("/api/models/openrouter/refresh")
        assert r.status_code == 200
        catalog = server.load_models()["providers"]["openrouter"]["catalog"]
        ids = {e["id"] for e in catalog}
        assert "partial/model-x" not in ids
        assert "bad/model-y" not in ids
        assert "negative/model-z" not in ids
        assert "free/qwen3-coder:free" in ids
        assert "free/model-b" in ids
        assert "paid/claude-sonnet" in ids
    finally:
        _remove_override()


def test_refresh_free_count_in_response(monkeypatch):
    """Refresh response reports correct total and free counts."""
    _reset_or_cooldown()
    mock_resp = unittest.mock.MagicMock()
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = lambda s, *a: False
    mock_resp.read = lambda: _OR_SAMPLE_RAW
    monkeypatch.setattr(server.urllib.request, "urlopen", lambda *a, **kw: mock_resp)
    _override_owner()
    try:
        r = client.post("/api/models/openrouter/refresh")
        data = r.json()
        # 3 valid models: free/qwen3-coder:free, paid/claude-sonnet, free/model-b
        assert data["total"] == 3
        assert data["free"] == 2
    finally:
        _remove_override()


def test_refresh_does_not_touch_key_or_selected(monkeypatch):
    """Refresh must never alter the provider's key or the selected field."""
    _reset_or_cooldown()
    cfg = server.load_models()
    cfg["providers"]["openrouter"]["key"] = "sk-sentinel-key"
    cfg["selected"] = "anthropic"
    server.save_models(cfg)

    mock_resp = unittest.mock.MagicMock()
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = lambda s, *a: False
    mock_resp.read = lambda: json.dumps({"data": []}).encode()
    monkeypatch.setattr(server.urllib.request, "urlopen", lambda *a, **kw: mock_resp)
    _override_owner()
    try:
        client.post("/api/models/openrouter/refresh")
        cfg2 = server.load_models()
        assert cfg2["providers"]["openrouter"]["key"] == "sk-sentinel-key"
        assert cfg2["selected"] == "anthropic"
    finally:
        _remove_override()


def test_refresh_requires_owner():
    r = client.post("/api/models/openrouter/refresh")
    assert r.status_code in (401, 403)


def test_refresh_cooldown_blocks_rapid_calls(monkeypatch):
    """Second refresh within cooldown window must return 429."""
    _reset_or_cooldown()
    mock_resp = unittest.mock.MagicMock()
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = lambda s, *a: False
    mock_resp.read = lambda: json.dumps({"data": []}).encode()
    monkeypatch.setattr(server.urllib.request, "urlopen", lambda *a, **kw: mock_resp)
    _override_owner()
    try:
        r1 = client.post("/api/models/openrouter/refresh")
        assert r1.status_code == 200
        r2 = client.post("/api/models/openrouter/refresh")
        assert r2.status_code == 429
    finally:
        _reset_or_cooldown()
        _remove_override()


def test_delete_provider_404_when_missing():
    """DELETE on an unknown provider id must return 404."""
    _override_owner()
    try:
        r = client.delete("/api/models/does-not-exist-xyz")
        assert r.status_code == 404
    finally:
        _remove_override()


# ---------------------------------------------------------------------------
# Add-all: upserts at t0, idempotent, doesn't touch keys/selection
# ---------------------------------------------------------------------------

def test_add_all_free_upserts_ids(monkeypatch):
    """Add-all adds all free model IDs to the openrouter models list."""
    _set_catalog([
        {"id": "free/a", "name": "A", "in": 0.0, "out": 0.0},
        {"id": "free/b", "name": "B", "in": 0.0, "out": 0.0},
        {"id": "paid/c", "name": "C", "in": 1.0, "out": 2.0},
    ])
    cfg = server.load_models()
    cfg["providers"]["openrouter"]["models"] = []  # start empty
    server.save_models(cfg)
    _override_owner()
    try:
        r = client.post("/api/models/free/add_all")
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert data["added"] == 2
        assert data["total"] == 2
        models = server.load_models()["providers"]["openrouter"]["models"]
        assert "free/a" in models
        assert "free/b" in models
        assert "paid/c" not in models
    finally:
        _remove_override()


def test_add_all_free_idempotent(monkeypatch):
    """Calling Add-all twice doesn't create duplicate model entries."""
    _set_catalog([
        {"id": "free/x", "name": "X", "in": 0.0, "out": 0.0},
    ])
    cfg = server.load_models()
    cfg["providers"]["openrouter"]["models"] = []
    server.save_models(cfg)
    _override_owner()
    try:
        client.post("/api/models/free/add_all")
        r2 = client.post("/api/models/free/add_all")
        assert r2.status_code == 200
        assert r2.json()["added"] == 0          # nothing new on second run
        models = server.load_models()["providers"]["openrouter"]["models"]
        assert models.count("free/x") == 1      # no duplicate
    finally:
        _remove_override()


def test_add_all_free_doesnt_touch_key_or_selected():
    """Add-all must not alter the provider key or the selected model."""
    _set_catalog([{"id": "free/y", "name": "Y", "in": 0.0, "out": 0.0}])
    cfg = server.load_models()
    cfg["providers"]["openrouter"]["key"] = "sk-do-not-touch"
    cfg["providers"]["openrouter"]["models"] = []
    cfg["selected"] = "openai"
    server.save_models(cfg)
    _override_owner()
    try:
        client.post("/api/models/free/add_all")
        cfg2 = server.load_models()
        assert cfg2["providers"]["openrouter"]["key"] == "sk-do-not-touch"
        assert cfg2["selected"] == "openai"
    finally:
        _remove_override()


def test_add_all_free_at_tier_t0():
    """Free models (cost 0) end up at tier t0 in provider_for_tier routing."""
    _set_catalog([{"id": "free/z", "name": "Z", "in": 0.0, "out": 0.0}])
    # Set up openrouter with a key so it's callable, and a paid provider too.
    cfg = server.load_models()
    cfg["providers"]["openrouter"]["key"] = "sk-test"
    cfg["providers"]["openrouter"]["in"] = 0.0
    cfg["providers"]["openrouter"]["out"] = 0.0
    cfg["providers"]["openrouter"]["models"] = ["free/z"]
    cfg["providers"]["openrouter"]["model"] = "free/z"
    cfg["providers"].setdefault("openai", {})["key"] = "sk-paid"
    cfg["providers"]["openai"]["in"] = 3.0
    cfg["providers"]["openai"]["out"] = 15.0
    cfg["providers"]["openai"]["kind"] = "openai"
    cfg["providers"]["openai"]["base_url"] = "https://api.openai.com/v1"
    cfg["providers"]["openai"]["model"] = "gpt-4o"
    cfg["providers"]["openai"]["out"] = 15.0
    server.save_models(cfg)
    # t0 must resolve to the cheapest (cost=0) provider — openrouter
    resolved = server.provider_for_tier(cfg, "t0")
    assert resolved is not None
    assert resolved["pid"] == "openrouter"


def test_add_all_free_empty_catalog_returns_400():
    """Add-all on an uncached catalog returns 400, not a silent no-op."""
    cfg = server.load_models()
    cfg["providers"]["openrouter"]["catalog"] = []
    server.save_models(cfg)
    _override_owner()
    try:
        r = client.post("/api/models/free/add_all")
        assert r.status_code == 400
    finally:
        _remove_override()


def test_add_all_free_requires_owner():
    r = client.post("/api/models/free/add_all")
    assert r.status_code in (401, 403)


# ---------------------------------------------------------------------------
# Redaction invariant: catalog model IDs must NOT be collected as secrets
# ---------------------------------------------------------------------------

def test_catalog_ids_not_in_sensitive_values():
    """_sensitive_values() collects provider keys, not catalog model IDs.

    If catalog IDs were treated as secrets they would be [REDACTED] in chat
    output whenever the model name appeared — a confusing false positive.
    """
    marker_id = "free/catalog-test-model-should-not-redact:free"
    _set_catalog([{"id": marker_id, "name": "Test", "in": 0.0, "out": 0.0}])
    # Bust cache so _sensitive_values re-reads the config
    server._bust_secret_cache()
    vals = server._sensitive_values()
    assert marker_id not in vals, (
        f"Catalog model ID '{marker_id}' ended up in _sensitive_values — "
        "it would be redacted from chat output as if it were an API key."
    )


def test_model_entry_delete_endpoint():
    """DELETE /api/models/{pid}/models/{mid} removes the model from the list."""
    cfg = server.load_models()
    cfg["providers"]["openrouter"]["models"] = ["model-a", "model-b", "model-c"]
    cfg["providers"]["openrouter"]["model"] = "model-a"
    server.save_models(cfg)
    _override_owner()
    try:
        r = client.delete("/api/models/openrouter/models/model-b")
        assert r.status_code == 200
        models = server.load_models()["providers"]["openrouter"]["models"]
        assert "model-b" not in models
        assert "model-a" in models
        assert "model-c" in models
    finally:
        _remove_override()


def test_model_entry_delete_active_model_fallback():
    """Removing the active model falls back to the first remaining model."""
    cfg = server.load_models()
    cfg["providers"]["openrouter"]["models"] = ["model-x", "model-y"]
    cfg["providers"]["openrouter"]["model"] = "model-x"
    server.save_models(cfg)
    _override_owner()
    try:
        client.delete("/api/models/openrouter/models/model-x")
        prov = server.load_models()["providers"]["openrouter"]
        assert prov["model"] == "model-y"
    finally:
        _remove_override()


def test_model_entry_delete_404_unknown_model():
    """Removing a model that isn't in the list returns 404."""
    cfg = server.load_models()
    cfg["providers"]["openrouter"]["models"] = ["real-model"]
    server.save_models(cfg)
    _override_owner()
    try:
        r = client.delete("/api/models/openrouter/models/ghost-model")
        assert r.status_code == 404
    finally:
        _remove_override()


def test_model_entry_delete_requires_owner():
    r = client.delete("/api/models/openrouter/models/anything")
    assert r.status_code in (401, 403)


# ---------------------------------------------------------------------------
# Key-save resets catalog_refreshed_at
# ---------------------------------------------------------------------------

def test_key_save_clears_catalog_refreshed_at():
    """Saving a new key removes catalog_refreshed_at so stale indicator resets."""
    cfg = server.load_models()
    cfg["providers"]["openrouter"]["catalog_refreshed_at"] = 1_000_000
    cfg["providers"]["openrouter"]["catalog"] = []
    server.save_models(cfg)
    _override_owner()
    try:
        r = client.post("/api/models", json={
            "id": "openrouter", "label": "OpenRouter", "kind": "openai",
            "base_url": "https://openrouter.ai/api/v1",
            "model": "qwen/qwen3-coder:free", "models": [],
            "key": "sk-new-key-xyz", "input_cost_per_m": 0, "output_cost_per_m": 0,
            "auto": True,
        })
        assert r.status_code == 200
        prov = server.load_models()["providers"]["openrouter"]
        assert "catalog_refreshed_at" not in prov
    finally:
        _remove_override()


def test_key_hint_shows_last_four_chars():
    """GET /api/models includes key_hint = last 4 chars of stored key."""
    cfg = server.load_models()
    cfg["providers"]["openrouter"]["key"] = "sk-abcdef1234"
    server.save_models(cfg)
    _override_owner()
    try:
        r = client.get("/api/models")
        or_prov = next(p for p in r.json()["providers"] if p["id"] == "openrouter")
        assert or_prov["key_hint"] == "…1234"
    finally:
        _remove_override()


def test_key_hint_empty_when_no_key():
    """key_hint is empty string when no key is stored."""
    cfg = server.load_models()
    cfg["providers"]["openrouter"]["key"] = ""
    server.save_models(cfg)
    _override_owner()
    try:
        r = client.get("/api/models")
        or_prov = next(p for p in r.json()["providers"] if p["id"] == "openrouter")
        assert or_prov["key_hint"] == ""
    finally:
        _remove_override()


def test_key_save_blank_preserves_catalog_refreshed_at():
    """Saving with a blank key (keep existing) must NOT clear catalog_refreshed_at."""
    cfg = server.load_models()
    cfg["providers"]["openrouter"]["catalog_refreshed_at"] = 1_000_001
    cfg["providers"]["openrouter"]["key"] = "sk-existing"
    server.save_models(cfg)
    _override_owner()
    try:
        client.post("/api/models", json={
            "id": "openrouter", "label": "OpenRouter", "kind": "openai",
            "base_url": "https://openrouter.ai/api/v1",
            "model": "qwen/qwen3-coder:free", "models": [],
            "key": "",  # blank = keep existing
            "input_cost_per_m": 0, "output_cost_per_m": 0, "auto": True,
        })
        prov = server.load_models()["providers"]["openrouter"]
        assert prov.get("catalog_refreshed_at") == 1_000_001
    finally:
        _remove_override()


def test_refresh_stores_last_error_on_network_failure(monkeypatch):
    """Failed refresh stores last_error + last_error_at on the provider."""
    _reset_or_cooldown()
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **kw: (_ for _ in ()).throw(OSError("timeout")))
    _override_owner()
    try:
        r = client.post("/api/models/openrouter/refresh")
        assert r.status_code == 502
        prov = server.load_models()["providers"]["openrouter"]
        assert "timeout" in prov.get("last_error", "")
        assert prov.get("last_error_at") is not None
    finally:
        _remove_override()


def test_refresh_clears_last_error_on_success(monkeypatch):
    """Successful refresh removes last_error and last_error_at."""
    _reset_or_cooldown()
    # Pre-seed a previous error
    cfg = server.load_models()
    cfg["providers"]["openrouter"]["last_error"] = "old error"
    cfg["providers"]["openrouter"]["last_error_at"] = 1
    server.save_models(cfg)

    payload = _or_response([_model("free/model", 0, 0)])
    class _Resp:
        def read(self): return payload
        def __enter__(self): return self
        def __exit__(self, *a): pass
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **kw: _Resp())
    _override_owner()
    try:
        r = client.post("/api/models/openrouter/refresh")
        assert r.status_code == 200
        prov = server.load_models()["providers"]["openrouter"]
        assert "last_error" not in prov
        assert "last_error_at" not in prov
    finally:
        _remove_override()


def test_models_get_exposes_last_error_fields():
    """GET /api/models includes last_error and last_error_at when set."""
    cfg = server.load_models()
    cfg["providers"]["openrouter"]["last_error"] = "network down"
    cfg["providers"]["openrouter"]["last_error_at"] = 9999
    server.save_models(cfg)
    _override_owner()
    try:
        r = client.get("/api/models")
        or_prov = next(p for p in r.json()["providers"] if p["id"] == "openrouter")
        assert or_prov["last_error"] == "network down"
        assert or_prov["last_error_at"] == 9999
    finally:
        _remove_override()


def test_export_strips_keys():
    """GET /api/models/export returns config without keys, includes has_key bool."""
    cfg = server.load_models()
    cfg["providers"]["openrouter"]["key"] = "sk-secret-key-123"
    server.save_models(cfg)
    _override_owner()
    try:
        r = client.get("/api/models/export")
        assert r.status_code == 200
        data = r.json()
        or_prov = next(p for p in data["providers"] if p["id"] == "openrouter")
        assert "key" not in or_prov
        assert or_prov["has_key"] is True
        assert "sk-secret" not in str(data)
    finally:
        _remove_override()


def test_export_requires_owner():
    """GET /api/models/export is owner-only."""
    r = client.get("/api/models/export")
    assert r.status_code == 401


def test_provider_notes_roundtrip():
    """Notes field is saved and returned by GET /api/models."""
    _override_owner()
    try:
        client.post("/api/models", json={
            "id": "openrouter", "label": "OpenRouter", "kind": "openai",
            "base_url": "https://openrouter.ai/api/v1",
            "model": "qwen/qwen3-coder:free", "models": [],
            "key": "", "notes": "use for cheap tasks",
            "input_cost_per_m": 0, "output_cost_per_m": 0, "auto": True,
        })
        r = client.get("/api/models")
        or_prov = next(p for p in r.json()["providers"] if p["id"] == "openrouter")
        assert or_prov["notes"] == "use for cheap tasks"
    finally:
        _remove_override()


def test_provider_notes_blank_preserves_existing():
    """Sending empty notes string keeps existing notes (not overwrite)."""
    cfg = server.load_models()
    cfg["providers"]["openrouter"]["notes"] = "pre-existing note"
    server.save_models(cfg)
    _override_owner()
    try:
        # POST with empty notes — should keep existing
        client.post("/api/models", json={
            "id": "openrouter", "label": "OpenRouter", "kind": "openai",
            "base_url": "https://openrouter.ai/api/v1",
            "model": "qwen/qwen3-coder:free", "models": [],
            "key": "", "notes": "",
            "input_cost_per_m": 0, "output_cost_per_m": 0, "auto": True,
        })
        prov = server.load_models()["providers"]["openrouter"]
        assert prov.get("notes") == "pre-existing note"
    finally:
        _remove_override()
