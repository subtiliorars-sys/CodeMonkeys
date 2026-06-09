#!/usr/bin/env python3
"""
🌉 Cline Proxy — Gemini & Anthropic Provider Adapters
=========================================================
Adapter implementations for:
  - Gemini (Google, free tier available with API key)
  - Anthropic (Claude models)

Each adapter translates OpenAI wire format to the provider's native format
and back, supporting both streaming and non-streaming modes.
"""

import json
import time
import urllib.error
import urllib.request
from typing import Iterator, Optional

from proxy_providers_openrouter import (
    BaseAdapter, RateLimitError, ProviderExhausted, ProviderUnavailable,
)

# ── Gemini Adapter ──────────────────────────────────────────────

GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"

# Gemini models and their max output token limits
GEMINI_MODEL_LIMITS = {
    "gemini-2.0-flash": 8192,
    "gemini-2.0-flash-lite": 8192,
    "gemini-1.5-pro": 8192,
    "gemini-1.5-flash": 8192,
    "gemini-1.5-flash-8b": 8192,
}

class GeminiAdapter(BaseAdapter):
    """
    Adapter for Google Gemini API.
    
    Translates OpenAI messages → Gemini contents format.
    Supports:
      - Non-streaming via generateContent
      - Streaming via streamGenerateContent (SSE)
      - Multi-key rotation for redundancy
    """

    def __init__(self, keys: list[str]):
        super().__init__()
        self.provider_name = "gemini"
        self._keys = list(keys)
        self._key_index = 0

    def is_available(self) -> bool:
        """Available if at least one Gemini API key is configured."""
        return len(self._keys) > 0

    def _next_key(self) -> Optional[str]:
        """Simple round-robin key selection."""
        if not self._keys:
            return None
        key = self._keys[self._key_index]
        self._key_index = (self._key_index + 1) % len(self._keys)
        return key

    def _openai_to_gemini(self, messages: list) -> tuple:
        """
        Convert OpenAI messages to Gemini contents format.
        
        OpenAI: [{"role": "system", "content": "..."}, {"role": "user", "content": "..."}]
        Gemini: {"system_instruction": {"parts": [{"text": "..."}]},
                 "contents": [{"role": "user", "parts": [{"text": "..."}]}]}
        
        Gemini doesn't have a system role in contents — it uses a separate
        system_instruction field at the top level.
        """
        system_instruction = None
        contents = []

        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")

            if role == "system":
                system_instruction = content
                continue

            # Map OpenAI roles to Gemini roles
            gemini_role = "user" if role == "user" else "model"

            contents.append({
                "role": gemini_role,
                "parts": [{"text": content}],
            })

        return contents, system_instruction

    def chat(self, messages: list, model_id: str,
             stream: bool = False, **kwargs) -> dict | Iterator[str]:
        """Send a chat request to Gemini API."""
        temperature = kwargs.get("temperature", 0.7)
        max_tokens = kwargs.get("max_tokens", 8192)
        if max_tokens is None:
            max_tokens = GEMINI_MODEL_LIMITS.get(model_id, 8192)

        contents, system_instruction = self._openai_to_gemini(messages)

        payload = {
            "contents": contents,
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_tokens,
                "topP": kwargs.get("top_p", 0.95),
            },
        }

        if system_instruction:
            payload["system_instruction"] = {
                "parts": [{"text": system_instruction}]
            }

        # Try keys in rotation
        last_error = None
        for attempt in range(len(self._keys) + 1):
            api_key = self._next_key()
            if api_key is None:
                break

            try:
                if stream:
                    return self._stream_request(payload, model_id, api_key)
                else:
                    return self._json_request(payload, model_id, api_key)
            except (RateLimitError, ProviderUnavailable) as e:
                last_error = e
                continue

        raise last_error or ProviderExhausted(self.provider_name)

    def _build_url(self, model_id: str, api_key: str, stream: bool) -> str:
        """Build the Gemini API URL with model and key."""
        if stream:
            endpoint = "streamGenerateContent"
        else:
            endpoint = "generateContent"
        # alt=sse for streaming
        if stream:
            return f"{GEMINI_API_BASE}/{model_id}:{endpoint}?key={api_key}&alt=sse"
        return f"{GEMINI_API_BASE}/{model_id}:{endpoint}?key={api_key}"

    def _json_request(self, payload: dict, model_id: str,
                      api_key: str) -> dict:
        """Send a non-streaming request to Gemini."""
        url = self._build_url(model_id, api_key, stream=False)
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                result = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            if e.code == 429:
                raise RateLimitError(self.provider_name)
            elif e.code in (400, 403):
                raise ProviderUnavailable(self.provider_name, f"HTTP {e.code}: {body[:200]}")
            raise RateLimitError(self.provider_name)

        return self._gemini_to_openai(result, model_id)

    def _stream_request(self, payload: dict, model_id: str,
                        api_key: str) -> Iterator[str]:
        """Send a streaming request to Gemini, yielding OpenAI SSE data strings."""
        url = self._build_url(model_id, api_key, stream=True)
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            resp = urllib.request.urlopen(req, timeout=120)
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            if e.code == 429:
                raise RateLimitError(self.provider_name)
            raise ProviderUnavailable(self.provider_name, f"HTTP {e.code}: {body[:200]}")

        try:
            buffer = ""
            while True:
                chunk = resp.read(4096)
                if not chunk:
                    break
                buffer += chunk.decode("utf-8", errors="replace")

                # Gemini SSE: lines prefixed with "data: "
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.strip()
                    if not line:
                        continue
                    if not line.startswith("data: "):
                        continue

                    data_str = line[6:]
                    if not data_str:
                        continue

                    try:
                        obj = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue

                    # Extract text from Gemini response
                    text = self._extract_gemini_text(obj)
                    if text is None:
                        # Check for finish reason
                        finish = self._extract_finish_reason(obj)
                        if finish:
                            finish_data = json.dumps({
                                "id": f"gemini-{time.time()}",
                                "object": "chat.completion.chunk",
                                "created": int(time.time()),
                                "model": model_id,
                                "choices": [{
                                    "index": 0,
                                    "delta": {},
                                    "finish_reason": finish,
                                }],
                            })
                            yield finish_data
                            yield "[DONE]"
                            return
                        continue

                    # Yield OpenAI-format chunk
                    chunk_data = json.dumps({
                        "id": f"gemini-{time.time()}",
                        "object": "chat.completion.chunk",
                        "created": int(time.time()),
                        "model": model_id,
                        "choices": [{
                            "index": 0,
                            "delta": {"content": text},
                            "finish_reason": None,
                        }],
                    })
                    yield chunk_data

            yield "[DONE]"
        finally:
            resp.close()

    def _extract_gemini_text(self, gemini_obj: dict) -> Optional[str]:
        """Extract text content from a Gemini response chunk."""
        try:
            candidates = gemini_obj.get("candidates", [])
            if not candidates:
                return None
            content = candidates[0].get("content", {})
            parts = content.get("parts", [])
            if not parts:
                return None
            return parts[0].get("text", "")
        except (IndexError, KeyError, TypeError):
            return None

    def _extract_finish_reason(self, gemini_obj: dict) -> Optional[str]:
        """Extract finish reason from a Gemini response."""
        try:
            candidates = gemini_obj.get("candidates", [])
            if not candidates:
                return None
            finish = candidates[0].get("finishReason", "")
            if not finish:
                return None
            # Map Gemini finish reasons to OpenAI
            mapping = {
                "STOP": "stop",
                "MAX_TOKENS": "length",
                "SAFETY": "content_filter",
                "RECITATION": "content_filter",
                "OTHER": "stop",
            }
            return mapping.get(finish, "stop")
        except (IndexError, KeyError, TypeError):
            return None

    def _gemini_to_openai(self, gemini_response: dict, model_id: str) -> dict:
        """Translate a Gemini non-streaming response to OpenAI format."""
        content = ""
        finish_reason = None

        try:
            candidates = gemini_response.get("candidates", [])
            if candidates:
                candidate = candidates[0]
                parts = candidate.get("content", {}).get("parts", [])
                text_parts = [p.get("text", "") for p in parts]
                content = "".join(text_parts)

                finish = candidate.get("finishReason", "")
                if finish:
                    mapping = {
                        "STOP": "stop",
                        "MAX_TOKENS": "length",
                        "SAFETY": "content_filter",
                        "RECITATION": "content_filter",
                        "OTHER": "stop",
                    }
                    finish_reason = mapping.get(finish, "stop")
        except (IndexError, KeyError, TypeError):
            pass

        # Usage info from Gemini
        usage = gemini_response.get("usageMetadata", {})
        prompt_tokens = usage.get("promptTokenCount", 0)
        completion_tokens = usage.get("candidatesTokenCount", 0)

        return {
            "id": f"gemini-{time.time()}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model_id,
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": content,
                },
                "finish_reason": finish_reason or "stop",
            }],
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
        }


