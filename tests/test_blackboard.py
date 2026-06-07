"""Tests for cross-session blackboard memory (IDEATION #4).

Covers: write/read round-trip, append vs replace, section preservation, the
.codemonkeys jail (no traversal/escape), enum + size guards, system-prompt
injection, and the plan-mode invariant (blackboard_write is NOT a plan-mode
tool — plan mode's only write affordance stays save_spec).

Run: ./.venv/bin/python -m pytest tests/ -q
"""
import os
import shutil
import sys
import tempfile

os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(prefix="cm_test_"))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

import server  # noqa: E402

_CMDIR = os.path.join(server.WORKSPACE_DIR, ".codemonkeys")


@pytest.fixture(autouse=True)
def clean_codemonkeys():
    shutil.rmtree(_CMDIR, ignore_errors=True)
    yield
    shutil.rmtree(_CMDIR, ignore_errors=True)


def W(**kw):
    return server.t_blackboard_write(kw)


def R(slug):
    return server.t_blackboard_read({"slug": slug})


def test_write_then_read_roundtrip():
    assert W(slug="demo", section="FACTS", content="server.py is single-file") \
        .startswith("Updated FACTS")
    out = R("demo")
    assert "## FACTS" in out and "server.py is single-file" in out
    # file landed exactly where expected
    assert os.path.exists(os.path.join(_CMDIR, "blackboard-demo.md"))


def test_append_accumulates_and_replace_overwrites():
    W(slug="demo", section="NEXT", content="step one")
    W(slug="demo", section="NEXT", content="step two")
    out = R("demo")
    assert "- step one" in out and "- step two" in out
    W(slug="demo", section="NEXT", content="only this", mode="replace")
    out = R("demo")
    assert "only this" in out and "step one" not in out


def test_writing_one_section_preserves_others():
    W(slug="demo", section="FACTS", content="fact A")
    W(slug="demo", section="DECISIONS", content="chose X because Y")
    out = R("demo")
    assert "fact A" in out and "chose X because Y" in out


def test_unknown_blackboard_reads_friendly():
    assert "no blackboard yet" in R("never-created")


def test_section_enum_and_mode_guards():
    assert W(slug="demo", section="BOGUS", content="x").startswith("ERROR")
    assert W(slug="demo", section="FACTS", content="x", mode="bogus").startswith("ERROR")
    assert W(slug="", section="FACTS", content="x").startswith("ERROR")


def test_slug_is_sanitized_and_jailed():
    # A traversal-flavored slug is sanitized to hyphens and stays inside .codemonkeys.
    res = W(slug="../../etc/passwd", section="FACTS", content="nope")
    assert res.startswith("Updated")
    for fn in os.listdir(_CMDIR):
        full = os.path.realpath(os.path.join(_CMDIR, fn))
        assert full.startswith(os.path.realpath(_CMDIR) + os.sep)
        assert "etc" not in os.path.dirname(full).replace(_CMDIR, "")
    # the jail helper itself rejects a slug that would escape the dir
    with pytest.raises(ValueError):
        server._jail_blackboard("../escape")


def test_size_cap_rejects_oversized_write():
    huge = "x" * (server._BB_MAX + 100)
    assert W(slug="demo", section="FACTS", content=huge).startswith("ERROR")


def test_context_injection_round_trips():
    assert server._blackboard_context() == ""        # none yet
    W(slug="proj", section="FACTS", content="alpha fact")
    ctx = server._blackboard_context()
    assert "blackboard-proj.md" in ctx and "alpha fact" in ctx
    assert "survives session resets" in ctx


def test_plan_mode_write_invariant():
    # The non-negotiable: plan mode may READ the blackboard but NEVER write it;
    # its only write affordance remains save_spec.
    assert "blackboard_read" in server.PLAN_TOOLS
    assert "blackboard_write" not in server.PLAN_TOOLS
    assert "blackboard_write" not in server._PLAN_READONLY_TOOLS
    assert "blackboard_read" in server._PLAN_READONLY_TOOLS
    # default/auto get both
    assert "blackboard_read" in server.FULL_TOOLS
    assert "blackboard_write" in server.FULL_TOOLS


def test_commander_prompt_includes_blackboard():
    W(slug="proj", section="DECISIONS", content="ship it")
    session = {"id": "s1"}
    prompt = server._commander_system(session)
    assert "PERSISTENT BLACKBOARD" in prompt and "ship it" in prompt


# ---- multi-AGENT half (subagent grants) -------------------------------------

def _agent(tools):
    return {"name": "x", "description": "", "tools": tools, "model": "haiku",
            "model_tier": "", "body": ""}


def test_every_subagent_gets_blackboard_read():
    # even a read-only recon unit shares the board
    tools = server.corps_tools(_agent(["Read", "Grep", "Glob"]))
    assert "blackboard_read" in tools
    assert "blackboard_write" not in tools          # not write-capable


def test_write_capable_subagents_get_blackboard_write():
    for fm in (["Read", "Edit"], ["Read", "Write"], ["Read", "Edit", "Write"]):
        tools = server.corps_tools(_agent(fm))
        assert "blackboard_write" in tools, fm
    # Bash alone is not an Edit/Write grant
    assert "blackboard_write" not in server.corps_tools(_agent(["Read", "Bash"]))


def test_plan_mode_strips_subagent_blackboard_write():
    # The read-only-end-to-end invariant: even a write-capable subagent spawned
    # from a plan-mode session keeps blackboard_read but loses blackboard_write
    # (and every other write affordance). Drives the live filter run_subagent uses.
    tools = server.corps_tools(_agent(["Read", "Edit", "Write", "Bash"]))
    filtered = server._plan_filter_subagent_tools(tools)
    assert "blackboard_read" in filtered
    for forbidden in ("blackboard_write", "write_file", "edit_file",
                      "apply_patch", "bash", "save_spec"):
        assert forbidden not in filtered, forbidden
    # fail-safe, not fail-open: an empty grant list degrades to read-only tools
    assert set(server._plan_filter_subagent_tools([])) == set(server._PLAN_READONLY_TOOLS)


def test_concurrent_appends_lose_nothing():
    import threading
    n = 16
    threads = [threading.Thread(
        target=W, kwargs=dict(slug="race", section="FACTS", content=f"fact-{i}"))
        for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    out = R("race")
    for i in range(n):
        assert f"fact-{i}" in out, f"lost update fact-{i}"
