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
import select
import shlex
import subprocess
import tempfile
import threading
import time
import urllib.parse
import uuid

import pyotp
import requests
from enum import Enum
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
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

MCP_TOKENS_FILE = os.path.join(DATA_DIR, "mcp_tokens.json")
# OAuth state entries expire after this many seconds (short window reduces CSRF exposure)
_OAUTH_STATE_TTL = 600

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
    r"\bfly(?:ctl)?\s+\w+",          # `fly` and the real binary name `flyctl`
    r"\brm\s+-rf\b",
    r"\bgit\s+reset\s+--hard\b",
    r"\bgit\s+clean\b",
    r"\bgh\s+repo\s+delete\b",
    r"\bsudo\b",
]


def _is_risky(cmd: str) -> bool:
    """True if *cmd* (or any quoted/escaped form of it) matches a RISKY pattern.

    Matching the raw string alone is bypassable by shell quoting and escaping:
    bash collapses `git "push"`, `g''it push`, and `git\\ push` all to `git push`,
    but those forms never match `\\bgit\\s+push\\b` because the intervening quote
    or backslash breaks the regex. We additionally normalize the command with
    shlex (which strips quotes/escapes exactly as the shell would) and match the
    rejoined token stream, so a quoted risky verb can no longer hide from the gate.

    Fail closed: a command we cannot tokenize (e.g. unbalanced quotes) is treated
    as risky and gated rather than waved through.

    Residual (documented in SECURITY.md): runtime-only constructs such as
    variable expansion (`g=git; $g push`), command substitution (`$(echo git) push`),
    and `eval` are resolved by bash at execution time and are not visible to static
    matching. Those are an accepted residual risk of gating a raw shell string.
    """
    candidates = [cmd]
    try:
        # posix shlex collapses quotes/escapes: 'git "push"' -> ['git', 'push']
        candidates.append(" ".join(shlex.split(cmd, comments=False, posix=True)))
    except ValueError:
        return True  # unparseable → fail closed
    return any(re.search(pat, text)
               for text in candidates for pat in RISKY_PATTERNS)

for _d in (DATA_DIR, SESSIONS_DIR, WORKSPACE_DIR):
    os.makedirs(_d, exist_ok=True)

app = FastAPI(title="CodeMonkeys")


@app.on_event("startup")
def _startup_warm_mcp():
    """Background-warm every enabled MCP server so tools are ready before first use."""
    def _warm(server: dict):
        try:
            _mcp_connect(server)
        except Exception:
            pass  # _mcp_connect already records the error in _MCP_RUNTIME; never propagate

    for _srv in _load_mcp_config():
        if _srv.get("enabled"):
            _t = threading.Thread(target=_warm, args=(_srv,), daemon=True)
            _t.start()


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

# Runtime state: {server_id: {session_id_header, tools, status, error[, proc]}}
# NOT persisted — rebuilt on connect.
# stdio entries additionally carry "proc": Popen handle (kept alive per session).
_MCP_RUNTIME: dict[str, dict] = {}

# Per-server connect lock: serializes connect/disconnect for the same sid so
# concurrent refresh/toggle/warmup calls cannot spawn duplicate orphan children.
_MCP_CONNECT_LOCKS: dict[str, threading.Lock] = {}
_MCP_CONNECT_LOCKS_LOCK = threading.Lock()  # protects the dict itself


def _mcp_connect_lock(sid: str) -> threading.Lock:
    """Return (creating if needed) the per-sid connect/disconnect lock."""
    with _MCP_CONNECT_LOCKS_LOCK:
        if sid not in _MCP_CONNECT_LOCKS:
            _MCP_CONNECT_LOCKS[sid] = threading.Lock()
        return _MCP_CONNECT_LOCKS[sid]


def _mcp_slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def _load_mcp_config() -> list:
    with _MCP_LOCK:
        return _load_json(MCP_CONFIG_FILE, [])


def _save_mcp_config(servers: list):
    with _MCP_LOCK:
        _save_json(MCP_CONFIG_FILE, servers)


# ---- OAuth token store (separate from mcp_config; never returned/logged) ----

_MCP_TOKENS_LOCK = threading.Lock()


def _load_mcp_tokens() -> dict:
    """Load {server_id: {access_token, refresh_token, expires_at, scope, token_type}}."""
    with _MCP_TOKENS_LOCK:
        return _load_json(MCP_TOKENS_FILE, {})


