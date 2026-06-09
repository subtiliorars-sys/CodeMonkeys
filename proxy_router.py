#!/usr/bin/env python3
"""
🌉 Cline Proxy — Request Router
=================================
Routes incoming OpenAI-format requests through the fallback chain of
provider adapters. Handles model alias resolution, key rotation,
retry logic, and request normalization.
"""

import sys
import traceback
from typing import Iterator, Optional

from proxy_config import (
    ProxyConfig,
    FALLBACK_CHAIN,
    load_aliases,
    get_provider_key_strings,
)
from proxy_streaming import format_error
from config_manager import is_budget_exhausted, is_session_exhausted
from proxy_providers_openrouter import (
    BaseAdapter,
    OpenRouterAdapter,
    OllamaAdapter,
    RateLimitError,
    ProviderExhausted,
    ProviderUnavailable,
)
from proxy_providers_gemini_anthropic import (
    GeminiAdapter,
    AnthropicAdapter,
)

# ── Model Resolution ─────────────────────────────────────────────

# Known provider prefixes for auto-routing when no alias matches
PROVIDER_PREFIXES = {
    "google/": "openrouter",       # OpenRouter-hosted Google models
    "meta-": "openrouter",         # OpenRouter-hosted Meta models
    "mistralai/": "openrouter",    # OpenRouter-hosted Mistral
    "openai/": "openrouter",       # OpenRouter-hosted OpenAI
    "anthropic/": "openrouter",    # OpenRouter-hosted Anthropic
    "cognitivecomputations/": "openrouter",
    "gemini-": "gemini",           # Native Gemini models
    "gemma": "ollama",             # Gemma is usually local
    "llama": "ollama",             # Llama is often local
    "mistral:": "ollama",          # Ollama-Mistral
    "qwen": "ollama",              # Ollama-Qwen
    "phi": "ollama",               # Ollama-Phi
    "claude-": "anthropic",        # Native Anthropic
}


def resolve_model(alias_or_model_id: str, aliases: Optional[dict] = None) -> tuple:
    """
    Resolve a model alias or model ID to (provider, real_model_id).

    Resolution order:
      1. Check alias table (including hot-reloaded overrides)
      2. Check provider prefixes (e.g., "claude-" → anthropic)
      3. Default to OpenRouter with raw model ID

    Returns:
        (provider_name: str, model_id: str)

    Examples:
        resolve_model("fast") → ("openrouter", "meta-llama/llama-3.2-3b-instruct")
        resolve_model("claude-sonnet-4-20250514") → ("anthropic", "claude-sonnet-4-20250514")
        resolve_model("unknown-model") → ("openrouter", "unknown-model")
    """
    if aliases is None:
        aliases = load_aliases()

    # 1. Check alias table (case-sensitive match)
    if alias_or_model_id in aliases:
        alias_info = aliases[alias_or_model_id]
        return alias_info["provider"], alias_info["model_id"]

    # 2. Check provider prefixes
    for prefix, provider in PROVIDER_PREFIXES.items():
        if alias_or_model_id.startswith(prefix):
            return provider, alias_or_model_id

    # 3. Check if it looks like a prefix-mapped model
    for prefix, provider in PROVIDER_PREFIXES.items():
        if alias_or_model_id.startswith(prefix):
            return provider, alias_or_model_id

    # 4. Default: route raw model ID through OpenRouter
    return "openrouter", alias_or_model_id


def infer_provider_from_model(model_id: str) -> str:
    """
    Infer which provider should handle a raw model ID.
    Uses the same prefix rules as resolve_model.
    """
    for prefix, provider in PROVIDER_PREFIXES.items():
        if model_id.startswith(prefix):
            return provider
    return "openrouter"


# ── Adapter Chain Builder ───────────────────────────────────────

def build_adapter_chain(config: ProxyConfig) -> list[BaseAdapter]:
    """
    Build a list of provider adapters in fallback chain order.
    Skips providers that have no keys configured (except Ollama,
    which doesn't need keys but needs the process running).

    Returns:
        List of adapter instances, in priority order.
    """
    adapters = []

    for provider in FALLBACK_CHAIN:
        if provider == "openrouter":
            keys = get_provider_key_strings("openrouter")
            if keys:
                adapters.append(OpenRouterAdapter(keys))

        elif provider == "gemini":
            keys = get_provider_key_strings("gemini")
            if keys:
                adapters.append(GeminiAdapter(keys))

        elif provider == "anthropic":
            keys = get_provider_key_strings("anthropic")
            if keys:
                adapters.append(AnthropicAdapter(keys))

        elif provider == "ollama":
            adapters.append(OllamaAdapter())

        else:
            if config.verbose:
                print(f"  ⚠️  Unknown provider in fallback chain: {provider}", file=sys.stderr)

    return adapters


# ── Request Normalizer ──────────────────────────────────────────

