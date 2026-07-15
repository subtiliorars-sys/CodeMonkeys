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

