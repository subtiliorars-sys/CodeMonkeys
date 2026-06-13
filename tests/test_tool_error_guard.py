"""Tests for N9 tool-error-repeat guard.

Covers:
  - repeated identical failure injects nudge at N_NUDGE then aborts at N_STOP
  - distinct failures (different signatures) do NOT trip the guard
  - a successful call resets that signature's counter
  - guard is mode-agnostic (default + auto both covered)
  - normal runs (no repeated failure) are unaffected

Run: ./.venv/bin/python -m pytest tests/ -q
"""
import os
import sys
import json
import tempfile

os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(prefix="cm_test_n9_"))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402
import server  # noqa: E402


ZERO_COST_PROVIDER = {
    "name": "p", "kind": "openai", "model": "m",
    "base_url": "http://x", "api_key": "k",
    "input_cost_per_m": 0, "output_cost_per_m": 0,
}

# ---- helpers -----------------------------------------------------------------

def _make_session(mode="default"):
    s = server.new_session(title="n9test")
    s["mode"] = mode
    s["budget_usd"] = 100.0
    return s


def _run(session, monkeypatch, call_model_fn):
    """Drive agent_loop synchronously with a stubbed provider."""
    monkeypatch.setattr(server, "main_provider", lambda cfg, username=None: ZERO_COST_PROVIDER)
    monkeypatch.setattr(server, "call_model", call_model_fn)
    monkeypatch.setattr(server, "_pricier_provider", lambda cfg, p, username=None: None)
    server.run_session_message(session, "go")


def _tool_responses(*pairs):
    """Build a call_model stub that cycles through (tool_calls, results) turns.

    Each element of *pairs* is either:
      - a str → plain text response (no tool calls), loop ends
      - a list of (name, args, result, ok) tuples → tool call turn

    The stub raises StopIteration if exhausted to catch runaway loops.
    """
    turns = list(pairs)
    state = {"i": 0}

    def _call(provider, system, history, tools, **kw):
        i = state["i"]
        if i >= len(turns):
            raise RuntimeError(f"call_model called after {i} turns — loop ran too long")
        turn = turns[i]
        state["i"] += 1
        if isinstance(turn, str):
            return {"text": turn, "tool_calls": [], "in_tokens": 1, "out_tokens": 1}
        # tool-call turn
        tool_calls = [
            {"id": f"tc{i}_{j}", "name": name, "args": args}
            for j, (name, args, _result, _ok) in enumerate(turn)
        ]
        return {"text": "", "tool_calls": tool_calls, "in_tokens": 1, "out_tokens": 1}

    return _call


def _fake_executor(sequence):
    """Build a make_executor stub that returns results from *sequence* in order.

    sequence: list of (result, ok) or (result, ok, diff).
    Raises if exhausted.
    """
    state = {"i": 0}

    def _make_exec(session, tool_names, agent_label, depth):
        def _exec(tc):
            i = state["i"]
            if i >= len(sequence):
                raise RuntimeError(f"executor called after {i} invocations — too many")
            r = sequence[i]
            state["i"] += 1
            return r
        return _exec

    return _make_exec


# ---- N_NUDGE / N_STOP values used in tests -----------------------------------
# Read from module so tests track the real values (not hardcoded).
_N_NUDGE = server.N_NUDGE
_N_STOP  = server.N_STOP


# ---- 1. Repeated identical failure: nudge then abort -------------------------

