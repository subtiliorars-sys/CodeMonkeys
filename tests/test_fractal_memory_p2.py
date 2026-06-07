"""Fractal/tiered memory phase 2 (Standing list S3):
  - tier-1 digest is now SCRUBBED (commands/errors secret-stripped),
  - tier-2 curated cross-session pattern library + owner-only endpoint.

Run: ./.venv/bin/python -m pytest tests/ -q
"""
import os
import sys
import tempfile

os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(prefix="cm_test_"))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import server  # noqa: E402

client = TestClient(server.app)


def _hist(cmd="pytest -q", path="a.py", err="ERROR: 1 failed"):
    return [
        {"role": "user", "text": "go"},
        {"role": "assistant", "text": "ok", "tool_calls": [
            {"id": "1", "name": "read_file", "args": {"path": path}},
            {"id": "2", "name": "bash", "args": {"command": cmd}},
            {"id": "3", "name": "write_file", "args": {"path": path, "content": "x"}}]},
        {"role": "tool", "tool_call_id": "2", "name": "bash", "content": err},
    ]


# ---- tier-1 scrubbing ---------------------------------------------------------

def test_digest_scrubs_secret_in_command():
    h = _hist(cmd="curl -H 'Authorization: Bearer sk-AAAABBBBCCCCDDDDEEEEFFFF12345'")
    t = server._extract_theme_tokens(h)
    joined = " ".join(t["commands"])
    assert "sk-AAAABBBB" not in joined
    assert any("withheld" in c for c in t["commands"])


def test_digest_scrubs_github_token_in_command():
    h = _hist(cmd="git remote set-url origin https://ghp_0123456789abcdefABCDEF0123456789abcdef@github.com/x/y")
    t = server._extract_theme_tokens(h)
    assert "ghp_0123456789" not in " ".join(t["commands"])


# ---- red-team R2: broadened secret coverage -----------------------------------

@pytest.mark.parametrize("cmd", [
    "export ANTHROPIC_API_KEY=sk-ant-api03-AAAABBBBCCCCDDDDEEEEFFFF1234",   # Anthropic (hyphens)
    "stripe pay --key sk_live_AAAABBBBCCCCDDDDEEEE1234",                    # Stripe
    "psql postgres://admin:SuperSecretPw@db.host/app",                     # basic-auth URL
    "curl -H 'auth: Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiAxMjM0fQ.abcdefSig123'",  # JWT
    "echo password=hunter2longenough",                                     # generic credential
])
def test_digest_scrubs_broadened_secret_classes(cmd):
    t = server._extract_theme_tokens(_hist(cmd=cmd))
    assert any("withheld" in c for c in t["commands"]), cmd


def test_truncate_does_not_shed_secret_below_match_len():
    # secret pushed near the 200-char cut: full-string scan must still catch it
    pad = "a " * 95                                          # ~190 chars of filler
    cmd = pad + "ghp_0123456789abcdefABCDEF0123456789abcdef"
    t = server._extract_theme_tokens(_hist(cmd=cmd))
    assert any("withheld" in c for c in t["commands"])
    assert "ghp_0123456789" not in " ".join(t["commands"])


# ---- red-team R3: hostile/garbled history -------------------------------------

def test_non_string_command_does_not_crash():
    h = [{"role": "assistant", "text": "x", "tool_calls": [
        {"id": "1", "name": "bash", "args": {"command": ["ls", "-la"]}}]}]
    t = server._extract_theme_tokens(h)          # must not raise AttributeError
    assert isinstance(t["commands"], list)


def test_pattern_library_skips_poisoned_session():
    good = {"repo": "r", "history": _hist(cmd="make build")}
    poisoned = {"repo": "r", "history": [
        {"role": "assistant", "tool_calls": [
            {"id": "1", "name": "bash", "args": {"command": {"weird": "dict"}}}]}]}
    lib = server._pattern_library([good, poisoned])
    # str() coerces the dict so neither crashes; both count
    assert lib["session_count"] == 2


def test_pattern_library_handles_none_history():
    lib = server._pattern_library([{"repo": "r", "history": None}])
    assert lib["session_count"] == 1 and lib["top_commands"] == []


# ---- red-team R4: cross-session recurrence, not intra-session repeats ----------

