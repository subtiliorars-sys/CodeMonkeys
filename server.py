#!/usr/bin/env python3
"""CodeMonkeys — self-hosted, multi-provider AI coding console.

Single-file FastAPI backend:
  - Auth: username + PIN (PBKDF2) + mandatory per-user TOTP, HMAC session tokens
  - Models: any OpenAI-compatible endpoint (Gemini, OpenRouter, DeepSeek, ...)
            plus native Anthropic — configured at runtime, keys on /data
  - Agent loop: Claude Code-style tool loop, workspace-jailed
  - Subagents: Daystrom agent corps (corps/agents/*.md) with tool allowlists,
               tier-routed models, and spawn caps
  - Cost governor: per-provider tier (t0..t3) + per-session USD budget
  - Safety: human approval gate for push/deploy/destructive commands

Storage: JSON files under DATA_DIR (no database). Frontend: static/forge/.
"""

import base64
import fnmatch
import hashlib
import hmac
import json
import os
import re
import secrets
import subprocess
import threading
import time
import urllib.parse
import uuid

import pyotp
import requests
from enum import Enum
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

try:
    import anthropic as anthropic_sdk
except ImportError:  # anthropic provider disabled until installed
    anthropic_sdk = None

try:
    from fido2.server import Fido2Server
    from fido2.webauthn import (AttestedCredentialData,
                                PublicKeyCredentialRpEntity,
                                PublicKeyCredentialUserEntity)
except ImportError:  # biometric login disabled until installed
    Fido2Server = None

# ----------------------------------------------------------------- config

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get("DATA_DIR", os.path.join(BASE_DIR, "data"))
USERS_FILE = os.environ.get("USERS_FILE", os.path.join(DATA_DIR, "users.json"))
MODELS_FILE = os.path.join(DATA_DIR, "model_config.json")
MCP_CONFIG_FILE = os.path.join(DATA_DIR, "mcp_config.json")
SESSIONS_DIR = os.path.join(DATA_DIR, "sessions")
WORKSPACE_DIR = os.environ.get("WORKSPACE_DIR", os.path.join(DATA_DIR, "workspace"))
SECRET_FILE = os.path.join(DATA_DIR, "session_secret.key")
CORPS_DIR = os.path.join(BASE_DIR, "corps", "agents")

SESSION_TTL = 7 * 24 * 3600
OPEN_ENROLLMENT = os.environ.get("OPEN_ENROLLMENT", "false").lower() == "true"
SESSION_BUDGET_USD = float(os.environ.get("SESSION_BUDGET_USD", "1.00"))
MAX_TURNS = int(os.environ.get("MAX_TURNS", "60"))
SUBAGENT_MAX_TURNS = int(os.environ.get("SUBAGENT_MAX_TURNS", "25"))
MAX_SUBAGENTS = 8          # Campaign cap from CORPS_COMMANDER.md
BASH_TIMEOUT = 180
OUTPUT_CAP = 16000         # chars of tool output fed back to the model
READ_CAP = 24000
APPROVAL_TIMEOUT = 3600
MCP_MAX_TOOLS = 128        # cap merged MCP tools/session — hostile server can't blow context/cost
MCP_DESC_CAP = 1024        # cap each MCP tool description fed to the model

# Commands that pause the loop for human approval (CodeMonkeys design rule:
# no silent pushes/deploys/destruction; git reset --hard has bitten us before)
RISKY_PATTERNS = [
    r"\bgit\s+push\b",
    r"\bfly\s+\w+",
    r"\brm\s+-rf\b",
    r"\bgit\s+reset\s+--hard\b",
    r"\bgit\s+clean\b",
    r"\bgh\s+repo\s+delete\b",
    r"\bsudo\b",
]

for _d in (DATA_DIR, SESSIONS_DIR, WORKSPACE_DIR):
    os.makedirs(_d, exist_ok=True)

app = FastAPI(title="CodeMonkeys")

# ----------------------------------------------------------------- storage

_USERS_LOCK = threading.Lock()
_MODELS_LOCK = threading.Lock()
_MCP_LOCK = threading.Lock()
_SESSIONS_LOCK = threading.Lock()


def _load_json(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def _save_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, path)


# ----------------------------------------------------------------- auth

def _session_secret():
    if not os.path.exists(SECRET_FILE):
        with open(SECRET_FILE, "wb") as f:
            f.write(secrets.token_bytes(32))
        os.chmod(SECRET_FILE, 0o600)
    with open(SECRET_FILE, "rb") as f:
        return f.read()


def hash_pin(pin: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", pin.encode(), bytes.fromhex(salt), 200_000
    ).hex()


def load_users():
    return _load_json(USERS_FILE, {})


def save_users(users):
    _save_json(USERS_FILE, users)