def test_nudge_injected_at_n_nudge(monkeypatch):
    """After N_NUDGE identical failures the nudge appears in history content."""
    monkeypatch.setattr(server, "N_NUDGE", 2)
    monkeypatch.setattr(server, "N_STOP",  99)  # disable abort for this test

    fail_result = "ERROR: permission denied"
    # Each turn: one tool call that fails, then a text turn to end the loop.
    # We need N_NUDGE failures, so N_NUDGE tool-call turns + one text turn.
    tool_turns = [
        [("bash", {"cmd": "rm -rf /x"}, fail_result, False)]
        for _ in range(2)  # N_NUDGE = 2
    ]
    call_model_stub = _tool_responses(*tool_turns, "done")

    # executor always returns failure
    exec_seq = [(fail_result, False)] * 2
    monkeypatch.setattr(server, "make_executor", _fake_executor(exec_seq))

    s = _make_session()
    _run(s, monkeypatch, call_model_stub)

    # find history entries of role=tool; the 2nd one should have the nudge
    tool_entries = [h for h in s["history"] if h.get("role") == "tool"]
    assert len(tool_entries) >= 2, f"expected ≥2 tool history entries, got {tool_entries}"
    nudged = tool_entries[-1]["content"]
    assert "tool-repeat guard" in nudged, \
        f"nudge not found in last tool entry: {nudged!r}"
    assert "bash" in nudged, f"tool name missing from nudge: {nudged!r}"
    del server.SESSIONS[s["id"]]


def test_abort_at_n_stop(monkeypatch):
    """After N_STOP identical failures the loop aborts with outcome='stuck'."""
    n_stop = 4
    monkeypatch.setattr(server, "N_NUDGE", 2)
    monkeypatch.setattr(server, "N_STOP",  n_stop)

    fail_result = "ERROR: connection refused"
    tool_turns = [
        [("bash", {"cmd": "curl http://bad"}, fail_result, False)]
        for _ in range(n_stop)
    ]
    # give extra text turns that should never fire if abort works
    call_model_stub = _tool_responses(*tool_turns, "should not reach here")
    exec_seq = [(fail_result, False)] * n_stop
    monkeypatch.setattr(server, "make_executor", _fake_executor(exec_seq))

    s = _make_session()
    _run(s, monkeypatch, call_model_stub)

    assert s.get("_run_outcome") == "stuck", \
        f"expected outcome='stuck', got {s.get('_run_outcome')!r}"
    del server.SESSIONS[s["id"]]


def test_abort_emits_error_event(monkeypatch):
    """The abort emits an 'error' event containing 'aborted'."""
    monkeypatch.setattr(server, "N_NUDGE", 2)
    monkeypatch.setattr(server, "N_STOP",  3)

    fail_result = "ERROR: timeout"
    tool_turns = [
        [("bash", {"cmd": "sleep 100"}, fail_result, False)]
        for _ in range(3)
    ]
    call_model_stub = _tool_responses(*tool_turns, "never")
    exec_seq = [(fail_result, False)] * 3
    monkeypatch.setattr(server, "make_executor", _fake_executor(exec_seq))

    s = _make_session()
    _run(s, monkeypatch, call_model_stub)

    error_events = [e for e in s["events"] if e.get("type") == "error"]
    abort_events = [e for e in error_events if "aborted" in e.get("message", "")]
    assert abort_events, f"no abort error event found; errors: {error_events}"
    del server.SESSIONS[s["id"]]


# ---- 2. Distinct failures do NOT trip the guard ------------------------------

def test_distinct_failures_dont_abort(monkeypatch):
    """Different tool names or different error text → different signatures → no abort."""
    monkeypatch.setattr(server, "N_NUDGE", 2)
    monkeypatch.setattr(server, "N_STOP",  3)

    # Three failures with distinct error messages — each has a unique signature
    tool_turns = [
        [("bash", {"cmd": "cmd1"}, "ERROR: alpha", False)],
        [("bash", {"cmd": "cmd1"}, "ERROR: beta",  False)],
        [("bash", {"cmd": "cmd1"}, "ERROR: gamma", False)],
    ]
    call_model_stub = _tool_responses(*tool_turns, "done")
    exec_seq = [
        ("ERROR: alpha", False),
        ("ERROR: beta",  False),
        ("ERROR: gamma", False),
    ]
    monkeypatch.setattr(server, "make_executor", _fake_executor(exec_seq))

    s = _make_session()
    _run(s, monkeypatch, call_model_stub)

    assert s.get("_run_outcome") != "stuck", \
        "distinct failures incorrectly triggered the guard"
    del server.SESSIONS[s["id"]]


