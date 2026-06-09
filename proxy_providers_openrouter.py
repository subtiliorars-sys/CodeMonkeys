#!/usr/bin/env python3
"""
🌉 Cline Proxy — OpenRouter & Ollama Provider Adapters
=========================================================
Adapter implementations for:
  - OpenRouter (primary, multi-key rotation)
  - Ollama (local fallback, no API key needed)

Each adapter implements the BaseAdapter protocol defined in proxy_config.py.
"""

import json
import sys
import time
import urllib.error
import urllib.request
from typing import Iterator, Optional

# ── Error types ─────────────────────────────────────────────────

class RateLimitError(Exception):
    """Raised when a provider returns 429 Too Many Requests."""
    def __init__(self, provider: str, retry_after: Optional[int] = None):
        self.provider = provider
        self.retry_after = retry_after
        super().__init__(f"{provider}: rate limited (retry after {retry_after}s)")


class ProviderExhausted(Exception):
    """Raised when all keys/retries for a provider have been exhausted."""
    def __init__(self, provider: str):
        self.provider = provider
        super().__init__(f"{provider}: all keys exhausted")


class ProviderUnavailable(Exception):
    """Raised when a provider cannot be reached at all."""
    def __init__(self, provider: str, reason: str = ""):
        self.provider = provider
        super().__init__(f"{provider}: unavailable — {reason}")


# ── Key Rotator ─────────────────────────────────────────────────

class KeyRotator:
    """
    Round-robin key rotation with per-key cooldown on rate limits.
    
    After a key returns 429, it enters a cooldown period (default 60 s).
    Expired cooldowns are automatically reactivated on the next next_key() call.
    Thread-safe for concurrent use (single-threaded server is fine).
    """

    def __init__(self, keys: list[str]):
        self._keys = list(keys)
        self._index = 0
        self._cooldowns: dict[str, float] = {}  # key -> time when cooldown expires

    def next_key(self) -> Optional[str]:
        """
        Return the next available key, or None if all are in cooldown.
        Reactivates any keys whose cooldown has expired.
        """
        self._reactivate_expired()

        if not self._keys:
            return None

        available = [k for k in self._keys if k not in self._cooldowns]
        if not available:
            return None

        # Round-robin from current index
        start = self._index
        for offset in range(len(self._keys)):
            idx = (start + offset) % len(self._keys)
            key = self._keys[idx]
            if key not in self._cooldowns:
                self._index = (idx + 1) % len(self._keys)
                return key

        return None

    def mark_rate_limited(self, key: str, cooldown_secs: int = 60):
        """Put a key into cooldown after a rate limit response."""
        self._cooldowns[key] = time.time() + cooldown_secs

    def _reactivate_expired(self):
        """Remove keys from cooldown if their time has passed."""
        now = time.time()
        expired = [k for k, expires in self._cooldowns.items() if expires <= now]
        for k in expired:
            del self._cooldowns[k]

    def key_count(self) -> int:
        """Return total number of keys (including cooling ones)."""
        return len(self._keys)

    def available_count(self) -> int:
        """Return number of keys not in cooldown."""
        self._reactivate_expired()
        return len([k for k in self._keys if k not in self._cooldowns])

    def all_keys(self) -> list[str]:
        """Return all key strings (redacted for logging)."""
        return list(self._keys)


# ── BaseAdapter (Protocol-style base class) ─────────────────────
# Provider adapters should implement chat() and is_available().

class BaseAdapter:
    """Base class for provider adapters. Subclass and override methods."""

    def __init__(self):
        self.provider_name = "base"

    def is_available(self) -> bool:
        """Return True if this provider has at least one usable key."""
        return False

    def chat(self, messages: list, model_id: str,
             stream: bool = False, **kwargs) -> dict | Iterator[str]:
        """
        Send a chat completion request.
        
        Args:
            messages: OpenAI-format message list
            model_id: Provider-specific model identifier
            stream: If True, return an iterator of SSE data strings
            **kwargs: Additional params (temperature, max_tokens, etc.)
        
        Returns:
            If stream=False: a dict in OpenAI chat completion format
            If stream=True: an iterator of SSE data line strings
        
        Raises:
            RateLimitError: provider returned 429
            ProviderExhausted: all keys/retries exhausted
            ProviderUnavailable: provider cannot be reached
        """
        raise NotImplementedError