def make_token(username: str) -> str:
    payload = base64.urlsafe_b64encode(
        json.dumps({"u": username, "exp": int(time.time()) + SESSION_TTL}).encode()
    ).decode().rstrip("=")
    sig = hmac.new(_session_secret(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{sig}"


def parse_token(token: str):
    try:
        payload, sig = token.rsplit(".", 1)
        expect = hmac.new(_session_secret(), payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expect):
            return None
        pad = "=" * (-len(payload) % 4)
        data = json.loads(base64.urlsafe_b64decode(payload + pad))
        if data.get("exp", 0) < time.time():
            return None
        return data.get("u")
    except Exception:
        return None


def verify_token(authorization: str = Header(default="")):
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing token")
    username = parse_token(authorization[7:])
    if not username or username not in load_users():
        raise HTTPException(401, "Invalid or expired token")
    return username


def verify_owner(username: str = Depends(verify_token)):
    if load_users().get(username, {}).get("role") != "Owner":
        raise HTTPException(403, "Owner only")
    return username


def verify_user(username: str = Depends(verify_token)):
    """Any active (non-pending) account — Owner or invited Member."""
    user = load_users().get(username, {})
    if user.get("must_reset"):
        raise HTTPException(403, "Finish first-time setup (new PIN + authenticator) first")
    if user.get("role") not in ("Owner", "Member"):
        raise HTTPException(403, "Not authorized")
    return username


class RegisterRequest(BaseModel):
    username: str
    pin: str
    mfa_code: str = ""


class LoginRequest(BaseModel):
    username: str
    pin: str
    mfa_code: str


@app.post("/api/register")
def register(req: RegisterRequest):
    username = req.username.strip()
    if not re.fullmatch(r"[A-Za-z0-9_.-]{2,32}", username):
        raise HTTPException(400, "Bad username")
    if len(req.pin) < 4:
        raise HTTPException(400, "PIN must be at least 4 digits")
    with _USERS_LOCK:
        users = load_users()
        if username in users:
            raise HTTPException(409, "Username taken")
        if users and not OPEN_ENROLLMENT:
            raise HTTPException(403, "Enrollment closed")
        role = "Owner" if not users else "Member"
        salt = secrets.token_hex(16)
        mfa_secret = pyotp.random_base32()
        users[username] = {
            "pin_hash": hash_pin(req.pin, salt),
            "salt": salt,
            "role": role,
            "mfa_secret": mfa_secret,
            "created": int(time.time()),
        }
        save_users(users)
    uri = pyotp.TOTP(mfa_secret).provisioning_uri(name=username, issuer_name="CodeMonkeys")
    return {
        "token": make_token(username),
        "username": username,
        "role": role,
        "mfa_otpauth_uri": uri,
    }


@app.post("/api/login")
def login(req: LoginRequest):
    users = load_users()
    uname = req.username.strip()
    user = users.get(uname)
    if not user or not hmac.compare_digest(
        user["pin_hash"], hash_pin(req.pin, user["salt"])
    ):
        raise HTTPException(401, "Bad credentials")
    # invited accounts log in with the starter PIN only (no authenticator yet),
    # then are forced through first-time setup
    if user.get("must_reset"):
        return {"token": make_token(uname), "username": uname,
                "role": user["role"], "must_reset": True}
    if not pyotp.TOTP(user["mfa_secret"]).verify(req.mfa_code, valid_window=1):
        raise HTTPException(401, "Bad MFA code")
    return {"token": make_token(uname), "username": uname, "role": user["role"]}


@app.get("/api/me")
def me(username: str = Depends(verify_token)):
    u = load_users()[username]
    return {"username": username, "role": u["role"], "must_reset": bool(u.get("must_reset"))}


# ------------------------------------------------- invitations (Owner -> dev)

def _gen_starter_pin():
    return "".join(secrets.choice("0123456789") for _ in range(6))


class InviteRequest(BaseModel):
    username: str = ""             # optional; auto-generated if blank


@app.post("/api/invite")
def invite(req: InviteRequest, _: str = Depends(verify_owner)):
    with _USERS_LOCK:
        users = load_users()
        uname = req.username.strip() or ("dev-" + secrets.token_hex(3))
        if not re.fullmatch(r"[A-Za-z0-9_.-]{2,32}", uname):
            raise HTTPException(400, "Bad username")
        if uname in users:
            raise HTTPException(409, "Username already exists")
        pin = _gen_starter_pin()
        salt = secrets.token_hex(16)
        users[uname] = {
            "pin_hash": hash_pin(pin, salt), "salt": salt, "role": "Member",
            "mfa_secret": "", "must_reset": True, "created": int(time.time()),
        }
        save_users(users)
    # the starter PIN is returned ONCE, in cleartext, for the owner to hand over
    return {"username": uname, "starter_pin": pin}


@app.get("/api/users")
def users_list(_: str = Depends(verify_owner)):
    return {"users": sorted([
        {"username": u, "role": d.get("role"),
         "pending": bool(d.get("must_reset")),
         "has_mfa": bool(d.get("mfa_secret")), "created": d.get("created", 0)}
        for u, d in load_users().items()], key=lambda x: x["created"])}


@app.delete("/api/users/{uname}")
def users_delete(uname: str, owner: str = Depends(verify_owner)):
    if uname == owner:
        raise HTTPException(400, "You can't delete your own Owner account")
    with _USERS_LOCK:
        users = load_users()
        if users.get(uname, {}).get("role") == "Owner":
            raise HTTPException(400, "Can't delete an Owner")
        if uname not in users:
            raise HTTPException(404, "No such user")
        del users[uname]
        save_users(users)
    return {"ok": True}


class FirstSetup(BaseModel):
    new_username: str = ""        # optional rename
    new_pin: str


@app.post("/api/account/setup")
def account_setup(req: FirstSetup, username: str = Depends(verify_token)):
    """First-login flow for an invited account: set a new PIN (and optional new
    username), get a fresh authenticator secret to scan."""
    if len(req.new_pin) < 4:
        raise HTTPException(400, "PIN must be at least 4 digits")
    with _USERS_LOCK:
        users = load_users()
        user = users.get(username)
        if not user:
            raise HTTPException(404, "Account not found")
        target = username
        new_name = req.new_username.strip()
        if new_name and new_name != username:
            if not re.fullmatch(r"[A-Za-z0-9_.-]{2,32}", new_name):
                raise HTTPException(400, "Bad username")
            if new_name in users:
                raise HTTPException(409, "Username taken")
            users[new_name] = user
            del users[username]
            target = new_name
        salt = secrets.token_hex(16)
        mfa_secret = pyotp.random_base32()
        user["salt"] = salt
        user["pin_hash"] = hash_pin(req.new_pin, salt)
        user["mfa_secret"] = mfa_secret
        user["must_reset"] = False
        users[target] = user
        save_users(users)
    uri = pyotp.TOTP(mfa_secret).provisioning_uri(name=target, issuer_name="CodeMonkeys")
    return {"token": make_token(target), "username": target,
            "role": load_users()[target]["role"], "mfa_otpauth_uri": uri}


# ------------------------------------------------- biometric / passkey (WebAuthn)
# Same pattern as MeniscusMaximus: python-fido2, AttestedCredentialData stored
# base64 in users.json. Passkey login replaces PIN+TOTP (the authenticator's
# user-verification — fingerprint/face/device PIN — is the second factor).

_webauthn_states = {}
_RP_NAME = "CodeMonkeys"


def _fido_clean(obj):
    """bytes -> base64url, enums -> values, drop Nones — JSON-safe options."""
    if isinstance(obj, bytes):
        return base64.urlsafe_b64encode(obj).decode().rstrip("=")
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, dict):
        return {k: _fido_clean(v) for k, v in obj.items() if v is not None}
    if isinstance(obj, (list, tuple)):
        return [_fido_clean(x) for x in obj]
    return obj


def _fido_server(request: Request):
    if Fido2Server is None:
        raise HTTPException(501, "Biometric login unavailable (fido2 not installed)")
    rp_id = request.url.hostname or "localhost"
    return Fido2Server(PublicKeyCredentialRpEntity(id=rp_id, name=_RP_NAME))


def _user_credentials(user_entry):
    creds = []
    for b64 in user_entry.get("webauthn_credentials", []):
        try:
            creds.append(AttestedCredentialData(base64.b64decode(b64)))
        except Exception:
            pass
    return creds


def _flat_options(data):
    d = _fido_clean(dict(data))
    return d.get("publicKey", d)  # tolerate either wrapped or flat shapes


@app.post("/api/webauthn/register/begin")
def webauthn_register_begin(request: Request, username: str = Depends(verify_token)):
    server = _fido_server(request)
    entity = PublicKeyCredentialUserEntity(
        id=username.encode(), name=username, display_name=username)
    options, state = server.register_begin(
        entity, credentials=_user_credentials(load_users()[username]))
    _webauthn_states[username] = state
    return _flat_options(options)


@app.post("/api/webauthn/register/complete")
def webauthn_register_complete(req: dict, request: Request,
                               username: str = Depends(verify_token)):
    state = _webauthn_states.pop(username, None)
    if state is None:
        raise HTTPException(400, "Registration challenge expired — try again")
    server = _fido_server(request)
    try:
        auth_data = server.register_complete(state, req)
    except Exception as e:
        raise HTTPException(400, f"Biometric registration failed: {e}")
    with _USERS_LOCK:
        users = load_users()
        users[username].setdefault("webauthn_credentials", []).append(
            base64.b64encode(bytes(auth_data.credential_data)).decode())
        save_users(users)
    return {"ok": True, "message": "Biometric credential bound to this account."}


class WebauthnBegin(BaseModel):
    username: str


@app.post("/api/webauthn/login/begin")
def webauthn_login_begin(req: WebauthnBegin, request: Request):
    users = load_users()
    user = users.get(req.username.strip())
    if not user:
        raise HTTPException(404, "User not found")
    creds = _user_credentials(user)
    if not creds:
        raise HTTPException(400, "No passkey on this account — sign in with PIN, "
                                 "then use 'Add passkey' in the sidebar")
    server = _fido_server(request)
    options, state = server.authenticate_begin(creds)
    _webauthn_states[f"login_{req.username.strip()}"] = {
        "state": state, "creds": creds}
    return _flat_options(options)


@app.post("/api/webauthn/login/complete")
def webauthn_login_complete(req: dict, request: Request):
    username = str(req.get("username", "")).strip()
    pending = _webauthn_states.pop(f"login_{username}", None)
    if pending is None:
        raise HTTPException(400, "Login challenge expired — try again")
    server = _fido_server(request)
    response = {k: v for k, v in req.items() if k != "username"}
    try:
        server.authenticate_complete(pending["state"], pending["creds"], response)
    except Exception as e:
        raise HTTPException(401, f"Biometric verification failed: {e}")
    role = load_users()[username]["role"]
    return {"token": make_token(username), "username": username, "role": role}


# ----------------------------------------------------------------- models / providers

# Wayfinder/OpenClaw model: ONE key per provider, pick ANY model from it.
# A provider = an endpoint + a key + the model you've selected + a menu of
# known models you can switch to without re-entering the key. `auto` flags it
# for the cheapest-first cascade. Costs are USD/1M tokens (spend estimates).
GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta/openai"

DEFAULT_PROVIDERS = {
    "gemini": {"label": "Google Gemini", "kind": "openai", "base_url": GEMINI_BASE,
               "key": "", "model": "gemini-2.5-flash",
               "models": ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.0-flash"],
               "in": 0.30, "out": 2.50, "auto": True},
    "openrouter": {"label": "OpenRouter", "kind": "openai",
                   "base_url": "https://openrouter.ai/api/v1", "key": "",
                   "model": "qwen/qwen3-coder:free",
                   "models": ["qwen/qwen3-coder:free", "deepseek/deepseek-r1:free",
                              "openai/gpt-oss-120b:free", "anthropic/claude-sonnet-4.6",
                              "google/gemini-2.5-flash"],
                   "in": 0.0, "out": 0.0, "auto": True},
    "anthropic": {"label": "Anthropic Claude", "kind": "anthropic", "base_url": "",
                  "key": "", "model": "claude-sonnet-4-6",
                  "models": ["claude-haiku-4-5", "claude-sonnet-4-6", "claude-opus-4-8"],
                  "in": 3.0, "out": 15.0, "auto": False},
    "openai": {"label": "OpenAI", "kind": "openai", "base_url": "https://api.openai.com/v1",
               "key": "", "model": "gpt-4o-mini",
               "models": ["gpt-4o-mini", "gpt-4o", "o4-mini"],
               "in": 0.15, "out": 0.60, "auto": False},
    "deepseek": {"label": "DeepSeek", "kind": "openai", "base_url": "https://api.deepseek.com/v1",
                 "key": "", "model": "deepseek-chat",
                 "models": ["deepseek-chat", "deepseek-reasoner"],
                 "in": 0.28, "out": 0.42, "auto": False},
    "xai": {"label": "xAI Grok", "kind": "openai", "base_url": "https://api.x.ai/v1",
            "key": "", "model": "grok-4-fast",
            "models": ["grok-4-fast", "grok-4"], "in": 0.20, "out": 0.50, "auto": False},
}
_GEMINI_BASES = {GEMINI_BASE}


def _new_cfg():
    return {"selected": "auto", "auto_cheapest": True,
            "providers": json.loads(json.dumps(DEFAULT_PROVIDERS))}


def _migrate_old(cfg):
    """Convert the old flat providers-list shape (gemini-flash, gemini-pro, …)
    into one-key-per-provider, preserving any keys already entered."""
    new = _new_cfg()
    old_main = cfg.get("main", "")
    for p in cfg.get("providers", []):
        base, kind = p.get("base_url", ""), p.get("kind", "openai")
        if base in _GEMINI_BASES:
            pid = "gemini"
        elif "openrouter" in base:
            pid = "openrouter"
        elif kind == "anthropic":
            pid = "anthropic"
        elif "openai.com" in base:
            pid = "openai"
        elif "deepseek" in base:
            pid = "deepseek"
        elif "x.ai" in base:
            pid = "xai"
        else:
            pid = p.get("name", "custom")
            new["providers"][pid] = {"label": pid, "kind": kind, "base_url": base,
                                     "key": "", "model": p.get("model", ""),
                                     "models": [p.get("model", "")],
                                     "in": p.get("input_cost_per_m", 0),
                                     "out": p.get("output_cost_per_m", 0), "auto": False}
        prov = new["providers"][pid]
        if p.get("api_key"):
            prov["key"] = p["api_key"]
            prov["auto"] = True
        if p.get("name") == old_main and p.get("model"):
            prov["model"] = p["model"]
            new["selected"] = pid
    return new


def load_models():
    with _MODELS_LOCK:
        cfg = _load_json(MODELS_FILE, None)
        if cfg is None:
            cfg = _new_cfg()
            _save_json(MODELS_FILE, cfg)
            return cfg
        if "providers" in cfg and isinstance(cfg["providers"], list):  # old shape
            cfg = _migrate_old(cfg)
            _save_json(MODELS_FILE, cfg)
        # ensure built-ins exist (so new presets appear without wiping keys)
        for pid, base in DEFAULT_PROVIDERS.items():
            cfg["providers"].setdefault(pid, json.loads(json.dumps(base)))
        return cfg


def save_models(cfg):
    with _MODELS_LOCK:
        _save_json(MODELS_FILE, cfg)


def _resolve(prov):
    """Provider entry -> dict the chat layer consumes."""
    return {"name": prov.get("label", "?"), "kind": prov["kind"],
            "base_url": prov.get("base_url", ""), "model": prov.get("model", ""),
            "api_key": prov.get("key", ""),
            "input_cost_per_m": prov.get("in", 0), "output_cost_per_m": prov.get("out", 0)}


def _usable(cfg):
    """Providers with a key, sorted cheapest-first by selected-model output cost."""
    items = [(pid, p) for pid, p in cfg["providers"].items() if p.get("key")]
    return sorted(items, key=lambda kv: kv[1].get("out", 1e9))


def main_provider(cfg):
    usable = _usable(cfg)
    if not usable:
        return None
    sel = cfg.get("selected", "auto")
    if sel != "auto" and not cfg.get("auto_cheapest"):
        prov = cfg["providers"].get(sel)
        if prov and prov.get("key"):
            return _resolve(prov)
    # auto / auto_cheapest: cheapest provider flagged for the cascade, else cheapest
    auto = [p for pid, p in usable if p.get("auto")]
    return _resolve(auto[0] if auto else usable[0][1])


def provider_for_tier(cfg, tier):
    """Cost governor: order usable providers by cost, pick by tier position."""
    usable = _usable(cfg)
    if not usable:
        return None
    provs = [p for _, p in usable]
    idx = {"t0": 0, "t1": len(provs) // 3, "t2": (2 * len(provs)) // 3,
           "t3": len(provs) - 1}.get(tier, len(provs) // 2)
    return _resolve(provs[min(idx, len(provs) - 1)])


class ProviderUpsert(BaseModel):
    id: str
    label: str = ""
    kind: str = "openai"           # openai | anthropic
    base_url: str = ""
    model: str = ""
    models: list[str] = []
    key: str = ""                  # empty = keep existing key
    input_cost_per_m: float = 0.0
    output_cost_per_m: float = 0.0
    auto: bool = True


class SelectModel(BaseModel):
    id: str                        # provider id, or "auto"


class ModelSettings(BaseModel):
    auto_cheapest: bool


@app.get("/api/models")
def models_get(_: str = Depends(verify_owner)):
    cfg = load_models()
    return {
        "selected": cfg.get("selected", "auto"),
        "auto_cheapest": cfg.get("auto_cheapest", True),
        "providers": [
            {"id": pid, "label": p.get("label", pid), "kind": p["kind"],
             "base_url": p.get("base_url", ""), "model": p.get("model", ""),
             "models": p.get("models", []), "has_key": bool(p.get("key")),
             "in": p.get("in", 0), "out": p.get("out", 0), "auto": p.get("auto", False)}
            for pid, p in cfg["providers"].items()],
    }


@app.post("/api/models")
def models_upsert(req: ProviderUpsert, _: str = Depends(verify_owner)):
    if req.kind not in ("openai", "anthropic"):
        raise HTTPException(400, "kind must be openai or anthropic")
    if req.kind == "openai" and not req.base_url.strip():
        raise HTTPException(400, "base_url is required for OpenAI-compatible providers "
                                 "(e.g. https://openrouter.ai/api/v1)")
    cfg = load_models()
    prov = cfg["providers"].get(req.id, {})
    prov.update({
        "label": req.label or prov.get("label", req.id), "kind": req.kind,
        "base_url": req.base_url, "model": req.model or prov.get("model", ""),
        "models": req.models or prov.get("models", []),
        "in": req.input_cost_per_m, "out": req.output_cost_per_m, "auto": req.auto,
    })
    if req.key:                    # blank key = keep existing
        prov["key"] = req.key
    prov.setdefault("key", "")
    if req.model and req.model not in prov["models"]:
        prov["models"].append(req.model)
    cfg["providers"][req.id] = prov
    save_models(cfg)
    return {"ok": True}


@app.delete("/api/models/{pid}")
def models_delete(pid: str, _: str = Depends(verify_owner)):
    cfg = load_models()
    cfg["providers"].pop(pid, None)
    if cfg.get("selected") == pid:
        cfg["selected"] = "auto"
    save_models(cfg)
    return {"ok": True}


@app.post("/api/models/select")
def models_select(req: SelectModel, _: str = Depends(verify_owner)):
    cfg = load_models()
    if req.id != "auto" and req.id not in cfg["providers"]:
        raise HTTPException(404, "No such provider")
    cfg["selected"] = req.id
    save_models(cfg)
    return {"ok": True}


@app.post("/api/models/settings")
def models_settings(req: ModelSettings, _: str = Depends(verify_owner)):
    cfg = load_models()
    cfg["auto_cheapest"] = req.auto_cheapest
    save_models(cfg)
    return {"ok": True}


# ----------- mcp

# Runtime state: {server_id: {session_id_header, tools, status, error}}
# NOT persisted — rebuilt on connect.
_MCP_RUNTIME: dict[str, dict] = {}


def _mcp_slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def _load_mcp_config() -> list:
    with _MCP_LOCK:
        return _load_json(MCP_CONFIG_FILE, [])


def _save_mcp_config(servers: list):
    with _MCP_LOCK:
        _save_json(MCP_CONFIG_FILE, servers)


def _mcp_rpc(server: dict, method: str, params: dict, timeout: int = 30):
    """POST a JSON-RPC 2.0 request; handle both application/json and SSE responses."""
    rid = uuid.uuid4().hex
    payload = {"jsonrpc": "2.0", "id": rid, "method": method, "params": params}
    headers = {"Content-Type": "application/json",
               "Accept": "application/json, text/event-stream"}
    if server.get("token"):
        headers["Authorization"] = f"Bearer {server['token']}"
    rt = _MCP_RUNTIME.get(server["id"], {})
    if rt.get("session_id_header"):
        headers["Mcp-Session-Id"] = rt["session_id_header"]
    if rt.get("protocol_version"):
        headers["MCP-Protocol-Version"] = rt["protocol_version"]
    _sse_byte_cap = 256 * 1024  # 256 KB hard stop on SSE body
    _deadline = time.time() + timeout
    resp = requests.post(server["url"], json=payload, headers=headers,
                         timeout=timeout, stream=True)
    resp.raise_for_status()
    ct = resp.headers.get("Content-Type", "")
    if "text/event-stream" in ct:
        _bytes_read = 0
        for line in resp.iter_lines():
            if time.time() > _deadline:
                raise RuntimeError("MCP SSE stream deadline exceeded")
            if isinstance(line, bytes):
                _bytes_read += len(line)
                line = line.decode()
            else:
                _bytes_read += len(line.encode())
            if _bytes_read > _sse_byte_cap:
                raise RuntimeError("MCP SSE stream exceeded byte cap")
            if not line.startswith("data:"):
                continue
            chunk = line[5:].strip()
            if not chunk or chunk == "[DONE]":
                continue
            try:
                obj = json.loads(chunk)
            except json.JSONDecodeError:
                continue
            if obj.get("id") == rid:
                if "error" in obj:
                    raise RuntimeError(f"MCP error {obj['error'].get('code')}: "
                                       f"{obj['error'].get('message')}")
                return obj.get("result", {})
        raise RuntimeError("MCP SSE stream ended without matching response")
    else:
        obj = resp.json()
        if "error" in obj:
            raise RuntimeError(f"MCP error {obj['error'].get('code')}: "
                               f"{obj['error'].get('message')}")
        return obj.get("result", {})


def _mcp_notify(server: dict, method: str, params: dict):
    """POST a JSON-RPC notification (no id, no response expected)."""
    payload = {"jsonrpc": "2.0", "method": method, "params": params}
    headers = {"Content-Type": "application/json",
               "Accept": "application/json, text/event-stream"}
    if server.get("token"):
        headers["Authorization"] = f"Bearer {server['token']}"
    rt = _MCP_RUNTIME.get(server["id"], {})
    if rt.get("session_id_header"):
        headers["Mcp-Session-Id"] = rt["session_id_header"]
    if rt.get("protocol_version"):
        headers["MCP-Protocol-Version"] = rt["protocol_version"]
    try:
        requests.post(server["url"], json=payload, headers=headers, timeout=10)
    except Exception:
        pass  # notifications are fire-and-forget


def _mcp_connect(server: dict):
    """initialize → notifications/initialized → tools/list; update _MCP_RUNTIME."""
    sid = server["id"]
    _MCP_RUNTIME[sid] = {"session_id_header": None, "protocol_version": None,
                         "tools": [], "status": "connecting", "error": None}
    try:
        # Step 1: initialize
        headers_pre = {"Content-Type": "application/json",
                       "Accept": "application/json, text/event-stream"}
        if server.get("token"):
            headers_pre["Authorization"] = f"Bearer {server['token']}"
        init_payload = {
            "jsonrpc": "2.0", "id": uuid.uuid4().hex, "method": "initialize",
            "params": {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "codemonkeys", "version": "0.1"},
            },
        }
        _connect_timeout = 30
        _connect_deadline = time.time() + _connect_timeout
        _connect_byte_cap = 256 * 1024  # 256 KB hard stop on SSE body
        resp = requests.post(server["url"], json=init_payload,
                             headers=headers_pre, timeout=_connect_timeout, stream=True)
        resp.raise_for_status()
        session_hdr = resp.headers.get("Mcp-Session-Id")
        ct = resp.headers.get("Content-Type", "")
        if "text/event-stream" in ct:
            init_result = None
            _bytes_read = 0
            for line in resp.iter_lines():
                if time.time() > _connect_deadline:
                    raise RuntimeError("MCP connect SSE stream deadline exceeded")
                if isinstance(line, bytes):
                    _bytes_read += len(line)
                    line = line.decode()
                else:
                    _bytes_read += len(line.encode())
                if _bytes_read > _connect_byte_cap:
                    raise RuntimeError("MCP connect SSE stream exceeded byte cap")
                if not line.startswith("data:"):
                    continue
                chunk = line[5:].strip()
                if not chunk or chunk == "[DONE]":
                    continue
                try:
                    obj = json.loads(chunk)
                except json.JSONDecodeError:
                    continue
                if "result" in obj or "error" in obj:
                    if "error" in obj:
                        raise RuntimeError(f"initialize error: {obj['error']}")
                    init_result = obj["result"]
                    break
            if init_result is None:
                raise RuntimeError("No initialize result in SSE stream")
        else:
            obj = resp.json()
            if "error" in obj:
                raise RuntimeError(f"initialize error: {obj['error']}")
            init_result = obj.get("result", {})

        proto = init_result.get("protocolVersion", "2025-03-26")
        _MCP_RUNTIME[sid]["session_id_header"] = session_hdr
        _MCP_RUNTIME[sid]["protocol_version"] = proto

        # Step 2: notifications/initialized (no response expected)
        _mcp_notify(server, "notifications/initialized", {})

        # Step 3: tools/list
        tl_result = _mcp_rpc(server, "tools/list", {}, timeout=30)
        raw_tools = tl_result.get("tools", [])
        _MCP_RUNTIME[sid]["tools"] = raw_tools
        _MCP_RUNTIME[sid]["status"] = "connected"
        _MCP_RUNTIME[sid]["error"] = None
    except Exception as exc:
        _MCP_RUNTIME[sid]["status"] = "error"
        _MCP_RUNTIME[sid]["error"] = str(exc)
        _MCP_RUNTIME[sid]["tools"] = []


def _mcp_disconnect(sid: str):
    _MCP_RUNTIME.pop(sid, None)


def mcp_tool_schemas() -> dict:
    """Return {namespaced_name: neutral_schema} for all enabled+connected MCP servers."""
    result = {}
    for srv in _load_mcp_config():
        if not srv.get("enabled"):
            continue
        rt = _MCP_RUNTIME.get(srv["id"])
        if not rt or rt.get("status") != "connected":
            continue
        slug = _mcp_slug(srv["name"])
        if not slug:
            continue  # skip servers whose slug is empty (same guard as registry)
        for t in rt.get("tools", []):
            tname = t.get("name", "")
            if not tname:
                continue
            ns = f"mcp_{slug}_{tname}"
            if ns in result:
                # first-writer-wins: a later server cannot shadow an earlier one's tool
                continue
            if len(result) >= MCP_MAX_TOOLS:
                return result  # hostile/huge server can't blow context/cost
            read_only = bool((t.get("annotations") or {}).get("readOnlyHint"))
            result[ns] = {
                "name": ns,
                "description": f"[{srv['name']}] {t.get('description', '')}"[:MCP_DESC_CAP],
                "parameters": t.get("inputSchema") or {"type": "object", "properties": {}},
                "_mcp_read_only": read_only,
            }
    return result


# Registry: namespaced_name -> (server_id, original_tool_name, read_only)
def _mcp_registry() -> dict:
    reg = {}
    for srv in _load_mcp_config():
        if not srv.get("enabled"):
            continue
        rt = _MCP_RUNTIME.get(srv["id"])
        if not rt or rt.get("status") != "connected":
            continue
        slug = _mcp_slug(srv["name"])
        if not slug:
            continue  # skip servers with empty slug to avoid mcp__tool ambiguity
        for t in rt.get("tools", []):
            tname = t.get("name", "")
            if not tname:
                continue
            ns = f"mcp_{slug}_{tname}"
            if ns in reg:
                # first-writer-wins: drop the collider to prevent tool shadowing
                continue
            if len(reg) >= MCP_MAX_TOOLS:
                return reg  # stay in lockstep with mcp_tool_schemas' cap
            read_only = bool((t.get("annotations") or {}).get("readOnlyHint"))
            reg[ns] = (srv["id"], tname, read_only)
    return reg


def _mcp_call_tool(srv_id: str, tool_name: str, arguments: dict) -> str:
    servers = {s["id"]: s for s in _load_mcp_config()}
    srv = servers.get(srv_id)
    if not srv:
        return "ERROR: MCP server not found"
    if _MCP_RUNTIME.get(srv_id, {}).get("status") != "connected":
        return "ERROR: MCP server not connected"
    try:
        result = _mcp_rpc(srv, "tools/call",
                          {"name": tool_name, "arguments": arguments},
                          timeout=120)
        parts = [c["text"] for c in result.get("content", []) if c.get("type") == "text"]
        text = "\n".join(parts)
        if result.get("isError"):
            text = "ERROR: " + text
        return text[:OUTPUT_CAP]
    except Exception as exc:
        return f"ERROR: {exc}"


def _mcp_entry_shape(srv: dict) -> dict:
    rt = _MCP_RUNTIME.get(srv["id"], {})
    tools_list = [
        {"name": t.get("name", ""),
         "description": t.get("description", ""),
         "read_only": bool((t.get("annotations") or {}).get("readOnlyHint"))}
        for t in rt.get("tools", [])
    ]
    return {
        "id": srv["id"],
        "name": srv["name"],
        "url": srv["url"],
        "enabled": srv.get("enabled", True),
        "has_token": bool(srv.get("token")),
        "status": rt.get("status", "disconnected"),
        "error": rt.get("error"),
        "tools": tools_list,
    }


class McpCreate(BaseModel):
    name: str
    url: str
    token: str = ""


@app.get("/api/mcp")
def mcp_list(_: str = Depends(verify_owner)):
    servers = _load_mcp_config()
    return {"servers": [_mcp_entry_shape(s) for s in servers]}


@app.post("/api/mcp")
def mcp_add(req: McpCreate, _: str = Depends(verify_owner)):
    if not req.name.strip():
        raise HTTPException(400, "name is required")
    url = req.url.strip()
    _parsed = urllib.parse.urlparse(url)
    _loopback = {"localhost", "127.0.0.1", "::1"}
    if not (_parsed.scheme == "https" or
            (_parsed.scheme == "http" and _parsed.hostname in _loopback)):
        raise HTTPException(400, "url must use https:// (or http://localhost|127.0.0.1|::1 for dev)")
    servers = _load_mcp_config()
    sid = uuid.uuid4().hex[:8]
    srv = {"id": sid, "name": req.name.strip(), "url": url,
           "token": req.token, "enabled": True}
    servers.append(srv)
    _save_mcp_config(servers)
    _mcp_connect(srv)
    return _mcp_entry_shape(srv)


@app.delete("/api/mcp/{sid}")
def mcp_delete(sid: str, _: str = Depends(verify_owner)):
    servers = _load_mcp_config()
    servers = [s for s in servers if s["id"] != sid]
    _save_mcp_config(servers)
    _mcp_disconnect(sid)
    return {"ok": True}


@app.post("/api/mcp/{sid}/toggle")
def mcp_toggle(sid: str, _: str = Depends(verify_owner)):
    servers = _load_mcp_config()
    srv = next((s for s in servers if s["id"] == sid), None)
    if not srv:
        raise HTTPException(404, "No such MCP server")
    srv["enabled"] = not srv.get("enabled", True)
    _save_mcp_config(servers)
    if not srv["enabled"]:
        _mcp_disconnect(sid)
    return _mcp_entry_shape(srv)


@app.post("/api/mcp/{sid}/refresh")
def mcp_refresh(sid: str, _: str = Depends(verify_owner)):
    servers = _load_mcp_config()
    srv = next((s for s in servers if s["id"] == sid), None)
    if not srv:
        raise HTTPException(404, "No such MCP server")
    _mcp_disconnect(sid)
    _mcp_connect(srv)
    return _mcp_entry_shape(srv)


# ----------------------------------------------------------------- unified chat
# History items (provider-agnostic):
#   {"role": "user", "text": str}
#   {"role": "assistant", "text": str, "tool_calls": [{"id","name","args"}]}
#   {"role": "tool", "tool_call_id": str, "name": str, "content": str}


def _chat_openai(provider, system, history, tools, max_tokens):
    messages = [{"role": "system", "content": system}]
    for h in history:
        if h["role"] == "user":
            messages.append({"role": "user", "content": h["text"]})
        elif h["role"] == "assistant":
            msg = {"role": "assistant", "content": h.get("text") or None}
            if h.get("tool_calls"):
                msg["tool_calls"] = [
                    {"id": tc["id"], "type": "function",
                     "function": {"name": tc["name"], "arguments": json.dumps(tc["args"])}}
                    for tc in h["tool_calls"]]
            messages.append(msg)
        elif h["role"] == "tool":
            messages.append({"role": "tool", "tool_call_id": h["tool_call_id"],
                             "content": h["content"]})
    payload = {"model": provider["model"], "messages": messages, "max_tokens": max_tokens}
    if tools:
        payload["tools"] = [{"type": "function", "function":
                             {"name": t["name"], "description": t["description"],
                              "parameters": t["parameters"]}} for t in tools]
    r = requests.post(
        provider["base_url"].rstrip("/") + "/chat/completions",
        headers={"Authorization": f"Bearer {provider['api_key']}",
                 "Content-Type": "application/json"},
        json=payload, timeout=300)
    if r.status_code >= 400:
        raise RuntimeError(f"{provider['name']} HTTP {r.status_code}: {r.text[:400]}")
    data = r.json()
    msg = data["choices"][0]["message"]
    tool_calls = []
    for tc in msg.get("tool_calls") or []:
        try:
            args = json.loads(tc["function"].get("arguments") or "{}")
        except json.JSONDecodeError:
            args = {}
        tool_calls.append({"id": tc["id"], "name": tc["function"]["name"], "args": args})
    usage = data.get("usage") or {}
    return {"text": msg.get("content") or "", "tool_calls": tool_calls,
            "in_tokens": usage.get("prompt_tokens", 0),
            "out_tokens": usage.get("completion_tokens", 0)}


def _chat_anthropic(provider, system, history, tools, max_tokens):
    if anthropic_sdk is None:
        raise RuntimeError("anthropic SDK not installed")
    client = anthropic_sdk.Anthropic(api_key=provider["api_key"])
    messages, pending_results = [], []

    def flush_results():
        if pending_results:
            messages.append({"role": "user", "content": list(pending_results)})
            pending_results.clear()

    for h in history:
        if h["role"] == "user":
            flush_results()
            messages.append({"role": "user", "content": h["text"]})
        elif h["role"] == "assistant":
            flush_results()
            content = []
            if h.get("text"):
                content.append({"type": "text", "text": h["text"]})
            for tc in h.get("tool_calls") or []:
                content.append({"type": "tool_use", "id": tc["id"],
                                "name": tc["name"], "input": tc["args"]})
            messages.append({"role": "assistant", "content": content or [{"type": "text", "text": "."}]})
        elif h["role"] == "tool":
            pending_results.append({"type": "tool_result",
                                    "tool_use_id": h["tool_call_id"],
                                    "content": h["content"]})
    flush_results()
    kwargs = {"model": provider["model"], "max_tokens": max_tokens,
              "system": system, "messages": messages}
    if tools:
        kwargs["tools"] = [{"name": t["name"], "description": t["description"],
                            "input_schema": t["parameters"]} for t in tools]
    resp = client.messages.create(**kwargs)
    text, tool_calls = "", []
    for block in resp.content:
        if block.type == "text":
            text += block.text
        elif block.type == "tool_use":
            tool_calls.append({"id": block.id, "name": block.name, "args": dict(block.input)})
    return {"text": text, "tool_calls": tool_calls,
            "in_tokens": resp.usage.input_tokens, "out_tokens": resp.usage.output_tokens}


def call_model(provider, system, history, tools, max_tokens=8192):
    if provider["kind"] == "anthropic":
        return _chat_anthropic(provider, system, history, tools, max_tokens)
    return _chat_openai(provider, system, history, tools, max_tokens)


def call_cost(provider, in_tokens, out_tokens):
    return (in_tokens * provider.get("input_cost_per_m", 0)
            + out_tokens * provider.get("output_cost_per_m", 0)) / 1e6


# ----------------------------------------------------------------- workspace tools

def _jail(path: str) -> str:
    """Resolve path inside WORKSPACE_DIR or raise."""
    full = os.path.realpath(os.path.join(WORKSPACE_DIR, path.lstrip("/")))
    root = os.path.realpath(WORKSPACE_DIR)
    if full != root and not full.startswith(root + os.sep):
        raise ValueError(f"Path escapes workspace: {path}")
    return full


def t_read_file(args):
    full = _jail(args["path"])
    with open(full, "r", errors="replace") as f:
        text = f.read(READ_CAP + 1)
    if len(text) > READ_CAP:
        text = text[:READ_CAP] + "\n...[truncated]"
    return text or "(empty file)"


def t_write_file(args):
    full = _jail(args["path"])
    os.makedirs(os.path.dirname(full) or full, exist_ok=True)
    with open(full, "w") as f:
        f.write(args["content"])
    return f"Wrote {len(args['content'])} chars to {args['path']}"


def t_edit_file(args):
    full = _jail(args["path"])
    with open(full, "r") as f:
        text = f.read()
    old = args["old_string"]
    n = text.count(old)
    if n == 0:
        return "ERROR: old_string not found"
    if n > 1 and not args.get("replace_all"):
        return f"ERROR: old_string occurs {n} times; pass replace_all=true or be more specific"
    with open(full, "w") as f:
        f.write(text.replace(old, args["new_string"]) if args.get("replace_all")
                else text.replace(old, args["new_string"], 1))
    return "Edit applied"


def t_list_dir(args):
    full = _jail(args.get("path", "."))
    entries = []
    for e in sorted(os.scandir(full), key=lambda x: x.name)[:200]:
        entries.append(e.name + ("/" if e.is_dir() else ""))
    return "\n".join(entries) or "(empty)"


def t_glob(args):
    pat = args["pattern"]
    out, root = [], os.path.realpath(WORKSPACE_DIR)
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in (".git", "node_modules", "__pycache__")]
        for fn in filenames:
            rel = os.path.relpath(os.path.join(dirpath, fn), root)
            if fnmatch.fnmatch(rel, pat) or fnmatch.fnmatch(fn, pat):
                out.append(rel)
                if len(out) >= 200:
                    return "\n".join(out) + "\n...[capped at 200]"
    return "\n".join(out) or "(no matches)"