def _save_mcp_tokens(tokens: dict):
    """Write token store at mode 0600 — never accessible via any API endpoint.

    Uses os.open(O_CREAT|O_TRUNC, 0o600) + unique tmp name so the file is
    0600 from the instant of creation (no 0644 window) and concurrent savers
    don't clobber each other's tmp file.
    """
    with _MCP_TOKENS_LOCK:
        dir_ = os.path.dirname(MCP_TOKENS_FILE) or "."
        # mkstemp creates the file 0600 (no umask window)
        fd, tmp = tempfile.mkstemp(dir=dir_, prefix=".mcp_tokens_")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(tokens, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
        except Exception:
            os.unlink(tmp)
            raise
        os.replace(tmp, MCP_TOKENS_FILE)


# Per-server-id refresh lock: serialises the check→refresh→save critical section so
# concurrent callers on the same sid never each POST with the same (rotated) refresh
# token.  Mirrors the connect-lock-per-server pattern used in _MCP_RUNTIME.
_MCP_REFRESH_LOCKS: dict[str, threading.Lock] = {}
_MCP_REFRESH_LOCKS_LOCK = threading.Lock()


def _mcp_refresh_lock(sid: str) -> threading.Lock:
    """Return (creating if needed) the per-sid refresh lock."""
    with _MCP_REFRESH_LOCKS_LOCK:
        if sid not in _MCP_REFRESH_LOCKS:
            _MCP_REFRESH_LOCKS[sid] = threading.Lock()
        return _MCP_REFRESH_LOCKS[sid]


# In-memory PKCE/state dict: state_key -> {server_id, code_verifier, created_at, username}
# Keyed by the opaque `state` value sent to the provider.
# TTL enforced on read; never persisted to disk (a restart clears all pending flows).
_MCP_OAUTH_STATES: dict[str, dict] = {}
_MCP_OAUTH_STATES_LOCK = threading.Lock()


def _oauth_state_put(state_key: str, server_id: str, code_verifier: str, username: str,
                     redirect_uri: str = ""):
    with _MCP_OAUTH_STATES_LOCK:
        _oauth_state_expire()  # prune stale entries opportunistically
        _MCP_OAUTH_STATES[state_key] = {
            "server_id": server_id,
            "code_verifier": code_verifier,
            "created_at": time.time(),
            "username": username,
            # MED-2: redirect_uri pinned at flow start; reused byte-for-byte at exchange
            # (RFC 6749 §4.1.3 requires identity match).
            "redirect_uri": redirect_uri,
        }


def _oauth_state_pop(state_key: str) -> dict | None:
    """Return and remove the state entry if it exists and has not expired."""
    with _MCP_OAUTH_STATES_LOCK:
        entry = _MCP_OAUTH_STATES.pop(state_key, None)
    if entry is None:
        return None
    if time.time() - entry["created_at"] > _OAUTH_STATE_TTL:
        return None  # expired — treat as if it never existed
    return entry


def _oauth_state_expire():
    """Prune all entries older than _OAUTH_STATE_TTL (called under lock)."""
    now = time.time()
    expired = [k for k, v in _MCP_OAUTH_STATES.items()
               if now - v["created_at"] > _OAUTH_STATE_TTL]
    for k in expired:
        del _MCP_OAUTH_STATES[k]


# ---- PKCE S256 helpers (RFC 7636) ----

def _pkce_verifier() -> str:
    """Generate a cryptographically random code_verifier (64 urlsafe chars)."""
    return secrets.token_urlsafe(48)   # 48 bytes -> 64-char base64url, within [43,128]


def _pkce_challenge(verifier: str) -> str:
    """Return BASE64URL(SHA256(ASCII(verifier))) — S256 method per RFC 7636 §4.2."""
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def _mcp_auth_header(server: dict) -> str | None:
    """Return the value for the Authorization header, or None if no auth needed.

    For auth=='oauth': load (and refresh if needed) the stored access token.
    For auth=='bearer' (default): use the static token field.
    Raises RuntimeError if oauth is configured but no token is available (fail-closed).
    """
    auth = server.get("auth", "bearer")
    if auth == "oauth":
        token = _mcp_oauth_access_token(server)   # raises on failure
        return f"Bearer {token}"
    # bearer / legacy (no auth field) — use static token if present
    if server.get("token"):
        return f"Bearer {server['token']}"
    return None


_STDIO_BYTE_CAP = 256 * 1024  # 256 KB hard stop on stdout bytes consumed before newline


def _mcp_stdio_rpc(proc: "subprocess.Popen[str]", payload: dict, timeout: int) -> dict:
    """Send one JSON-RPC request over newline-delimited stdio; return the parsed response.

    Uses select(2) so the wall-clock deadline is enforced even when the child goes
    silent: if select times out, we raise immediately (fail closed) so the caller can
    kill the child.  MED-1: _STDIO_BYTE_CAP is applied to bytes consumed from the
    pipe, not to completed lines — a no-newline flood is aborted before OOM.
    """
    line_out = (json.dumps(payload) + "\n").encode()
    proc.stdin.write(line_out)
    proc.stdin.flush()
    rid = payload.get("id")
    _deadline = time.time() + timeout
    _bytes_read = 0
    _buf = b""
    fd = proc.stdout.fileno()

    while True:
        remaining = _deadline - time.time()
        if remaining <= 0:
            raise RuntimeError("MCP stdio stream deadline exceeded")

        # select with the wall-clock remainder — returns empty on timeout
        ready, _, _ = select.select([proc.stdout], [], [], remaining)
        if not ready:
            raise RuntimeError("MCP stdio stream deadline exceeded")

        # Read a chunk (non-blocking now that select said ready)
        chunk = os.read(fd, 4096)
        if not chunk:
            # EOF — child closed stdout
            raise RuntimeError("MCP stdio child closed stdout unexpectedly")

        _bytes_read += len(chunk)
        if _bytes_read > _STDIO_BYTE_CAP:
            raise RuntimeError("MCP stdio stream exceeded byte cap")

        _buf += chunk

        # Process all complete newline-delimited objects in the buffer
        while b"\n" in _buf:
            line_bytes, _buf = _buf.split(b"\n", 1)
            raw = line_bytes.decode(errors="replace").strip()
            if not raw:
                continue
            try:
                obj = json.loads(raw)
            except json.JSONDecodeError:
                continue  # skip non-JSON lines (e.g. child startup noise)
            # Notifications and log messages have no "id" — skip them
            if obj.get("id") != rid:
                continue
            if "error" in obj:
                raise RuntimeError(f"MCP error {obj['error'].get('code')}: "
                                   f"{obj['error'].get('message')}")
            return obj.get("result", {})


def _mcp_stdio_notify(proc: "subprocess.Popen[str]", payload: dict):
    """Send a JSON-RPC notification (no id) over stdio; fire-and-forget."""
    try:
        proc.stdin.write((json.dumps(payload) + "\n").encode())
        proc.stdin.flush()
    except Exception:
        pass


def _mcp_rpc(server: dict, method: str, params: dict, timeout: int = 30):
    """Route a JSON-RPC request to the right transport (http or stdio)."""
    transport = server.get("transport", "http")
    rid = uuid.uuid4().hex
    payload = {"jsonrpc": "2.0", "id": rid, "method": method, "params": params}

    if transport == "stdio":
        rt = _MCP_RUNTIME.get(server["id"], {})
        proc = rt.get("proc")
        if not proc or proc.poll() is not None:
            raise RuntimeError("MCP stdio child is not running")
        return _mcp_stdio_rpc(proc, payload, timeout)

    # ---- http path ----
    headers = {"Content-Type": "application/json",
               "Accept": "application/json, text/event-stream"}
    auth_hdr = _mcp_auth_header(server)
    if auth_hdr:
        headers["Authorization"] = auth_hdr
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
    """Send a JSON-RPC notification (no response expected) via the right transport."""
    transport = server.get("transport", "http")
    payload = {"jsonrpc": "2.0", "method": method, "params": params}

    if transport == "stdio":
        rt = _MCP_RUNTIME.get(server["id"], {})
        proc = rt.get("proc")
        if proc and proc.poll() is None:
            _mcp_stdio_notify(proc, payload)
        return

    # ---- http path ----
    headers = {"Content-Type": "application/json",
               "Accept": "application/json, text/event-stream"}
    try:
        auth_hdr = _mcp_auth_header(server)
    except RuntimeError:
        auth_hdr = None  # notifications are fire-and-forget; don't raise
    if auth_hdr:
        headers["Authorization"] = auth_hdr
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
    """initialize → notifications/initialized → tools/list; update _MCP_RUNTIME.

    Dispatches on server.get("transport","http"):
      "http"  — exactly the existing HTTP/SSE path (unchanged).
      "stdio" — spawns the child process ONCE, keeps it alive in _MCP_RUNTIME[sid]["proc"].

    MED-2: serialized per-sid via _mcp_connect_lock so concurrent refresh/warmup
    calls never spawn duplicate orphan children.
    """
    sid = server["id"]
    transport = server.get("transport", "http")

    with _mcp_connect_lock(sid):
        # Before overwriting runtime state, kill any existing live child so it is
        # never orphaned (handles the refresh/concurrent-connect race).
        _existing = _MCP_RUNTIME.get(sid, {})
        _existing_proc = _existing.get("proc")
        if _existing_proc and _existing_proc.poll() is None:
            try:
                _existing_proc.terminate()
                _existing_proc.wait(timeout=3)
            except Exception:
                try:
                    _existing_proc.kill()
                    _existing_proc.wait()
                except Exception:
                    pass

        _MCP_RUNTIME[sid] = {"session_id_header": None, "protocol_version": None,
                             "tools": [], "status": "connecting", "error": None,
                             "proc": None}
        try:
            if transport == "stdio":
                # ---- stdio path ----
                cmd = server.get("command", "")
                if not cmd:
                    raise ValueError("stdio MCP server missing 'command'")
                args_list = server.get("args", [])
                env_extra = server.get("env", {})
                child_env = {**os.environ, **env_extra}
                proc = subprocess.Popen(
                    [cmd, *args_list],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,  # HIGH-2: never accumulate stderr → no 64KB deadlock
                    env=child_env,
                    cwd=WORKSPACE_DIR,
                    # Never shell=True; args is always a list
                    # text=False: we use os.read on the raw fd in _mcp_stdio_rpc
                )
                _MCP_RUNTIME[sid]["proc"] = proc

                _connect_timeout = 30
                init_payload = {
                    "jsonrpc": "2.0", "id": uuid.uuid4().hex, "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-03-26",
                        "capabilities": {},
                        "clientInfo": {"name": "codemonkeys", "version": "0.1"},
                    },
                }
                init_result = _mcp_stdio_rpc(proc, init_payload, _connect_timeout)
                proto = init_result.get("protocolVersion", "2025-03-26")
                _MCP_RUNTIME[sid]["protocol_version"] = proto

                _mcp_stdio_notify(proc, {"jsonrpc": "2.0",
                                         "method": "notifications/initialized",
                                         "params": {}})

                tl_result = _mcp_stdio_rpc(proc,
                                           {"jsonrpc": "2.0", "id": uuid.uuid4().hex,
                                            "method": "tools/list", "params": {}},
                                           30)
                raw_tools = tl_result.get("tools", [])
                _MCP_RUNTIME[sid]["tools"] = raw_tools
                _MCP_RUNTIME[sid]["status"] = "connected"
                _MCP_RUNTIME[sid]["error"] = None
                return

            # ---- http path (auth via _mcp_auth_header: bearer or oauth) ----
            headers_pre = {"Content-Type": "application/json",
                           "Accept": "application/json, text/event-stream"}
            auth_hdr = _mcp_auth_header(server)   # raises if oauth configured but not connected
            if auth_hdr:
                headers_pre["Authorization"] = auth_hdr
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
            # If a stdio child was spawned but init failed, kill and reap it now
            _proc = _MCP_RUNTIME[sid].get("proc")
            if _proc and _proc.poll() is None:
                try:
                    _proc.terminate()
                    _proc.wait(timeout=3)
                except Exception:
                    try:
                        _proc.kill()
                        _proc.wait()  # LOW: reap zombie after kill
                    except Exception:
                        pass