def test_different_args_dont_trip(monkeypatch):
    """Same tool + same error class but different args → different signature → no abort."""
    monkeypatch.setattr(server, "N_NUDGE", 2)
    monkeypatch.setattr(server, "N_STOP",  3)

    fail_msg = "ERROR: file not found"
    tool_turns = [
        [("read_file", {"path": "/a"}, fail_msg, False)],
        [("read_file", {"path": "/b"}, fail_msg, False)],
        [("read_file", {"path": "/c"}, fail_msg, False)],
    ]
    call_model_stub = _tool_responses(*tool_turns, "done")
    exec_seq = [(fail_msg, False)] * 3
    monkeypatch.setattr(server, "make_executor", _fake_executor(exec_seq))

    s = _make_session()
    _run(s, monkeypatch, call_model_stub)

    assert s.get("_run_outcome") != "stuck", \
        "differing args incorrectly shared a failure signature"
    del server.SESSIONS[s["id"]]


# ---- 3. Success resets the counter -------------------------------------------

def test_success_resets_counter(monkeypatch):
    """A successful call clears the failure count for that signature."""
    monkeypatch.setattr(server, "N_NUDGE", 2)
    monkeypatch.setattr(server, "N_STOP",  3)

    fail_msg = "ERROR: disk full"
    # fail once, succeed once (resets), fail once again — total repeats = 1, no abort
    tool_turns = [
        [("bash", {"cmd": "write"}, fail_msg,  False)],   # fail #1 → count=1
        [("bash", {"cmd": "write"}, "ok",       True)],   # success → count=0
        [("bash", {"cmd": "write"}, fail_msg,  False)],   # fail #1 again → count=1
    ]
    call_model_stub = _tool_responses(*tool_turns, "done")
    exec_seq = [
        (fail_msg, False),
        ("ok",     True),
        (fail_msg, False),
    ]
    monkeypatch.setattr(server, "make_executor", _fake_executor(exec_seq))

    s = _make_session()
    _run(s, monkeypatch, call_model_stub)

    assert s.get("_run_outcome") != "stuck", \
        "counter not reset by success — guard fired incorrectly"
    del server.SESSIONS[s["id"]]


# ---- 4. Normal run (no repeated failure) unaffected --------------------------

def test_normal_run_unaffected(monkeypatch):
    """A run with no tool failures completes normally — guard is silent."""
    call_model_stub = _tool_responses("all good")
    monkeypatch.setattr(server, "make_executor",
                        _fake_executor([]))   # no tool calls expected

    s = _make_session()
    _run(s, monkeypatch, call_model_stub)

    assert s.get("_run_outcome") == "ok", \
        f"normal run unexpectedly hit guard: {s.get('_run_outcome')}"
    del server.SESSIONS[s["id"]]


def test_tool_success_run_unaffected(monkeypatch):
    """Successful tool calls complete normally."""
    tool_turns = [
        [("bash", {"cmd": "ls"}, "file1.txt\nfile2.txt", True)],
    ]
    call_model_stub = _tool_responses(*tool_turns, "listed files")
    exec_seq = [("file1.txt\nfile2.txt", True)]
    monkeypatch.setattr(server, "make_executor", _fake_executor(exec_seq))

    s = _make_session()
    _run(s, monkeypatch, call_model_stub)

    assert s.get("_run_outcome") == "ok", \
        f"successful tool run unexpectedly hit guard: {s.get('_run_outcome')}"
    del server.SESSIONS[s["id"]]


# ---- 5. Mode-agnostic: default + auto both covered ---------------------------

def test_guard_triggers_in_default_mode(monkeypatch):
    """Guard fires in default mode."""
    monkeypatch.setattr(server, "N_NUDGE", 2)
    monkeypatch.setattr(server, "N_STOP",  3)

    fail_result = "ERROR: nope"
    tool_turns = [
        [("bash", {"cmd": "x"}, fail_result, False)]
        for _ in range(3)
    ]
    call_model_stub = _tool_responses(*tool_turns, "never")
    exec_seq = [(fail_result, False)] * 3
    monkeypatch.setattr(server, "make_executor", _fake_executor(exec_seq))

    s = _make_session(mode="default")
    _run(s, monkeypatch, call_model_stub)

    assert s.get("_run_outcome") == "stuck"
    del server.SESSIONS[s["id"]]


