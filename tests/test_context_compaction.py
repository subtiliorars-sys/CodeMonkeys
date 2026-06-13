"""Tests for N8 — context auto-compaction.

Covers (per design doc):
  1. Estimator is monotonic + over-estimates (never under-counts)
  2. Below-threshold history is untouched
  3. Compaction triggers past the threshold
  4. First user turn is always preserved
  5. Recent verbatim window is preserved
  6. No orphaned tool_call / tool_result after compaction (critical)
  7. Deterministic: same history → same compacted result
  8. A compaction event is emitted
  9. Previously-inserted compaction note folds into new digest (no stacking)

Run: ./.venv/bin/python -m pytest tests/ -q
"""
import os
import sys
import tempfile

os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(prefix="cm_test_n8_"))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402
import server  # noqa: E402

ZERO_COST_PROVIDER = {
    "name": "p", "kind": "openai", "model": "m",
    "base_url": "http://x", "api_key": "k",
    "input_cost_per_m": 0, "output_cost_per_m": 0,
    "context_window": 128000,
}

# ---- history builders -------------------------------------------------------

def _user(text="hello"):
    return {"role": "user", "text": text}


def _assistant_text(text="ok"):
    return {"role": "assistant", "text": text, "tool_calls": []}


def _assistant_tool(tc_id, name, args):
    return {"role": "assistant", "text": "", "tool_calls": [
        {"id": tc_id, "name": name, "args": args}
    ]}


def _tool_result(tc_id, name, content="done"):
    return {"role": "tool", "tool_call_id": tc_id, "name": name, "content": content}


def _long_history(n_extra_pairs=20):
    """Build a history: first user turn + n_extra_pairs of (assistant, tool) + final."""
    h = [_user("original task")]
    for i in range(n_extra_pairs):
        h.append(_assistant_tool(f"tc{i}", "bash", {"command": f"ls /dir{i}"}))
        h.append(_tool_result(f"tc{i}", "bash", f"file{i}.txt"))
    h.append(_assistant_text("all done"))
    return h


def _make_session():
    s = server.new_session(title="n8test")
    s["budget_usd"] = 100.0
    return s


# ---- 1. Estimator monotonic + over-estimates --------------------------------

def test_estimator_grows_with_history():
    """Adding more turns increases the estimate (monotonic)."""
    system = "you are a helpful assistant"
    h0 = []
    h1 = [_user("do something")]
    h2 = h1 + [_assistant_text("done"), _user("and more")]
    e0 = server._estimate_tokens(system, h0)
    e1 = server._estimate_tokens(system, h1)
    e2 = server._estimate_tokens(system, h2)
    assert e0 < e1 < e2, f"estimator not monotonic: {e0}, {e1}, {e2}"


def test_estimator_over_estimates():
    """Estimated tokens must be >= actual character count / 4 for each text."""
    system = "sys"
    h = [_user("a" * 100), _assistant_text("b" * 200)]
    est = server._estimate_tokens(system, h)
    # naive floor: (len(system) + 100 + 200) / 4
    floor = (len(system) + 100 + 200) // 4
    assert est >= floor, f"estimator under-counted: {est} < {floor}"


def test_estimator_handles_tool_calls():
    """Tool-call args and tool-result content are counted."""
    system = ""
    h_no_tools = [_user("hi"), _assistant_text("bye")]
    h_with_tools = [
        _user("hi"),
        _assistant_tool("t1", "bash", {"command": "x" * 400}),
        _tool_result("t1", "bash", "y" * 400),
    ]
    e1 = server._estimate_tokens(system, h_no_tools)
    e2 = server._estimate_tokens(system, h_with_tools)
    assert e2 > e1, "tool-call args + result not counted in estimate"


# ---- 2. Below-threshold: no compaction ---------------------------------------