def _mcp_disconnect(sid: str):
    """Remove runtime state; for stdio servers, terminate the child process.

    MED-2: holds the per-sid connect lock so disconnect cannot race with a
    concurrent _mcp_connect call for the same server.
    """
    with _mcp_connect_lock(sid):
        rt = _MCP_RUNTIME.pop(sid, {})
        proc = rt.get("proc")
        if proc and proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=3)
            except Exception:
                try:
                    proc.kill()
                    proc.wait()  # LOW: reap zombie after kill
                except Exception:
                    pass


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
    transport = srv.get("transport", "http")
    auth = srv.get("auth", "bearer")
    out = {
        "id": srv["id"],
        "name": srv["name"],
        "transport": transport,
        "auth": auth,
        "enabled": srv.get("enabled", True),
        "status": rt.get("status", "disconnected"),
        "error": rt.get("error"),
        "tools": tools_list,
    }
    if transport == "http":
        out["url"] = srv.get("url", "")
        if auth == "oauth":
            # Surface connected status — NEVER tokens, client_secret, or refresh_token
            tokens = _load_mcp_tokens()
            out["oauth_connected"] = bool(tokens.get(srv["id"], {}).get("access_token"))
            # Surface OAuth config (public fields only — client_secret excluded)
            oa = srv.get("oauth") or {}
            out["oauth_config"] = {
                "authorize_url": oa.get("authorize_url", ""),
                "token_url": oa.get("token_url", ""),
                "client_id": oa.get("client_id", ""),
                "scope": oa.get("scope", ""),
            }
        else:
            out["has_token"] = bool(srv.get("token"))
    else:
        # stdio: surface command but NEVER env/token values
        out["command"] = srv.get("command", "")
    return out


class OAuthConfig(BaseModel):
    authorize_url: str = ""
    token_url: str = ""
    client_id: str = ""
    client_secret: str = ""   # optional — public clients omit this
    scope: str = ""


class McpCreate(BaseModel):
    name: str
    transport: str = "http"   # "http" | "stdio"; absent = http (migration-safe)
    # http fields
    url: str = ""
    token: str = ""
    # auth type: "bearer" (default) | "oauth"
    auth: str = "bearer"
    oauth: OAuthConfig = OAuthConfig()
    # stdio fields
    command: str = ""
    args: list = []
    env: dict = {}


def _validate_https_url(url: str, label: str):
    """Raise HTTPException if url is not https (or http loopback)."""
    _parsed = urllib.parse.urlparse(url)
    _loopback = {"localhost", "127.0.0.1", "::1"}
    if not (_parsed.scheme == "https" or
            (_parsed.scheme == "http" and _parsed.hostname in _loopback)):
        raise HTTPException(400, f"{label} must use https://")


