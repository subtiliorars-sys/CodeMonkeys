#!/usr/bin/env python3
"""
🌉 Cline Proxy — Configuration & Alias Layer
==============================================
Shared configuration, model alias tables, key loading, and hot-reload
for the local API proxy server.

Design:
  - Single source of truth for model aliases, fallback chain, ports
  - Reads API keys from existing config_manager.py (no duplication)
  - Hot-reloads proxy_aliases.json on each access via mtime check
  - Thread-safe via threading.Lock for alias reload
"""

import json
import os
import stat
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

# ── Defaults ─────────────────────────────────────────────────────

DEFAULT_PORT = 4891

# Fallback chain: providers are tried in this order.
# Ollama is last since it requires a local process.
FALLBACK_CHAIN = ["openrouter", "gemini", "anthropic", "ollama"]

# ── Model Alias Table ───────────────────────────────────────────
# Maps short aliases → (provider, model_id) tuples.
# These are the "friendly names" users type in Cline.
#
# Model IDs are chosen from known-working free/cheap models on each
# provider. The proxy translates these to the actual provider API.
#
# "fast"    → smallest/cheapest, low latency
# "cheap"   → best quality per dollar (free first, then cheap paid)
# "smart"   → most capable model on the chain (may be paid)
# "code"    → models with strong coding track records
# "balanced" → good quality at reasonable cost

ALIAS_TABLE = {
    "fast": {
        "provider": "openrouter",
        "model_id": "meta-llama/llama-3.2-3b-instruct",
        "description": "Fastest — tiny Llama 3B, near-instant responses",
    },
    "fast-gemini": {
        "provider": "gemini",
        "model_id": "gemini-2.0-flash",
        "description": "Fast — Gemini Flash, free tier",
    },
    "cheap": {
        "provider": "openrouter",
        "model_id": "google/gemini-2.0-flash-001",
        "description": "Cheapest — Gemini Flash via OpenRouter (free)",
    },
    "smart": {
        "provider": "openrouter",
        "model_id": "openai/gpt-4o-mini",
        "description": "Smart — GPT-4o Mini, best reasoning for low cost",
    },
    "code": {
        "provider": "openrouter",
        "model_id": "google/gemini-2.0-flash-001",
        "description": "Code — Gemini Flash, strong on coding tasks",
    },
    "free": {
        "provider": "openrouter",
        "model_id": "google/gemini-2.0-flash-001",
        "description": "Absolutely free — Gemini Flash via OpenRouter, $0 cost",
    },
    "balanced": {
        "provider": "openrouter",
        "model_id": "mistralai/mistral-7b-instruct",
        "description": "Balanced — Mistral 7B, good all-rounder (free)",
    },
}

# ── Provider → Model List (for /v1/models endpoint) ─────────────
# Combined list of real model IDs and aliases for the model listing.
# Built from ALIAS_TABLE plus known provider model IDs.

PROVIDER_MODEL_IDS = {
    "openrouter": [
        "google/gemini-2.0-flash-001",
        "meta-llama/llama-3.2-3b-instruct",
        "mistralai/mistral-7b-instruct",
        "cognitivecomputations/dolphin-mixtral-8x7b",
        "openai/gpt-4o-mini",
        "openai/gpt-4o",
        "anthropic/claude-3-haiku",
        "anthropic/claude-sonnet-4-20250514",
    ],
    "gemini": [
        "gemini-2.0-flash",
        "gemini-2.0-flash-lite",
        "gemini-1.5-pro",
        "gemini-1.5-flash",
    ],
    "anthropic": [
        "claude-sonnet-4-20250514",
        "claude-3-5-sonnet-20241022",
        "claude-3-haiku-20240307",
    ],
    "ollama": [
        "llama3.2:3b",
        "llama3.2:1b",
        "llama3.1:8b",
        "mistral:7b",
        "qwen2.5:7b",
        "gemma2:9b",
        "phi3:mini",
    ],
}


# ── Config dataclass ────────────────────────────────────────────

@dataclass
class ProxyConfig:
    """Runtime configuration for the Cline proxy server."""
    port: int = DEFAULT_PORT
    config_dir: str = ""  # empty = use default (~/.banana_shelter)
    verbose: bool = False
    alias_file: str = ""  # empty = ~/.banana_shelter/proxy_aliases.json

    def __post_init__(self):
        if not self.config_dir:
            self.config_dir = os.path.expanduser("~/.banana_shelter")
        if not self.alias_file:
            self.alias_file = os.path.join(self.config_dir, "proxy_aliases.json")


# ── Provider Key Loading ────────────────────────────────────────
# These call config_manager functions to get active API keys.
# We import lazily to avoid circular imports at module level.

def _get_config_manager():
    """Lazy import config_manager to avoid startup overhead."""
    import config_manager
    return config_manager


def get_provider_keys(provider: str) -> list[str]:
    """
    Return list of active API key strings for a provider.
    Returns empty list if no keys configured or provider unknown.
    """
    cm = _get_config_manager()

    if provider == "openrouter":
        return cm.get_all_openrouter_keys()
    elif provider == "gemini":
        return cm.get_all_keys()
    elif provider == "anthropic":
        # Anthropic keys stored in config under anthropic_api_keys
        config = cm.load_config()
        raw = config.get("anthropic_api_keys", [])
        return [k["key"] for k in raw if k.get("key", "").strip() and k.get("is_active", True)]
    elif provider == "ollama":
        # Ollama doesn't need API keys — returns a sentinel
        return ["ollama-local"]
    return []


