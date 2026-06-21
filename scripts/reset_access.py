#!/usr/bin/env python3
"""Lockout recovery — run on the server (fly ssh console -a <app>).

Usage:
  python scripts/reset_access.py list
  python scripts/reset_access.py reset-mfa <username>   # prints new otpauth URI
"""
import json
import os
import sys

import pyotp


def _default_users_file() -> str:
    if os.environ.get("USERS_FILE"):
        return os.environ["USERS_FILE"]
    fly = "/data/users.json"
    if os.path.isfile(fly):
        return fly
    local = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "users.json")
    return local if os.path.isfile(local) else fly


USERS_FILE = _default_users_file()


def load():
    with open(USERS_FILE) as f:
        return json.load(f)


def save(users):
    with open(USERS_FILE, "w") as f:
        json.dump(users, f, indent=2)


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "list"
    users = load()
    if cmd == "list":
        for u, d in users.items():
            mfa = "mfa" if d.get("mfa_secret") else "no-mfa"
            print(f"{u}  role={d['role']}  {mfa}")
    elif cmd == "reset-mfa":
        u = sys.argv[2]
        users[u]["mfa_secret"] = pyotp.random_base32()
        users[u].pop("pin_hash", None)
        users[u].pop("salt", None)
        save(users)
        print(pyotp.TOTP(users[u]["mfa_secret"]).provisioning_uri(
            name=u, issuer_name="CodeMonkeys"))
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