@app.get("/api/mcp")
def mcp_list(_: str = Depends(verify_owner)):
    servers = _load_mcp_config()
    return {"servers": [_mcp_entry_shape(s) for s in servers]}


@app.post("/api/mcp")
def mcp_add(req: McpCreate, _: str = Depends(verify_owner)):
    if not req.name.strip():
        raise HTTPException(400, "name is required")
    transport = req.transport if req.transport in ("http", "stdio") else "http"
    auth = req.auth if req.auth in ("bearer", "oauth") else "bearer"
    sid = uuid.uuid4().hex[:8]
    if transport == "http":
        url = req.url.strip()
        _validate_https_url(url, "url")
        if auth == "oauth":
            # Validate OAuth config
            az = req.oauth.authorize_url.strip()
            tz = req.oauth.token_url.strip()
            cid = req.oauth.client_id.strip()
            if not cid:
                raise HTTPException(400, "oauth.client_id is required for auth=oauth")
            _validate_https_url(az, "oauth.authorize_url")
            _validate_https_url(tz, "oauth.token_url")
            srv = {
                "id": sid, "name": req.name.strip(), "transport": "http",
                "url": url, "auth": "oauth", "enabled": True,
                "oauth": {
                    "authorize_url": az,
                    "token_url": tz,
                    "client_id": cid,
                    # client_secret stored in config (plaintext on /data — consistent
                    # with existing bearer token policy; see SECURITY.md)
                    "client_secret": req.oauth.client_secret,
                    "scope": req.oauth.scope.strip(),
                },
            }
        else:
            srv = {"id": sid, "name": req.name.strip(), "transport": "http",
                   "url": url, "token": req.token, "auth": "bearer", "enabled": True}
    else:
        cmd = req.command.strip()
        if not cmd:
            raise HTTPException(400, "command is required for stdio transport")
        srv = {"id": sid, "name": req.name.strip(), "transport": "stdio",
               "command": cmd, "args": list(req.args),
               "env": dict(req.env), "enabled": True}
    servers = _load_mcp_config()
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


# ---- OAuth 2.1 + PKCE endpoints ----

def _build_redirect_uri(request: Request) -> str:
    """Derive absolute redirect_uri from the incoming request's base URL.
    Never hardcoded — works on localhost and on Fly alike."""
    base = str(request.base_url).rstrip("/")
    return f"{base}/api/mcp/oauth/callback"


def _mcp_oauth_access_token(server: dict) -> str:
    """Return a valid access token for an oauth MCP server.

    If the stored token is expiring within 60 s, refresh it first.
    Raises RuntimeError (fail-closed) if no token is stored or refresh fails.
    The return value is used directly as a Bearer token in Authorization headers.

    Concurrency: a per-sid lock serialises the full check→refresh→save critical
    section.  Inside the lock we re-read the token store so a second thread that
    enters after a refresh is already complete will use the new token without
    making another network call (and will never reuse a rotated refresh token).
    """
    sid = server["id"]

    # Fast pre-check without the refresh lock: if no entry at all, fail now.
    tokens = _load_mcp_tokens()
    entry = tokens.get(sid)
    if not entry or not entry.get("access_token"):
        raise RuntimeError(f"MCP server '{server.get('name')}' is not OAuth-connected. "
                           "Complete the OAuth flow via the MCP settings panel.")

    # Acquire per-sid lock for the check→refresh→merge→save section.
    with _mcp_refresh_lock(sid):
        # Re-read inside the lock: another thread may have just refreshed.
        tokens = _load_mcp_tokens()
        entry = tokens.get(sid)
        if not entry or not entry.get("access_token"):
            raise RuntimeError(f"MCP server '{server.get('name')}' is not OAuth-connected. "
                               "Complete the OAuth flow via the MCP settings panel.")

        expires_at = entry.get("expires_at", 0)
        if not (expires_at and time.time() > expires_at - 60):
            # Token is still valid (either originally, or a sibling thread just refreshed it).
            return entry["access_token"]

        # Token needs refreshing.
        refresh_token = entry.get("refresh_token")
        if not refresh_token:
            raise RuntimeError(f"MCP server '{server.get('name')}' OAuth token expired "
                               "and no refresh_token available. Re-authorise via MCP settings.")

        oa = server.get("oauth") or {}
        token_url = oa.get("token_url", "")
        client_id = oa.get("client_id", "")
        client_secret = oa.get("client_secret", "")

        # HIGH-2(a): validate token_url before posting (defends bash-rewrites-config vector)
        _validate_https_url(token_url, "oauth.token_url")

        form = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_id,
        }
        if client_secret:
            form["client_secret"] = client_secret
        try:
            # HIGH-2(b): allow_redirects=False — a 307/308 would re-POST the
            # refresh_token+client_secret to wherever the Location header points.
            r = requests.post(token_url, data=form,
                              headers={"Content-Type": "application/x-www-form-urlencoded"},
                              timeout=30, allow_redirects=False)
            if r.is_redirect:
                raise RuntimeError("token endpoint issued an unexpected redirect")
            r.raise_for_status()
            tok = r.json()
        except RuntimeError:
            raise
        except Exception as exc:
            raise RuntimeError(f"OAuth token refresh failed for '{server.get('name')}': {exc}")

        # LOW-2: defensive expires_in coercion; absent/bad value → 300s conservative TTL
        try:
            expires_delta = int(tok["expires_in"])
        except (KeyError, TypeError, ValueError):
            expires_delta = 300

        new_entry = {
            "access_token": tok.get("access_token", entry["access_token"]),
            "refresh_token": tok.get("refresh_token", refresh_token),
            "token_type": tok.get("token_type", "bearer"),
            "scope": tok.get("scope", entry.get("scope", "")),
            "expires_at": time.time() + expires_delta,
        }
        # Merge only THIS sid into a freshly-loaded dict (no lost-update for other sids).
        fresh_tokens = _load_mcp_tokens()
        fresh_tokens[sid] = new_entry
        _save_mcp_tokens(fresh_tokens)
        return new_entry["access_token"]