def t_grep(args):
    target = _jail(args.get("path", "."))
    try:
        r = subprocess.run(
            ["grep", "-rnI", "--exclude-dir=.git", "--exclude-dir=node_modules",
             "-m", "5", "-e", args["pattern"], target],
            capture_output=True, text=True, timeout=30)
    except subprocess.TimeoutExpired:
        return "ERROR: grep timed out"
    out = (r.stdout or r.stderr or "(no matches)")
    out = out.replace(os.path.realpath(WORKSPACE_DIR) + os.sep, "")
    return out[:OUTPUT_CAP]


def t_bash(args, session=None):
    cmd = args["command"]
    # auto mode skips the approval gate; default/plan still gate risky commands
    if session is not None and session.get("mode") != "auto":
        for pat in RISKY_PATTERNS:
            if re.search(pat, cmd):
                if not request_approval(session, cmd):
                    return "DENIED: user rejected this command"
                break
    env = dict(os.environ)
    try:
        r = subprocess.run(["bash", "-c", cmd], cwd=WORKSPACE_DIR, env=env,
                           capture_output=True, text=True, timeout=BASH_TIMEOUT)
    except subprocess.TimeoutExpired:
        return f"ERROR: command timed out after {BASH_TIMEOUT}s"
    out = ""
    if r.stdout:
        out += r.stdout
    if r.stderr:
        out += ("\n[stderr]\n" + r.stderr)
    out = out.strip() or f"(no output, exit {r.returncode})"
    if r.returncode != 0:
        out += f"\n[exit code {r.returncode}]"
    return out[:OUTPUT_CAP]


