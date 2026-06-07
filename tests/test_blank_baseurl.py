"""Tests for the blank-base_url provider guard (Standing list S1).

Live-smoke bug 2026-06-07: an openai-kind provider entry with a blank base_url
reached the runtime and died with "Invalid URL '/chat/completions'", burning the
full transient-retry backoff before escalation rescued the session. Three layers:
  1. config-load repair — load_models() backfills built-in providers' base_url
     from DEFAULT_PROVIDERS,
  2. selection fail-fast — _usable()/main_provider() skip uncallable entries,
  3. call-time guard — _chat_openai raises a NON-transient RuntimeError.

Run: ./.venv/bin/python -m pytest tests/ -q
"""
import os
import sys
import tempfile

os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(prefix="cm_test_"))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

import server  # noqa: E402


def _prov(pid, kind="openai", base_url="http://x", key="k", out=1.0, auto=True):
    return {"label": pid, "kind": kind, "base_url": base_url, "key": key,
            "model": f"m-{pid}", "models": [f"m-{pid}"],
            "in": 0.0, "out": out, "auto": auto}


# ---- layer 2: selection fail-fast --------------------------------------------

def test_usable_skips_blank_baseurl_openai_provider():
    cfg = {"providers": {"good": _prov("good"),
                         "broken": _prov("broken", base_url="", out=0.1)}}
    assert [pid for pid, _ in server._usable(cfg)] == ["good"]


def test_usable_keeps_anthropic_with_blank_baseurl():
    # anthropic-kind legitimately ships base_url: "" (SDK default endpoint)
    cfg = {"providers": {"anthropic": _prov("anthropic", kind="anthropic",
                                            base_url="")}}
    assert [pid for pid, _ in server._usable(cfg)] == ["anthropic"]


def test_usable_treats_whitespace_baseurl_as_blank():
    cfg = {"providers": {"ws": _prov("ws", base_url="   ")}}
    assert server._usable(cfg) == []


def test_main_provider_cascade_never_picks_blank_baseurl():
    # broken entry is the CHEAPEST + auto-flagged — the old code picked it
    cfg = {"selected": "auto", "auto_cheapest": True,
           "providers": {"broken": _prov("broken", base_url="", out=0.0),
                         "good": _prov("good", out=5.0)}}
    main = server.main_provider(cfg)
    assert main is not None and main["name"] == "good"


def test_main_provider_explicit_selection_of_broken_falls_to_cascade():
    cfg = {"selected": "broken", "auto_cheapest": False,
           "providers": {"broken": _prov("broken", base_url=""),
                         "good": _prov("good")}}
    main = server.main_provider(cfg)
    assert main is not None and main["name"] == "good"


def test_main_provider_none_when_only_broken():
    cfg = {"selected": "auto", "auto_cheapest": True,
           "providers": {"broken": _prov("broken", base_url="")}}
    assert server.main_provider(cfg) is None


# ---- layer 3: call-time guard is NON-transient --------------------------------

def test_chat_openai_blank_baseurl_raises_nontransient():
    provider = {"kind": "openai", "name": "broken", "model": "m",
                "base_url": "", "api_key": "k",
                "input_cost_per_m": 0, "output_cost_per_m": 0}
    with pytest.raises(RuntimeError, match="blank base_url"):
        server._chat_openai(provider, "sys", [], [], 64)


def test_call_model_blank_baseurl_does_not_retry(monkeypatch):
    slept = []
    monkeypatch.setattr(server.time, "sleep", lambda s: slept.append(s))
    provider = {"kind": "openai", "name": "broken", "model": "m",
                "base_url": "  ", "api_key": "k",
                "input_cost_per_m": 0, "output_cost_per_m": 0}
    with pytest.raises(RuntimeError, match="blank base_url"):
        server.call_model(provider, "sys", [], [])
    assert slept == []          # no transient backoff burned


# ---- layer 1: config-load repair ----------------------------------------------

def test_load_models_backfills_builtin_blank_baseurl(monkeypatch, tmp_path):
    models_file = tmp_path / "models.json"
    monkeypatch.setattr(server, "MODELS_FILE", str(models_file))
    cfg = server._new_cfg()
    cfg["providers"]["openrouter"]["base_url"] = ""     # the live-smoke shape
    cfg["providers"]["openrouter"]["key"] = "k"
    server._save_json(str(models_file), cfg)

    loaded = server.load_models()
    expected = server.DEFAULT_PROVIDERS["openrouter"]["base_url"]
    assert loaded["providers"]["openrouter"]["base_url"] == expected
    # repair persisted, not just in-memory
    reloaded = server._load_json(str(models_file), None)
    assert reloaded["providers"]["openrouter"]["base_url"] == expected
    # key untouched by the repair
    assert loaded["providers"]["openrouter"]["key"] == "k"


def test_load_models_leaves_anthropic_blank_baseurl_alone(monkeypatch, tmp_path):
    models_file = tmp_path / "models.json"
    monkeypatch.setattr(server, "MODELS_FILE", str(models_file))
    server._save_json(str(models_file), server._new_cfg())

    loaded = server.load_models()
    assert loaded["providers"]["anthropic"]["base_url"] == ""


def test_load_models_custom_provider_not_backfilled(monkeypatch, tmp_path):
    # no known default for a custom id — selection-layer skip covers it instead
    models_file = tmp_path / "models.json"
    monkeypatch.setattr(server, "MODELS_FILE", str(models_file))
    cfg = server._new_cfg()
    cfg["providers"]["mycustom"] = _prov("mycustom", base_url="")
    server._save_json(str(models_file), cfg)

    loaded = server.load_models()
    assert loaded["providers"]["mycustom"]["base_url"] == ""
    assert server._usable(loaded) == [] or all(
        pid != "mycustom" for pid, _ in server._usable(loaded))