# ── Anthropic Adapter ───────────────────────────────────────────

ANTHROPIC_API_BASE = "https://api.anthropic.com/v1"
ANTHROPIC_MESSAGES_URL = f"{ANTHROPIC_API_BASE}/messages"
ANTHROPIC_HEADERS = {
    "anthropic-version": "2023-06-01",
    "content-type": "application/json",
}

# Anthropic model limits
ANTHROPIC_MODEL_LIMITS = {
    "claude-sonnet-4-20250514": 8192,
    "claude-3-5-sonnet-20241022": 8192,
    "claude-3-haiku-20240307": 4096,
}

class AnthropicAdapter(BaseAdapter):
    """
    Adapter for Anthropic Messages API.
    
    Translates OpenAI messages → Anthropic format and back.
    Supports:
      - Non-streaming via /v1/messages
      - Streaming via content_block_delta events
      - Separate system prompt handling
    """

    def __init__(self, keys: list[str]):
        super().__init__()
        self.provider_name = "anthropic"
        self._keys = list(keys)
        self._key_index = 0

    def is_available(self) -> bool:
        """Available if at least one Anthropic key is configured."""
        return len(self._keys) > 0

    def _next_key(self) -> Optional[str]:
        if not self._keys:
            return None
        key = self._keys[self._key_index]
        self._key_index = (self._key_index + 1) % len(self._keys)
        return key

    def _openai_to_anthropic(self, messages: list) -> tuple:
        """
        Convert OpenAI messages to Anthropic v1/messages format.
        
        Anthropic format:
          - "system" at top level (not in messages)
          - messages: [{"role": "user"|"assistant", "content": "..."}]
          - No "system" role in messages array
        
        OpenAI format:
          - messages: [{"role": "system", "content": "..."},
                        {"role": "user", "content": "..."}]
        """
        system_prompt = None
        anthropic_msgs = []

        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")

            if role == "system":
                system_prompt = content
                continue

            # Anthropic only accepts "user" and "assistant" roles
            anthropic_role = role if role in ("user", "assistant") else "user"

            anthropic_msgs.append({
                "role": anthropic_role,
                "content": content,
            })

        return anthropic_msgs, system_prompt

    def chat(self, messages: list, model_id: str,
             stream: bool = False, **kwargs) -> dict | Iterator[str]:
        """Send a chat request to Anthropic Messages API."""
        temperature = kwargs.get("temperature", 0.7)
        max_tokens = kwargs.get("max_tokens", 8192)
        if max_tokens is None:
            max_tokens = ANTHROPIC_MODEL_LIMITS.get(model_id, 8192)

        anthropic_msgs, system_prompt = self._openai_to_anthropic(messages)

        payload = {
            "model": model_id,
            "messages": anthropic_msgs,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": stream,
        }

        if system_prompt:
            payload["system"] = system_prompt

        # Try keys in rotation
        last_error = None
        for attempt in range(len(self._keys) + 1):
            api_key = self._next_key()
            if api_key is None:
                break

            try:
                if stream:
                    return self._stream_request(payload, api_key)
                else:
                    return self._json_request(payload, api_key, model_id)
            except (RateLimitError, ProviderUnavailable) as e:
                last_error = e
                continue

        raise last_error or ProviderExhausted(self.provider_name)

    def _json_request(self, payload: dict, api_key: str,
                      model_id: str) -> dict:
        """Send a non-streaming request to Anthropic."""
        # Remove stream flag for non-streaming
        payload = dict(payload)
        payload.pop("stream", None)

        data = json.dumps(payload).encode("utf-8")
        headers = dict(ANTHROPIC_HEADERS)
        headers["x-api-key"] = api_key

        req = urllib.request.Request(
            ANTHROPIC_MESSAGES_URL,
            data=data,
            headers=headers,
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                result = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            if e.code == 429:
                raise RateLimitError(self.provider_name)
            elif e.code in (400, 401, 403):
                raise ProviderUnavailable(self.provider_name, f"HTTP {e.code}: {body[:200]}")
            raise RateLimitError(self.provider_name)

        return self._anthropic_to_openai(result, model_id)

    def _stream_request(self, payload: dict,
                        api_key: str) -> Iterator[str]:
        """Send a streaming request to Anthropic, yielding OpenAI SSE data strings."""
        data = json.dumps(payload).encode("utf-8")
        headers = dict(ANTHROPIC_HEADERS)
        headers["x-api-key"] = api_key
        headers["accept"] = "text/event-stream"

        req = urllib.request.Request(
            ANTHROPIC_MESSAGES_URL,
            data=data,
            headers=headers,
            method="POST",
        )

        try:
            resp = urllib.request.urlopen(req, timeout=120)
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            if e.code == 429:
                raise RateLimitError(self.provider_name)
            raise ProviderUnavailable(self.provider_name, f"HTTP {e.code}: {body[:200]}")

        model_id = payload.get("model", "unknown")

        try:
            buffer = ""
            # Track the current message block for text content
            content_block_text = ""
            current_block_index = 0

            while True:
                chunk = resp.read(4096)
                if not chunk:
                    break
                buffer += chunk.decode("utf-8", errors="replace")

                # Anthropic SSE format:
                # event: message_start / content_block_start / content_block_delta / etc.
                # data: {json}
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.strip()
                    if not line:
                        continue

                    if line.startswith("data: "):
                        data_str = line[6:]
                        if data_str == "[DONE]":
                            yield "[DONE]"
                            return

                        try:
                            event_data = json.loads(data_str)
                        except json.JSONDecodeError:
                            continue

                        event_type = event_data.get("type", "")

                        if event_type == "content_block_delta":
                            delta = event_data.get("delta", {})
                            text = delta.get("text", "")
                            if text:
                                content_block_text += text
                                chunk_data = json.dumps({
                                    "id": f"anthropic-{time.time()}",
                                    "object": "chat.completion.chunk",
                                    "created": int(time.time()),
                                    "model": model_id,
                                    "choices": [{
                                        "index": current_block_index,
                                        "delta": {"content": text},
                                        "finish_reason": None,
                                    }],
                                })
                                yield chunk_data

                        elif event_type == "message_delta":
                            stop_reason = event_data.get("delta", {}).get("stop_reason", "")
                            if stop_reason == "end_turn":
                                finish_data = json.dumps({
                                    "id": f"anthropic-{time.time()}",
                                    "object": "chat.completion.chunk",
                                    "created": int(time.time()),
                                    "model": model_id,
                                    "choices": [{
                                        "index": 0,
                                        "delta": {},
                                        "finish_reason": "stop",
                                    }],
                                })
                                yield finish_data

                        elif event_type in ("content_block_start", "content_block_stop"):
                            # Just track block boundaries
                            if event_type == "content_block_start":
                                current_block_index = event_data.get("index", 0)

                # end while buffer
            # end while chunk

            yield "[DONE]"
        finally:
            resp.close()

    def _anthropic_to_openai(self, anthro_response: dict, model_id: str) -> dict:
        """Translate an Anthropic Messages API response to OpenAI format."""
        content = ""
        finish_reason = "stop"

        # Extract text from content blocks
        content_blocks = anthro_response.get("content", [])
        text_parts = []
        for block in content_blocks:
            if block.get("type") == "text":
                text_parts.append(block.get("text", ""))

        content = "".join(text_parts)

        stop_reason = anthro_response.get("stop_reason", "")
        if stop_reason == "max_tokens":
            finish_reason = "length"
        elif stop_reason in ("end_turn", "stop_sequence"):
            finish_reason = "stop"

        # Usage
        usage = anthro_response.get("usage", {})
        prompt_tokens = usage.get("input_tokens", 0)
        completion_tokens = usage.get("output_tokens", 0)

        return {
            "id": f"anthropic-{time.time()}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model_id,
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": content,
                },
                "finish_reason": finish_reason,
            }],
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
        }