class RequestNormalizer:
    """
    Normalizes incoming request payloads to a clean format
    that all providers can handle.
    """

    @staticmethod
    def normalize(payload: dict) -> dict:
        """
        Clean and normalize an incoming request payload.

        Operations:
          - Ensures "model" field is present
          - Clamps max_tokens to reasonable defaults
          - Strips unknown fields that might confuse some providers
          - Ensures messages list is present
          - Ensures each message has "role" and "content"
        """
        normalized = dict(payload)

        # Ensure model
        if "model" not in normalized or not normalized["model"]:
            normalized["model"] = "fast"

        # Normalize max_tokens
        max_tokens = normalized.get("max_tokens")
        if max_tokens is None or (isinstance(max_tokens, (int, float)) and max_tokens <= 0):
            normalized["max_tokens"] = 4096
        elif isinstance(max_tokens, float):
            normalized["max_tokens"] = int(max_tokens)

        # Normalize temperature
        temp = normalized.get("temperature")
        if temp is None:
            normalized["temperature"] = 0.7

        # Normalize messages
        messages = normalized.get("messages", [])
        if not messages:
            normalized["messages"] = [{"role": "user", "content": "Hello"}]
        else:
            # Ensure each message has role and content
            cleaned = []
            for msg in messages:
                if not isinstance(msg, dict):
                    continue
                if "role" not in msg:
                    msg["role"] = "user"
                if "content" not in msg or msg["content"] is None:
                    msg["content"] = ""
                cleaned.append(msg)
            normalized["messages"] = cleaned

        # Strip None values that some providers reject
        for key in ("frequency_penalty", "presence_penalty", "top_p", "stop"):
            if key in normalized and normalized[key] is None:
                del normalized[key]

        return normalized


# ── Route Request ───────────────────────────────────────────────

class RouteStats:
    """Tracks routing statistics for the status endpoint."""

    def __init__(self):
        self.last_provider: str = ""
        self.last_model: str = ""
        self.total_requests: int = 0
        self.successful_requests: int = 0
        self.failed_requests: int = 0
        self.recent_errors: list[dict] = []
        self.provider_attempts: dict[str, int] = {}
        self.fallback_events: int = 0

    def add_error(self, provider: str, error: str):
        """Record an error event."""
        import time
        self.recent_errors.append({
            "time": time.strftime("%H:%M:%S"),
            "provider": provider,
            "error": error[:200],
        })
        if len(self.recent_errors) > 10:
            self.recent_errors = self.recent_errors[-10:]

    def record_attempt(self, provider: str):
        """Record an attempt for a provider."""
        self.provider_attempts[provider] = self.provider_attempts.get(provider, 0) + 1


route_stats = RouteStats()


