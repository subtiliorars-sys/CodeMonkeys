"""Shared test setup, loaded by pytest before any test module imports `server`.

`server` reads several gate env vars at import time. FLEET_TOKEN in particular
decides whether the /fleet-status.json route is registered at all (red-team R4:
no route when unset). Set it here so the route exists regardless of which test
module triggers the one-time `import server` first; per-test auth/disabled
behavior is still exercised via monkeypatch.
"""
import os
import tempfile

os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(prefix="cm_test_"))
os.environ.setdefault("FLEET_TOKEN", "fleet-test-token-123456")   # ≥16 chars