@app.post("/api/mcp/{sid}/oauth/start")
def mcp_oauth_start(sid: str, request: Request, username: str = Depends(verify_owner)):
    """Build the OAuth 2.1 authorization URL with PKCE S256 and return it.
    The frontend opens this URL in a new window; the provider redirects back to
    /api/mcp/oauth/callback after the user grants consent."""
    servers = _load_mcp_config()
    srv = next((s for s in servers if s["id"] == sid), None)
    if not srv:
        raise HTTPException(404, "No such MCP server")
    if srv.get("auth") != "oauth":
        raise HTTPException(400, "Server is not configured for OAuth")
    oa = srv.get("oauth") or {}
    authorize_url = oa.get("authorize_url", "")
    client_id = oa.get("client_id", "")
    scope = oa.get("scope", "")
    if not authorize_url or not client_id:
        raise HTTPException(400, "OAuth server config incomplete (authorize_url and client_id required)")

    verifier = _pkce_verifier()
    challenge = _pkce_challenge(verifier)
    state_key = secrets.token_urlsafe(32)
    redirect_uri = _build_redirect_uri(request)

    # MED-2: pin redirect_uri in the state entry so /callback uses the byte-for-byte
    # same value regardless of how the callback request arrives (Host header, proxy, etc.)
    _oauth_state_put(state_key, sid, verifier, username, redirect_uri)

    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": scope,
        "state": state_key,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    full_url = authorize_url + ("&" if "?" in authorize_url else "?") + urllib.parse.urlencode(params)
    return {"authorize_url": full_url}


@app.get("/api/mcp/oauth/callback")
def mcp_oauth_callback(request: Request,
                       code: str = "", state: str = "", error: str = "",
                       error_description: str = ""):
    """OAuth 2.1 authorization code callback.

    Validates state (CSRF), exchanges code at the token endpoint with PKCE
    code_verifier, persists tokens in mcp_tokens.json (0600), returns a
    self-closing HTML page. Tokens are NEVER reflected in the response body.
    """
    # --- CSRF guard ---
    if not state:
        return HTMLResponse(_oauth_error_page("Missing state parameter."), status_code=400)
    entry = _oauth_state_pop(state)
    if entry is None:
        return HTMLResponse(_oauth_error_page("Unknown, expired, or already-used state. "
                                              "Please start the OAuth flow again."),
                            status_code=400)

    # --- Provider-reported error ---
    if error:
        return HTMLResponse(_oauth_error_page("The OAuth provider reported an error. "
                                              "Check the CodeMonkeys MCP settings and try again."),
                            status_code=400)
    if not code:
        return HTMLResponse(_oauth_error_page("No authorization code received."), status_code=400)

    # --- Look up server config ---
    servers = _load_mcp_config()
    srv = next((s for s in servers if s["id"] == entry["server_id"]), None)
    if not srv:
        return HTMLResponse(_oauth_error_page("MCP server no longer exists."), status_code=400)
    oa = srv.get("oauth") or {}

    token_url = oa.get("token_url", "")
    client_id = oa.get("client_id", "")
    client_secret = oa.get("client_secret", "")
    # MED-2: use the redirect_uri that was pinned in the state at /start — never
    # recompute from the current request (Host header may differ behind a proxy).
    redirect_uri = entry.get("redirect_uri") or _build_redirect_uri(request)
    code_verifier = entry["code_verifier"]

    # HIGH-2(a): validate token_url before posting (defends bash-rewrites-config vector)
    try:
        _validate_https_url(token_url, "oauth.token_url")
    except Exception:
        return HTMLResponse(_oauth_error_page("OAuth token endpoint is not https. "
                                              "Check MCP server config."), status_code=400)

    # --- Exchange authorization code ---
    form = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": client_id,
        "code_verifier": code_verifier,
    }
    if client_secret:
        form["client_secret"] = client_secret
    try:
        # HIGH-2(b): allow_redirects=False — a 307/308 would re-POST code+client_secret
        # to wherever the Location header points (SSRF / secret exfil vector).
        r = requests.post(token_url, data=form,
                          headers={"Content-Type": "application/x-www-form-urlencoded"},
                          timeout=30, allow_redirects=False)
        if r.is_redirect:
            return HTMLResponse(_oauth_error_page("Token exchange failed. Check server logs."),
                                status_code=500)
        r.raise_for_status()
        tok = r.json()
    except Exception:
        # Do not leak any details about the token exchange failure to the browser
        return HTMLResponse(_oauth_error_page("Token exchange failed. Check server logs."),
                            status_code=500)

    if not tok.get("access_token"):
        return HTMLResponse(_oauth_error_page("No access_token in provider response."),
                            status_code=500)

    # LOW-2: defensive expires_in coercion; absent/bad value → 300s conservative TTL
    try:
        expires_delta = int(tok["expires_in"])
    except (KeyError, TypeError, ValueError):
        expires_delta = 300

    # --- Persist tokens at mode 0600 ---
    new_entry = {
        "access_token": tok["access_token"],
        "refresh_token": tok.get("refresh_token", ""),
        "token_type": tok.get("token_type", "bearer"),
        "scope": tok.get("scope", oa.get("scope", "")),
        "expires_at": time.time() + expires_delta,
    }
    tokens = _load_mcp_tokens()
    tokens[entry["server_id"]] = new_entry
    _save_mcp_tokens(tokens)

    # Trigger a reconnect so the server can use the new token immediately
    if srv.get("enabled"):
        threading.Thread(target=_mcp_connect, args=(srv,), daemon=True).start()

    return HTMLResponse(_oauth_success_page())


def _oauth_success_page() -> str:
    return """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Connected</title>
<style>body{background:#050507;color:#e2e8f0;font-family:monospace;
display:flex;align-items:center;justify-content:center;height:100vh;margin:0;}
.box{text-align:center;padding:2rem;border:1px solid rgba(212,175,55,.45);border-radius:8px;}
h1{color:#d4af37;}</style></head>
<body><div class="box">
<h1>Connected</h1>
<p>OAuth authorisation successful. You can close this window.</p>
<script>window.close();</script>
</div></body></html>"""