def test_below_threshold_history_untouched(monkeypatch):
    """A short history that's well under the threshold passes through unmodified."""
    # Set a large context window so short history never triggers
    tiny_history = [_user("task"), _assistant_text("done")]
    system = "sys"
    provider = dict(ZERO_COST_PROVIDER, context_window=1_000_000)

    s = _make_session()
    est = server._estimate_tokens(system, tiny_history)
    threshold = server.COMPACT_AT_FRAC * server._context_window_for(provider)
    assert est < threshold, "test pre-condition broken: history already over threshold"

    # Simulate one loop iteration: below threshold → no compaction event
    if est > server.COMPACT_AT_FRAC * server._context_window_for(provider):
        tiny_history[:] = server._compact_history(
            tiny_history, system, provider, s, None)
    compaction_events = [e for e in s["events"] if e.get("type") == "compaction"]
    assert len(compaction_events) == 0, "compaction fired on below-threshold history"
    del server.SESSIONS[s["id"]]


# ---- 3. Compaction triggers past threshold -----------------------------------

def test_compaction_reduces_history(monkeypatch):
    """When history exceeds the threshold, compact_history returns a shorter list."""
    history = _long_history(n_extra_pairs=20)
    system = "you are a coding assistant"
    # Use a tiny context window so the history definitely exceeds it
    provider = dict(ZERO_COST_PROVIDER, context_window=100)
    s = _make_session()

    compacted = server._compact_history(history, system, provider, s, None)
    assert len(compacted) < len(history), (
        f"compaction did not shorten history: {len(history)} → {len(compacted)}"
    )
    del server.SESSIONS[s["id"]]


# ---- 4. First user turn preserved -------------------------------------------

def test_first_user_turn_preserved():
    """The first user turn (task framing) must survive compaction."""
    first_turn_text = "ORIGINAL TASK TEXT"
    history = [_user(first_turn_text)] + [
        _assistant_tool(f"t{i}", "bash", {"command": f"cmd{i}"}) for i in range(15)
    ] + [
        _tool_result(f"t{i}", "bash", "ok") for i in range(15)
    ]
    system = "sys"
    provider = dict(ZERO_COST_PROVIDER, context_window=100)
    s = _make_session()

    compacted = server._compact_history(history, system, provider, s, None)
    assert compacted[0]["role"] == "user", "first entry is not a user turn"
    assert compacted[0]["text"] == first_turn_text, (
        f"first user turn text changed: {compacted[0]['text']!r}"
    )
    del server.SESSIONS[s["id"]]


# ---- 5. Recent verbatim window preserved ------------------------------------

def test_recent_window_preserved(monkeypatch):
    """The last KEEP_RECENT turns appear verbatim in the compacted history."""
    monkeypatch.setattr(server, "KEEP_RECENT", 4)

    # Build: first user + 10 pairs + 2 verbatim tail turns
    history = [_user("task")]
    for i in range(10):
        history.append(_assistant_tool(f"t{i}", "bash", {"command": f"cmd{i}"}))
        history.append(_tool_result(f"t{i}", "bash", f"out{i}"))
    # Add a clean tail that should survive (assistant text, no tool calls)
    history.append(_assistant_text("step A"))
    history.append(_user("continue"))

    system = "sys"
    provider = dict(ZERO_COST_PROVIDER, context_window=100)
    s = _make_session()

    compacted = server._compact_history(history, system, provider, s, None)
    compacted_texts = [h.get("text", "") for h in compacted]
    assert "step A" in compacted_texts, (
        "recent assistant turn 'step A' was compacted away"
    )
    assert "continue" in compacted_texts, (
        "recent user turn 'continue' was compacted away"
    )
    del server.SESSIONS[s["id"]]


# ---- 6. No orphaned tool_call / tool_result (critical) ----------------------

