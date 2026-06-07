"""Tests for N4 diff preview — write_file / edit_file / apply_patch.

Verifies that unified diffs are produced (or surfaced for apply_patch),
capped, and redacted before being emitted on the event stream.

Run: ./.venv/bin/python -m pytest tests/ -q
"""
import os
import sys
import tempfile
import threading

os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(prefix="cm_test_diff_"))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402
import server  # noqa: E402


# ---- helpers -----------------------------------------------------------------

def _session():
    sid = "diff-test-" + os.urandom(4).hex()
    return {"id": sid, "events": [], "lock": threading.Lock()}


def _workspace_file(content: str, name: str = "test.txt") -> str:
    """Write *content* into the jailed workspace and return its relative path."""
    full = os.path.join(server.WORKSPACE_DIR, name)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w") as f:
        f.write(content)
    return name


# ---- _diff_preview -----------------------------------------------------------

def test_diff_preview_new_file():
    """Empty old content (new file) should yield a diff with only '+' lines."""
    old = ""
    new = "hello\nworld\n"
    diff = server._diff_preview(old, new, "new.txt")
    assert "+hello" in diff
    assert "+world" in diff
    assert "--- a/new.txt" in diff


def test_diff_preview_edit():
    """Old→new edit should show removed and added lines."""
    old = "line one\nline two\nline three\n"
    new = "line one\nline TWO\nline three\n"
    diff = server._diff_preview(old, new, "f.txt")
    assert "-line two" in diff
    assert "+line TWO" in diff


def test_diff_preview_no_change():
    """Identical old/new returns empty string (no noise for no-op writes)."""
    content = "unchanged content\n"
    diff = server._diff_preview(content, content, "f.txt")
    assert diff == ""


def test_diff_preview_size_cap():
    """Diffs exceeding DIFF_LINE_CAP or DIFF_BYTE_CAP are truncated."""
    old = ""
    # Produce a large diff by adding many lines
    new = "\n".join(f"line {i}" for i in range(server.DIFF_LINE_CAP + 50)) + "\n"
    diff = server._diff_preview(old, new, "big.txt")
    assert "...[diff truncated]" in diff


def test_diff_preview_byte_cap():
    """Byte cap enforced when lines are very long."""
    old = ""
    # One very long line that will exceed DIFF_BYTE_CAP on its own
    new = "x" * (server.DIFF_BYTE_CAP + 100) + "\n"
    diff = server._diff_preview(old, new, "wide.txt")
    assert "...[diff truncated]" in diff
    assert len(diff) <= server.DIFF_BYTE_CAP + len("\n...[diff truncated]") + 5


def test_diff_preview_redacted(monkeypatch):
    """Secret values are scrubbed from the diff output."""
    server._bust_secret_cache()
    secret = "sk-supersecretkey12345"
    os.environ["TEST_SECRET_N4"] = secret
    server._bust_secret_cache()
    try:
        old = "no secret here\n"
        new = f"the key is {secret}\n"
        diff = server._diff_preview(old, new, "cfg.txt")
        assert secret not in diff
        assert "[REDACTED]" in diff
    finally:
        del os.environ["TEST_SECRET_N4"]
        server._bust_secret_cache()


# ---- _patch_preview ----------------------------------------------------------

def test_patch_preview_surfaces_patch():
    """_patch_preview returns the patch text (capped + redacted)."""
    patch = (
        "--- a/foo.py\n+++ b/foo.py\n"
        "@@ -1,2 +1,2 @@\n"
        "-old line\n"
        "+new line\n"
    )
    preview = server._patch_preview(patch)
    assert "--- a/foo.py" in preview
    assert "+new line" in preview


def test_patch_preview_size_cap():
    big = "--- a/f\n+++ b/f\n" + "+line\n" * (server.DIFF_LINE_CAP + 50)
    preview = server._patch_preview(big)
    assert "...[diff truncated]" in preview