TOOL_SCHEMAS = {
    "read_file": {"name": "read_file", "description": "Read a file in the workspace.",
                  "parameters": {"type": "object", "properties": {
                      "path": {"type": "string", "description": "Path relative to workspace root"}},
                      "required": ["path"]}},
    "write_file": {"name": "write_file", "description": "Create or overwrite a file in the workspace. Parent dirs are created.",
                   "parameters": {"type": "object", "properties": {
                       "path": {"type": "string"}, "content": {"type": "string"}},
                       "required": ["path", "content"]}},
    "edit_file": {"name": "edit_file", "description": "Replace an exact string in a file. old_string must match exactly once unless replace_all.",
                  "parameters": {"type": "object", "properties": {
                      "path": {"type": "string"}, "old_string": {"type": "string"},
                      "new_string": {"type": "string"}, "replace_all": {"type": "boolean"}},
                      "required": ["path", "old_string", "new_string"]}},
    "list_dir": {"name": "list_dir", "description": "List a directory in the workspace.",
                 "parameters": {"type": "object", "properties": {
                     "path": {"type": "string", "description": "Defaults to workspace root"}},
                     "required": []}},
    "glob_files": {"name": "glob_files", "description": "Find files by glob pattern (e.g. **/*.py or *.md).",
                   "parameters": {"type": "object", "properties": {
                       "pattern": {"type": "string"}}, "required": ["pattern"]}},
    "grep": {"name": "grep", "description": "Regex search file contents recursively (grep -rn, 5 matches/file).",
             "parameters": {"type": "object", "properties": {
                 "pattern": {"type": "string"}, "path": {"type": "string"}},
                 "required": ["pattern"]}},
    "bash": {"name": "bash", "description":
             "Run a bash command in the workspace (git, tests, builds...). "
             "Pushes, deploys and destructive commands pause for human approval.",
             "parameters": {"type": "object", "properties": {
                 "command": {"type": "string"}}, "required": ["command"]}},
    "spawn_agent": {"name": "spawn_agent", "description":
                    "Delegate a task to a specialist subagent from the Daystrom corps. "
                    "Use for parallel-izable or specialist work (recon-scout for cheap search, "
                    "field-engineer for code changes, provost-qa to verify, red-team for risky "
                    "changes, staff-planner before big campaigns). Returns the agent's report.",
                    "parameters": {"type": "object", "properties": {
                        "agent": {"type": "string", "description": "Agent name, e.g. recon-scout"},
                        "task": {"type": "string", "description": "Objective with context — intent and end-state, not micromanagement"}},
                        "required": ["agent", "task"]}},
}

