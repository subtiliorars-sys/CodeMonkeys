"""Shared test setup, loaded by pytest before any test module imports `server`.

`server` reads several gate env vars at import time. FLEET_TOKEN in particular
decides whether the /fleet-status.json route is registered at all (red-team R4:
no route when unset). Set it here so the route exists regardless of which test
module triggers the one-time `import server` first; per-test auth/disabled
behavior is still exercised via monkeypatch.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import warnings

import pytest

os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(prefix="cm_test_"))
os.environ.setdefault("FLEET_TOKEN", "fleet-test-token-123456")   # ≥16 chars

# M-4 cloud-egress consent (issue #67): the default in production is "explicit"
# — an absent record blocks egress. `test_egress_consent.py` exercises that gate
# explicitly (it deletes EGRESS_CONSENT_MODE and sets it per-case). For every
# *other* test the consent gate is orthogonal, so default it to "byok-implied"
# here so unrelated tests (call_model / debate-verify / etc.) don't all fail on
# a missing consent record. The gate's own behavior is still fully covered.
os.environ.setdefault("EGRESS_CONSENT_MODE", "byok-implied")


def bash_is_functional() -> bool:
    """True when `bash -c` can actually run (Git Bash / WSL / native).

    On a bare Windows host `bash.exe` may exist only as the WSL relay shim,
    which fails with 'execvpe(/bin/bash) failed' because no distro is
    installed. Tests that drive `bash -c` are skipped in that case rather than
    reporting false failures."""
    exe = shutil.which("bash")
    if not exe:
        return False
    try:
        r = subprocess.run([exe, "-c", "echo ok"],
                           capture_output=True, timeout=10)
    except Exception:
        return False
    return r.returncode == 0 and b"ok" in r.stdout


BASH_AVAILABLE = bash_is_functional()
IS_WINDOWS = sys.platform == "win32"

# Re-export for test modules that need them.
pytest_helpers = {"BASH_AVAILABLE": BASH_AVAILABLE, "IS_WINDOWS": IS_WINDOWS}


@pytest.fixture(autouse=True)
def _join_background_threads():
    """CI issue #212: join every real `threading.Thread` a test starts before
    the test returns, so none can outlive it.

    server.py's route handlers (e.g. `/api/specs/{slug}/execute`,
    `/api/sessions/{sid}/message`, `/api/sessions/{sid}/resume`) dispatch
    `run_session_message` -> `agent_loop` on a fire-and-forget daemon thread
    to answer the HTTP request immediately. A test that hits one of these
    routes without neutralizing the thread (some tests substitute their own
    inert Thread stand-in, which is unaffected by this fixture since it isn't
    a `threading.Thread` instance) would otherwise return to pytest while
    that thread keeps running in the background, mutating shared
    module-level state in server.py (`_DECRYPT_FAILED`, model config,
    provider cooldown dicts, ...) while a LATER, unrelated test is running.
    That produced a different, unpredictable test failure on each CI run.

    This fixture wraps `threading.Thread.start` for the duration of each
    test, records every thread actually started, and joins them all (with a
    timeout, so a genuinely hung thread doesn't wedge the whole suite) at
    teardown -- before the next test can begin.
    """
    started = []
    real_start = threading.Thread.start

    def _tracking_start(self, *args, **kwargs):
        started.append(self)
        return real_start(self, *args, **kwargs)

    threading.Thread.start = _tracking_start
    try:
        yield
    finally:
        threading.Thread.start = real_start
        for t in started:
            if t is threading.main_thread() or not t.is_alive():
                continue
            t.join(timeout=5)
            if t.is_alive():
                warnings.warn(
                    f"background thread {t.name!r} was still running 5s "
                    "after its test finished; it may leak shared server.py "
                    "state into a later test (see issue #212)",
                    stacklevel=1,
                )

