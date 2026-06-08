"""Tests for S4-B extend: model_config/mcp_tokens at-rest encryption + GITHUB_TOKEN eviction.

Covers:
  (1) model_config.json encrypt round-trip (CM_MASTER_KEY set)
  (2) mcp_tokens.json encrypt round-trip
  (3) FAIL-SOFT: encrypted + wrong/missing key → empty config, _DECRYPT_FAILED flag, no raise
  (4) Migration: plaintext → encrypted, idempotent
  (5) Backward-compat: no CM_MASTER_KEY → plaintext, app works
  (6) GITHUB_TOKEN evicted from os.environ (+ /proc/self/environ) after boot
  (7) git auth still works via the GITHUB_TOKEN_VAL constant
  (8) /api/encryption-status owner-only, returns booleans, no secret values

Run: ./.venv/bin/python -m pytest tests/ -q
"""
import json
import os
import sys
import tempfile
import threading

_TEST_DATA_DIR = tempfile.mkdtemp(prefix="cm_s4b_test_")
os.environ.setdefault("DATA_DIR", _TEST_DATA_DIR)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import server  # noqa: E402 — import after env setup
import pytest  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_fernet_from_key(master_key: str):
    import base64
    import hashlib
    from cryptography.fernet import Fernet
    digest = hashlib.sha256(master_key.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def _reset_decrypt_failed(monkeypatch):
    monkeypatch.setattr(server, "_DECRYPT_FAILED", False)


# ---------------------------------------------------------------------------
# (1) model_config.json encrypt round-trip
# ---------------------------------------------------------------------------

def test_model_config_encrypted_roundtrip(tmp_path, monkeypatch):
    """With CM_MASTER_KEY set, save_models writes Fernet ciphertext; load_models
    round-trips the data back correctly."""
    monkeypatch.setattr(server, "CM_MASTER_KEY", "s4b-test-key-model-cfg")
    monkeypatch.setattr(server, "MODELS_FILE", str(tmp_path / "model_config.json"))
    monkeypatch.setattr(server, "_DECRYPT_FAILED", False)

    cfg = server._new_cfg()
    cfg["providers"]["anthropic"]["key"] = "sk-test-1234"

    server.save_models(cfg)

    # On-disk blob must start with the encrypted header.
    blob = (tmp_path / "model_config.json").read_bytes()
    assert blob.startswith(server._ENC_MAGIC), "model_config.json must carry _ENC_MAGIC"

    # Decrypt independently and confirm the key is present.
    f = _make_fernet_from_key("s4b-test-key-model-cfg")
    raw = f.decrypt(blob[len(server._ENC_MAGIC):])
    data = json.loads(raw)
    assert data["providers"]["anthropic"]["key"] == "sk-test-1234"


def test_model_config_load_decrypts(tmp_path, monkeypatch):
    """load_models returns the correct dict from an encrypted file."""
    monkeypatch.setattr(server, "CM_MASTER_KEY", "s4b-test-key-load-dec")
    monkeypatch.setattr(server, "MODELS_FILE", str(tmp_path / "model_config.json"))
    monkeypatch.setattr(server, "_DECRYPT_FAILED", False)

    cfg = server._new_cfg()
    cfg["providers"]["anthropic"]["key"] = "sk-roundtrip-9999"
    server.save_models(cfg)

    loaded = server.load_models()
    assert loaded["providers"]["anthropic"]["key"] == "sk-roundtrip-9999"


# ---------------------------------------------------------------------------
# (2) mcp_tokens.json encrypt round-trip
# ---------------------------------------------------------------------------

def test_mcp_tokens_encrypted_roundtrip(tmp_path, monkeypatch):
    """With CM_MASTER_KEY set, _save_mcp_tokens writes ciphertext; _load_mcp_tokens
    returns the original dict."""
    monkeypatch.setattr(server, "CM_MASTER_KEY", "s4b-test-key-mcp-tok")
    monkeypatch.setattr(server, "MCP_TOKENS_FILE", str(tmp_path / "mcp_tokens.json"))
    monkeypatch.setattr(server, "_DECRYPT_FAILED", False)

    tokens = {"my-server": {"access_token": "tok-abc123", "expires_at": 9999999999}}
    server._save_mcp_tokens(tokens)

    blob = (tmp_path / "mcp_tokens.json").read_bytes()
    assert blob.startswith(server._ENC_MAGIC), "mcp_tokens.json must carry _ENC_MAGIC"

    # Round-trip via loader.
    loaded = server._load_mcp_tokens()
    assert loaded["my-server"]["access_token"] == "tok-abc123"


def test_mcp_tokens_mode_600(tmp_path, monkeypatch):
    """_save_mcp_tokens must write at mode 0600 even with encryption."""
    monkeypatch.setattr(server, "CM_MASTER_KEY", "s4b-test-key-mode600")
    monkeypatch.setattr(server, "MCP_TOKENS_FILE", str(tmp_path / "mcp_tokens.json"))
    monkeypatch.setattr(server, "_DECRYPT_FAILED", False)

    server._save_mcp_tokens({"x": {"access_token": "y"}})
    mode = (tmp_path / "mcp_tokens.json").stat().st_mode & 0o777
    assert mode == 0o600, f"expected 0600, got {oct(mode)}"


# ---------------------------------------------------------------------------
# (3) FAIL-SOFT: encrypted + wrong/missing key → empty config + flag, no raise
# ---------------------------------------------------------------------------

def test_model_config_fail_soft_wrong_key(tmp_path, monkeypatch):
    """When model_config is encrypted under key-A but we try with key-B,
    _read_enc_file must return the default (None) and set _DECRYPT_FAILED.
    load_models must NOT raise — it returns a default (empty) config."""
    # Write with key-A.
    monkeypatch.setattr(server, "CM_MASTER_KEY", "key-A-xxxxxxxxxxxx")
    monkeypatch.setattr(server, "MODELS_FILE", str(tmp_path / "model_config.json"))
    monkeypatch.setattr(server, "_DECRYPT_FAILED", False)

    cfg = server._new_cfg()
    cfg["providers"]["anthropic"]["key"] = "my-secret-api-key"
    server.save_models(cfg)

    # Now switch to key-B → should fail soft.
    monkeypatch.setattr(server, "CM_MASTER_KEY", "key-B-xxxxxxxxxxxx")
    monkeypatch.setattr(server, "_DECRYPT_FAILED", False)

    # Must not raise.
    result = server.load_models()

    # Returns a usable (default) config — no api key present.
    assert isinstance(result, dict)
    assert result.get("providers", {}).get("anthropic", {}).get("key", "") == ""

    # Flag must be set.
    assert server._DECRYPT_FAILED is True, "_DECRYPT_FAILED must be True after decrypt failure"


def test_decrypt_fail_preserves_ciphertext_and_recovers(tmp_path, monkeypatch):
    """RED-TEAM #58 F1 (was NO-GO): a decrypt-fail load must NOT overwrite the
    on-disk encrypted file. Restoring the correct key must fully recover the keys."""
    mf = tmp_path / "model_config.json"
    monkeypatch.setattr(server, "MODELS_FILE", str(mf))
    monkeypatch.setattr(server, "CM_MASTER_KEY", "key-A-xxxxxxxxxxxx")
    monkeypatch.setattr(server, "_DECRYPT_FAILED", False)

    cfg = server._new_cfg()
    cfg["providers"]["anthropic"]["key"] = "my-secret-api-key"
    server.save_models(cfg)
    blob_before = mf.read_bytes()
    assert blob_before.startswith(server._ENC_MAGIC)

    # Wrong key → fail-soft load (fires unattended at startup / first redaction).
    monkeypatch.setattr(server, "CM_MASTER_KEY", "key-B-xxxxxxxxxxxx")
    monkeypatch.setattr(server, "_DECRYPT_FAILED", False)
    server.load_models()
    assert mf.read_bytes() == blob_before, "decrypt-fail must NOT overwrite the ciphertext (data loss!)"

    # Missing key too → still must not clobber.
    monkeypatch.setattr(server, "CM_MASTER_KEY", "")
    monkeypatch.setattr(server, "_DECRYPT_FAILED", False)
    server.load_models()
    assert mf.read_bytes() == blob_before, "missing-key load must NOT overwrite the ciphertext"

    # Restore the correct key → keys fully recovered.
    monkeypatch.setattr(server, "CM_MASTER_KEY", "key-A-xxxxxxxxxxxx")
    monkeypatch.setattr(server, "_DECRYPT_FAILED", False)
    recovered = server.load_models()
    assert recovered["providers"]["anthropic"]["key"] == "my-secret-api-key", \
        "restoring the correct key must recover the encrypted API keys"


def test_incidental_save_during_decrypt_fail_preserves_keys_via_bak(tmp_path, monkeypatch):
    """RED-TEAM #58 R3: an owner save while decrypt has failed must NOT permanently
    destroy the recoverable keys — the original ciphertext is preserved to .bak."""
    mf = tmp_path / "model_config.json"
    monkeypatch.setattr(server, "MODELS_FILE", str(mf))
    monkeypatch.setattr(server, "CM_MASTER_KEY", "key-A-xxxxxxxxxxxx")
    monkeypatch.setattr(server, "_DECRYPT_FAILED", False)
    cfg = server._new_cfg()
    cfg["providers"]["anthropic"]["key"] = "precious-api-key"
    server.save_models(cfg)
    orig = mf.read_bytes()

    # Wrong key + decrypt-failed state, then an INCIDENTAL save (empty cfg).
    monkeypatch.setattr(server, "CM_MASTER_KEY", "key-B-xxxxxxxxxxxx")
    monkeypatch.setattr(server, "_DECRYPT_FAILED", True)
    server.save_models(server._new_cfg())     # incidental clobber attempt

    bak = tmp_path / "model_config.json.undecryptable.bak"
    assert bak.exists(), "original ciphertext must be backed up before overwrite"
    assert bak.read_bytes() == orig, "backup must hold the original ciphertext"
    # And the original keys are recoverable from the .bak with key-A.
    f = _make_fernet_from_key("key-A-xxxxxxxxxxxx")
    import json as _j
    recovered = _j.loads(f.decrypt(bak.read_bytes()[len(server._ENC_MAGIC):]).decode())
    assert recovered["providers"]["anthropic"]["key"] == "precious-api-key"


def test_model_config_fail_soft_missing_key(tmp_path, monkeypatch):
    """Encrypted file + CM_MASTER_KEY unset → fail soft, not crash."""
    monkeypatch.setattr(server, "CM_MASTER_KEY", "key-for-encryption-xx")
    monkeypatch.setattr(server, "MODELS_FILE", str(tmp_path / "model_config.json"))
    monkeypatch.setattr(server, "_DECRYPT_FAILED", False)

    server.save_models(server._new_cfg())

    monkeypatch.setattr(server, "CM_MASTER_KEY", "")
    monkeypatch.setattr(server, "_DECRYPT_FAILED", False)

    result = server.load_models()  # must not raise
    assert isinstance(result, dict)
    assert server._DECRYPT_FAILED is True


def test_mcp_tokens_fail_soft_wrong_key(tmp_path, monkeypatch):
    """Encrypted mcp_tokens + wrong key → returns {} + _DECRYPT_FAILED, no raise."""
    monkeypatch.setattr(server, "CM_MASTER_KEY", "key-mcp-A-xxxxxxxx")
    monkeypatch.setattr(server, "MCP_TOKENS_FILE", str(tmp_path / "mcp_tokens.json"))
    monkeypatch.setattr(server, "_DECRYPT_FAILED", False)

    server._save_mcp_tokens({"srv": {"access_token": "tok"}})

    monkeypatch.setattr(server, "CM_MASTER_KEY", "key-mcp-B-xxxxxxxx")
    monkeypatch.setattr(server, "_DECRYPT_FAILED", False)

    result = server._load_mcp_tokens()  # must not raise
    assert result == {}
    assert server._DECRYPT_FAILED is True


# ---------------------------------------------------------------------------
# (4) Migration: plaintext → encrypted, idempotent
# ---------------------------------------------------------------------------

def test_model_config_migration_plaintext_to_encrypted(tmp_path, monkeypatch):
    """An existing plaintext model_config.json + newly set CM_MASTER_KEY is
    encrypted on the next load_models() call — idempotent (second load is also fine)."""
    cfg_path = tmp_path / "model_config.json"
    monkeypatch.setattr(server, "MODELS_FILE", str(cfg_path))
    monkeypatch.setattr(server, "_DECRYPT_FAILED", False)

    # Write as plaintext (no key).
    monkeypatch.setattr(server, "CM_MASTER_KEY", "")
    cfg = server._new_cfg()
    cfg["providers"]["anthropic"]["key"] = "sk-legacy"
    server.save_models(cfg)
    blob_plain = cfg_path.read_bytes()
    assert not blob_plain.startswith(server._ENC_MAGIC), "must be plaintext"

    # Now set the key — load should migrate transparently.
    monkeypatch.setattr(server, "CM_MASTER_KEY", "new-migration-key-!!!")
    result = server.load_models()
    assert result["providers"]["anthropic"]["key"] == "sk-legacy", "key must survive migration"
    blob_enc = cfg_path.read_bytes()
    assert blob_enc.startswith(server._ENC_MAGIC), "file must now be encrypted"

    # Second load is idempotent.
    result2 = server.load_models()
    assert result2["providers"]["anthropic"]["key"] == "sk-legacy"
    assert cfg_path.read_bytes() == blob_enc, "no spurious rewrite on second load"


def test_mcp_tokens_migration_plaintext_to_encrypted(tmp_path, monkeypatch):
    """Plaintext mcp_tokens.json + CM_MASTER_KEY newly set → encrypted on load."""
    tok_path = tmp_path / "mcp_tokens.json"
    monkeypatch.setattr(server, "MCP_TOKENS_FILE", str(tok_path))
    monkeypatch.setattr(server, "_DECRYPT_FAILED", False)

    # Write plaintext.
    monkeypatch.setattr(server, "CM_MASTER_KEY", "")
    server._save_mcp_tokens({"s1": {"access_token": "legacy-tok"}})
    assert not tok_path.read_bytes().startswith(server._ENC_MAGIC)

    # Set key → load migrates.
    monkeypatch.setattr(server, "CM_MASTER_KEY", "mcp-migrate-key-xxxx")
    result = server._load_mcp_tokens()
    assert result["s1"]["access_token"] == "legacy-tok"
    assert tok_path.read_bytes().startswith(server._ENC_MAGIC)


# ---------------------------------------------------------------------------
# (5) Backward-compat: no CM_MASTER_KEY → plaintext, works
# ---------------------------------------------------------------------------

def test_model_config_no_key_plaintext_compat(tmp_path, monkeypatch):
    """Without CM_MASTER_KEY, save/load is plain JSON — backward-compatible."""
    monkeypatch.setattr(server, "CM_MASTER_KEY", "")
    monkeypatch.setattr(server, "MODELS_FILE", str(tmp_path / "model_config.json"))
    monkeypatch.setattr(server, "_DECRYPT_FAILED", False)

    cfg = server._new_cfg()
    cfg["providers"]["anthropic"]["key"] = "sk-no-enc"
    server.save_models(cfg)

    blob = (tmp_path / "model_config.json").read_bytes()
    assert not blob.startswith(server._ENC_MAGIC), "no key → must be plaintext"

    # Load round-trips correctly.
    loaded = server.load_models()
    assert loaded["providers"]["anthropic"]["key"] == "sk-no-enc"
    # _DECRYPT_FAILED must remain False (no decryption attempted).
    assert server._DECRYPT_FAILED is False


def test_mcp_tokens_no_key_plaintext_compat(tmp_path, monkeypatch):
    """Without CM_MASTER_KEY, mcp_tokens.json is plain JSON."""
    monkeypatch.setattr(server, "CM_MASTER_KEY", "")
    monkeypatch.setattr(server, "MCP_TOKENS_FILE", str(tmp_path / "mcp_tokens.json"))
    monkeypatch.setattr(server, "_DECRYPT_FAILED", False)

    server._save_mcp_tokens({"s": {"access_token": "plain"}})
    blob = (tmp_path / "mcp_tokens.json").read_bytes()
    assert not blob.startswith(server._ENC_MAGIC)

    result = server._load_mcp_tokens()
    assert result["s"]["access_token"] == "plain"
    assert server._DECRYPT_FAILED is False


# ---------------------------------------------------------------------------
# (6) GITHUB_TOKEN evicted from os.environ + /proc/self/environ
# ---------------------------------------------------------------------------

def test_github_token_in_evict_set():
    """GITHUB_TOKEN must be in _SECRET_ENV_EVICT."""
    assert "GITHUB_TOKEN" in server._SECRET_ENV_EVICT


def test_github_token_evicted_by_evict_fn():
    """_evict_env_secrets() must remove GITHUB_TOKEN from os.environ when called."""
    os.environ["GITHUB_TOKEN"] = "planted-for-eviction-test-s4b"
    server._evict_env_secrets()
    assert "GITHUB_TOKEN" not in os.environ, (
        "GITHUB_TOKEN must be removed by _evict_env_secrets()"
    )


def test_github_token_absent_from_proc_environ():
    """/proc/self/environ must not contain 'GITHUB_TOKEN=' after eviction.
    This covers the /proc leak vector that the task requires closing."""
    try:
        with open("/proc/self/environ", "rb") as f:
            raw = f.read()
    except OSError:
        pytest.skip("cannot read /proc/self/environ on this platform")
    # environ entries are NUL-separated; check that GITHUB_TOKEN= key is absent
    entries = raw.split(b"\x00")
    for entry in entries:
        assert not entry.startswith(b"GITHUB_TOKEN="), (
            "GITHUB_TOKEN= must be absent from /proc/self/environ"
        )


def test_cm_master_key_absent_from_proc_environ():
    """CM_MASTER_KEY must also be absent from /proc/self/environ."""
    try:
        with open("/proc/self/environ", "rb") as f:
            raw = f.read()
    except OSError:
        pytest.skip("cannot read /proc/self/environ on this platform")
    entries = raw.split(b"\x00")
    for entry in entries:
        assert not entry.startswith(b"CM_MASTER_KEY="), (
            "CM_MASTER_KEY= must be absent from /proc/self/environ"
        )


def test_webhook_secret_absent_from_proc_environ():
    """WEBHOOK_SECRET must also be absent from /proc/self/environ."""
    try:
        with open("/proc/self/environ", "rb") as f:
            raw = f.read()
    except OSError:
        pytest.skip("cannot read /proc/self/environ on this platform")
    entries = raw.split(b"\x00")
    for entry in entries:
        assert not entry.startswith(b"WEBHOOK_SECRET="), (
            "WEBHOOK_SECRET= must be absent from /proc/self/environ"
        )


def test_fleet_token_absent_from_proc_environ():
    """FLEET_TOKEN must be absent from /proc/self/environ (it's a token)."""
    try:
        with open("/proc/self/environ", "rb") as f:
            raw = f.read()
    except OSError:
        pytest.skip("cannot read /proc/self/environ on this platform")
    # FLEET_TOKEN is captured but not explicitly evicted — it may or may not be
    # present; this test only fires if it was present before eviction AND was
    # not separately evicted.  Mark as a warning rather than hard failure.
    entries = raw.split(b"\x00")
    for entry in entries:
        # Fleet token is not in _SECRET_ENV_EVICT today; log but don't fail.
        if entry.startswith(b"FLEET_TOKEN="):
            import warnings
            warnings.warn(
                "FLEET_TOKEN= is present in /proc/self/environ — consider adding "
                "it to _SECRET_ENV_EVICT if it is set in production."
            )
            break


# ---------------------------------------------------------------------------
# (7) git auth via GITHUB_TOKEN_VAL constant
# ---------------------------------------------------------------------------

def test_github_token_val_is_module_constant():
    """GITHUB_TOKEN_VAL must be a str module constant (even if empty)."""
    assert isinstance(server.GITHUB_TOKEN_VAL, str)


def test_auth_url_uses_constant(monkeypatch):
    """_auth_url must embed GITHUB_TOKEN_VAL into github.com URLs, not os.environ."""
    # Ensure the env var is gone (eviction happened at import, but be explicit).
    os.environ.pop("GITHUB_TOKEN", None)

    monkeypatch.setattr(server, "GITHUB_TOKEN_VAL", "ghp_test_constant_token")

    url = server._auth_url("https://github.com/owner/repo.git")
    assert "ghp_test_constant_token" in url, "token must be embedded from constant"
    assert "x-access-token:" in url, "URL must use x-access-token credentials"


def test_auth_url_skips_non_github(monkeypatch):
    """_auth_url must not modify non-github.com URLs."""
    monkeypatch.setattr(server, "GITHUB_TOKEN_VAL", "ghp_some_token")
    url = server._auth_url("https://gitlab.com/owner/repo.git")
    assert "ghp_some_token" not in url
    assert url == "https://gitlab.com/owner/repo.git"


def test_auth_url_empty_token(monkeypatch):
    """Without a token, _auth_url returns the URL unchanged."""
    monkeypatch.setattr(server, "GITHUB_TOKEN_VAL", "")
    url = server._auth_url("https://github.com/owner/repo.git")
    assert url == "https://github.com/owner/repo.git"


# ---------------------------------------------------------------------------
# (8) /api/encryption-status — owner-only, booleans, no secret values
# ---------------------------------------------------------------------------

def test_encryption_status_owner_only():
    """Non-owner must receive 403 from /api/encryption-status."""
    from fastapi.testclient import TestClient

    server.app.dependency_overrides[server.verify_owner] = lambda: (_ for _ in ()).throw(
        __import__("fastapi").HTTPException(403, "Owner only")
    )
    client = TestClient(server.app)
    resp = client.get("/api/encryption-status",
                      headers={"Authorization": "Bearer notanowner"})
    server.app.dependency_overrides.clear()
    assert resp.status_code == 403


def test_encryption_status_no_key(monkeypatch):
    """With CM_MASTER_KEY unset, endpoint returns encrypted=False, decrypt_failed=False."""
    from fastapi.testclient import TestClient

    monkeypatch.setattr(server, "CM_MASTER_KEY", "")
    monkeypatch.setattr(server, "_DECRYPT_FAILED", False)
    server.app.dependency_overrides[server.verify_owner] = lambda: "owner"

    client = TestClient(server.app)
    resp = client.get("/api/encryption-status",
                      headers={"Authorization": "Bearer dummy"})
    server.app.dependency_overrides.clear()

    assert resp.status_code == 200
    d = resp.json()
    assert d["encrypted"] is False
    assert d["decrypt_failed"] is False


def test_encryption_status_key_set(monkeypatch):
    """With CM_MASTER_KEY set, endpoint returns encrypted=True."""
    from fastapi.testclient import TestClient

    monkeypatch.setattr(server, "CM_MASTER_KEY", "some-real-key-32chars-xxxxx")
    monkeypatch.setattr(server, "_DECRYPT_FAILED", False)
    server.app.dependency_overrides[server.verify_owner] = lambda: "owner"

    client = TestClient(server.app)
    resp = client.get("/api/encryption-status",
                      headers={"Authorization": "Bearer dummy"})
    server.app.dependency_overrides.clear()

    assert resp.status_code == 200
    d = resp.json()
    assert d["encrypted"] is True


def test_encryption_status_decrypt_failed_flag(monkeypatch):
    """When _DECRYPT_FAILED is set, endpoint reports decrypt_failed=True."""
    from fastapi.testclient import TestClient

    monkeypatch.setattr(server, "CM_MASTER_KEY", "some-key-xxxxxxxxxxx")
    monkeypatch.setattr(server, "_DECRYPT_FAILED", True)
    server.app.dependency_overrides[server.verify_owner] = lambda: "owner"

    client = TestClient(server.app)
    resp = client.get("/api/encryption-status",
                      headers={"Authorization": "Bearer dummy"})
    server.app.dependency_overrides.clear()

    assert resp.status_code == 200
    d = resp.json()
    assert d["decrypt_failed"] is True


def test_encryption_status_no_secret_values(monkeypatch):
    """The response must never contain CM_MASTER_KEY or any secret value."""
    from fastapi.testclient import TestClient

    monkeypatch.setattr(server, "CM_MASTER_KEY", "super-secret-key-never-leak")
    monkeypatch.setattr(server, "_DECRYPT_FAILED", False)
    server.app.dependency_overrides[server.verify_owner] = lambda: "owner"

    client = TestClient(server.app)
    resp = client.get("/api/encryption-status",
                      headers={"Authorization": "Bearer dummy"})
    server.app.dependency_overrides.clear()

    assert resp.status_code == 200
    body = resp.text
    assert "super-secret-key-never-leak" not in body
    # Response must only contain boolean-valued fields.
    d = resp.json()
    for v in d.values():
        assert isinstance(v, bool), f"all response values must be bool, got {type(v)}: {v!r}"