# ── Self-test ───────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n  🌉 Gemini & Anthropic Adapters — Self-Test\n")

    from proxy_config import get_provider_key_strings

    # Check Gemini
    print("  🔑 Gemini keys...")
    g_keys = get_provider_key_strings("gemini")
    print(f"     {len(g_keys)} key(s) configured")
    ga = GeminiAdapter(g_keys)
    print(f"     Available: {ga.is_available()}")

    # Test message translation
    test_messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Hello!"},
        {"role": "assistant", "content": "Hi there!"},
    ]
    contents, system = ga._openai_to_gemini(test_messages)
    assert system == "You are a helpful assistant."
    assert len(contents) == 2
    assert contents[0]["role"] == "user"
    assert contents[1]["role"] == "model"
    print("     Message translation: ✅")

    # Check Anthropic
    print("\n  🔑 Anthropic keys...")
    a_keys = get_provider_key_strings("anthropic")
    print(f"     {len(a_keys)} key(s) configured")
    aa = AnthropicAdapter(a_keys)
    print(f"     Available: {aa.is_available()}")

    # Test Anthropic message translation
    anthro_msgs, sys_prompt = aa._openai_to_anthropic(test_messages)
    assert sys_prompt == "You are a helpful assistant."
    assert len(anthro_msgs) == 2
    assert anthro_msgs[0]["role"] == "user"
    assert anthro_msgs[1]["role"] == "assistant"
    print("     Message translation: ✅")

    print("\n  ✅ Adapters ready")