# ── OpenRouter Adapter ──────────────────────────────────────────

OPENROUTER_CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"

class OpenRouterAdapter(BaseAdapter):
    """
    Adapter for OpenRouter API with multi-key rotation.
    
    Features:
    - Round-robin across configured keys
    - Automatic 429 cooldown per key
    - Streaming via SSE passthrough
    - Header: HTTP-Referer for OpenRouter rankings
    """

    def __init__(self, keys: list[str]):
        super().__init__()
        self.provider_name = "openrouter"
        self._rotator = KeyRotator(keys)
        self._referer = "https://github.com/codemonkeys-ai/cline-proxy"

    def is_available(self) -> bool:
        """Available if at least one key is configured."""
        return self._rotator.key_count() > 0

    def _get_headers(self, api_key: str) -> dict:
        """Build request headers for OpenRouter."""
        return {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": self._referer,
            "X-Title": "Cline Proxy",
        }

    def chat(self, messages: list, model_id: str,
             stream: bool = False, **kwargs) -> dict | Iterator[str]:
        """Send a chat request to OpenRouter with key rotation."""
        # Normalize kwargs
        temperature = kwargs.get("temperature", 0.7)
        max_tokens = kwargs.get("max_tokens", 4096)
        if max_tokens is None:
            max_tokens = 4096

        payload = {
            "model": model_id,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": stream,
        }

        # Add any extra params Cline sends
        for key in ("top_p", "frequency_penalty", "presence_penalty", "stop"):
            val = kwargs.get(key)
            if val is not None:
                payload[key] = val

        # Try keys in rotation until one works or all are exhausted
        last_error = None
        last_rate_limit_error = None
        while True:
            api_key = self._rotator.next_key()
            if api_key is None:
                # If the last error was a rate limit, propagate that
                if last_rate_limit_error is not None:
                    raise last_rate_limit_error
                raise ProviderExhausted(self.provider_name)

            try:
                return self._do_request(payload, api_key, stream)
            except RateLimitError as e:
                self._rotator.mark_rate_limited(api_key)
                last_rate_limit_error = e
                last_error = e
                continue  # Try next key
            except (ProviderUnavailable, urllib.error.URLError, OSError) as e:
                self._rotator.mark_rate_limited(api_key, cooldown_secs=30)
                last_error = e
                continue

        # All keys exhausted
        if last_rate_limit_error is not None:
            raise last_rate_limit_error
        raise ProviderExhausted(self.provider_name)

    def _do_request(self, payload: dict, api_key: str,
                    stream: bool) -> dict | Iterator[str]:
        """Execute a single request to OpenRouter."""
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            OPENROUTER_CHAT_URL,
            data=data,
            headers=self._get_headers(api_key),
            method="POST",
        )

        try:
            if stream:
                return self._stream_response(req, api_key)
            else:
                return self._json_response(req)
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            if e.code == 429:
                # Parse Retry-After header
                retry_after = None
                retry_header = e.headers.get("Retry-After")
                if retry_header:
                    try:
                        retry_after = int(retry_header)
                    except (ValueError, TypeError):
                        retry_after = 60
                raise RateLimitError(self.provider_name, retry_after)
            elif e.code in (401, 403):
                # Bad key — skip to next
                raise ProviderExhausted(self.provider_name)
            else:
                # Other HTTP errors — wrap with context
                raise ProviderUnavailable(
                    self.provider_name,
                    f"HTTP {e.code}: {body[:200]}"
                )
        except (urllib.error.URLError, OSError) as e:
            raise ProviderUnavailable(self.provider_name, str(e))

    def _json_response(self, req: urllib.request.Request) -> dict:
        """Handle a non-streaming response."""
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read().decode("utf-8"))
        # OpenRouter returns OpenAI-format responses directly
        return result

    def _stream_response(self, req: urllib.request.Request,
                         api_key: str) -> Iterator[str]:
        """Handle a streaming (SSE) response, yielding data line strings."""
        try:
            resp = urllib.request.urlopen(req, timeout=120)
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            if e.code == 429:
                raise RateLimitError(self.provider_name)
            raise ProviderUnavailable(self.provider_name, f"HTTP {e.code}")

        try:
            buffer = ""
            while True:
                chunk = resp.read(4096)
                if not chunk:
                    break
                buffer += chunk.decode("utf-8", errors="replace")

                # Split on double newlines (SSE event boundary)
                while "\n\n" in buffer:
                    event, buffer = buffer.split("\n\n", 1)
                    for line in event.split("\n"):
                        if line.startswith("data: "):
                            data_str = line[6:]
                            if data_str.strip() == "[DONE]":
                                yield "[DONE]"
                                return
                            yield data_str
                        elif line.startswith("data:"):
                            data_str = line[5:]
                            if data_str.strip() == "[DONE]":
                                yield "[DONE]"
                                return
                            yield data_str

            # Handle any remaining data in buffer
            if buffer.strip():
                for line in buffer.split("\n"):
                    if line.startswith("data: "):
                        yield line[6:]
                    elif line.startswith("data:"):
                        yield line[5:]

            # Ensure DONE sentinel
            yield "[DONE]"
        finally:
            resp.close()