def route_request(
    payload: dict,
    adapters: list[BaseAdapter],
    config: ProxyConfig,
) -> dict | Iterator[str]:
    """
    Route a chat completion request through the fallback chain.

    Iterates through adapters in priority order. If an adapter raises
    RateLimitError or ProviderExhausted, advances to the next adapter.
    If all fail, returns an OpenAI-format error dict.

    Args:
        payload: Normalized OpenAI-format request payload
        adapters: List of adapter instances in priority order
        config: Proxy config (for verbose logging)

    Returns:
        If stream=False: a dict (OpenAI chat completion or error format)
        If stream=True: an iterator of SSE data bytes
    """
    stream = payload.get("stream", False)
    model_alias = payload.get("model", "fast")
    route_stats.total_requests += 1

    # Resolve model alias to (provider, model_id)
    aliases = load_aliases(config.alias_file if config.alias_file else None)

    # ── Budget check: force free models when budget exhausted ──
    budget_exhausted = False
    try:
        budget_exhausted = is_budget_exhausted() or is_session_exhausted()
    except Exception:
        pass  # Don't crash on config read errors

    if budget_exhausted and model_alias not in ("free",):
        old_alias = model_alias
        model_alias = "free"
        print(f"  💰 Budget exhausted — forcing 'free' model (was '{old_alias}')", file=sys.stderr)

    provider_name, model_id = resolve_model(model_alias, aliases)

    if config.verbose:
        print(f"\n  🎯 Route: '{model_alias}' → {provider_name}/{model_id}", file=sys.stderr)
        print(f"     Stream: {stream}", file=sys.stderr)

    # Find the adapter for the resolved provider first
    provider_adapter = None
    for adapter in adapters:
        if adapter.provider_name == provider_name:
            provider_adapter = adapter
            break

    if provider_adapter is None:
        # Provider not in chain — use full chain from start
        pass

    # Build attempt order: preferred provider first, then full chain fallback
    attempt_order = []
    if provider_adapter:
        attempt_order.append(provider_adapter)
    for adapter in adapters:
        if adapter != provider_adapter:
            attempt_order.append(adapter)

    if not attempt_order:
        return format_error("api_error", "No providers available")

    last_error_msg = ""
    for idx, adapter in enumerate(attempt_order):
        route_stats.record_attempt(adapter.provider_name)

        if config.verbose:
            print(f"     Trying {adapter.provider_name}...", file=sys.stderr)

        try:
            result = adapter.chat(
                messages=payload.get("messages", []),
                model_id=model_id,
                stream=stream,
                temperature=payload.get("temperature", 0.7),
                max_tokens=payload.get("max_tokens", 4096),
                top_p=payload.get("top_p"),
                frequency_penalty=payload.get("frequency_penalty"),
                presence_penalty=payload.get("presence_penalty"),
                stop=payload.get("stop"),
            )

            route_stats.last_provider = adapter.provider_name
            route_stats.last_model = model_id
            route_stats.successful_requests += 1

            if config.verbose:
                print(f"     ✅ {adapter.provider_name} accepted", file=sys.stderr)

            return result

        except RateLimitError as e:
            msg = f"Rate limited on {adapter.provider_name}"
            route_stats.add_error(adapter.provider_name, str(e))
            if idx < len(attempt_order) - 1:
                route_stats.fallback_events += 1
                print(f"     ⚠️  {msg} — falling through...", file=sys.stderr)
                last_error_msg = msg
                continue
            else:
                # Last provider failed with rate limit — return error
                route_stats.failed_requests += 1
                return format_error("rate_limit_error", msg)

        except ProviderExhausted as e:
            msg = f"All keys exhausted for {adapter.provider_name}"
            route_stats.add_error(adapter.provider_name, str(e))
            if idx < len(attempt_order) - 1:
                route_stats.fallback_events += 1
                print(f"     ⚠️  {msg} — falling through...", file=sys.stderr)
                last_error_msg = msg
                continue
            else:
                route_stats.failed_requests += 1
                return format_error("provider_exhausted", msg)

        except ProviderUnavailable as e:
            msg = str(e)
            route_stats.add_error(adapter.provider_name, str(e))
            if idx < len(attempt_order) - 1:
                route_stats.fallback_events += 1
                print(f"     ⚠️  {msg} — falling through...", file=sys.stderr)
                last_error_msg = msg
                continue
            else:
                route_stats.failed_requests += 1
                return format_error("provider_unavailable", msg)

        except Exception as e:
            # Unexpected error — log details and fall through or fail
            msg = f"{adapter.provider_name}: {type(e).__name__}: {e}"
            route_stats.add_error(adapter.provider_name, traceback.format_exc())
            if idx < len(attempt_order) - 1:
                print(f"     ⚠️  {msg} — falling through...", file=sys.stderr)
                last_error_msg = msg
                continue
            else:
                route_stats.failed_requests += 1
                return format_error("api_error", msg)

    # All providers exhausted
    route_stats.failed_requests += 1
    return format_error("all_providers_exhausted",
                        f"All providers failed. Last error: {last_error_msg}")


def get_route_stats() -> dict:
    """Return current routing statistics (for /v1/proxy/status endpoint)."""
    return {
        "last_provider": route_stats.last_provider,
        "last_model": route_stats.last_model,
        "total_requests": route_stats.total_requests,
        "successful_requests": route_stats.successful_requests,
        "failed_requests": route_stats.failed_requests,
        "fallback_events": route_stats.fallback_events,
        "provider_attempts": route_stats.provider_attempts,
        "recent_errors": route_stats.recent_errors[-5:],
    }


# ── Self-test ───────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n  🌉 Router — Self-Test\n")

    # Test alias resolution
    aliases = load_aliases()
    for alias in ("fast", "cheap", "smart", "code", "balanced"):
        provider, model_id = resolve_model(alias, aliases)
        print(f"  {alias:12s} → {provider:12s} {model_id}")
        assert provider, f"Empty provider for {alias}"

    # Test unknown model
    provider, model_id = resolve_model("unknown-model", aliases)
    print(f"  {'unknown-model':12s} → {provider:12s} {model_id}")
    assert provider == "openrouter"

    # Test provider prefix resolution
    provider, model_id = resolve_model("claude-sonnet-4-20250514", aliases)
    print(f"  {'claude-sonnet-4-20250514':12s} → {provider:12s} {model_id}")

    provider, model_id = resolve_model("gemini-2.0-flash", aliases)
    print(f"  {'gemini-2.0-flash':12s} → {provider:12s} {model_id}")

    provider, model_id = resolve_model("llama3.2:3b", aliases)
    print(f"  {'llama3.2:3b':12s} → {provider:12s} {model_id}")

    # Test normalizer
    normalizer = RequestNormalizer()
    cleaned = normalizer.normalize({
        "model": "fast",
        "messages": [{"role": "user", "content": "Hi"}],
        "max_tokens": None,
    })
    assert cleaned["max_tokens"] == 4096
    assert cleaned["temperature"] == 0.7
    print("\n  Request normalizer: ✅")

    # Test adapter chain building
    cfg = ProxyConfig()
    adapters = build_adapter_chain(cfg)
    print(f"\n  Adapter chain built: {len(adapters)} adapter(s)")
    for a in adapters:
        print(f"     {a.provider_name} — {'✅' if a.is_available() else '⚠️  unavailable'}")

    print("\n  ✅ Router ready")