def _oauth_error_page(reason: str) -> str:
    # reason must NOT contain any token, secret, or provider error detail
    from html import escape as _he
    safe_reason = _he(str(reason)[:200])
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>OAuth Error</title>
<style>body{{background:#050507;color:#e2e8f0;font-family:monospace;
display:flex;align-items:center;justify-content:center;height:100vh;margin:0;}}
.box{{text-align:center;padding:2rem;border:1px solid rgba(239,68,68,.45);border-radius:8px;}}
h1{{color:#ef4444;}}</style></head>
<body><div class="box">
<h1>OAuth Error</h1>
<p>{safe_reason}</p>
<p style="color:#475569;font-size:.8em;">Close this window and check the MCP settings panel.</p>
</div></body></html>"""


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


def _jail_specs(slug: str, artifact: str) -> str:
    """Resolve .codemonkeys/specs/<slug>/<artifact>.md, confined strictly to
    <WORKSPACE>/.codemonkeys/specs/ — tighter than _jail so plan mode can never
    reach code even via traversal or symlink."""
    specs_root = os.path.realpath(
        os.path.join(WORKSPACE_DIR, ".codemonkeys", "specs"))
    candidate = os.path.realpath(
        os.path.join(specs_root, slug, artifact + ".md"))
    if not candidate.startswith(specs_root + os.sep):
        raise ValueError(f"Path escapes specs dir: {slug}/{artifact}")
    return candidate


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
        if _is_risky(cmd):
            if not request_approval(session, cmd):
                return "DENIED: user rejected this command"
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


_PATCH_SIZE_CAP = 512 * 1024  # 512 KB — larger than any sane diff


def t_apply_patch(args):
    """Apply a standard unified diff (git-style) atomically to the workspace.

    The patch may touch one or more files.  Every target path is jail-checked
    before git apply is invoked; if any path escapes the workspace nothing is
    written and an error is returned.  /dev/null markers (new-file / delete)
    are handled — only the real side is jail-checked.
    """
    patch = args.get("patch", "")
    if not patch or not patch.strip():
        return "ERROR: patch is empty"
    if len(patch) > _PATCH_SIZE_CAP:
        return f"ERROR: patch exceeds size cap ({_PATCH_SIZE_CAP} bytes)"

    # --- Parse target paths from --- / +++ headers ---
    # Standard unified diff header lines look like:
    #   --- a/path/to/file   or   --- /dev/null
    #   +++ b/path/to/file   or   +++ /dev/null
    # We strip the a/ / b/ prefixes; /dev/null means new/deleted file (skip jail).
    _ab_prefix = re.compile(r"^[ab]/")
    target_paths = set()
    for line in patch.splitlines():
        if line.startswith("--- ") or line.startswith("+++ "):
            raw = line[4:].split("\t")[0].strip()  # strip optional timestamp
            if raw == "/dev/null":
                continue
            clean = _ab_prefix.sub("", raw)
            target_paths.add(clean)

    if not target_paths:
        return "ERROR: no target file paths found in patch headers"

    # --- Jail-check every path before touching the filesystem ---
    for p in target_paths:
        # Absolute paths are an explicit escape attempt
        if os.path.isabs(p):
            return f"ERROR: patch targets a path outside the workspace: {p}"
        try:
            _jail(p)
        except ValueError:
            return f"ERROR: patch targets a path outside the workspace: {p}"

    # --- Apply with git apply (atomic, works even without a git repo) ---
    patch_bytes = patch.encode()
    try:
        r = subprocess.run(
            ["git", "apply", "-"],
            input=patch_bytes,
            capture_output=True,
            cwd=WORKSPACE_DIR,
            timeout=60,
        )
    except subprocess.TimeoutExpired:
        return "ERROR: git apply timed out after 60s"
    except FileNotFoundError:
        return "ERROR: git is not installed in this environment"

    if r.returncode != 0:
        stderr = (r.stderr or b"").decode(errors="replace").strip()
        return ("ERROR: " + stderr)[:OUTPUT_CAP]

    n = len(target_paths)
    return f"Patch applied to {n} file(s): {', '.join(sorted(target_paths))}"


_SPEC_ARTIFACTS = ("constitution", "spec", "plan", "tasks")
# _SLUG_RE removed (was compiled but never referenced)

_PLAN_READONLY_TOOLS = frozenset({"read_file", "list_dir", "glob_files", "grep",
                                  "blackboard_read"})


def t_save_spec(args):
    """Plan-mode write affordance: persist a PRD artifact under
    .codemonkeys/specs/<slug>/<artifact>.md.  Confined to that subtree only."""
    slug_raw = args.get("slug", "")
    artifact = args.get("artifact", "")
    content = args.get("content", "")

    # --- slug sanitization + length cap (NAME_MAX guard) ---
    slug = re.sub(r"[^a-z0-9]+", "-", slug_raw.lower()).strip("-")
    slug = slug[:64].rstrip("-")
    if not slug:
        return "ERROR: slug is empty or produced no valid characters after sanitization"

    # --- artifact enum guard ---
    if artifact not in _SPEC_ARTIFACTS:
        return f"ERROR: artifact must be one of {_SPEC_ARTIFACTS}, got {artifact!r}"

    # --- content cap ---
    if len(content) > READ_CAP:
        content = content[:READ_CAP]

    # --- jail: confine to .codemonkeys/specs/ only ---
    try:
        full = _jail_specs(slug, artifact)
    except ValueError as e:
        return f"ERROR: {e}"

    os.makedirs(os.path.dirname(full), exist_ok=True)
    # O_NOFOLLOW: refuse to open if the final path component is a symlink
    # (closes a TOCTOU window between _jail_specs realpath check and open).
    try:
        fd = os.open(full, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o644)
    except OSError as e:
        return f"ERROR: could not open spec file for writing: {e}"
    with os.fdopen(fd, "w") as f:
        f.write(content)
    rel = os.path.join(".codemonkeys", "specs", slug, artifact + ".md")
    return f"Saved {len(content)} chars → {rel}"


# ---- cross-session blackboard memory (IDEATION #4) -------------------------
# A persistent FACTS/DECISIONS/NEXT note per task, confined to
# <WORKSPACE>/.codemonkeys/blackboard-<slug>.md, that survives session resets:
# existing blackboards are injected into the commander prompt at session start.
# Same jail discipline as save_spec. blackboard_read is read-only (all modes);
# blackboard_write is a default/auto-only write (NOT in plan mode — plan's only
# write affordance stays save_spec, preserving the read-only-end-to-end invariant).
_BB_SECTIONS = ("FACTS", "DECISIONS", "NEXT")
_BB_MAX = READ_CAP                 # per-file content cap


def _bb_slug(raw: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (raw or "").lower()).strip("-")[:64].rstrip("-")


def _jail_blackboard(slug: str) -> str:
    """Resolve .codemonkeys/blackboard-<slug>.md, confined strictly to
    <WORKSPACE>/.codemonkeys/ (no subdir, no traversal)."""
    root = os.path.realpath(os.path.join(WORKSPACE_DIR, ".codemonkeys"))
    candidate = os.path.realpath(os.path.join(root, f"blackboard-{slug}.md"))
    if os.path.dirname(candidate) != root:
        raise ValueError(f"Path escapes .codemonkeys dir: {slug}")
    return candidate


def _bb_parse(text: str) -> dict:
    """Split a blackboard markdown body into its canonical sections."""
    sections = {s: "" for s in _BB_SECTIONS}
    current = None
    for line in text.splitlines():
        m = re.match(r"^##\s+(\w+)", line)
        if m and m.group(1).upper() in sections:
            current = m.group(1).upper()
            continue
        if current:
            sections[current] += line + "\n"
    return {k: v.strip() for k, v in sections.items()}


def _bb_render(slug: str, sections: dict) -> str:
    out = [f"# Blackboard — {slug}", ""]
    for s in _BB_SECTIONS:
        out.append(f"## {s}")
        out.append(sections.get(s, "").strip() or "_(none yet)_")
        out.append("")
    return "\n".join(out).strip() + "\n"


def t_blackboard_read(args):
    slug = _bb_slug(args.get("slug", ""))
    if not slug:
        return "ERROR: slug is empty after sanitization"
    try:
        full = _jail_blackboard(slug)
    except ValueError as e:
        return f"ERROR: {e}"
    if not os.path.exists(full):
        return f"(no blackboard yet for '{slug}' — create one with blackboard_write)"
    with open(full, "r", errors="replace") as f:
        return f.read(_BB_MAX + 1)[:_BB_MAX]


def t_blackboard_write(args):
    slug = _bb_slug(args.get("slug", ""))
    section = str(args.get("section", "")).upper()
    content = (args.get("content", "") or "").strip()
    mode = args.get("mode", "append")
    if not slug:
        return "ERROR: slug is empty after sanitization"
    if section not in _BB_SECTIONS:
        return f"ERROR: section must be one of {_BB_SECTIONS}, got {section!r}"
    if mode not in ("append", "replace"):
        return "ERROR: mode must be 'append' or 'replace'"
    try:
        full = _jail_blackboard(slug)
    except ValueError as e:
        return f"ERROR: {e}"
    existing = ""
    if os.path.exists(full):
        with open(full, "r", errors="replace") as f:
            existing = f.read()
    sections = _bb_parse(existing)
    if mode == "replace":
        sections[section] = content
    else:
        bullet = content if content.startswith(("-", "*")) else f"- {content}"
        sections[section] = (sections[section] + "\n" + bullet).strip()
    rendered = _bb_render(slug, sections)
    if len(rendered) > _BB_MAX:
        return (f"ERROR: blackboard would exceed {_BB_MAX} chars — "
                "replace/trim a section instead of appending")
    os.makedirs(os.path.dirname(full), exist_ok=True)
    # O_NOFOLLOW (when the platform has it) closes the realpath→open symlink
    # TOCTOU; falls back to 0 on Windows dev hosts where the flag is absent.
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(full, flags, 0o644)
    except OSError as e:
        return f"ERROR: could not open blackboard for writing: {e}"
    with os.fdopen(fd, "w") as f:
        f.write(rendered)
    return f"Updated {section} ({mode}) → .codemonkeys/blackboard-{slug}.md"


def _blackboard_context() -> str:
    """Inject existing blackboards into the commander prompt — this is what makes
    the memory survive session resets. Bounded so a large board can't blow context."""
    root = os.path.realpath(os.path.join(WORKSPACE_DIR, ".codemonkeys"))
    try:
        files = sorted(f for f in os.listdir(root)
                       if f.startswith("blackboard-") and f.endswith(".md"))
    except OSError:
        return ""
    if not files:
        return ""
    chunks, total = [], 0
    for fn in files:
        try:
            with open(os.path.join(root, fn), "r", errors="replace") as f:
                body = f.read(4000)
        except OSError:
            continue
        chunk = f"\n--- {fn} ---\n{body}\n"
        if total + len(chunk) > 8000:
            chunks.append("\n…[more blackboards truncated]")
            break
        chunks.append(chunk)
        total += len(chunk)
    return (
        "\n\nPERSISTENT BLACKBOARD (cross-session memory — survives session "
        "resets). Read with blackboard_read(slug); in default/auto mode record "
        "durable FACTS, DECISIONS, and NEXT steps with blackboard_write(slug, "
        "section, content, mode). Current state:\n" + "".join(chunks))


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
    "save_spec": {"name": "save_spec",
                  "description":
                      "Persist a PRD artifact for a project plan. Writes "
                      ".codemonkeys/specs/<slug>/<artifact>.md inside the workspace. "
                      "PLAN MODE ONLY write affordance — cannot reach any code path. "
                      "Call once per artifact; re-calling overwrites that artifact. "
                      "artifact must be one of: constitution, spec, plan, tasks. "
                      "constitution = durable principles/constraints/non-negotiables. "
                      "spec = WHAT: problem, goals, non-goals, acceptance criteria. "
                      "plan = HOW: approach, architecture, files touched, risks, sequence. "
                      "tasks = decomposed checklist; each item must include a verification step.",
                  "parameters": {"type": "object", "properties": {
                      "slug": {"type": "string",
                               "description": "Short project identifier, e.g. 'auth-refactor'. "
                                              "Lowercased; non-alphanumeric chars become hyphens."},
                      "artifact": {"type": "string",
                                   "enum": ["constitution", "spec", "plan", "tasks"],
                                   "description": "Which artifact to write."},
                      "content": {"type": "string",
                                  "description": "Full markdown content for this artifact."}},
                      "required": ["slug", "artifact", "content"]}},
    "blackboard_read": {"name": "blackboard_read",
                        "description":
                            "Read the persistent cross-session blackboard for a task "
                            "(.codemonkeys/blackboard-<slug>.md): durable FACTS, DECISIONS, "
                            "and NEXT steps that survive session resets. Read-only; "
                            "available in every mode.",
                        "parameters": {"type": "object", "properties": {
                            "slug": {"type": "string",
                                     "description": "Task identifier, e.g. 'auth-refactor'. "
                                                    "Lowercased; non-alphanumerics become hyphens."}},
                            "required": ["slug"]}},
    "blackboard_write": {"name": "blackboard_write",
                         "description":
                             "Update the persistent cross-session blackboard for a task. "
                             "Confined to .codemonkeys/blackboard-<slug>.md (cannot reach code). "
                             "Use it to record durable knowledge so a future session can resume: "
                             "FACTS (established truths), DECISIONS (choices + rationale), NEXT "
                             "(remaining steps). mode 'append' adds a bullet; 'replace' rewrites "
                             "the whole section (use for NEXT as it changes).",
                         "parameters": {"type": "object", "properties": {
                             "slug": {"type": "string", "description": "Task identifier."},
                             "section": {"type": "string", "enum": ["FACTS", "DECISIONS", "NEXT"]},
                             "content": {"type": "string", "description": "Text to add or set."},
                             "mode": {"type": "string", "enum": ["append", "replace"],
                                      "description": "Default 'append'."}},
                             "required": ["slug", "section", "content"]}},
    "apply_patch": {"name": "apply_patch",
                    "description":
                        "Apply a standard unified diff (git-style) to one or more files in the "
                        "workspace.  Produce a normal `git diff` / `diff -u` patch with "
                        "workspace-relative paths (e.g. `--- a/src/foo.py` / `+++ b/src/foo.py`). "
                        "The patch is applied atomically — either every hunk succeeds or nothing "
                        "is written.  On failure the exact git reject reason is returned so you "
                        "can correct the diff and retry.  Paths that escape the workspace are "
                        "rejected before any write occurs.",
                    "parameters": {"type": "object", "properties": {
                        "patch": {"type": "string",
                                  "description": "A complete unified diff string (git format)."}},
                        "required": ["patch"]}},
}

# Daystrom frontmatter tools -> our runtime tools
CORPS_TOOL_MAP = {
    "Read": ["read_file", "list_dir"],
    "Grep": ["grep"],
    "Glob": ["glob_files", "list_dir"],
    "Bash": ["bash"],
    "Edit": ["edit_file", "apply_patch"],
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
        + _blackboard_context()
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
            if name == "apply_patch":
                r = t_apply_patch(args)
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
            if name == "save_spec":
                r = t_save_spec(args)
                return r, not r.startswith("ERROR")
            if name == "blackboard_read":
                return t_blackboard_read(args), True
            if name == "blackboard_write":
                r = t_blackboard_write(args)
                return r, not r.startswith("ERROR")
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
    # Plan mode must stay read-only even through subagents: a subagent spawned
    # from a plan-mode session must not gain write_file/edit_file/bash/save_spec.
    # save_spec is reserved for the top-level planner, not arbitrary subagents.
    if session.get("mode") == "plan":
        filtered = [t for t in tool_names if t in _PLAN_READONLY_TOOLS]
        tool_names = filtered if filtered else list(_PLAN_READONLY_TOOLS)
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
        "\n\nMODE: PLAN — SPEC-FIRST WORKFLOW.\n"
        "You have read-only workspace tools (read_file, list_dir, glob_files, grep, "
        "spawn_agent) plus ONE write affordance: save_spec. You MUST NOT use "
        "write_file, edit_file, or bash. save_spec writes exclusively to "
        ".codemonkeys/specs/<slug>/ and cannot reach code.\n\n"
        "REQUIRED WORKFLOW — execute in order:\n"
        "1. INVESTIGATE. Read the workspace: entry points, existing tests, "
        "CLAUDE.md / CONSTITUTION.md / docs/STATE.md, any existing "
        ".codemonkeys/specs/<slug>/ artifacts. Use grep/glob as needed.\n"
        "2. CHOOSE A SLUG. Short, lowercase, hyphenated identifier for this "
        "initiative, e.g. 'auth-refactor'.\n"
        "3. PRODUCE FOUR ARTIFACTS via save_spec (one call per artifact):\n"
        "   a. constitution — durable project principles: security invariants, "
        "style rules, scope guardrails, non-negotiables. If a CONSTITUTION.md or "
        "prior .codemonkeys/specs/<slug>/constitution.md exists, read it first "
        "and refine rather than overwrite blindly.\n"
        "   b. spec — WHAT to build: problem statement, goals, explicit non-goals, "
        "user-visible behavior, acceptance criteria.\n"
        "   c. plan — HOW: approach, architecture, which files are touched, "
        "risks and mitigations, sequencing rationale.\n"
        "   d. tasks — decomposed checklist. Every item MUST carry its own "
        "verification step, e.g.:\n"
        "      - [ ] T1 Add foo() to bar.py — verify: "
        "`./.venv/bin/python -c 'from bar import foo'`\n"
        "4. SUMMARIZE. After all four saves, print a short summary: "
        "list the artifact paths, call out any open questions or risks, "
        "and tell the user to switch to default or auto mode to execute tasks.\n\n"
        "HARD RULES: save_spec is the ONLY thing you may write in plan mode. "
        "Do not modify source code, configs, tests, or anything outside "
        ".codemonkeys/specs/. Present the plan; do not execute it."),
    "default": (
        "\n\nMODE: DEFAULT. Implement the work. Pushes, deploys, and destructive "
        "commands will pause for the user's approval — that is expected."),
    "auto": (
        "\n\nMODE: AUTO. Full autonomy — every command runs without approval, "
        "including pushes and deploys. Be careful and deliberate; the user is "
        "trusting you to ship. Still work on a branch for non-trivial changes."
        "\n\nSELF-HEAL PROTOCOL. After every change, verify before moving on: "
        "if tests exist (pytest, npm test, etc.) run them; else run the best "
        "available linter (ruff for Python, tsc --noEmit for TypeScript); else "
        "do a smoke import/build. Read the full output. If it fails: make the "
        "smallest targeted fix, then rerun the same verify command. Repeat until "
        "green. Hard stops — do NOT continue iterating if: (a) the verify command "
        "exits 0 (done); (b) the same failure signature appears twice in a row "
        "(you are blocked — stop, report exactly what is failing and why, and "
        "what you tried); (c) you have iterated 5 self-heal cycles without going "
        "green (stop and report). Never exceed the session budget or max-turns "
        "cap. When blocked, state the blocker plainly so the user can act."),
}
PLAN_TOOLS = ["read_file", "list_dir", "glob_files", "grep", "spawn_agent",
              "save_spec", "blackboard_read"]
FULL_TOOLS = ["read_file", "write_file", "edit_file", "apply_patch", "list_dir",
              "glob_files", "grep", "bash", "spawn_agent",
              "blackboard_read", "blackboard_write"]


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


class NoCacheStaticFiles(StaticFiles):
    """Serve static files with Cache-Control: no-cache so browsers revalidate
    (ETag/304 — cheap) instead of running stale JS after a deploy."""

    def file_response(self, *args, **kwargs):
        resp = super().file_response(*args, **kwargs)
        resp.headers["Cache-Control"] = "no-cache"
        return resp


app.mount("/static", NoCacheStaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")


@app.get("/")
def root():
    return FileResponse(
        os.path.join(BASE_DIR, "static", "forge", "index.html"),
        headers={"Cache-Control": "no-cache"},
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))