# Daystrom frontmatter tools -> our runtime tools
CORPS_TOOL_MAP = {
    "Read": ["read_file", "list_dir"],
    "Grep": ["grep"],
    "Glob": ["glob_files", "list_dir"],
    "Bash": ["bash"],
    "Edit": ["edit_file"],
    "Write": ["write_file"],
}


# ----------------------------------------------------------------- corps (Daystrom)

def load_corps():
    corps = {}
    if not os.path.isdir(CORPS_DIR):
        return corps
    for fn in os.listdir(CORPS_DIR):
        if not fn.endswith(".md"):
            continue
        try:
            with open(os.path.join(CORPS_DIR, fn)) as f:
                text = f.read()
        except OSError:
            continue
        m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.DOTALL)
        if not m:
            continue
        meta = {}
        for line in m.group(1).splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip()] = v.strip()
        name = meta.get("name", fn[:-3])
        corps[name] = {
            "name": name,
            "description": meta.get("description", ""),
            "tools": [t.strip() for t in meta.get("tools", "").split(",") if t.strip()],
            "model": meta.get("model", "sonnet"),
            "model_tier": meta.get("model-tier", ""),
            "body": m.group(2).strip(),
        }
    return corps


CORPS = load_corps()


def corps_tier(agent_def):
    mt = agent_def.get("model_tier", "").upper()
    if mt in ("T0", "T1", "T2", "T3"):
        return mt.lower()
    return {"haiku": "t0", "sonnet": "t1", "opus": "t3"}.get(agent_def.get("model"), "t1")


