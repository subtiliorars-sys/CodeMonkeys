"""CM-W4 lint feedback loop: auto-inject diagnostics after edits + run_lint tool.

Run: ./.venv/bin/python -m pytest tests/test_lint_feedback.py -q
"""
import os
import sys
import tempfile

os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(prefix="cm_test_lint_"))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402
import server  # noqa: E402


@pytest.fixture
def ws(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "WORKSPACE_DIR", str(tmp_path))
    return tmp_path


def test_patch_target_paths():
    patch = (
        "--- a/src/foo.py\n"
        "+++ b/src/foo.py\n"
        "@@\n"
        "+x = 1\n"
        "--- /dev/null\n"
        "+++ b/bar.ts\n"
    )
    assert server._patch_target_paths(patch) == ["bar.ts", "src/foo.py"]


def test_lint_command_python_prefers_ruff(monkeypatch):
    monkeypatch.setattr(server.shutil, "which", lambda cmd: "/usr/bin/ruff" if cmd == "ruff" else None)
    cmd, label = server._lint_command("foo.py")
    assert label == "ruff"
    assert cmd[0] == "ruff"


def test_lint_command_python_fallback_py_compile(monkeypatch):
    monkeypatch.setattr(server.shutil, "which", lambda _cmd: None)
    cmd, label = server._lint_command("foo.py")
    assert label == "py_compile"
    assert "py_compile" in cmd


def test_run_lint_one_reports_syntax_error(ws, monkeypatch):
    bad = ws / "bad.py"
    bad.write_text("def oops(\n")
    monkeypatch.setattr(server.shutil, "which", lambda _cmd: None)
    note = server._run_lint_one("bad.py")
    assert "[lint:py_compile]" in note
    assert "bad.py" in note


def test_run_lint_one_silent_on_clean_file(ws, monkeypatch):
    good = ws / "good.py"
    good.write_text("x = 1\n")
    monkeypatch.setattr(server.shutil, "which", lambda _cmd: None)
    assert server._run_lint_one("good.py") == ""


def test_run_lint_tool_on_file(ws, monkeypatch):
    good = ws / "ok.py"
    good.write_text("y = 2\n")
    monkeypatch.setattr(server.shutil, "which", lambda _cmd: None)
    out = server.t_run_lint({"path": "ok.py"})
    assert "ok" in out


def test_agent_loop_injects_lint_after_write(ws, monkeypatch):
    monkeypatch.setattr(server, "LINT_AFTER_EDIT", True)
    monkeypatch.setattr(server.shutil, "which", lambda _cmd: None)

    provider = {
        "name": "p", "kind": "openai", "model": "m",
        "base_url": "http://x", "api_key": "k",
        "input_cost_per_m": 0, "output_cost_per_m": 0,
    }
    session = server.new_session(title="lint-test")
    session["mode"] = "default"
    session["budget_usd"] = 100.0
    history = [{"role": "user", "text": "fix it"}]
    calls = {"n": 0}

    def fake_call_model(_prov, _sys, hist, _tools, session=None, agent_label=None):
        calls["n"] += 1
        if calls["n"] == 1:
            return {
                "text": "",
                "tool_calls": [{
                    "id": "tc1", "name": "write_file",
                    "args": {"path": "broken.py", "content": "def bad(\n"},
                }],
                "in_tokens": 1, "out_tokens": 1,
            }
        return {"text": "done", "tool_calls": [], "in_tokens": 1, "out_tokens": 1}

    monkeypatch.setattr(server, "call_model", fake_call_model)
    monkeypatch.setattr(server, "emit", lambda *a, **k: None)

    server.agent_loop(session, provider, "sys", history, ["write_file"], max_turns=3)

    tool_msgs = [h for h in history if h.get("role") == "tool"]
    assert len(tool_msgs) == 1
    assert "[lint:py_compile]" in tool_msgs[0]["content"]


def test_lint_after_edit_disabled(ws, monkeypatch):
    monkeypatch.setattr(server, "LINT_AFTER_EDIT", False)
    monkeypatch.setattr(server.shutil, "which", lambda _cmd: None)

    provider = {
        "name": "p", "kind": "openai", "model": "m",
        "base_url": "http://x", "api_key": "k",
        "input_cost_per_m": 0, "output_cost_per_m": 0,
    }
    session = server.new_session(title="lint-off")
    session["mode"] = "default"
    session["budget_usd"] = 100.0
    history = [{"role": "user", "text": "write"}]
    calls = {"n": 0}

    def fake_call_model(_prov, _sys, hist, _tools, session=None, agent_label=None):
        calls["n"] += 1
        if calls["n"] == 1:
            return {
                "text": "",
                "tool_calls": [{
                    "id": "tc1", "name": "write_file",
                    "args": {"path": "broken.py", "content": "def bad(\n"},
                }],
                "in_tokens": 1, "out_tokens": 1,
            }
        return {"text": "done", "tool_calls": [], "in_tokens": 1, "out_tokens": 1}

    monkeypatch.setattr(server, "call_model", fake_call_model)
    monkeypatch.setattr(server, "emit", lambda *a, **k: None)

    server.agent_loop(session, provider, "sys", history, ["write_file"], max_turns=3)
    tool_msgs = [h for h in history if h.get("role") == "tool"]
    assert "[lint:" not in tool_msgs[0]["content"]