def test_patch_preview_empty():
    assert server._patch_preview("") == ""


# ---- t_write_file / t_edit_file return tuple --------------------------------

def test_write_file_returns_tuple_new():
    """write_file returns (result_str, diff_str) tuple for a new file."""
    path = f"_n4_new_{os.urandom(3).hex()}.txt"
    full = os.path.join(server.WORKSPACE_DIR, path)
    # Ensure no prior file
    if os.path.exists(full):
        os.remove(full)
    result, diff = server.t_write_file({"path": path, "content": "hello\n"})
    os.remove(full)  # cleanup
    assert "Wrote" in result
    assert "+hello" in diff


def test_write_file_returns_tuple_edit():
    """write_file diff shows old vs new when overwriting existing file."""
    path = f"_n4_edit_{os.urandom(3).hex()}.txt"
    _workspace_file("before\n", path)
    result, diff = server.t_write_file({"path": path, "content": "after\n"})
    full = os.path.join(server.WORKSPACE_DIR, path)
    if os.path.exists(full):
        os.remove(full)
    assert "-before" in diff
    assert "+after" in diff


def test_write_file_no_op_empty_diff():
    """write_file with same content produces empty diff."""
    content = "same content\n"
    path = f"_n4_noop_{os.urandom(3).hex()}.txt"
    _workspace_file(content, path)
    result, diff = server.t_write_file({"path": path, "content": content})
    full = os.path.join(server.WORKSPACE_DIR, path)
    if os.path.exists(full):
        os.remove(full)
    assert diff == ""


def test_edit_file_returns_tuple():
    """edit_file returns (result_str, diff_str) tuple on success."""
    path = f"_n4_ef_{os.urandom(3).hex()}.txt"
    _workspace_file("foo bar baz\n", path)
    result, diff = server.t_edit_file({
        "path": path,
        "old_string": "foo bar",
        "new_string": "FOO BAR",
    })
    full = os.path.join(server.WORKSPACE_DIR, path)
    if os.path.exists(full):
        os.remove(full)
    assert result == "Edit applied"
    assert "-foo bar baz" in diff
    assert "+FOO BAR baz" in diff


def test_edit_file_error_returns_empty_diff():
    """edit_file with missing old_string returns error + empty diff (no partial diff)."""
    path = f"_n4_ef_err_{os.urandom(3).hex()}.txt"
    _workspace_file("unchanged\n", path)
    result, diff = server.t_edit_file({
        "path": path,
        "old_string": "NOTFOUND",
        "new_string": "anything",
    })
    full = os.path.join(server.WORKSPACE_DIR, path)
    if os.path.exists(full):
        os.remove(full)
    assert result.startswith("ERROR")
    assert diff == ""


# ---- emit integration: diff field appears in tool_result event ---------------

def test_diff_field_emitted_on_write(tmp_path, monkeypatch):
    """agent_loop emits diff field on tool_result for write_file mutations."""
    # We test the emit path directly via the executor (no model call needed).
    sess = _session()
    path = f"_n4_emit_{os.urandom(3).hex()}.txt"
    full = os.path.join(server.WORKSPACE_DIR, path)
    if os.path.exists(full):
        os.remove(full)

    executor = server.make_executor(sess, {"write_file"})
    tc = {"name": "write_file", "args": {"path": path, "content": "emitted\n"}, "id": "t1"}
    raw = executor(tc)
    # executor returns 3-tuple for write_file
    assert len(raw) == 3
    result, ok, diff = raw
    assert ok is True
    assert "+emitted" in diff

    # Simulate what agent_loop does: emit tool_result with diff
    kw = {"name": "write_file", "ok": ok, "detail": result[:600], "agent": None}
    if diff:
        kw["diff"] = diff
    evt = server.emit(sess, "tool_result", **kw)
    assert "diff" in evt
    assert "+emitted" in evt["diff"]

    if os.path.exists(full):
        os.remove(full)