def corps_tools(agent_def):
    allowed = []
    for t in agent_def["tools"]:
        allowed += CORPS_TOOL_MAP.get(t, [])
    # de-dup, keep order
    return [t for i, t in enumerate(allowed) if t not in allowed[:i]]


# ----------------------------------------------------------------- sessions

SESSIONS = {}  # id -> dict (in-memory; events mirrored to JSONL on /data)


def _session_index_path():
    return os.path.join(SESSIONS_DIR, "index.json")


def _persist_index():
    idx = {sid: {"title": s["title"], "repo": s["repo"], "created": s["created"]}
           for sid, s in SESSIONS.items()}
    _save_json(_session_index_path(), idx)


def _events_path(sid):
    return os.path.join(SESSIONS_DIR, f"{sid}.events.jsonl")


def new_session(title="", repo=""):
    sid = uuid.uuid4().hex[:12]
    with _SESSIONS_LOCK:
        SESSIONS[sid] = {
            "id": sid, "title": title or f"session-{sid[:6]}", "repo": repo,
            "created": int(time.time()), "status": "idle", "mode": "default",
            "events": [], "history": [], "spent_usd": 0.0,
            "agents_spawned": 0, "stop_flag": threading.Event(),
            "approvals": {}, "lock": threading.Lock(),
        }
        _persist_index()
    return SESSIONS[sid]


def restore_sessions():
    idx = _load_json(_session_index_path(), {})
    for sid, meta in idx.items():
        s = {
            "id": sid, "title": meta.get("title", sid), "repo": meta.get("repo", ""),
            "created": meta.get("created", 0), "status": "idle", "mode": "default",
            "events": [], "history": [], "spent_usd": 0.0,
            "agents_spawned": 0, "stop_flag": threading.Event(),
            "approvals": {}, "lock": threading.Lock(),
        }
        try:
            with open(_events_path(sid)) as f:
                lines = f.readlines()[-500:]
            s["events"] = [json.loads(l) for l in lines if l.strip()]
            for e in s["events"]:
                if e.get("type") == "cost":
                    s["spent_usd"] += e.get("usd", 0)
        except OSError:
            pass
        hist = _load_json(os.path.join(SESSIONS_DIR, f"{sid}.history.json"), [])
        s["history"] = hist
        SESSIONS[sid] = s


restore_sessions()


def emit(session, etype, **fields):
    with session["lock"]:
        evt = {"i": len(session["events"]), "ts": int(time.time()), "type": etype, **fields}
        session["events"].append(evt)
    try:
        with open(_events_path(session["id"]), "a") as f:
            f.write(json.dumps(evt) + "\n")
    except OSError:
        pass
    return evt


