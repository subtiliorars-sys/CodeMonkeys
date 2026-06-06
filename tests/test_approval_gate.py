"""Tests for the risky-command approval gate (server._is_risky).

Regression coverage for the shell-quoting bypass: the gate used to match
RISKY_PATTERNS against the *raw* command string, so quoted/escaped forms of a
risky verb (e.g. `git "push"`) executed without ever tripping the human
approval gate. See SECURITY.md hard-rule #4 ("approval gates stay on").

Run: ./.venv/bin/python -m pytest tests/ -q
"""
import os
import sys
import tempfile

# Import the single-file backend without requiring a deploy-shaped env, and
# point its data/workspace dirs at a throwaway temp dir so importing the module
# never writes into the repo.
os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(prefix="cm_test_"))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import server  # noqa: E402


# --- Plainly risky commands are still gated (no regression) ------------------

PLAIN_RISKY = [
    "git push",
    "git push origin main",
    "fly deploy",
    "flyctl deploy --app codemonkeys",   # real binary name, previously missed
    "rm -rf /data",
    "git reset --hard HEAD~1",
    "git clean -fdx",
    "gh repo delete subtiliorars-sys/CodeMonkeys",
    "sudo apt install x",
    "echo hi && git push",               # risky verb inside a compound command
]


# --- Quoted / escaped forms that used to bypass the gate ---------------------

QUOTED_BYPASS = [
    'git "push"',
    "git 'push'",
    "g''it push",
    'g""it push',
    'git\\ push',
    '"git" push',
    "git   'push'   origin",
    'rm -rf "/data"',
    "git reset '--hard' HEAD",
]


# --- Ordinary commands must NOT be gated (no false positives) ----------------

SAFE = [
    "ls -la",
    "git status",
    "git pull --rebase",          # pull, not push
    "git commit -m 'wip'",
    "python -m pytest",
    "grep -rn push src/",         # mentions 'push' but is not `git push`
    "cat fly.toml",               # 'fly' as a filename, not the `fly` command
    "echo hello world",
]


def test_plain_risky_commands_are_gated():
    for cmd in PLAIN_RISKY:
        assert server._is_risky(cmd), f"should be gated: {cmd!r}"


def test_quoted_bypass_is_now_gated():
    for cmd in QUOTED_BYPASS:
        assert server._is_risky(cmd), f"quoting bypass not caught: {cmd!r}"


def test_safe_commands_are_not_gated():
    for cmd in SAFE:
        assert not server._is_risky(cmd), f"false positive (over-gated): {cmd!r}"


def test_unparseable_command_fails_closed():
    # Unbalanced quote: cannot reason about it -> must gate, never wave through.
    assert server._is_risky('git push "unterminated')


def test_quoted_literals_with_risky_text_are_conservatively_gated():
    # shlex normalization strips quotes, so a risky phrase living inside a string
    # literal (e.g. `echo "...rm -rf..."`) also trips the gate. This is
    # intentional fail-safe behavior: an extra approval prompt on a benign echo
    # is acceptable; silently missing a real `rm -rf` is not.
    assert server._is_risky("echo 'cleanup tip: never run rm -rf /'")