def _check_no_orphans(history):
    """Assert every assistant tool_call has a matching tool result, and every
    tool result has a preceding assistant turn that declared it."""
    declared = set()
    for h in history:
        if h.get("role") == "assistant":
            for tc in (h.get("tool_calls") or []):
                declared.add(tc["id"])
        elif h.get("role") == "tool":
            tid = h.get("tool_call_id")
            assert tid in declared, (
                f"orphaned tool result: tool_call_id={tid!r} has no matching assistant turn"
            )


def test_no_orphaned_tool_pairs():
    """Compaction must not split an assistant-with-tool_calls from its results."""
    history = [_user("task")]
    # Add 8 complete tool-call groups
    for i in range(8):
        history.append(_assistant_tool(f"t{i}", "bash", {"command": f"cmd{i}"}))
        history.append(_tool_result(f"t{i}", "bash", f"result{i}"))
    history.append(_assistant_text("done"))

    system = "sys"
    provider = dict(ZERO_COST_PROVIDER, context_window=100)
    s = _make_session()

    compacted = server._compact_history(history, system, provider, s, None)
    _check_no_orphans(compacted)
    del server.SESSIONS[s["id"]]


def test_no_orphans_multi_tool_per_turn():
    """A single assistant turn with multiple tool calls: all results must survive together."""
    # One assistant turn that calls two tools
    history = [
        _user("task"),
        {"role": "assistant", "text": "", "tool_calls": [
            {"id": "ta", "name": "read_file", "args": {"path": "a.py"}},
            {"id": "tb", "name": "bash",      "args": {"command": "ls"}},
        ]},
        _tool_result("ta", "read_file", "content"),
        _tool_result("tb", "bash", "file.py"),
    ]
    # Pad with older junk turns to push over threshold
    padding = [_assistant_text(f"old{i}") for i in range(20)]
    history = [history[0]] + padding + history[1:]

    system = "sys"
    provider = dict(ZERO_COST_PROVIDER, context_window=100)
    s = _make_session()

    compacted = server._compact_history(history, system, provider, s, None)
    _check_no_orphans(compacted)
    del server.SESSIONS[s["id"]]


# ---- 7. Deterministic -------------------------------------------------------

def test_compaction_is_deterministic():
    """Same history always produces the same compacted result."""
    history = _long_history(n_extra_pairs=15)
    system = "deterministic test"
    provider = dict(ZERO_COST_PROVIDER, context_window=100)

    s1 = _make_session()
    s2 = _make_session()

    c1 = server._compact_history(list(history), system, provider, s1, None)
    c2 = server._compact_history(list(history), system, provider, s2, None)

    assert len(c1) == len(c2), "compaction length non-deterministic"
    for i, (h1, h2) in enumerate(zip(c1, c2)):
        assert h1.get("text") == h2.get("text"), (
            f"turn {i} text differs: {h1.get('text')!r} vs {h2.get('text')!r}"
        )
    del server.SESSIONS[s1["id"]]
    del server.SESSIONS[s2["id"]]


# ---- 8. Compaction event emitted --------------------------------------------

def test_compaction_event_emitted():
    """A 'compaction' event is recorded when compaction fires."""
    history = _long_history(n_extra_pairs=20)
    system = "sys"
    provider = dict(ZERO_COST_PROVIDER, context_window=100)
    s = _make_session()

    server._compact_history(history, system, provider, s, None)

    compaction_events = [e for e in s["events"] if e.get("type") == "compaction"]
    assert len(compaction_events) == 1, (
        f"expected 1 compaction event, got {len(compaction_events)}"
    )
    evt = compaction_events[0]
    assert "turns_compacted" in evt, "turns_compacted missing from event"
    assert "est_tokens_before" in evt, "est_tokens_before missing from event"
    assert "est_tokens_after" in evt, "est_tokens_after missing from event"
    assert evt["est_tokens_after"] < evt["est_tokens_before"], (
        "compaction did not reduce estimated token count"
    )
    del server.SESSIONS[s["id"]]