def persist_history(session):
    _save_json(os.path.join(SESSIONS_DIR, f"{session['id']}.history.json"),
               session["history"])


def request_approval(session, command):
    aid = uuid.uuid4().hex[:8]
    flag = threading.Event()
    session["approvals"][aid] = {"flag": flag, "approve": None, "command": command}
    emit(session, "approval", approval_id=aid, command=command)
    session["status"] = "waiting_approval"
    flag.wait(APPROVAL_TIMEOUT)
    session["status"] = "running"
    return session["approvals"].pop(aid, {}).get("approve") is True


# ----------------------------------------------------------------- agent loop

def _commander_system(session):
    repos = []
    try:
        for e in os.scandir(WORKSPACE_DIR):
            if e.is_dir():
                repos.append(e.name)
    except OSError:
        pass
    corps_list = "\n".join(f"- {a['name']}: {a['description']}" for a in CORPS.values())
    return (
        "You are CodeMonkeys, an autonomous coding agent commanding the Daystrom "
        "agent corps. You work inside a jailed workspace; all file paths are relative "
        f"to it. Workspace contents: {', '.join(sorted(repos)) or '(empty — clone a repo or create folders)'}.\n\n"
        "DOCTRINE (mission command): triage every objective —\n"
        "- Skirmish (single scoped edit / question): work solo, no subagents.\n"
        "- Operation (a few strands): up to 4 subagents; recon first, then line "
        "units, then a provost-qa verify pass.\n"
        "- Campaign (broad audit/migration): staff-planner first, up to 8 subagents, "
        "verify with provost-qa AND red-team for high-risk changes (auth, data, "
        "irreversible actions). Hold reserve spawns for verification and one retry.\n\n"
        f"AVAILABLE SUBAGENTS:\n{corps_list}\n\n"
        "RULES: Give subagents intent and end-state, not micromanagement. Match the "
        "surrounding code's conventions. Stage only files you changed — NEVER `git add -A` "
        "or `commit -a`. Work on a branch (work/<topic>) for non-trivial changes. "
        "Pushes/deploys/destructive commands pause for human approval — that is expected, "
        "proceed when you genuinely need them. Be token-efficient: act, don't narrate. "
        "When done, give a short report of what changed and how it was verified."
    )


def make_executor(session, allowed, agent_label=None, depth=0):
    """Returns fn(tool_call) -> (result_str, ok)."""
    _registry = _mcp_registry() if depth == 0 else {}

    def execute(tc):
        name, args = tc["name"], tc["args"]
        if name not in allowed:
            return f"ERROR: tool '{name}' not permitted for this agent", False
        try:
            if name.startswith("mcp_") and depth == 0:
                entry = _registry.get(name)
                if not entry:
                    # lazy connect: server enabled but not yet initialized
                    servers = {s["id"]: s for s in _load_mcp_config()}
                    for srv in servers.values():
                        if srv.get("enabled") and _mcp_slug(srv["name"]):
                            slug = _mcp_slug(srv["name"])
                            if name.startswith(f"mcp_{slug}_"):
                                _mcp_connect(srv)
                    _registry.update(_mcp_registry())
                    entry = _registry.get(name)
                if not entry:
                    return f"ERROR: MCP tool '{name}' not found", False
                srv_id, tool_name, read_only = entry
                # readOnlyHint is remote-controlled and not trusted for gating.
                if session.get("mode") != "auto":
                    approved = request_approval(
                        session,
                        f"MCP {name} {json.dumps(args)[:200]}"
                    )
                    if not approved:
                        return "DENIED", False
                return _mcp_call_tool(srv_id, tool_name, args), True
            if name == "bash":
                return t_bash(args, session=session), True
            if name == "read_file":
                return t_read_file(args), True
            if name == "write_file":
                return t_write_file(args), True
            if name == "edit_file":
                r = t_edit_file(args)
                return r, not r.startswith("ERROR")
            if name == "list_dir":
                return t_list_dir(args), True
            if name == "glob_files":
                return t_glob(args), True
            if name == "grep":
                return t_grep(args), True
            if name == "spawn_agent":
                if depth > 0:
                    return "ERROR: subagents cannot spawn subagents", False
                return run_subagent(session, args.get("agent", ""), args.get("task", "")), True
            return f"ERROR: unknown tool {name}", False
        except Exception as e:  # tool errors go back to the model, not the user
            return f"ERROR: {type(e).__name__}: {e}", False
    return execute


def agent_loop(session, provider, system, history, tool_names, max_turns,
               agent_label=None, depth=0):
    _mcp_schemas = mcp_tool_schemas() if depth == 0 else {}
    _combined = {**TOOL_SCHEMAS, **_mcp_schemas}
    tools = [_combined[t] for t in tool_names if t in _combined]
    executor = make_executor(session, tool_names, agent_label, depth)
    final_text = ""
    for _ in range(max_turns):
        if session["stop_flag"].is_set():
            emit(session, "error", message="Stopped by user", agent=agent_label)
            break
        if session["spent_usd"] >= SESSION_BUDGET_USD:
            emit(session, "error", agent=agent_label,
                 message=f"Session budget ${SESSION_BUDGET_USD:.2f} reached "
                         f"(spent ${session['spent_usd']:.2f}). Raise SESSION_BUDGET_USD or start a new session.")
            break
        try:
            resp = call_model(provider, system, history, tools)
        except Exception as e:
            emit(session, "error", message=f"Model call failed: {e}", agent=agent_label)
            break
        usd = call_cost(provider, resp["in_tokens"], resp["out_tokens"])
        session["spent_usd"] += usd
        emit(session, "cost", usd=round(usd, 6), in_tokens=resp["in_tokens"],
             out_tokens=resp["out_tokens"], model=provider["model"], agent=agent_label)
        history.append({"role": "assistant", "text": resp["text"],
                        "tool_calls": resp["tool_calls"]})
        if resp["text"]:
            emit(session, "text", text=resp["text"], agent=agent_label)
            final_text = resp["text"]
        if not resp["tool_calls"]:
            return final_text
        for tc in resp["tool_calls"]:
            detail = json.dumps(tc["args"])[:300]
            emit(session, "tool", name=tc["name"], detail=detail, agent=agent_label)
            result, ok = executor(tc)
            emit(session, "tool_result", name=tc["name"], ok=ok,
                 detail=result[:600], agent=agent_label)
            history.append({"role": "tool", "tool_call_id": tc["id"],
                            "name": tc["name"], "content": result})
    else:
        emit(session, "error", message="Max turns reached", agent=agent_label)
    return final_text


def run_subagent(session, agent_name, task):
    agent_def = CORPS.get(agent_name)
    if not agent_def:
        return f"ERROR: no such agent '{agent_name}'. Available: {', '.join(CORPS)}"
    if session["agents_spawned"] >= MAX_SUBAGENTS:
        return f"ERROR: subagent cap ({MAX_SUBAGENTS}) reached for this session"
    session["agents_spawned"] += 1
    cfg = load_models()
    tier = corps_tier(agent_def)
    provider = provider_for_tier(cfg, tier) or main_provider(cfg)
    if not provider:
        return "ERROR: no enabled model provider"
    tool_names = corps_tools(agent_def)
    emit(session, "agent_start", agent=agent_name, tier=tier,
         model=provider["model"], task=task[:300])
    system = (
        f"{agent_def['body']}\n\n"
        "You are operating inside a jailed workspace; all paths are relative to it. "
        f"Your tools: {', '.join(tool_names)}. Work the objective, then return a "
        "concise structured report as your final message — it goes to your commander, "
        "not the user."
    )
    history = [{"role": "user", "text": task}]
    text = agent_loop(session, provider, system, history, tool_names,
                      SUBAGENT_MAX_TURNS, agent_label=agent_name, depth=1)
    emit(session, "agent_end", agent=agent_name, ok=bool(text),
         summary=(text or "(no report)")[:400])
    return text or "(subagent returned no report)"


MODE_GUIDANCE = {
    "plan": (
        "\n\nMODE: PLAN. You have READ-ONLY tools. Do NOT write, edit, or run "
        "mutating commands. Investigate the workspace, then present a clear, "
        "numbered implementation plan and STOP. The user will switch you to "
        "default or auto mode to execute it."),
    "default": (
        "\n\nMODE: DEFAULT. Implement the work. Pushes, deploys, and destructive "
        "commands will pause for the user's approval — that is expected."),
    "auto": (
        "\n\nMODE: AUTO. Full autonomy — every command runs without approval, "
        "including pushes and deploys. Be careful and deliberate; the user is "
        "trusting you to ship. Still work on a branch for non-trivial changes."),
}
PLAN_TOOLS = ["read_file", "list_dir", "glob_files", "grep", "spawn_agent"]
FULL_TOOLS = ["read_file", "write_file", "edit_file", "list_dir",
              "glob_files", "grep", "bash", "spawn_agent"]


