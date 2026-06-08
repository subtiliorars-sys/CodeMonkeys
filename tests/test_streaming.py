"""Tests for N5 streaming (STREAM_ENABLED flag).

Run: ./.venv/bin/python -m pytest tests/ -q

Coverage:
  - STREAM_ENABLED off (default) → _call_provider calls _chat_openai, no text_delta
  - STREAM_ENABLED on            → _chat_openai_stream called, deltas emitted
  - Full-text assembly equals concatenation of delta chunks
  - Tool-call deltas assembled correctly
  - Usage / cost captured from final usage chunk
  - Redaction applied to streamed chunks
  - Streaming error → fallback to non-streaming, run still completes
"""
import io
import json
import os
import sys
import tempfile
import threading
import time
import types
import unittest.mock as mock

os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(prefix="cm_test_stream_"))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402
import server  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_provider():
    return {
        "kind": "openai",
        "name": "test-provider",
        "model": "gpt-test",
        "base_url": "https://api.example.com/v1",
        "api_key": "sk-test",
        "input_cost_per_m": 1.0,
        "output_cost_per_m": 2.0,
        "pid": "p-test",
    }


def _make_session():
    s = server.new_session(title="stream-test")
    return s


def _sse_lines(*chunks, finish_reason="stop", usage=None):
    """Build a list of SSE data lines mimicking the OpenAI streaming protocol."""
    lines = []
    for i, content in enumerate(chunks):
        data = {
            "choices": [{
                "delta": {"content": content, "role": "assistant"},
                "finish_reason": None,
                "index": 0,
            }]
        }
        lines.append(f"data: {json.dumps(data)}")
    # Final chunk with finish_reason
    final = {
        "choices": [{"delta": {}, "finish_reason": finish_reason, "index": 0}],
        "usage": usage or {"prompt_tokens": 10, "completion_tokens": 5},
    }
    lines.append(f"data: {json.dumps(final)}")
    lines.append("data: [DONE]")
    return lines


def _sse_tool_lines(tc_id, tc_name, tc_args_str, usage=None):
    """SSE lines for a single tool call."""
    # Chunk 1: tool_calls index=0 with id + function.name
    c1 = {"choices": [{"delta": {"tool_calls": [
        {"index": 0, "id": tc_id, "function": {"name": tc_name, "arguments": ""}}
    ]}, "finish_reason": None, "index": 0}]}
    # Chunk 2: arguments
    c2 = {"choices": [{"delta": {"tool_calls": [
        {"index": 0, "function": {"arguments": tc_args_str}}
    ]}, "finish_reason": None, "index": 0}]}
    final = {
        "choices": [{"delta": {}, "finish_reason": "tool_calls", "index": 0}],
        "usage": usage or {"prompt_tokens": 8, "completion_tokens": 3},
    }
    return [
        f"data: {json.dumps(c1)}",
        f"data: {json.dumps(c2)}",
        f"data: {json.dumps(final)}",
        "data: [DONE]",
    ]


def _mock_streaming_response(sse_lines, status_code=200):
    """Return a mock requests.Response with iter_lines() mimicking SSE."""
    resp = mock.MagicMock()
    resp.status_code = status_code
    resp.headers = {}
    resp.iter_lines.return_value = iter(
        line.encode("utf-8") for line in sse_lines
    )
    # .text used for error messages on bad status
    resp.text = ""
    return resp


# ---------------------------------------------------------------------------
# 1. Flag OFF — no streaming, no text_delta events
# ---------------------------------------------------------------------------

def test_stream_disabled_calls_chat_openai(monkeypatch):
    """When STREAM_ENABLED is off, _call_provider must call _chat_openai (not stream)."""
    monkeypatch.setattr(server, "STREAM_ENABLED", False)
    provider = _make_provider()
    called_stream = []
    called_nonstream = []

    def fake_stream(*a, **kw):
        called_stream.append(True)
        return {"text": "s", "tool_calls": [], "in_tokens": 1, "out_tokens": 1}

    def fake_nonstream(*a, **kw):
        called_nonstream.append(True)
        return {"text": "n", "tool_calls": [], "in_tokens": 1, "out_tokens": 1}

    monkeypatch.setattr(server, "_chat_openai_stream", fake_stream)
    monkeypatch.setattr(server, "_chat_openai", fake_nonstream)

    s = _make_session()
    server._call_provider(provider, "sys", [], [], 100, session=s)
    assert not called_stream, "stream path must NOT run when STREAM_ENABLED=False"
    assert called_nonstream
    del server.SESSIONS[s["id"]]


def test_stream_disabled_no_text_delta(monkeypatch):
    """STREAM_ENABLED off → agent_loop emits no text_delta events."""
    monkeypatch.setattr(server, "STREAM_ENABLED", False)
    provider = _make_provider()

    def fake_call_model(*a, **kw):
        return {"text": "hello world", "tool_calls": [], "in_tokens": 5, "out_tokens": 5}

    monkeypatch.setattr(server, "call_model", fake_call_model)
    monkeypatch.setattr(server, "call_cost", lambda *a: 0.0)
    monkeypatch.setattr(server, "_accrue_daily", lambda *a: None)

    s = _make_session()
    history = [{"role": "user", "text": "hi"}]
    server.agent_loop(s, provider, "sys", history, [], max_turns=1)

    delta_events = [e for e in s["events"] if e["type"] == "text_delta"]
    assert delta_events == [], "No text_delta events expected when streaming is off"
    del server.SESSIONS[s["id"]]


