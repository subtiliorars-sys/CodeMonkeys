"""Tests for Wave-3 W12 — remove-passkey list + delete endpoints.

Run: ./.venv/bin/python -m pytest tests/ -q
"""
import base64
import os
import sys
import tempfile

os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(prefix="cm_test_"))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from fido2.webauthn import AttestedCredentialData  # noqa: E402
from fido2.cose import ES256  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import ec  # noqa: E402

import server  # noqa: E402

client = TestClient(server.app)


def _cred_blob(cred_id: bytes) -> str:
    priv = ec.generate_private_key(ec.SECP256R1())
    cose = ES256.from_cryptography_key(priv.public_key())
    acd = AttestedCredentialData.create(
        aaguid=b"\x00" * 16, credential_id=cred_id, public_key=cose)
    return base64.b64encode(bytes(acd)).decode()


@pytest.fixture
def user_with_passkeys(monkeypatch):
    """A user 'alice' with two passkeys, authed as herself."""
    blob_a = _cred_blob(b"AAAA1111")
    blob_b = _cred_blob(b"BBBB2222")
    users = {"alice": {"webauthn_credentials": [blob_a, blob_b]}}
    monkeypatch.setattr(server, "load_users", lambda: users)
    monkeypatch.setattr(server, "save_users", lambda u: users.update(u))
    server.app.dependency_overrides[server.verify_token] = lambda: "alice"
    yield users, b"AAAA1111".hex(), b"BBBB2222".hex()
    server.app.dependency_overrides.pop(server.verify_token, None)


def test_credential_id_hex_roundtrip():
    blob = _cred_blob(b"ZZZZ9999")
    assert server._credential_id_hex(blob) == b"ZZZZ9999".hex()
    assert server._credential_id_hex("not-base64!!") is None


def test_list_credentials(user_with_passkeys):
    _, id_a, id_b = user_with_passkeys
    r = client.get("/api/webauthn/credentials")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 2
    ids = {c["id"] for c in body["credentials"]}
    assert ids == {id_a, id_b}
    # no key material leaks — only id/index/short
    for c in body["credentials"]:
        assert set(c) == {"id", "index", "short"}


def test_delete_one_passkey(user_with_passkeys):
    users, id_a, id_b = user_with_passkeys
    r = client.delete(f"/api/webauthn/credentials/{id_a}")
    assert r.status_code == 200
    assert r.json()["remaining"] == 1
    remaining_ids = [server._credential_id_hex(b)
                     for b in users["alice"]["webauthn_credentials"]]
    assert remaining_ids == [id_b]      # only the other one survives


def test_delete_unknown_id_404(user_with_passkeys):
    assert client.delete("/api/webauthn/credentials/deadbeef").status_code == 404


def test_delete_all_passkeys_is_allowed(user_with_passkeys):
    # PIN+TOTP remain, so removing every passkey must not be blocked
    users, id_a, id_b = user_with_passkeys
    client.delete(f"/api/webauthn/credentials/{id_a}")
    client.delete(f"/api/webauthn/credentials/{id_b}")
    assert users["alice"]["webauthn_credentials"] == []


def test_endpoints_require_auth():
    assert client.get("/api/webauthn/credentials").status_code in (401, 403)
    assert client.delete("/api/webauthn/credentials/x").status_code in (401, 403)