def get_provider_key_strings(provider: str) -> list[str]:
    """
    Return list of raw key strings for direct use in Authorization headers.
    Filters out inactive keys, returns only the key values.
    """
    cm = _get_config_manager()

    if provider == "openrouter":
        keys = cm.get_all_openrouter_keys()
        return [k["key"] for k in keys if k.get("key", "").strip() and k.get("is_active", True)]
    elif provider == "gemini":
        keys = cm.get_all_keys()
        return [k["key"] for k in keys if k.get("key", "").strip() and k.get("is_active", True)]
    elif provider == "anthropic":
        config = cm.load_config()
        raw = config.get("anthropic_api_keys", [])
        return [k["key"] for k in raw if k.get("key", "").strip() and k.get("is_active", True)]
    elif provider == "ollama":
        return ["ollama-local"]
    return []


# ── Alias Hot-Reload ────────────────────────────────────────────

_alias_cache: dict = {}
_alias_mtime: float = 0
_alias_lock = threading.Lock()


def _default_alias_file() -> str:
    """Get the default path to the user alias override file."""
    return os.path.expanduser("~/.banana_shelter/proxy_aliases.json")


def load_aliases(alias_file: Optional[str] = None) -> dict:
    """
    Load aliases, merging user overrides over the built-in ALIAS_TABLE.
    Hot-reloads: checks file mtime; only re-reads if changed.
    Thread-safe via threading.Lock.

    The user file format is a dict of alias_name -> {provider, model_id, description}.
    These are merged over ALIAS_TABLE (user entries override built-in ones).

    Returns a dict of alias_name -> {provider, model_id, description}.
    """
    global _alias_cache, _alias_mtime

    if alias_file is None:
        alias_file = _default_alias_file()

    with _alias_lock:
        try:
            current_mtime = os.path.getmtime(alias_file)
        except (FileNotFoundError, OSError):
            current_mtime = 0

        # If mtime hasn't changed and we have a cache, use it
        if current_mtime == _alias_mtime and _alias_cache:
            return dict(_alias_cache)

        # Re-read: start with built-in table
        merged = dict(ALIAS_TABLE)

        if current_mtime > 0:
            try:
                with open(alias_file, "r") as f:
                    overrides = json.load(f)
                if isinstance(overrides, dict):
                    merged.update(overrides)
                _alias_mtime = current_mtime
            except (json.JSONDecodeError, IOError) as e:
                # Log but don't fail — use built-in table as fallback
                import sys
                print(f"  ⚠️  Failed to load proxy_aliases.json: {e}", file=sys.stderr)
                _alias_mtime = current_mtime  # Don't retry on every request

        _alias_cache = merged
        return dict(merged)


# ── Model Info for /v1/models Endpoint ──────────────────────────

def get_all_model_entries(aliases: dict) -> list[dict]:
    """
    Build a list of OpenAI-format model objects for the /v1/models endpoint.
    Includes both aliases and known provider model IDs.

    Returns list of dicts with: id, object, created, owned_by
    """
    entries = []
    now_ts = int(time.time())

    # Add aliases as model entries
    for alias, info in aliases.items():
        entries.append({
            "id": alias,
            "object": "model",
            "created": now_ts,
            "owned_by": info.get("provider", "proxy"),
            "description": info.get("description", ""),
        })

    # Add known provider model IDs
    for provider, models in PROVIDER_MODEL_IDS.items():
        for model_id in models:
            entries.append({
                "id": model_id,
                "object": "model",
                "created": now_ts,
                "owned_by": provider,
            })

    # Deduplicate by id
    seen = set()
    unique = []
    for e in entries:
        if e["id"] not in seen:
            seen.add(e["id"])
            unique.append(e)

    return unique


# ── Ensure config dir exists (for alias file) ───────────────────

def ensure_config_dir(config_dir: Optional[str] = None):
    """Ensure the config directory exists with restricted permissions."""
    if config_dir is None:
        config_dir = os.path.expanduser("~/.banana_shelter")
    if not os.path.exists(config_dir):
        os.makedirs(config_dir, mode=0o700, exist_ok=True)
    try:
        os.chmod(config_dir, stat.S_IRWXU)
    except PermissionError:
        pass


# ── Quick self-test ─────────────────────────────────────────────

if __name__ == "__main__":
    print("\n  🌉 Proxy Config Self-Test\n")

    print(f"  Default port: {DEFAULT_PORT}")
    print(f"  Fallback chain: {FALLBACK_CHAIN}")
    print(f"  Built-in aliases: {len(ALIAS_TABLE)}")

    for alias, info in ALIAS_TABLE.items():
        print(f"     {alias:12s} → {info['provider']:12s} {info['model_id']}")

    print(f"\n  Provider model IDs:")
    for prov, models in PROVIDER_MODEL_IDS.items():
        print(f"     {prov:12s} {len(models)} models")

    print(f"\n  Key store check:")
    for prov in FALLBACK_CHAIN:
        keys = get_provider_key_strings(prov)
        if keys:
            print(f"     {prov:12s} {len(keys)} key(s) configured")
            # Show redacted keys for verification
            for k in keys[:2]:
                if k == "ollama-local":
                    print(f"       🟢 local (Ollama)")
                elif len(k) > 8:
                    print(f"       🟢 {k[:4]}...{k[-4:]}")
                else:
                    print(f"       🟢 (key present)")
        else:
            print(f"     {prov:12s} ⚠️  No keys configured (will be skipped)")

    cfg = ProxyConfig()
    print(f"\n  ProxyConfig: port={cfg.port}, config_dir={cfg.config_dir}")
    print(f"  Alias file: {cfg.alias_file}")

    aliases = load_aliases()
    print(f"  Loaded aliases: {len(aliases)} (merged)")
    print(f"  Model entries for /v1/models: {len(get_all_model_entries(aliases))}")
    print("\n  ✅ Proxy config ready")