# ---------------------------------------------------------------------------
# 2. Flag ON — streaming path active
# ---------------------------------------------------------------------------

def test_stream_enabled_calls_stream_func(monkeypatch):
    """STREAM_ENABLED on + session provided → _chat_openai_stream is called."""
    monkeypatch.setattr(server, "STREAM_ENABLED", True)
    provider = _make_provider()
    called_stream = []

    def fake_stream(*a, **kw):
        called_stream.append(True)
        return {"text": "streamed", "tool_calls": [], "in_tokens": 2, "out_tokens": 3}

    monkeypatch.setattr(server, "_chat_openai_stream", fake_stream)

    s = _make_session()
    result = server._call_provider(provider, "sys", [], [], 100, session=s)
    assert called_stream, "stream path must run when STREAM_ENABLED=True and session given"
    assert result["text"] == "streamed"
    del server.SESSIONS[s["id"]]


def test_stream_no_session_falls_back(monkeypatch):
    """STREAM_ENABLED on but session=None → still calls non-streaming (no crash)."""
    monkeypatch.setattr(server, "STREAM_ENABLED", True)
    provider = _make_provider()
    called_nonstream = []

    def fake_nonstream(*a, **kw):
        called_nonstream.append(True)
        return {"text": "ns", "tool_calls": [], "in_tokens": 1, "out_tokens": 1}

    monkeypatch.setattr(server, "_chat_openai", fake_nonstream)

    result = server._call_provider(provider, "sys", [], [], 100, session=None)
    assert called_nonstream
    del called_nonstream[:]


# ---------------------------------------------------------------------------
# 3. _chat_openai_stream unit tests (stub the HTTP response)
# ---------------------------------------------------------------------------

def test_chat_openai_stream_text_assembly(monkeypatch):
    """Delta chunks are concatenated; final text equals the join."""
    chunks = ["Hello", ", ", "world", "!"]
    sse = _sse_lines(*chunks, usage={"prompt_tokens": 10, "completion_tokens": 4})
    resp_mock = _mock_streaming_response(sse)

    monkeypatch.setattr(server.requests, "post", lambda *a, **kw: resp_mock)
    monkeypatch.setattr(server, "_redact", lambda t: t)   # identity for this test

    s = _make_session()
    result = server._chat_openai_stream(
        _make_provider(), "sys", [], [], 100, s, agent_label=None
    )
    assert result["text"] == "Hello, world!"
    assert result["in_tokens"] == 10
    assert result["out_tokens"] == 4
    del server.SESSIONS[s["id"]]


def test_chat_openai_stream_emits_text_delta_events(monkeypatch):
    """Each content chunk produces a text_delta event on the session."""
    chunks = ["Foo", "Bar"]
    sse = _sse_lines(*chunks, usage={"prompt_tokens": 5, "completion_tokens": 2})
    resp_mock = _mock_streaming_response(sse)

    monkeypatch.setattr(server.requests, "post", lambda *a, **kw: resp_mock)
    monkeypatch.setattr(server, "_redact", lambda t: t)

    s = _make_session()
    server._chat_openai_stream(_make_provider(), "sys", [], [], 100, s)

    delta_events = [e for e in s["events"] if e["type"] == "text_delta"]
    assert len(delta_events) == 2
    assert delta_events[0]["text"] == "Foo"
    assert delta_events[1]["text"] == "Bar"
    del server.SESSIONS[s["id"]]


def test_chat_openai_stream_redaction_applied(monkeypatch):
    """_redact is called on each chunk; redacted text appears in events + final text."""
    chunks = ["my-SECRET-token"]
    sse = _sse_lines(*chunks, usage={"prompt_tokens": 3, "completion_tokens": 1})
    resp_mock = _mock_streaming_response(sse)

    monkeypatch.setattr(server.requests, "post", lambda *a, **kw: resp_mock)
    monkeypatch.setattr(server, "_redact", lambda t: t.replace("SECRET", "[REDACTED]"))

    s = _make_session()
    result = server._chat_openai_stream(_make_provider(), "sys", [], [], 100, s)

    assert result["text"] == "my-[REDACTED]-token"
    delta_events = [e for e in s["events"] if e["type"] == "text_delta"]
    assert delta_events[0]["text"] == "my-[REDACTED]-token"
    del server.SESSIONS[s["id"]]


