"""Bash/terminal subprocess env hardening (Standing list S4, part A).

The `bash` tool and owner terminal previously ran with `env=dict(os.environ)`,
so a command could exfiltrate a secret env var with `printenv X | base64` — a
transform that slips past the output redactor's literal-substring match. We now
strip secret-named vars from the subprocess env, while preserving PATH/HOME/etc.

Run: ./.venv/bin/python -m pytest tests/ -q
"""
import os
import sys
import tempfile

os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(prefix="cm_test_"))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

import server  # noqa: E402
from conftest import BASH_AVAILABLE  # noqa: E402

# The `bash` tool shells out to `bash -c`; on a bare Windows host bash is at best
# the non-functional WSL relay shim, so skip the end-to-end bash assertions
# there. The env-scrubbing logic itself is still unit-tested above.
requires_bash = pytest.mark.skipif(
    not BASH_AVAILABLE, reason="bash -c not functional on this host")


# ---- the env-name matcher ----------------------------------------------------

@pytest.mark.parametrize("name", [
    "GITHUB_TOKEN", "WEBHOOK_SECRET", "FLEET_TOKEN", "GEMINI_API_KEY",
    "ANTHROPIC_API_KEY", "DB_PASSWORD", "MY_PAT", "PAT", "AUTH_TOKEN",
    "SOME_CREDENTIAL", "X_ACCESSKEY", "FOO_PASSPHRASE",
    # red-team: glued (no separator) names must also be caught
    "PGPASSWORD", "CLIENTSECRET", "GITHUBTOKEN", "APISECRET",
    # red-team: creds-in-URL / connection-string vars
    "DATABASE_URL", "REDIS_URL", "MONGO_URI", "SENTRY_DSN", "MY_COOKIE",
])
def test_secret_names_are_dropped(name):
    assert server._env_name_is_secret(name)


@pytest.mark.parametrize("name", [
    "PATH", "EXECPATH", "HOME", "LANG", "PWD", "SHELL", "TERM", "USER",
    "MONKEY_BUSINESS", "FLY_APP_NAME", "HOSTNAME", "LD_LIBRARY_PATH",
])
def test_essential_names_are_kept(name):
    # critically PATH must survive (it contains the substring 'PAT')
    assert name in server._ENV_KEEP or not server._env_name_is_secret(name)


def test_ssh_auth_sock_kept_despite_matching(monkeypatch):
    # red-team R3: SSH_AUTH_SOCK matches AUTH but is a socket path, not a secret —
    # the safelist must keep it so ssh-agent git keeps working
    assert server._env_name_is_secret("SSH_AUTH_SOCK")      # it DOES match
    monkeypatch.setenv("SSH_AUTH_SOCK", "/tmp/ssh-agent.sock")
    assert server._subprocess_env().get("SSH_AUTH_SOCK") == "/tmp/ssh-agent.sock"


def test_pgpassword_actually_scrubbed_from_env(monkeypatch):
    monkeypatch.setenv("PGPASSWORD", "hunter2value")
    monkeypatch.setenv("DATABASE_URL", "postgres://u:p@host/db")
    env = server._subprocess_env()
    assert "PGPASSWORD" not in env and "DATABASE_URL" not in env


def test_subprocess_env_keeps_path_drops_secrets(monkeypatch):
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    monkeypatch.setenv("MY_SECRET_KEY", "shhh-value-123")
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_xxxxxxxx")
    monkeypatch.setenv("MY_PUBLIC_VAR", "hello")
    env = server._subprocess_env()
    assert env.get("PATH") == "/usr/bin:/bin"
    assert env.get("MY_PUBLIC_VAR") == "hello"
    assert "MY_SECRET_KEY" not in env
    assert "GITHUB_TOKEN" not in env


# ---- end-to-end: the bash tool can't exfiltrate a secret via transform --------

@requires_bash
def test_bash_cannot_read_secret_env_even_with_transform(monkeypatch):
    # base64 of the value evades the literal-substring redactor; the env scrub is
    # what actually stops it. Value chosen to have no secret-ish name collision.
    monkeypatch.setenv("MY_SECRET_KEY", "abc123xyz")
    import base64
    b64 = base64.b64encode(b"abc123xyz").decode()
    out = server.t_bash({"command": "printenv MY_SECRET_KEY | base64"})
    assert "abc123xyz" not in out
    assert b64 not in out                 # the var simply isn't in the env


@requires_bash
def test_bash_still_sees_nonsecret_env(monkeypatch):
    monkeypatch.setenv("MY_PUBLIC_VAR", "publicvalue42")
    out = server.t_bash({"command": "printenv MY_PUBLIC_VAR"})
    assert "publicvalue42" in out


@requires_bash
def test_bash_path_intact(monkeypatch):
    # commands must still resolve — proves we didn't nuke PATH
    out = server.t_bash({"command": "echo hello-from-bash"})
    assert "hello-from-bash" in out