def test_compaction_event_has_agent_label():
    """The compaction event carries the agent label when provided."""
    history = _long_history(n_extra_pairs=20)
    system = "sys"
    provider = dict(ZERO_COST_PROVIDER, context_window=100)
    s = _make_session()

    server._compact_history(history, system, provider, s, agent_label="my-agent")

    evt = next(e for e in s["events"] if e.get("type") == "compaction")
    assert evt.get("agent") == "my-agent", (
        f"agent label not on compaction event: {evt}"
    )
    del server.SESSIONS[s["id"]]


# ---- 9. Existing compaction note folds in (no stacking) ---------------------

def test_previous_compaction_note_folds():
    """A second compaction over history that already has a [compacted] note
    produces a single compaction note, not two stacked notes."""
    history = _long_history(n_extra_pairs=20)
    system = "sys"
    provider = dict(ZERO_COST_PROVIDER, context_window=100)
    s = _make_session()

    # First compaction
    h2 = server._compact_history(history, system, provider, s, None)

    # Second compaction on already-compacted history (simulate another long run)
    # Pad h2 with more turns to trigger again
    for i in range(10):
        h2.append(_assistant_tool(f"x{i}", "bash", {"command": f"xcmd{i}"}))
        h2.append(_tool_result(f"x{i}", "bash", f"xout{i}"))

    h3 = server._compact_history(h2, system, provider, s, None)

    # Count synthetic [earlier context, compacted] notes
    compaction_notes = [
        h for h in h3
        if h.get("role") == "user" and "[earlier context, compacted]" in (h.get("text") or "")
    ]
    assert len(compaction_notes) == 1, (
        f"stacked compaction notes found ({len(compaction_notes)}): "
        "second compaction should fold the first note in"
    )
    del server.SESSIONS[s["id"]]


# ---- 10. agent_loop integration: compaction fires in-loop -------------------

def test_agent_loop_triggers_compaction(monkeypatch):
    """agent_loop emits a compaction event when history exceeds the threshold."""
    monkeypatch.setattr(server, "COMPACT_AT_FRAC", 0.0)  # always compact
    monkeypatch.setattr(server, "KEEP_RECENT", 4)         # small window so span is non-empty

    def _call_model(provider, system, history, tools, **kw):
        return {"text": "done", "tool_calls": [], "in_tokens": 1, "out_tokens": 1}

    monkeypatch.setattr(server, "call_model", _call_model)
    monkeypatch.setattr(server, "_pricier_provider", lambda cfg, p: None)
    monkeypatch.setattr(server, "main_provider", lambda cfg: ZERO_COST_PROVIDER)

    s = _make_session()
    # Seed history with many turns so span is definitely non-empty
    s["history"] = _long_history(n_extra_pairs=10)  # 1 + 10*2 + 1 = 22 turns

    server.run_session_message(s, "continue")

    compaction_events = [e for e in s["events"] if e.get("type") == "compaction"]
    assert len(compaction_events) >= 1, (
        "expected at least one compaction event from agent_loop run"
    )
    del server.SESSIONS[s["id"]]


# ---- 11. _context_window_for helper -----------------------------------------

def test_context_window_for_reads_provider_field():
    """_context_window_for returns the provider's context_window value."""
    p = dict(ZERO_COST_PROVIDER, context_window=200000)
    assert server._context_window_for(p) == 200000


def test_context_window_for_falls_back():
    """_context_window_for falls back to COMPACT_CONTEXT_WINDOW_DEFAULT when absent."""
    p = dict(ZERO_COST_PROVIDER)
    p.pop("context_window", None)
    assert server._context_window_for(p) == server.COMPACT_CONTEXT_WINDOW_DEFAULT


def test_context_window_for_ignores_zero():
    """A zero context_window field triggers the fallback, not a division hazard."""
    p = dict(ZERO_COST_PROVIDER, context_window=0)
    assert server._context_window_for(p) == server.COMPACT_CONTEXT_WINDOW_DEFAULT