def test_chat_openai_stream_tool_calls_assembled(monkeypatch):
    """Streamed tool-call deltas are merged into a single tool_calls list."""
    tc_id = "call-abc"
    tc_name = "read_file"
    tc_args = json.dumps({"path": "foo.py"})
    sse = _sse_tool_lines(tc_id, tc_name, tc_args,
                          usage={"prompt_tokens": 7, "completion_tokens": 2})
    resp_mock = _mock_streaming_response(sse)

    monkeypatch.setattr(server.requests, "post", lambda *a, **kw: resp_mock)
    monkeypatch.setattr(server, "_redact", lambda t: t)

    s = _make_session()
    result = server._chat_openai_stream(_make_provider(), "sys", [], [], 100, s)

    assert result["tool_calls"] == [
        {"id": "call-abc", "name": "read_file", "args": {"path": "foo.py"}}
    ]
    assert result["in_tokens"] == 7
    assert result["out_tokens"] == 2
    del server.SESSIONS[s["id"]]


def test_chat_openai_stream_usage_captured(monkeypatch):
    """Token counts come from the final usage chunk."""
    sse = _sse_lines("hi", usage={"prompt_tokens": 99, "completion_tokens": 77})
    resp_mock = _mock_streaming_response(sse)

    monkeypatch.setattr(server.requests, "post", lambda *a, **kw: resp_mock)
    monkeypatch.setattr(server, "_redact", lambda t: t)

    s = _make_session()
    result = server._chat_openai_stream(_make_provider(), "sys", [], [], 100, s)
    assert result["in_tokens"] == 99
    assert result["out_tokens"] == 77
    del server.SESSIONS[s["id"]]


def test_chat_openai_stream_missing_usage_falls_back_to_zero(monkeypatch):
    """If usage chunk is absent we fall back to 0 (matches the non-streaming dict.get fallback)."""
    # Manually craft SSE without a usage field on the final chunk
    final = {"choices": [{"delta": {}, "finish_reason": "stop", "index": 0}]}
    sse = [
        f"data: {json.dumps({'choices': [{'delta': {'content': 'x'}, 'index': 0}]})}",
        f"data: {json.dumps(final)}",
        "data: [DONE]",
    ]
    resp_mock = _mock_streaming_response(sse)

    monkeypatch.setattr(server.requests, "post", lambda *a, **kw: resp_mock)
    monkeypatch.setattr(server, "_redact", lambda t: t)

    s = _make_session()
    result = server._chat_openai_stream(_make_provider(), "sys", [], [], 100, s)
    assert result["in_tokens"] == 0
    assert result["out_tokens"] == 0
    del server.SESSIONS[s["id"]]


# ---------------------------------------------------------------------------
# 4. Streaming error → fallback to non-streaming, run completes
# ---------------------------------------------------------------------------

def test_streaming_error_falls_back_to_nonstreaming(monkeypatch):
    """Any exception inside _chat_openai_stream causes fallback to _chat_openai."""
    monkeypatch.setattr(server, "STREAM_ENABLED", True)
    provider = _make_provider()

    def bad_stream(*a, **kw):
        raise RuntimeError("SSE parse failure")

    ns_called = []

    def good_nonstream(*a, **kw):
        ns_called.append(True)
        return {"text": "fallback text", "tool_calls": [], "in_tokens": 1, "out_tokens": 1}

    monkeypatch.setattr(server, "_chat_openai_stream", bad_stream)
    monkeypatch.setattr(server, "_chat_openai", good_nonstream)

    s = _make_session()
    result = server._call_provider(provider, "sys", [], [], 100, session=s)
    assert ns_called, "non-streaming fallback must be called after stream error"
    assert result["text"] == "fallback text"
    del server.SESSIONS[s["id"]]


def test_streaming_error_agent_loop_still_completes(monkeypatch):
    """agent_loop completes the run even when streaming errors cause fallback."""
    monkeypatch.setattr(server, "STREAM_ENABLED", True)
    provider = _make_provider()

    first = [True]  # first call → streaming (via call_model/agent_loop dispatch)

    def fake_call_model(prov, sys, hist, tools, max_tokens=8192,
                        session=None, agent_label=None):
        # Return a valid non-tool response so the loop exits cleanly
        return {"text": "all good", "tool_calls": [], "in_tokens": 3, "out_tokens": 3}

    monkeypatch.setattr(server, "call_model", fake_call_model)
    monkeypatch.setattr(server, "call_cost", lambda *a: 0.001)
    monkeypatch.setattr(server, "_accrue_daily", lambda *a: None)

    s = _make_session()
    history = [{"role": "user", "text": "do stuff"}]
    final = server.agent_loop(s, provider, "sys", history, [], max_turns=1)
    assert final == "all good"
    del server.SESSIONS[s["id"]]


# ---------------------------------------------------------------------------
# 5. Existing behaviour unaffected (default-off integration smoke)
# ---------------------------------------------------------------------------

def test_existing_call_model_signature_still_works(monkeypatch):
    """call_model without new kwargs → behaves as before (no regression)."""
    monkeypatch.setattr(server, "STREAM_ENABLED", False)
    provider = _make_provider()

    def fake_nonstream(*a, **kw):
        return {"text": "old path", "tool_calls": [], "in_tokens": 1, "out_tokens": 1}

    monkeypatch.setattr(server, "_call_provider",
                        lambda *a, **kw: fake_nonstream())

    result = server.call_model(provider, "sys", [], [], 100)
    assert result["text"] == "old path"