def test_guard_triggers_in_auto_mode(monkeypatch):
    """Guard fires in auto mode the same way."""
    monkeypatch.setattr(server, "N_NUDGE", 2)
    monkeypatch.setattr(server, "N_STOP",  3)

    fail_result = "ERROR: nope"
    tool_turns = [
        [("bash", {"cmd": "x"}, fail_result, False)]
        for _ in range(3)
    ]
    call_model_stub = _tool_responses(*tool_turns, "never")
    exec_seq = [(fail_result, False)] * 3
    monkeypatch.setattr(server, "make_executor", _fake_executor(exec_seq))

    s = _make_session(mode="auto")
    _run(s, monkeypatch, call_model_stub)

    assert s.get("_run_outcome") == "stuck"
    del server.SESSIONS[s["id"]]


# ---- 6. Signature scheme unit tests -----------------------------------------

def test_fail_sig_stable_for_same_inputs():
    """_fail_sig produces the same key for identical (name, args, error)."""
    s = server.new_session(title="sig_test")

    def _fail_sig(name, args, error):
        import hashlib, json as _json
        args_hash = hashlib.sha256(
            _json.dumps(args, sort_keys=True, default=str).encode()
        ).hexdigest()[:8]
        return f"{name}:{args_hash}:{server._error_signature(error)}"

    sig1 = _fail_sig("bash", {"cmd": "rm -rf /x"}, "ERROR: 42 files deleted")
    sig2 = _fail_sig("bash", {"cmd": "rm -rf /x"}, "ERROR: 99 files deleted")
    assert sig1 == sig2, \
        "digits in error should be folded — different counts must share signature"

    sig3 = _fail_sig("bash", {"cmd": "rm -rf /y"}, "ERROR: 42 files deleted")
    assert sig3 != sig1, "different args must produce different signature"

    sig4 = _fail_sig("write_file", {"cmd": "rm -rf /x"}, "ERROR: 42 files deleted")
    assert sig4 != sig1, "different tool name must produce different signature"

    del server.SESSIONS[s["id"]]


def test_error_signature_folds_numbers():
    """_error_signature collapses numeric noise so count-variants share a key."""
    s1 = server._error_signature("ERROR: 3 retries exceeded")
    s2 = server._error_signature("ERROR: 10 retries exceeded")
    assert s1 == s2, f"numeric folding failed: {s1!r} != {s2!r}"


# ---- 7. N9 state is reset between runs ---------------------------------------

def test_fail_counts_reset_on_new_run(monkeypatch):
    """_tool_fail_counts is cleared at the start of each run, not carried over."""
    monkeypatch.setattr(server, "N_NUDGE", 2)
    monkeypatch.setattr(server, "N_STOP",  3)

    fail_result = "ERROR: boom"
    # First run: 2 failures (below N_STOP=3) — outcome should be ok (loop ends normally)
    tool_turns_1 = [
        [("bash", {"cmd": "x"}, fail_result, False)],
        [("bash", {"cmd": "x"}, fail_result, False)],
    ]
    call_stub_1 = _tool_responses(*tool_turns_1, "done")
    exec_seq_1 = [(fail_result, False)] * 2
    monkeypatch.setattr(server, "make_executor", _fake_executor(exec_seq_1))

    s = _make_session()
    _run(s, monkeypatch, call_stub_1)
    assert s.get("_run_outcome") == "ok", \
        f"first run should be ok, got {s.get('_run_outcome')}"

    # Second run on same session: 1 failure — count must restart from 1, not 3+1=4
    tool_turns_2 = [
        [("bash", {"cmd": "x"}, fail_result, False)],
    ]
    call_stub_2 = _tool_responses(*tool_turns_2, "done")
    exec_seq_2 = [(fail_result, False)]
    monkeypatch.setattr(server, "make_executor", _fake_executor(exec_seq_2))

    _run(s, monkeypatch, call_stub_2)
    assert s.get("_run_outcome") == "ok", \
        f"second run carried over old count — expected ok, got {s.get('_run_outcome')}"

    del server.SESSIONS[s["id"]]