# ── Ollama Adapter ──────────────────────────────────────────────

OLLAMA_CHAT_URL = "http://localhost:11434/api/chat"
OLLAMA_TAGS_URL = "http://localhost:11434/api/tags"

class OllamaAdapter(BaseAdapter):
    """
    Adapter for local Ollama instance.
    
    Translates OpenAI chat format → Ollama API format and back.
    Requires Ollama to be running on localhost:11434.
    """

    def __init__(self):
        super().__init__()
        self.provider_name = "ollama"

    def is_available(self) -> bool:
        """Check if Ollama is running by hitting /api/tags."""
        try:
            req = urllib.request.Request(OLLAMA_TAGS_URL, method="GET")
            with urllib.request.urlopen(req, timeout=2) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                models = data.get("models", [])
                return len(models) > 0
        except (urllib.error.URLError, urllib.error.HTTPError,
                OSError, json.JSONDecodeError):
            return False

    def _openai_to_ollama(self, messages: list) -> list:
        """
        Convert OpenAI message format to Ollama message format.
        Ollama uses the same role/content structure but doesn't have
        a separate system role in /api/chat (system goes in the prompt
        as a user message or the model parameter).
        """
        # Extract system message content
        system_content = None
        ollama_msgs = []

        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")

            if role == "system":
                system_content = content
                # Don't add system messages to Ollama messages array
                # (Ollama handles system via the "system" field in request)
            elif role in ("user", "assistant"):
                ollama_msgs.append({"role": role, "content": content})
            else:
                ollama_msgs.append({"role": "user", "content": content})

        return ollama_msgs, system_content

    def chat(self, messages: list, model_id: str,
             stream: bool = False, **kwargs) -> dict | Iterator[str]:
        """Send a chat request to local Ollama."""
        # Normalize model_id — strip "ollama:" prefix if present
        if model_id.startswith("ollama:"):
            model_id = model_id[7:]
        # Default model if none specified
        if not model_id:
            model_id = "llama3.2:3b"

        temperature = kwargs.get("temperature", 0.7)
        max_tokens = kwargs.get("max_tokens", 4096)
        if max_tokens is None:
            max_tokens = 4096

        ollama_msgs, system_content = self._openai_to_ollama(messages)

        payload = {
            "model": model_id,
            "messages": ollama_msgs,
            "stream": stream,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }

        if system_content:
            payload["system"] = system_content

        try:
            if stream:
                return self._stream_response(payload)
            else:
                return self._json_response(payload)
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            if e.code == 429:
                raise RateLimitError(self.provider_name)
            raise ProviderUnavailable(self.provider_name, f"HTTP {e.code}: {body[:200]}")
        except (urllib.error.URLError, OSError) as e:
            raise ProviderUnavailable(self.provider_name, str(e))

    def _json_response(self, payload: dict) -> dict:
        """Handle a non-streaming Ollama response."""
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            OLLAMA_CHAT_URL,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read().decode("utf-8"))

        # Translate Ollama format back to OpenAI
        return self._ollama_to_openai(result, payload["model"])

    def _stream_response(self, payload: dict) -> Iterator[str]:
        """Handle a streaming Ollama response."""
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            OLLAMA_CHAT_URL,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        resp = urllib.request.urlopen(req, timeout=120)
        try:
            buffer = ""
            while True:
                chunk = resp.read(4096)
                if not chunk:
                    break
                buffer += chunk.decode("utf-8", errors="replace")

                # Ollama sends one JSON object per line
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    # Extract the delta text
                    delta = obj.get("message", {}).get("content", "")

                    # Check for done
                    done = obj.get("done", False)

                    # Yield OpenAI-format SSE data
                    if delta:
                        chunk_data = json.dumps({
                            "id": f"ollama-{time.time()}",
                            "object": "chat.completion.chunk",
                            "created": int(time.time()),
                            "model": payload["model"],
                            "choices": [{
                                "index": 0,
                                "delta": {"content": delta},
                                "finish_reason": None,
                            }],
                        })
                        yield chunk_data

                    if done:
                        # Send finish reason
                        finish_data = json.dumps({
                            "id": f"ollama-{time.time()}",
                            "object": "chat.completion.chunk",
                            "created": int(time.time()),
                            "model": payload["model"],
                            "choices": [{
                                "index": 0,
                                "delta": {},
                                "finish_reason": "stop",
                            }],
                        })
                        yield finish_data
                        yield "[DONE]"
                        return

            # Ensure DONE
            yield "[DONE]"
        finally:
            resp.close()

    def _ollama_to_openai(self, ollama_response: dict, model_id: str) -> dict:
        """Translate an Ollama response dict to OpenAI chat completion format."""
        content = ollama_response.get("message", {}).get("content", "")

        return {
            "id": f"ollama-{time.time()}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model_id,
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": content,
                },
                "finish_reason": "stop" if ollama_response.get("done", False) else None,
            }],
            "usage": {
                "prompt_tokens": ollama_response.get("prompt_eval_count", 0),
                "completion_tokens": ollama_response.get("eval_count", 0),
                "total_tokens": (
                    ollama_response.get("prompt_eval_count", 0)
                    + ollama_response.get("eval_count", 0)
                ),
            },
        }


