"""Commercial billing — CodeMonkeys sold by OmniTender ($1/mo).

Fail-closed when BILLING_ENABLED is false. Webhook signature verified without
the stripe SDK. Free-pack seeding is idempotent.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time

import pytest

import server


@pytest.fixture(autouse=True)
def clean_billing(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(server, "USERS_FILE", str(tmp_path / "users.json"))
    monkeypatch.setattr(server, "SUBSCRIPTIONS_FILE", str(tmp_path / "subscriptions.json"))
    monkeypatch.setattr(server, "MODELS_FILE", str(tmp_path / "model_config.json"))
    monkeypatch.setattr(server, "BILLING_ENABLED", False)
    monkeypatch.setattr(server, "STRIPE_SECRET_KEY", "")
    monkeypatch.setattr(server, "STRIPE_WEBHOOK_SECRET", "")
    monkeypatch.setattr(server, "STRIPE_PRICE_ID", "")
    server.save_users({})
    yield


def test_billing_status_public_when_disabled():
    info = server.billing_status()
    assert info["enabled"] is False
    assert info["product"] == "CodeMonkeys"
    assert "OmniTender" in info["seller"]
    assert info["price_usd"] == 1.0
    assert info["interval"] == "month"


def test_checkout_fail_closed_when_disabled():
    with pytest.raises(server.HTTPException) as ei:
        server.billing_checkout(
            server.CheckoutRequest(username="player1"),
            request=None,
        )
    assert ei.value.status_code == 503


def test_openrouter_free_callable_without_key():
    p = {
        "kind": "openai",
        "base_url": "https://openrouter.ai/api/v1",
        "key": "",
        "model": "qwen/qwen3-coder:free",
        "models": ["qwen/qwen3-coder:free"],
    }
    assert server._callable_provider(p) is True
    p["model"] = "anthropic/claude-sonnet-4.6"
    assert server._callable_provider(p) is False


def test_ensure_free_pack_ready_seeds_models():
    r = server.ensure_free_pack_ready()
    assert r["ok"] is True
    cfg = server.load_models()
    or_ = cfg["providers"]["openrouter"]
    for mid in server._FREE_PACK_MODELS:
        assert mid in or_["models"]
    assert cfg["selected"] == "auto"
    assert or_["model"].endswith(":free") or or_.get("key")


def test_activate_subscriber_creates_member_and_seeds(monkeypatch):
    monkeypatch.setattr(server, "BILLING_ENABLED", True)
    server._activate_subscriber(
        "arcade", customer_id="cus_x", subscription_id="sub_x", status="active"
    )
    users = server.load_users()
    assert users["arcade"]["role"] == "Member"
    assert users["arcade"]["must_reset"] is True
    assert users["arcade"]["subscription_status"] == "active"
    assert users["arcade"]["stripe_subscription_id"] == "sub_x"
    subs = server._load_subscriptions()
    assert subs["sub_x"]["username"] == "arcade"
    cfg = server.load_models()
    assert "qwen/qwen3-coder:free" in cfg["providers"]["openrouter"]["models"]


def test_verify_user_requires_active_sub_when_billing_on(monkeypatch):
    monkeypatch.setattr(server, "BILLING_ENABLED", True)
    server.save_users({
        "broke": {
            "role": "Member", "must_reset": False, "mfa_secret": "x",
            "subscription_status": "canceled", "created": 1,
        },
        "boss": {
            "role": "Owner", "must_reset": False, "mfa_secret": "y", "created": 0,
        },
    })
    # Patch verify_token dependency by calling verify_user with username directly
    # after faking token parse — exercise the gate body via Depends pattern:
    with pytest.raises(server.HTTPException) as ei:
        server.verify_user(username="broke")
    assert ei.value.status_code == 402
    assert server.verify_user(username="boss") == "boss"


def test_stripe_webhook_signature_roundtrip(monkeypatch):
    secret = "whsec_test_secret"
    monkeypatch.setattr(server, "STRIPE_WEBHOOK_SECRET", secret)
    monkeypatch.setattr(server, "BILLING_ENABLED", True)
    body = json.dumps({
        "type": "checkout.session.completed",
        "data": {"object": {
            "client_reference_id": "newbie",
            "customer": "cus_1",
            "subscription": "sub_1",
            "metadata": {"username": "newbie"},
        }},
    }).encode()
    ts = str(int(time.time()))
    signed = f"{ts}.".encode() + body
    sig = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    header = f"t={ts},v1={sig}"
    event = server._verify_stripe_webhook(body, header)
    assert event["type"] == "checkout.session.completed"
    # Bad signature
    with pytest.raises(server.HTTPException) as ei:
        server._verify_stripe_webhook(body, f"t={ts},v1=deadbeef")
    assert ei.value.status_code == 400
