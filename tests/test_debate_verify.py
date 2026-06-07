"""Tests for the debate-verify gate (IDEATION #7).

Auto mode skips the human approval gate; before a RISKY command runs in auto
mode, three heterogeneous verifiers (intent/safety/security lenses) each try
to refute it — majority refute = BLOCKED. Fail closed on verifier errors,
garbled verdicts, or a missing provider. default/plan keep the human gate.

Run: ./.venv/bin/python -m pytest tests/ -q
"""
import os
import sys
import tempfile
import threading

os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(prefix="cm_test_"))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

import server  # noqa: E402

_PROVIDER = {"kind": "openai", "model": "test-model",
             "input_cost_per_m": 0.0, "output_cost_per_m": 0.0}


def _session(mode="auto"):
    return {"id": "dbv-test", "mode": mode, "lock": threading.Lock(),
            "events": [], "history": [{"role": "user", "text": "do the task"}],
            "spent_usd": 0.0}


def _resp(text):
    return {"text": text, "in_tokens": 10, "out_tokens": 5, "tool_calls": []}


@pytest.fixture
def provider_ok(monkeypatch):
    monkeypatch.setattr(server, "load_models", lambda: {})
    monkeypatch.setattr(server, "_verifier_providers",
                        lambda cfg: [dict(_PROVIDER) for _ in server._DEBATE_LENSES])


def _script_verdicts(monkeypatch, verdicts):
    """call_model returns the scripted verdicts in order; a verdict that is an
    Exception instance is raised instead."""
    it = iter(verdicts)

    def fake_call_model(provider, system, history, tools, max_tokens=8192):
        v = next(it)
        if isinstance(v, Exception):
            raise v
        return _resp(v)
    monkeypatch.setattr(server, "call_model", fake_call_model)


def test_unanimous_allow_passes(provider_ok, monkeypatch):
    _script_verdicts(monkeypatch, ["ALLOW: in scope", "ALLOW: necessary",
                                   "ALLOW: no secret path"])
    allowed, summary = server._debate_verify(_session(), "git push origin main")
    assert allowed
    assert "in scope" in summary


def test_majority_refute_blocks(provider_ok, monkeypatch):
    _script_verdicts(monkeypatch, ["REFUTE: goal drift", "ALLOW: fine",
                                   "REFUTE: exfil risk"])
    allowed, summary = server._debate_verify(_session(), "git push --force")
    assert not allowed
    assert "goal drift" in summary and "exfil risk" in summary


def test_single_refute_still_passes(provider_ok, monkeypatch):
    _script_verdicts(monkeypatch, ["ALLOW: ok", "REFUTE: uneasy", "ALLOW: ok"])
    allowed, _ = server._debate_verify(_session(), "fly deploy")
    assert allowed


def test_verifier_error_counts_as_refute(provider_ok, monkeypatch):
    # 2 verifier crashes + 1 allow = majority refute → blocked (fail closed)
    _script_verdicts(monkeypatch, [RuntimeError("api down"),
                                   RuntimeError("api down"), "ALLOW: ok"])
    allowed, summary = server._debate_verify(_session(), "rm -rf build")
    assert not allowed
    assert "verifier error" in summary


def test_garbled_verdict_counts_as_refute(provider_ok, monkeypatch):
    _script_verdicts(monkeypatch, ["sure, go ahead!", "", "ALLOW: ok"])
    allowed, _ = server._debate_verify(_session(), "sudo reboot")
    assert not allowed


def test_no_provider_fails_closed(monkeypatch):
    monkeypatch.setattr(server, "load_models", lambda: {})
    monkeypatch.setattr(server, "_verifier_providers", lambda cfg: [])
    allowed, summary = server._debate_verify(_session(), "git push")
    assert not allowed
    assert "blocked" in summary


# ---- verifier provider selection (decorrelation) ----------------------------

def _cfg(*outs):
    return {"providers": {f"p{i}": {"key": "k", "label": f"p{i}", "kind": "openai",
                                    "model": f"m{i}", "out": o,
                                    "base_url": "http://x"}
                          for i, o in enumerate(outs)}}


def test_distinct_providers_when_three_keyed():
    provs = server._verifier_providers(_cfg(5, 1, 3))
    assert len(provs) == len(server._DEBATE_LENSES)
    # cheapest-first, and all three distinct models — a decorrelated panel
    assert [p["model"] for p in provs] == ["m1", "m2", "m0"]
    assert len({p["model"] for p in provs}) == 3


def test_fewer_providers_repeats_cheapest_to_fill():
    provs = server._verifier_providers(_cfg(9, 2))   # only 2 keyed
    assert len(provs) == 3
    # cheapest (m1, out=2) reused to fill the third slot
    assert provs[0]["model"] == "m1" and provs[2]["model"] == "m1"


def test_no_keyed_providers_returns_empty():
    assert server._verifier_providers({"providers": {}}) == []


def test_emits_debate_verify_event(provider_ok, monkeypatch):
    _script_verdicts(monkeypatch, ["REFUTE: a", "REFUTE: b", "REFUTE: c"])
    s = _session()
    server._debate_verify(s, "git push")
    evts = [e for e in s["events"] if e["type"] == "debate_verify"]
    assert len(evts) == 1 and evts[0]["allowed"] is False and evts[0]["refutes"] == 3


# ---- t_bash integration ------------------------------------------------------

def test_auto_risky_blocked_command_never_executes(provider_ok, monkeypatch):
    _script_verdicts(monkeypatch, ["REFUTE: no", "REFUTE: no", "ALLOW: ok"])

    def boom(*a, **kw):
        raise AssertionError("blocked command must not reach subprocess.run")
    monkeypatch.setattr(server.subprocess, "run", boom)
    out = server.t_bash({"command": "git push origin main"}, session=_session())
    assert out.startswith("BLOCKED by debate-verify")


def test_auto_risky_allowed_command_executes(provider_ok, monkeypatch):
    _script_verdicts(monkeypatch, ["ALLOW: ok", "ALLOW: ok", "ALLOW: ok"])
    ran = {}

    class R:
        returncode = 0
        stdout = "pushed"
        stderr = ""

    def fake_run(*a, **kw):
        ran["yes"] = True
        return R()
    monkeypatch.setattr(server.subprocess, "run", fake_run)
    out = server.t_bash({"command": "git push origin main"}, session=_session())
    assert ran.get("yes") and "pushed" in out


def test_auto_nonrisky_skips_debate_entirely(provider_ok, monkeypatch):
    def no_call(*a, **kw):
        raise AssertionError("non-risky auto command must not invoke verifiers")
    monkeypatch.setattr(server, "call_model", no_call)

    class R:
        returncode = 0
        stdout = "ok"
        stderr = ""
    monkeypatch.setattr(server.subprocess, "run", lambda *a, **kw: R())
    out = server.t_bash({"command": "ls -la"}, session=_session())
    assert "ok" in out


def test_default_mode_still_uses_human_gate(monkeypatch):
    asked = {}

    def fake_approval(session, cmd):
        asked["cmd"] = cmd
        return False
    monkeypatch.setattr(server, "request_approval", fake_approval)

    def no_call(*a, **kw):
        raise AssertionError("default mode must use the human gate, not debate")
    monkeypatch.setattr(server, "call_model", no_call)
    out = server.t_bash({"command": "git push"}, session=_session(mode="default"))
    assert out.startswith("DENIED") and asked["cmd"] == "git push"