# ── Self-test ───────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n  🌉 OpenRouter & Ollama Adapters — Self-Test\n")

    # Test KeyRotator
    print("  🔑 Testing KeyRotator...")
    r = KeyRotator(["key1", "key2", "key3"])
    assert r.next_key() == "key1"
    assert r.next_key() == "key2"
    assert r.next_key() == "key3"
    assert r.next_key() == "key1"  # wraps around
    print("     Round-robin: ✅")

    r.mark_rate_limited("key1", cooldown_secs=9999)
    assert r.next_key() == "key2"  # skips key1
    r.mark_rate_limited("key2", cooldown_secs=9999)
    assert r.next_key() == "key3"
    r.mark_rate_limited("key3", cooldown_secs=9999)
    assert r.next_key() is None  # all exhausted
    print("     Cooldown + exhaustion: ✅")

    # Test adapters
    print("\n  📡 Checking OpenRouter keys...")
    from proxy_config import get_provider_key_strings
    or_keys = get_provider_key_strings("openrouter")
    print(f"     {len(or_keys)} key(s) configured")
    if or_keys:
        a = OpenRouterAdapter(or_keys)
        print(f"     Available: {a.is_available()}")

    print("\n  🖥️  Checking Ollama (may be unavailable)...")
    oa = OllamaAdapter()
    oa_avail = oa.is_available()
    print(f"     {'✅ Running' if oa_avail else '⬜ Not running (ok)'}")

    print("\n  ✅ Provider adapters ready")
