#!/usr/bin/env python3
"""
🌉 Cline Proxy — Streaming Engine
===================================
SSE formatting and streaming utilities for the proxy server.

Handles:
  - OpenAI SSE chunk wrapping
  - Stream-to-SSE conversion
  - Non-streaming drain (collect chunks into full response)
  - Error formatting
"""

import json
import time
from typing import Iterator, Optional


def openai_chunk_wrap(
    delta_text: str,
    model: str,
    finish_reason: Optional[str] = None,
) -> str:
    """
    Format a single streaming delta as an OpenAI SSE data payload.

    Returns a JSON string matching OpenAI's streaming chunk format:
    {"id":"...", "object":"chat.completion.chunk", "created":..., "model":"...",
     "choices":[{"index":0, "delta":{"content":"..."}, "finish_reason":null}]}
    """
    chunk = {
        "id": f"chatcmpl-{int(time.time() * 1000)}",
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "delta": {},
                "finish_reason": finish_reason,
            }
        ],
    }

    if delta_text:
        chunk["choices"][0]["delta"]["content"] = delta_text

    return json.dumps(chunk)


def stream_to_sse(chunk_iter: Iterator[str]) -> Iterator[bytes]:
    """
    Wrap an iterator of data strings into OpenAI SSE format.

    Each yielded value is bytes ready to write to the wire:
      data: {json}\n\n

    Automatically appends the [DONE] sentinel when the iterator is exhausted.
    If the iterator yields "[DONE]", it is converted to the SSE [DONE] line.
    """
    for chunk in chunk_iter:
        if chunk == "[DONE]":
            yield b"data: [DONE]\n\n"
            return
        yield f"data: {chunk}\n\n".encode("utf-8")

    # Ensure [DONE] sentinel
    yield b"data: [DONE]\n\n"


def drain_to_json(chunk_iter: Iterator[str], model: str) -> dict:
    """
    Collect all streaming chunks and assemble a complete OpenAI
    non-streaming response dict.

    Used when the caller requested non-streaming but the provider only
    supports streaming (rare, but defensive).
    """
    all_text = ""
    finish_reason = None

    for chunk in chunk_iter:
        if chunk == "[DONE]":
            break

        try:
            data = json.loads(chunk)
        except (json.JSONDecodeError, TypeError):
            all_text += str(chunk)
            continue

        choices = data.get("choices", [])
        if choices:
            delta = choices[0].get("delta", {})
            text = delta.get("content", "")
            if text:
                all_text += text
            fr = choices[0].get("finish_reason")
            if fr:
                finish_reason = fr

    return {
        "id": f"chatcmpl-{int(time.time() * 1000)}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": all_text,
                },
                "finish_reason": finish_reason or "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 0,
            "completion_tokens": len(all_text.split()),
            "total_tokens": len(all_text.split()),
        },
    }


def format_error(
    error_type: str = "api_error",
    message: str = "An error occurred",
    code: str = "500",
) -> dict:
    """
    Format an error response in OpenAI-compatible format.
    Returns a dict suitable for JSON serialization.
    """
    return {
        "error": {
            "message": message,
            "type": error_type,
            "param": None,
            "code": code,
        }
    }


# ── Self-test ───────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n  🌉 Streaming Engine — Self-Test\n")

    # Test SSE format
    chunks = iter(["Hello", " world"])
    sse = list(stream_to_sse(chunks))
    assert sse[-1] == b"data: [DONE]\n\n", f"Missing DONE: {sse[-1]}"
    assert all(s.startswith(b"data: ") for s in sse), "SSE format wrong"
    print("  SSE format: ✅")

    # Test chunk wrap
    wrapped = openai_chunk_wrap("Hello", "test-model")
    data = json.loads(wrapped)
    assert data["object"] == "chat.completion.chunk"
    assert data["choices"][0]["delta"]["content"] == "Hello"
    print("  Chunk wrap: ✅")

    # Test drain
    chunks2 = [
        json.dumps({"choices": [{"delta": {"content": "Hello "}, "finish_reason": None}]}),
        json.dumps({"choices": [{"delta": {"content": "world"}, "finish_reason": None}]}),
        json.dumps({"choices": [{"index": 0, "delta": {}}]}),
    ]
    result = drain_to_json(iter(chunks2), "test-model")
    assert result["choices"][0]["message"]["content"] == "Hello world"
    print("  Drain to JSON: ✅")

    # Test error format
    err = format_error("rate_limit", "Too fast")
    assert "error" in err
    assert err["error"]["type"] == "rate_limit"
    print("  Error format: ✅")

    print("\n  ✅ Streaming engine ready")