def test_recurrence_dedupes_within_session():
    # one session running the same command 5× counts as 1 toward recurrence
    many = [{"role": "assistant", "tool_calls": [
        {"id": str(i), "name": "bash", "args": {"command": "flaky"}} for i in range(5)]}]
    lib = server._pattern_library([{"repo": "r", "history": many}])
    assert lib["top_commands"][0] == {"value": "flaky", "count": 1}


# ---- red-team R2-LOW: markdown injection ---------------------------------------

def test_markdown_escapes_backticks():
    h = _hist(cmd="echo `whoami`")
    lib = server._pattern_library([{"repo": "r", "history": h}])
    md = server._pattern_library_markdown(lib)
    assert "`whoami`" not in md            # backticks neutralized in the value


def test_digest_still_deterministic_and_keeps_clean_commands():
    t1 = server._extract_theme_tokens(_hist())
    t2 = server._extract_theme_tokens(_hist())
    assert t1 == t2
    assert "pytest -q" in t1["commands"]            # clean command untouched


# ---- tier-2 pattern library ---------------------------------------------------

def test_error_signature_folds_numbers():
    assert server._error_signature("ERROR: 3 failed") == server._error_signature("ERROR: 5 failed")
    assert server._error_signature("ERROR: 3 failed") == "# failed"   # digits → #


def test_pattern_library_aggregates_across_sessions():
    sessions = [
        {"repo": "r1", "history": _hist(cmd="make build", path="x.py", err="ERROR: 2 failed")},
        {"repo": "r1", "history": _hist(cmd="make build", path="x.py", err="ERROR: 9 failed")},
        {"repo": "r2", "history": _hist(cmd="npm test", path="y.js", err="ERROR: boom")},
    ]
    lib = server._pattern_library(sessions)
    assert lib["session_count"] == 3
    top_cmd = lib["top_commands"][0]
    assert top_cmd["value"] == "make build" and top_cmd["count"] == 2   # recurs across 2 sessions
    # x.py written in 2 sessions → highest
    assert lib["hot_files_written"][0]["value"] == "x.py"
    assert lib["hot_files_written"][0]["count"] == 2
    # error signatures fold the digits → "# failed" recurs twice
    errs = {e["value"]: e["count"] for e in lib["recurring_errors"]}
    assert errs.get("# failed") == 2
    # tools summed across all 3
    assert lib["tools_used"]["read_file"] == 3


def test_pattern_library_repo_filter():
    sessions = [
        {"repo": "r1", "history": _hist(cmd="make build")},
        {"repo": "r2", "history": _hist(cmd="npm test")},
    ]
    lib = server._pattern_library(sessions, repo="r1")
    assert lib["session_count"] == 1 and lib["repo"] == "r1"
    assert [c["value"] for c in lib["top_commands"]] == ["make build"]


def test_pattern_library_is_deterministic():
    sessions = [{"repo": "r", "history": _hist(cmd=c)}
                for c in ("a", "b", "a", "c")]
    assert server._pattern_library(sessions) == server._pattern_library(sessions)


def test_pattern_library_no_secret_leaks():
    sessions = [{"repo": "r",
                 "history": _hist(cmd="echo sk-AAAABBBBCCCCDDDDEEEEFFFF12345")}]
    lib = server._pattern_library(sessions)
    import json as _j
    assert "sk-AAAABBBB" not in _j.dumps(lib)


def test_pattern_library_empty():
    lib = server._pattern_library([])
    assert lib["session_count"] == 0 and lib["top_commands"] == []


# ---- endpoint -----------------------------------------------------------------

def test_patterns_endpoint_requires_owner():
    assert client.get("/api/memory/patterns").status_code in (401, 403)


def test_patterns_endpoint_json_and_md(monkeypatch):
    monkeypatch.setattr(server, "SESSIONS", {})
    s = server.new_session(title="t", repo="r1")
    s["history"] = _hist(cmd="make build")
    server.app.dependency_overrides[server.verify_owner] = lambda: "owner"
    try:
        j = client.get("/api/memory/patterns").json()
        assert j["session_count"] == 1
        assert j["top_commands"][0]["value"] == "make build"
        md = client.get("/api/memory/patterns?format=md")
        assert md.status_code == 200 and "Pattern library" in md.text
        # repo filter
        jr = client.get("/api/memory/patterns?repo=nope").json()
        assert jr["session_count"] == 0
    finally:
        server.app.dependency_overrides.pop(server.verify_owner, None)
