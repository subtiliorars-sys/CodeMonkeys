"""Tests for secret redaction (server._redact / emit scrubbing).

bash can read env vars and app files (the conceded kernel-sandbox gap), and
GITHUB_TOKEN is the most sensitive item on the machine. Secret VALUES must be
scrubbed from anything echoed to the model, shown in the UI, or written to the
immutable JSONL event log / history.json — without affecting execution.

Run: ./.venv/bin/python -m pytest tests/ -q
"""
import os
import sys
import tempfile
import threading

os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(prefix="cm_test_"))
# A secret-named env var present before import, to prove env scraping works.
os.environ["GITHUB_TOKEN"] = "github_pat_11ABCDEF_supersecretvalue_0123456789"
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

import server  # noqa: E402

TOKEN = os.environ["GITHUB_TOKEN"]


@pytest.fixture(autouse=True)
def fresh_cache():
    server._bust_secret_cache()
    yield
    server._bust_secret_cache()


def test_env_secret_is_collected_and_redacted():
    assert TOKEN in server._sensitive_values()
    out = server._redact(f"the token is {TOKEN} ok")
    assert TOKEN not in out and "[REDACTED]" in out


def test_session_secret_is_redacted():
    sec = server._session_secret().hex()
    assert sec in server._sensitive_values()
    assert sec not in server._redact(f"leaked secret={sec}")


def test_model_api_keys_are_redacted_after_save():
    cfg = server.load_models()
    # plant a key the way the UI would, then save (which busts the cache)
    pid = next(iter(cfg["providers"]))
    cfg["providers"][pid]["key"] = "sk-test-MODELKEY-abcdef123456"
    server.save_models(cfg)
    try:
        out = server._redact("dumped config: sk-test-MODELKEY-abcdef123456")
        assert "sk-test-MODELKEY-abcdef123456" not in out
    finally:
        cfg["providers"][pid]["key"] = ""
        server.save_models(cfg)


def test_short_or_nonsensitive_values_not_redacted():
    # Non-secret-named env var and short values must pass through untouched.
    os.environ["EDITOR"] = "vim"
    server._bust_secret_cache()
    assert server._redact("editor is vim and PATH is fine") == \
        "editor is vim and PATH is fine"


def test_redact_passthrough_for_non_strings_and_empty():
    assert server._redact("") == ""
    assert server._redact(None) is None
    assert server._redact(12345) == 12345


def test_emit_scrubs_event_fields_and_jsonl_log():
    # A real emit() must redact string fields in the in-memory event AND in the
    # JSONL audit log written to /data.
    sid = "redact-test-sess"
    session = {
        "id": sid, "events": [], "lock": threading.Lock(),
    }
    server._bust_secret_cache()
    evt = server.emit(session, "tool_result", name="bash",
                      detail=f"output contained {TOKEN} oops", ok=True)
    assert TOKEN not in evt["detail"] and "[REDACTED]" in evt["detail"]
    # and the persisted line on disk is scrubbed too
    with open(server._events_path(sid), "r") as f:
        line = f.read()
    assert TOKEN not in line and "[REDACTED]" in line
