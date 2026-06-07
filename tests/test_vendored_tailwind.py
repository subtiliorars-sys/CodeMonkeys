"""Wave 4 #3 (phase 1) — vendored-Tailwind wiring checks.

These assert the pipeline is wired (config present, index.html references the
vendored CSS, build artifact gitignored). The CSS *compilation* is verified by
the CI `css` job (dev host has no Node); the *rendering* needs a human browser
check before the CDN is removed + CSP tightened (phase 2).

Run: ./.venv/bin/python -m pytest tests/ -q
"""
import os
import sys
import tempfile

os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(prefix="cm_test_"))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import server  # noqa: E402

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(rel):
    with open(os.path.join(_ROOT, rel)) as f:
        return f.read()


def test_tailwind_config_present_and_scans_frontend():
    cfg = _read("tailwind.config.js")
    assert "./static/forge/*.html" in cfg and "./static/forge/*.js" in cfg


def test_input_css_has_tailwind_directives():
    css = _read("static/forge/tailwind.input.css")
    assert "@tailwind base" in css and "@tailwind utilities" in css


def test_index_links_vendored_css():
    html = _read("static/forge/index.html")
    assert '/static/forge/tailwind.css' in html


def test_dockerfile_builds_tailwind():
    df = _read("Dockerfile")
    assert "tailwindcss" in df and "tailwind.css" in df


def test_built_css_is_gitignored():
    gi = _read(".gitignore")
    assert "static/forge/tailwind.css" in gi
