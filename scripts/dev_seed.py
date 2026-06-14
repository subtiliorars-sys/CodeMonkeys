#!/usr/bin/env python3
"""LOCAL DEV ONLY — seed a throwaway audit/login account into a dev users file.

Usage:
  USERS_FILE=./data/audit/users.json python scripts/dev_seed.py
  USERS_FILE=./data/audit/users.json python scripts/dev_seed.py --code
"""
import hashlib
import json
import os
import secrets
import sys

DEV_DEFAULT = "./data/audit/users.json"
USERS_FILE = os.environ.get("USERS_FILE", DEV_DEFAULT)
USERNAME = os.environ.get("DEV_USER", "ui-audit")
PIN = os.environ.get("DEV_PIN", "9999")
ROLE = os.environ.get("DEV_ROLE", "Owner")


def _prod_guard() -> None:
    resolved = os.path.abspath(USERS_FILE)
    is_dev = resolved.endswith("audit/users.json") or resolved.endswith("dev_users.json")
    if os.environ.get("FLY_APP_NAME"):
        sys.exit("REFUSING: FLY_APP_NAME set — dev_seed is local-only")
    if "/data/users.json" in resolved.replace("\\", "/"):
        sys.exit("REFUSING: production users path")
    if not is_dev and "--i-understand-dev-only" not in sys.argv:
        sys.exit(f"REFUSING: USERS_FILE={resolved} — use audit/dev path or --i-understand-dev-only")


def hash_pin(pin: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", pin.encode(), bytes.fromhex(salt), 200_000).hex()


def main() -> None:
    _prod_guard()
    try:
        import pyotp
    except ImportError:
        sys.exit("pip install pyotp (or activate CodeMonkeys .venv)")

    code_only = "--code" in sys.argv
    os.makedirs(os.path.dirname(os.path.abspath(USERS_FILE)) or ".", exist_ok=True)
    users = {}
    if os.path.exists(USERS_FILE):
        with open(USERS_FILE, encoding="utf-8") as f:
            users = json.load(f)

    entry = users.get(USERNAME, {})
    secret = entry.get("mfa_secret") if isinstance(entry, dict) else None
    if code_only:
        if not secret:
            sys.exit(f"No '{USERNAME}' in {USERS_FILE} — run without --code first")
    else:
        secret = secret or pyotp.random_base32()
        salt = (entry.get("salt") if isinstance(entry, dict) else None) or secrets.token_hex(16)
        users[USERNAME] = {
            "pin_hash": hash_pin(PIN, salt),
            "salt": salt,
            "role": ROLE,
            "mfa_secret": secret,
            "created": entry.get("created", 0) or int(__import__("time").time()),
        }
        with open(USERS_FILE, "w", encoding="utf-8") as f:
            json.dump(users, f, indent=2)
        print(f"Seeded '{USERNAME}' → {USERS_FILE}  PIN={PIN} role={ROLE}")

    print(f"MFA: {pyotp.TOTP(secret).now()}")


if __name__ == "__main__":
    main()
