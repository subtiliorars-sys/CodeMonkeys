"""Tests for local TOTP QR generation (server.totp_qr_data_uri + endpoints).

Regression: the frontend used to POST the otpauth:// URI (which embeds the TOTP
shared secret) to api.qrserver.com, leaking the second factor to a third party.
The QR is now generated locally as an SVG data URI. These tests assert the
helper produces a self-contained data URI with no external reference, and that
the register/account-setup responses carry `mfa_qr`.

Run: ./.venv/bin/python -m pytest tests/ -q
"""
import os
import sys
import tempfile

os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(prefix="cm_test_"))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

import server  # noqa: E402

OTPAUTH = "otpauth://totp/CodeMonkeys:alice?secret=JBSWY3DPEHPK3PXP&issuer=CodeMonkeys"


def _reset_users():
    server.save_users({})


def test_qr_is_local_self_contained_svg_data_uri():
    uri = server.totp_qr_data_uri(OTPAUTH)
    assert uri.startswith("data:image/svg+xml;base64,")
    # decode and confirm it is an SVG with NO external/network reference
    import base64
    svg = base64.b64decode(uri.split(",", 1)[1]).decode(errors="replace").lower()
    assert "<svg" in svg
    # no external fetch: no QR CDN, no embedded <image>, no http(s) href/src.
    # (an xmlns="http://www.w3.org/..." namespace declaration is an identifier,
    # not a network reference, so we check for real fetch attributes instead.)
    assert "qrserver" not in svg
    assert "<image" not in svg
    assert 'href="http' not in svg and "href='http" not in svg
    assert "src=" not in svg


def test_qr_empty_for_empty_input():
    assert server.totp_qr_data_uri("") == ""


def test_secret_value_does_not_appear_verbatim_in_data_uri():
    # the QR encodes the URI as modules, not as readable text — the base32 secret
    # must not be sittable as plaintext in the emitted SVG
    uri = server.totp_qr_data_uri(OTPAUTH)
    import base64
    svg = base64.b64decode(uri.split(",", 1)[1]).decode(errors="replace")
    assert "JBSWY3DPEHPK3PXP" not in svg


def test_register_response_includes_local_qr(monkeypatch):
    _reset_users()
    monkeypatch.setattr(server, "OPEN_ENROLLMENT", False)
    out = server.register(server.RegisterRequest(username="owner1", pin="4321"))
    try:
        assert out["mfa_otpauth_uri"].startswith("otpauth://")
        # when segno is present the response carries a local data-URI QR
        if server.segno is not None:
            assert out["mfa_qr"].startswith("data:image/svg+xml;base64,")
        else:
            assert out["mfa_qr"] == ""
    finally:
        _reset_users()


def test_no_external_qr_url_in_frontend():
    # belt-and-suspenders: the shipped JS must not reference the external QR CDN
    here = os.path.dirname(os.path.abspath(__file__))
    appjs = os.path.join(os.path.dirname(here), "static", "forge", "app.js")
    with open(appjs, "r", encoding="utf-8") as f:
        js = f.read()
    assert "qrserver.com" not in js
    assert "d.mfa_qr" in js
