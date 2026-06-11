"""CI gate: the Steady Ground crisis exit must ship on EVERY frontend.

The "Steady Ground" button + modal is the always-present, offline-safe crisis
resource (988, Crisis Text Line, findahelpline, 911). It is deliberately
self-contained in each frontend's index.html — no JS bundle, no network, no
auth — so it works even when the app doesn't. This test makes its presence a
hard deploy gate for BOTH brand frontends: a redesign that drops it fails CI.
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Every surface a signed-in user can land on its OWN must carry the crisis exit —
# not just the app shells. The index.html is the main entry point;
# swarm.html is a standalone page opened in its own tab, so without its own button
# it would be a dead end.
FRONTENDS = [
    "static/forge/index.html",
    "static/forge/swarm.html",
]

# Each of these must literally appear in every listed frontend surface above.
REQUIRED = [
    "steady-ground-btn",        # the always-visible button
    "steady-ground-modal",      # the modal it opens
    'href="tel:988"',           # Suicide & Crisis Lifeline
    "sms:741741",               # Crisis Text Line
    "findahelpline.com",        # international fallback
    'href="tel:911"',           # immediate danger
]


def test_steady_ground_checks():
    failed = False
    for path in FRONTENDS:
        full_path = os.path.join(_ROOT, path)
        assert os.path.isfile(full_path), f"{path} is missing"
        html = open(full_path, encoding="utf-8").read()
        missing = [r for r in REQUIRED if r not in html]
        assert not missing, f"{path} is missing crisis elements: {missing}"