def run_session_message(session, text):
    cfg = load_models()
    provider = main_provider(cfg)
    if not provider:
        emit(session, "error", message="No enabled model provider — add an API key in Models settings.")
        emit(session, "done")
        session["status"] = "idle"
        return
    session["status"] = "running"
    session["stop_flag"].clear()
    session["history"].append({"role": "user", "text": text})
    mode = session.get("mode", "default")
    _mcp = mcp_tool_schemas()
    _mcp_all = list(_mcp.keys())
    if mode == "plan":
        # plan is read-only-local; remote MCP tools are excluded entirely —
        # a malicious server could lie about readOnlyHint.
        tool_names = PLAN_TOOLS
    else:
        tool_names = FULL_TOOLS + _mcp_all
    system = _commander_system(session) + MODE_GUIDANCE.get(mode, "")
    try:
        agent_loop(session, provider, system,
                   session["history"], tool_names, MAX_TURNS)
    finally:
        session["status"] = "idle"
        emit(session, "done")
        persist_history(session)


# ----------------------------------------------------------------- session API

class SessionCreate(BaseModel):
    title: str = ""
    repo: str = ""


class FileUpload(BaseModel):
    name: str
    content_b64: str


class MessageRequest(BaseModel):
    text: str
    files: list[FileUpload] = []
    mode: str = "default"          # plan | default | auto


class ApproveRequest(BaseModel):
    approval_id: str
    approve: bool


@app.post("/api/sessions")
def session_create(req: SessionCreate, _: str = Depends(verify_user)):
    s = new_session(req.title, req.repo)
    return {"id": s["id"]}


@app.get("/api/sessions")
def session_list(_: str = Depends(verify_user)):
    return {"sessions": sorted([
        {"id": s["id"], "title": s["title"], "repo": s["repo"],
         "created": s["created"], "status": s["status"],
         "spent_usd": round(s["spent_usd"], 4)}
        for s in SESSIONS.values()], key=lambda x: -x["created"])}


@app.post("/api/sessions/{sid}/message")
def session_message(sid: str, req: MessageRequest, _: str = Depends(verify_user)):
    s = SESSIONS.get(sid)
    if not s:
        raise HTTPException(404, "No such session")
    if s["status"] != "idle":
        raise HTTPException(409, "Session is busy")
    s["mode"] = req.mode if req.mode in ("plan", "default", "auto") else "default"
    text = req.text
    if req.files:
        updir = os.path.join(WORKSPACE_DIR, "uploads", sid)
        os.makedirs(updir, exist_ok=True)
        names = []
        for f in req.files[:20]:
            safe = os.path.basename(f.name) or "file"
            try:
                blob = base64.b64decode(f.content_b64)
            except Exception:
                continue
            with open(os.path.join(updir, safe), "wb") as fh:
                fh.write(blob[:10_000_000])
            names.append(f"uploads/{sid}/{safe}")
        if names:
            text += "\n\n[Attached files saved in workspace: " + ", ".join(names) + "]"
    emit(s, "user", text=text)
    threading.Thread(target=run_session_message, args=(s, text), daemon=True).start()
    return {"ok": True}


@app.get("/api/sessions/{sid}/events")
def session_events(sid: str, after: int = -1, _: str = Depends(verify_user)):
    s = SESSIONS.get(sid)
    if not s:
        raise HTTPException(404, "No such session")
    with s["lock"]:
        events = [e for e in s["events"] if e["i"] > after]
        nxt = s["events"][-1]["i"] if s["events"] else -1
    return {"events": events, "next": nxt, "status": s["status"],
            "spent_usd": round(s["spent_usd"], 4)}


@app.post("/api/sessions/{sid}/approve")
def session_approve(sid: str, req: ApproveRequest, _: str = Depends(verify_user)):
    s = SESSIONS.get(sid)
    if not s:
        raise HTTPException(404, "No such session")
    a = s["approvals"].get(req.approval_id)
    if not a:
        raise HTTPException(404, "No such approval (it may have timed out)")
    a["approve"] = req.approve
    a["flag"].set()
    emit(s, "approval_result", approval_id=req.approval_id, approved=req.approve)
    return {"ok": True}


@app.post("/api/sessions/{sid}/stop")
def session_stop(sid: str, _: str = Depends(verify_user)):
    s = SESSIONS.get(sid)
    if not s:
        raise HTTPException(404, "No such session")
    s["stop_flag"].set()
    # release any pending approvals as denied
    for a in list(s["approvals"].values()):
        a["approve"] = False
        a["flag"].set()
    return {"ok": True}


@app.delete("/api/sessions/{sid}")
def session_delete(sid: str, _: str = Depends(verify_user)):
    s = SESSIONS.get(sid)
    if not s:
        raise HTTPException(404, "No such session")
    if s["status"] != "idle":
        raise HTTPException(409, "Stop the session before deleting it")
    with _SESSIONS_LOCK:
        SESSIONS.pop(sid, None)
        _persist_index()
    for path in (_events_path(sid),
                 os.path.join(SESSIONS_DIR, f"{sid}.history.json")):
        try:
            os.remove(path)
        except OSError:
            pass
    return {"ok": True}


# ----------------------------------------------------------------- repos

class RepoClone(BaseModel):
    url: str


def _auth_url(url):
    token = os.environ.get("GITHUB_TOKEN", "")
    if token and url.startswith("https://github.com/"):
        return url.replace("https://", f"https://x-access-token:{token}@", 1)
    return url


@app.get("/api/repos")
def repos_list(_: str = Depends(verify_user)):
    repos = []
    try:
        entries = sorted(os.scandir(WORKSPACE_DIR), key=lambda e: e.name)
    except OSError:
        entries = []
    for e in entries:
        if not e.is_dir() or not os.path.isdir(os.path.join(e.path, ".git")):
            continue
        def git(*a):
            r = subprocess.run(["git", "-C", e.path, *a],
                               capture_output=True, text=True, timeout=15)
            return r.stdout.strip()
        try:
            repos.append({"name": e.name,
                          "branch": git("rev-parse", "--abbrev-ref", "HEAD"),
                          "dirty": bool(git("status", "--porcelain"))})
        except Exception:
            repos.append({"name": e.name, "branch": "?", "dirty": False})
    return {"repos": repos}


@app.post("/api/repos")
def repos_clone(req: RepoClone, _: str = Depends(verify_user)):
    url = req.url.strip()
    if not re.match(r"^https://[\w.-]+/[\w./-]+$", url):
        raise HTTPException(400, "Provide an https git URL")
    name = os.path.basename(url.rstrip("/")).removesuffix(".git")
    dest = os.path.join(WORKSPACE_DIR, name)
    if os.path.exists(dest):
        raise HTTPException(409, f"{name} already exists in workspace")
    r = subprocess.run(["git", "clone", "--depth", "50", _auth_url(url), dest],
                       capture_output=True, text=True, timeout=300)
    if r.returncode != 0:
        raise HTTPException(500, f"Clone failed: {(r.stderr or '')[-300:]}")
    return {"name": name}


# ----------------------------------------------------------------- swarm viz feed

@app.get("/api/swarm/state")
def swarm_state(_: str = Depends(verify_user)):
    agents, activity = [], []
    for s in SESSIONS.values():
        with s["lock"]:
            recent = s["events"][-40:]
        live = {}
        for e in recent:
            if e["type"] == "agent_start":
                live[e["agent"]] = {"id": f"{s['id']}:{e['agent']}", "name": e["agent"],
                                    "tier": e.get("tier", "t1"), "status": "running",
                                    "session": s["title"]}
            elif e["type"] == "agent_end":
                if e.get("agent") in live:
                    live[e["agent"]]["status"] = "done"
            elif e["type"] in ("tool", "text"):
                activity.append({"type": e["type"], "from": e.get("agent") or "core",
                                 "detail": e.get("name", "") or (e.get("text", "")[:60]),
                                 "ts": e["ts"]})
        agents += list(live.values())
    return {
        "orchestrator": {"id": "core", "name": "CodeMonkeys", "tier": "orchestrate"},
        "agents": agents,
        "activity": activity[-30:],
        "stats": {
            "sessions": len(SESSIONS),
            "running": sum(1 for s in SESSIONS.values() if s["status"] != "idle"),
            "spend_today_usd": round(sum(s["spent_usd"] for s in SESSIONS.values()), 4),
            "budget_per_session_usd": SESSION_BUDGET_USD,
        },
    }


# ----------------------------------------------------------------- static

app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")


@app.get("/")
def root():
    return FileResponse(os.path.join(BASE_DIR, "static", "forge", "index.html"))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))
