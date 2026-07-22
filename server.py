#!/usr/bin/env python3
"""CodeMonkeys â€” self-hosted, multi-provider AI coding console.

Single-file FastAPI backend:
  - Auth: username + mandatory per-user TOTP, HMAC session tokens
  - Models: any OpenAI-compatible endpoint (Gemini, OpenRouter, DeepSeek, ...)
            plus native Anthropic â€” configured at runtime, keys on /data
  - Agent loop: Claude Code-style tool loop, workspace-jailed
  - Subagents: Daystrom agent corps (corps/agents/*.md) with tool allowlists,
               tier-routed models, and spawn caps
  - Cost governor: per-provider tier (t0..t3) + per-session USD budget
  - Safety: human approval gate for push/deploy/destructive commands

Storage: JSON files under DATA_DIR (no database). Frontend: static/forge/.
"""

import base64
import difflib
import fnmatch
import hashlib
from typing import Optional
import hmac
import io
import json
import logging
import math
import os
import re
import secrets
import select
import shlex
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
import urllib.request
import uuid

_log = logging.getLogger(__name__)

import pyotp
import requests
from enum import Enum
from typing import Optional, List, Dict, Union
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import (FileResponse, HTMLResponse, JSONResponse,
                               PlainTextResponse)
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

try:
    import segno          # pure-python QR; renders the TOTP secret locally
except ImportError:       # falls back to manual-entry (never to an external CDN)
    segno = None

try:
    from cryptography.fernet import Fernet, InvalidToken as _FernetInvalidToken
    _FERNET_AVAILABLE = True
except ImportError:
    Fernet = None  # type: ignore[assignment,misc]
    _FernetInvalidToken = Exception  # type: ignore[assignment,misc]
    _FERNET_AVAILABLE = False

try:
    import google.auth
    import google.auth.transport.requests as _google_auth_requests
    _GOOGLE_AUTH_AVAILABLE = True
except ImportError:
    google = None  # type: ignore[assignment]
    _google_auth_requests = None  # type: ignore[assignment]
    _GOOGLE_AUTH_AVAILABLE = False

try:
    from pywebpush import WebPushException, webpush
    _WEBPUSH_AVAILABLE = True
except ImportError:
    WebPushException = Exception  # type: ignore[assignment,misc]
    webpush = None  # type: ignore[assignment]
    _WEBPUSH_AVAILABLE = False

# ----------------------------------------------------------------- config

def _app_base_dir() -> str:
    """Repo root in source checkouts; PyInstaller extract dir when frozen."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return sys._MEIPASS  # type: ignore[attr-defined]
    return os.path.dirname(os.path.abspath(__file__))


BASE_DIR = _app_base_dir()
# Desktop launcher sets DATA_DIR to %APPDATA%\\codemonkeys\\data (or XDG).
DATA_DIR = os.environ.get("DATA_DIR", os.path.join(BASE_DIR, "data"))
CM_DESKTOP = os.environ.get("CM_DESKTOP", "").strip() in ("1", "true", "yes")


def _vertex_config_dir():
    """Cross-platform config dir: ~/.config/codemonkeys (Linux/macOS) or %APPDATA%\\codemonkeys (Windows)."""
    if os.name == "nt":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        return os.path.join(base, "codemonkeys")
    xdg = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return os.path.join(xdg, "codemonkeys")


def _load_env_file(path):
    """Load KEY=VALUE lines into os.environ (never override keys already set)."""
    try:
        with open(path) as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = val
    except OSError as e:
        _log.debug("vertex env file %s unreadable: %s", path, e)


def _load_portable_vertex_env():
    """Portable Vertex/GCP settings â€” same paths on Linux, macOS, and Windows."""
    cfg = _vertex_config_dir()
    for path in (
        os.path.join(cfg, "vertex.env"),
        os.path.join(BASE_DIR, "vertex.env"),
        os.path.join(BASE_DIR, ".vertex.env"),
    ):
        if os.path.isfile(path):
            _load_env_file(path)
    sa_path = os.path.join(cfg, "vertex-sa.json")
    if os.path.isfile(sa_path) and not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = sa_path


_load_portable_vertex_env()
VERTEX_PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT", "gen-lang-client-0246315501")
VERTEX_REGION = os.environ.get("GOOGLE_CLOUD_REGION", "global")
USERS_FILE = os.environ.get("USERS_FILE", os.path.join(DATA_DIR, "users.json"))
FEEDBACK_FILE = os.path.join(DATA_DIR, "feedback.jsonl")
FEEDBACK_SHOT_DIR = os.path.join(DATA_DIR, "feedback_shots")
FEEDBACK_STATUS_FILE = os.path.join(DATA_DIR, "feedback_status.json")
FEEDBACK_CATEGORIES = {"bug", "improvement", "question"}
FEEDBACK_STATUSES = {"new", "planned", "fixed", "dismissed"}
FEEDBACK_MAX_MESSAGE = 4000
FEEDBACK_MAX_CONTEXT = 1000
FEEDBACK_MAX_BYTES = 5 * 1024 * 1024
FEEDBACK_SHOT_MAX_B64 = 2 * 1024 * 1024
FEEDBACK_SHOT_DIR_MAX = 50 * 1024 * 1024
FEEDBACK_RATE_MAX = 8
FEEDBACK_RATE_WINDOW = 3600
FEEDBACK_SHOT_PREFIXES = {"data:image/jpeg;base64,": ".jpg", "data:image/png;base64,": ".png"}
_feedback_hits = {}  # user -> [timestamps]
MODELS_FILE = os.path.join(DATA_DIR, "model_config.json")
MODEL_CATALOG_FILE = os.path.join(DATA_DIR, "model_catalog.json")
MASTER_KEY_FILE = os.path.join(DATA_DIR, "master.key")
MCP_CONFIG_FILE = os.path.join(DATA_DIR, "mcp_config.json")
FEATURE_FLAGS_FILE = os.path.join(DATA_DIR, "feature_flags.json")
SESSIONS_DIR = os.path.join(DATA_DIR, "sessions")
WORKSPACE_DIR = os.environ.get("WORKSPACE_DIR", os.path.join(DATA_DIR, "workspace"))
SECRET_FILE = os.path.join(DATA_DIR, "session_secret.key")
CORPS_DIR = os.path.join(BASE_DIR, "corps", "agents")
CORPS_SKILLS_DIR = os.path.join(BASE_DIR, "corps", "skills")
CORPS_HOOKS_FILE = os.path.join(BASE_DIR, "corps", "hooks.json")
_AGENTS_CONFIG_MAX_BYTES = 256_000
_DEFAULT_HOOKS_DOC = {"version": 1, "hooks": {}}

MCP_TOKENS_FILE = os.path.join(DATA_DIR, "mcp_tokens.json")
VERTEX_USER_CREDS_DIR = os.path.join(DATA_DIR, "vertex_user")
DAILY_SPEND_FILE = os.path.join(DATA_DIR, "daily_spend.json")
VERTEX_ACCESS_OFF = "off"
VERTEX_ACCESS_ASSIGNED = "assigned"   # owner's server GCP creds â€” no member setup
VERTEX_ACCESS_BYO = "byo"             # member uploads service account JSON (PA handoff)
VERTEX_SA_ROLE = "roles/aiplatform.user"
VERTEX_SA_PREFIX = "cm-"
_GCP_API_TIMEOUT = 30
# OAuth state entries expire after this many seconds (short window reduces CSRF exposure)
_OAUTH_STATE_TTL = 600

SESSION_TTL = 7 * 24 * 3600
OPEN_ENROLLMENT = os.environ.get("OPEN_ENROLLMENT", "false").lower() == "true"
# Commercial hosted seats (docs/COMMERCIAL.md): $1/mo CodeMonkeys sold by
# OmniTender Systems LLC. Fail-closed OFF until Stripe secrets are set AND
# BILLING_ENABLED=true â€” self-host / desktop unchanged.
STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "").strip()
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "").strip()
STRIPE_PRICE_ID = os.environ.get("STRIPE_PRICE_ID", "").strip()
BILLING_ENABLED = (
    os.environ.get("BILLING_ENABLED", "false").lower() == "true"
    and bool(STRIPE_SECRET_KEY and STRIPE_WEBHOOK_SECRET and STRIPE_PRICE_ID)
)
BILLING_PRICE_USD = float(os.environ.get("BILLING_PRICE_USD", "1.00"))
BILLING_SELLER = os.environ.get(
    "BILLING_SELLER", "OmniTender Systems LLC"
).strip() or "OmniTender Systems LLC"
BILLING_PRODUCT = os.environ.get("BILLING_PRODUCT", "CodeMonkeys").strip() or "CodeMonkeys"
SUBSCRIPTIONS_FILE = os.path.join(DATA_DIR, "subscriptions.json")
_SUBSCRIPTIONS_LOCK = threading.Lock()
_FREE_PACK_MODELS = [
    "qwen/qwen3-coder:free",
    "deepseek/deepseek-r1:free",
    "openai/gpt-oss-120b:free",
]
# Login brute-force throttle (fail2ban-style; SECURITY.md "no login rate-limit"):
# after LOGIN_MAX_FAILS bad attempts within LOGIN_WINDOW_SEC, lock that account
# for LOGIN_LOCKOUT_SEC. PBKDF2+TOTP already make brute force slow; this bounds it.
LOGIN_MAX_FAILS = int(os.environ.get("LOGIN_MAX_FAILS", "10"))
LOGIN_WINDOW_SEC = int(os.environ.get("LOGIN_WINDOW_SEC", "300"))
LOGIN_LOCKOUT_SEC = int(os.environ.get("LOGIN_LOCKOUT_SEC", "900"))
LOGIN_TRACK_CAP = 4096     # max distinct keys tracked â€” bounds memory vs username-spam
# Two extra throttle dimensions layered on top of the per-username lock, required
# before OPEN_ENROLLMENT widens the attack surface (SECURITY.md "Add an IP/global
# dimension..."). Both share LOGIN_WINDOW_SEC / LOGIN_LOCKOUT_SEC. A threshold of
# <= 0 DISABLES that dimension (escape hatch / restores pre-#13 per-account-only
# behaviour). IP defaults sit above the per-account default so a single source can
# brute a couple of accounts before its IP trips; the global ceiling is a
# system-wide circuit-breaker for distributed guessing across many usernames/IPs.
LOGIN_IP_MAX_FAILS = int(os.environ.get("LOGIN_IP_MAX_FAILS", "30"))
LOGIN_GLOBAL_MAX_FAILS = int(os.environ.get("LOGIN_GLOBAL_MAX_FAILS", "200"))
# Persistent lock store: the throttle state is written through to disk so locks
# and in-window counters SURVIVE A RESTART (the pre-#13 in-memory tracker was
# fail-open on restart). Lives under DATA_DIR like users.json / mcp_tokens.json.
LOGIN_THROTTLE_FILE = os.path.join(DATA_DIR, "login_throttle.json")
PUSH_SUBS_FILE = os.path.join(DATA_DIR, "push_subscriptions.json")
PUSH_VAPID_FILE = os.path.join(DATA_DIR, "push_vapid.json")
PUSH_VAPID_SUBJECT = os.environ.get("VAPID_SUBJECT", "mailto:owner@codemonkeys.local")
_PUSH_LOCK = threading.Lock()
# M-7 real erasure (constitution invariant, OWNER-RATIFIED Option A). When an
# account is erased we hard-delete every per-user store, write a TOMBSTONE so the
# id can never be reactivated/re-registered into residue, and append an
# owner-auditable erasure RECEIPT. Both live under DATA_DIR (/data) like users.json.
ERASED_FILE = os.path.join(DATA_DIR, "erased_accounts.json")          # tombstone
ERASURE_RECEIPTS_FILE = os.path.join(DATA_DIR, "erasure_receipts.jsonl")  # receipts
ROLE_RECEIPTS_FILE = os.path.join(DATA_DIR, "role_receipts.jsonl")    # promote/demote receipts
# S-3 (issue #68) â€” hash-chained tamper-evident audit trail.  Every safelisted
# security event (see _AUDIT_SAFELIST) and every erasure receipt is ALSO
# appended to this chain: each entry commits to the previous entry's SHA-256,
# so mutation/deletion/insertion/reorder of any entry is detectable by
# verify_audit_chain() (owner endpoint /api/audit/verify, CLI
# scripts/verify_audit_chain.py).  The head file records the current tail so
# truncation of the newest entries is detectable too.
AUDIT_CHAIN_FILE = os.path.join(DATA_DIR, "audit_chain.jsonl")
AUDIT_CHAIN_HEAD_FILE = os.path.join(DATA_DIR, "audit_chain.head.json")
# M-4 cloud-egress consent (Tier B invariant, issue #67): a recorded, revocable,
# per-user consent decision gating any egress of a user's content to a
# third-party model provider. The record lives under DATA_DIR like users.json;
# the gate sits in call_model (the single chokepoint every outbound LLM call
# goes through) and FAILS CLOSED. EGRESS_CONSENT_MODE decides what an ABSENT
# record means:
#   "explicit" (default, OWNER-RATIFIED 2026-07-13, issue #67) â€” an affirmative
#       per-user grant is required; absent â†’ blocked.
#   "byok-implied" â€” the owner-configured BYO keys are read as org-level
#       consent, so absent â†’ allowed. An explicit per-user REVOCATION always
#       blocks, in every mode, regardless of which reading is active.
# Owner decision (issue #67 "Owner-reserved"): BYO-key does NOT by itself
# constitute consent for member content; an explicit per-user gate is required.
# Reverting to the looser reading is `EGRESS_CONSENT_MODE=byok-implied` â€” no
# code change.
EGRESS_CONSENT_FILE = os.path.join(DATA_DIR, "egress_consent.json")
_EGRESS_CONSENT_MODES = ("byok-implied", "explicit")
_EGRESS_CONSENT_HISTORY_CAP = 20   # bounded per-user grant/revoke audit trail
# M-8 backup posture (Tier B invariant): GOVERNANCE.md requires the backup path
# to be VERIFIED, not just documented â€” "test: restore drill + receipt". CM's
# data lives on the Fly volume `cm_data` at /data (docs/RECOVERY.md); its backup
# notion is the Fly volume snapshot. run_backup_drill() (below, near the M-7
# receipt code) proves a tree is restorable-in-practice by reading back and
# validating every structured store CM writes, and appends a timestamped receipt
# here â€” same append-only JSONL idiom as erasure_receipts.jsonl. Owner-only
# viewer: GET /api/backup/drill-history; trigger: POST /api/backup/drill or
# scripts/backup_drill.py (fly ssh console, or against a restored snapshot copy).
BACKUP_DRILL_RECEIPTS_FILE = os.path.join(DATA_DIR, "backup_drill_receipts.jsonl")
_BACKUP_DRILL_HISTORY_CAP = 100    # newest receipts returned by the owner endpoint
SESSION_BUDGET_USD = float(os.environ.get("SESSION_BUDGET_USD", "5.00"))
# Ceiling for a per-session budget override (W10) â€” a client can't set a runaway cap.
SESSION_BUDGET_MAX_USD = float(os.environ.get("SESSION_BUDGET_MAX_USD", "50.00"))
# H-2: per-session budget ceiling for Member-role users (not Owners).  Defaults
# to SESSION_BUDGET_USD so Members can't silently escalate beyond the global
# default.  Set MEMBER_SESSION_BUDGET_MAX_USD to raise it intentionally.
MEMBER_SESSION_BUDGET_MAX_USD = float(
    os.environ.get("MEMBER_SESSION_BUDGET_MAX_USD", str(SESSION_BUDGET_USD))
)
# N2 rolling daily spend cap across ALL sessions. Unset or <=0 â†’ no daily cap
# (fully backward compatible). When set, agent_loop halts ANY run that would push
# today's cumulative spend over the ceiling.
_raw_daily_cap = os.environ.get("SPEND_DAILY_CAP_USD", "")
SPEND_DAILY_CAP_USD: float = float(_raw_daily_cap) if _raw_daily_cap else 0.0
# Budget fallback threshold â€” when session spend hits this, switch to a free
# model so the session keeps running instead of dying at the budget ceiling.
BUDGET_FALLBACK_USD = float(os.environ.get("BUDGET_FALLBACK_USD", "0.10"))
# Free-tier fallback models, tried in order.  Gemini has rate limits but no
# hard daily cap; OpenRouter free models have daily request limits.
_FREE_FALLBACK = [
    ("vertex-gemini", "google/gemini-2.5-flash"),  # GCP billing credits first
    ("gemini", "gemini-2.5-flash"),        # generous rate limits, no daily cap
    ("openrouter", "qwen/qwen3-coder:free"),
    ("openrouter", "deepseek/deepseek-r1:free"),
]
MAX_TURNS = int(os.environ.get("MAX_TURNS", "60"))
SUBAGENT_MAX_TURNS = int(os.environ.get("SUBAGENT_MAX_TURNS", "25"))
# N9 â€” tool-error-repeat guard. Nudge the model after N_NUDGE identical failures;
# abort the run after N_STOP identical failures to stop budget burn on stuck loops.
N_NUDGE = int(os.environ.get("N_NUDGE", "2"))
N_STOP  = int(os.environ.get("N_STOP",  "4"))
# N8 â€” context auto-compaction. When estimated token count of system+history
# exceeds COMPACT_AT_FRAC of the model's context window, replace the oldest turns
# (past KEEP_RECENT) with a single synthetic digest note. Deterministic, no model call.
COMPACT_AT_FRAC = float(os.environ.get("COMPACT_AT_FRAC", "0.7"))
KEEP_RECENT     = int(os.environ.get("KEEP_RECENT", "12"))
COMPACT_CONTEXT_WINDOW_DEFAULT = 128000   # safe fallback when model is unknown
MAX_SUBAGENTS = 8          # Campaign cap from CORPS_COMMANDER.md
BASH_TIMEOUT = int(os.environ.get("CM_BASH_TIMEOUT", "180"))
OUTPUT_CAP = 16000         # chars of tool output fed back to the model
READ_CAP = 24000
APPROVAL_TIMEOUT = 3600
MCP_MAX_TOOLS = 128        # cap merged MCP tools/session â€” hostile server can't blow context/cost
MCP_DESC_CAP = 1024        # cap each MCP tool description fed to the model
MAX_MSG_CHARS = int(os.environ.get("MAX_MSG_CHARS", "200000"))   # cap a single message
# Wave 4 #5 â€” GitHub webhook â†’ background run. OFF by default; this is an
# unauthenticated ingress that can spawn an agent with a shell, so it stays
# fail-closed until the owner deliberately enables it AND sets a secret.
WEBHOOK_ENABLED = os.environ.get("WEBHOOK_ENABLED", "").lower() in ("1", "true", "yes")
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "")
# Only these GitHub logins may trigger a run (comma-separated). Empty = nobody,
# so a misconfig fails closed rather than open to the whole internet.
WEBHOOK_ALLOWED_SENDERS = [s.strip().lower() for s in
                           os.environ.get("WEBHOOK_ALLOWED_SENDERS", "").split(",") if s.strip()]
WEBHOOK_TRIGGER_LABEL = os.environ.get("WEBHOOK_TRIGGER_LABEL", "codemonkeys").lower()
WEBHOOK_MAX_CONCURRENT = int(os.environ.get("WEBHOOK_MAX_CONCURRENT", "2"))
WEBHOOK_MAX_BODY_BYTES = 1_000_000   # cap webhook payload before hashing/parsing
WEBHOOK_SEEN_MAX = 500               # bounded dedup memory (FIFO eviction)
# Notify-on-done (S5): outbound ping when a session run finishes. OFF until the
# owner sets NOTIFY_WEBHOOK_URL (e.g. a self-hosted ntfy endpoint). Best-effort,
# ops-metadata only (never prompts/code/secrets). NOTIFY_ON: "all" (default) or
# "error" (only failed/errored runs). Optional HMAC via NOTIFY_WEBHOOK_SECRET.
NOTIFY_WEBHOOK_URL = os.environ.get("NOTIFY_WEBHOOK_URL", "").strip()
NOTIFY_WEBHOOK_SECRET = os.environ.get("NOTIFY_WEBHOOK_SECRET", "")
NOTIFY_ON = os.environ.get("NOTIFY_ON", "all").strip().lower()
NOTIFY_TIMEOUT_S = 5
MAX_UPLOAD_FILES = 20
MAX_UPLOAD_BYTES = 10_000_000                                    # 10 MB written per file
# base64 expands ~4/3; cap the ENCODED input so we never decode a huge blob into memory
MAX_UPLOAD_B64 = MAX_UPLOAD_BYTES * 4 // 3 + 1024
MAX_REQUEST_BODY_BYTES = 5_000_000   # reject requests with body > 5 MB (DoS guard)
# Web terminal (docs/TERMINAL_DESIGN.md) â€” a Claude Code-style REPL fallback.
# Double env gate, BOTH default OFF (404 when off â€” don't advertise):
#   TERMINAL_ENABLED      â†’ serves the /terminal page (REPL over existing,
#                           already-auth-gated session APIs; no new capability)
#   TERMINAL_EXEC_ENABLED â†’ additionally arms the Owner-only !cmd one-shot exec
TERMINAL_ENABLED = os.environ.get("TERMINAL_ENABLED", "").lower() in ("1", "true", "yes")
TERMINAL_EXEC_ENABLED = os.environ.get("TERMINAL_EXEC_ENABLED", "").lower() in ("1", "true", "yes")
TERMINAL_MAX_CONCURRENT = int(os.environ.get("TERMINAL_MAX_CONCURRENT", "1"))
TERMINAL_CMD_MAX_CHARS = 8000        # bound a single !cmd before any processing
# N5: incremental model output streaming.  Default OFF so the non-streaming path
# is byte-identical to pre-N5 when unset.  Set STREAM_ENABLED=1 to activate.
STREAM_ENABLED = os.environ.get("STREAM_ENABLED", "").lower() in ("1", "true", "yes")
# CM-W4: lint feedback after edits. Default ON; set LINT_AFTER_EDIT=0 to disable.
LINT_AFTER_EDIT = os.environ.get("LINT_AFTER_EDIT", "1").strip().lower() not in (
    "0", "false", "no", "off")
LINT_TIMEOUT_S = 30
LINT_OUTPUT_CAP = 4000
# Fleet Deck feed (~/fleet/contracts/fleetdeck-codemonkeys.md): read-only ops
# metadata for the local fleet dashboard. OFF until the owner sets the
# FLEET_TOKEN Fly secret â€” unset/too-weak token = the route isn't registered
# at all (true 404 for every method; nothing to fingerprint). A token <16 chars
# is treated as unset so a stray/whitespace value can't open the feed weakly.
FLEET_TOKEN = os.environ.get("FLEET_TOKEN", "").strip()
if len(FLEET_TOKEN) < 16:
    FLEET_TOKEN = ""
FLEET_MAX_WORKERS = 200              # contract bound; payload stays â‰ª 1 MB
# Fleet Store Bridge â€” governed Playwright itch/Steam automation (fleet-automation npm run bridge)
FLEET_BRIDGE_URL = os.environ.get("FLEET_BRIDGE_URL", "http://127.0.0.1:9477").rstrip("/")
FLEET_BRIDGE_TOKEN = os.environ.get("FLEET_BRIDGE_TOKEN", "").strip()

# ---- secret-hardening: CM_MASTER_KEY + GITHUB_TOKEN capture -----------------
# Both captured here at import time; evicted from os.environ after boot (see
# _evict_env_secrets() near the bottom of this module) so /proc/self/environ
# no longer carries them after startup.
# _auth_url() now reads GITHUB_TOKEN_VAL (the constant below), not os.environ.
# Residual: a same-uid ptrace of the server process can still read decrypted
# secrets from in-memory variables; full closure requires the bash sandbox
# described in docs/design/PER_USER_ISOLATION.md L4.
CM_MASTER_KEY: str = os.environ.get("CM_MASTER_KEY", "")       # Fernet at-rest encryption key
# BREAK-GLASS recovery: if the master key is lost/rotated and the app won't boot
# ("cannot decrypt session_secret.key"), set CM_MASTER_KEY_RESET=true (+ the new
# CM_MASTER_KEY) and redeploy. On boot the app then GENERATES A FRESH signing
# secret (does NOT adopt the old/leaked file), so it boots â€” everyone simply has
# to log in again. Remove the flag after. Setting Fly env vars already requires
# owner-level access, so this adds no attacker capability. See docs/RECOVERY.md.
CM_MASTER_KEY_RESET: bool = os.environ.get("CM_MASTER_KEY_RESET", "").lower() in ("1", "true", "yes")

# GITHUB_TOKEN â€” captured at import time so _evict_env_secrets() can remove it
# from os.environ without breaking _auth_url() or the git subprocess env (which
# is built via _subprocess_env(), which already strips secret-named vars by name
# and therefore strips GITHUB_TOKEN).  Consumers use GITHUB_TOKEN_VAL directly.
GITHUB_TOKEN_VAL: str = os.environ.get("GITHUB_TOKEN", "")

# Commands that pause the loop for human approval (CodeMonkeys design rule:
# no silent pushes/deploys/destruction; git reset --hard has bitten us before)
# _CMD_START anchors a verb to a command position (line start or just after a
# separator) so dictionary words in commit messages / grep targets / filenames
# (`grep shutdown`, `git commit -m "graceful shutdown"`, `cat x.dd`) don't trip
# the gate. (Shlex-normalized candidate is rejoined with spaces, so the verb
# stays at its command position.)
_CMD_START = r"(?:^|[\n;|&]\s*)"
RISKY_PATTERNS = [
    r"\bgit\s+push\b",
    r"\bfly(?:ctl)?\s+\w+",          # `fly` and the real binary name `flyctl`
    r"\brm\s+-rf\b",
    r"\bgit\s+reset\s+--hard\b",
    r"\bgit\s+clean\b",
    r"\bgh\s+repo\s+delete\b",
    r"\bsudo\b",
    # W5 â€” more irreversible / system-level verbs the gate should not miss
    # (red-team R2/R4 hardening, 2026-06-07).
    _CMD_START + r"dd\b",            # raw block writes (dd of=/dev/â€¦)
    r"\bmkfs(?:\.\w+)?\b",           # filesystem format
    # recursive chmod/chown in ANY flag form: -R, -fR, -Rf, --recursive.
    # (A rare filename like `my-Report` may also prompt â€” an extra click on a
    # destructive verb, never a missed action.)
    r"\bchmod\b.*(?:-[A-Za-z]*R[A-Za-z]*|--recursive)\b",
    r"\bchown\b.*(?:-[A-Za-z]*R[A-Za-z]*|--recursive)\b",
    _CMD_START + r"truncate\b",      # truncate -s 0 file
    # redirect into a BLOCK device (disk wipe) â€” NOT /dev/null|stderr|stdout|tty
    # which appear in almost every command (`2>/dev/null`, `>/dev/null 2>&1`).
    r">\s*/dev/(?:sd|nvme|hd|vd|xvd|mmcblk|disk|dm-|sg|sr|loop|mapper|ram|zram)",
    # pipe a network fetch â†’ ANY interpreter (sh/bash/zsh/python/perl/ruby/node),
    # tolerating intermediate pipes.
    r"\b(?:curl|wget|fetch)\b.*\|\s*(?:sudo\s+)?(?:sh|bash|zsh|ksh|dash|python\d?|perl|ruby|node)\b",
    # NOT bare `init` (git/npm/terraform init are benign); anchored to cmd start
    # so the words don't false-positive in prose/filenames.
    _CMD_START + r"(?:shutdown|reboot|halt|poweroff)\b",
    r"\btelinit\b",
    r"\bgit\s+push\b.*(?:--force\b|\s-f\b)",                # explicit force-push
    r"\bgit\s+branch\b.*(?:-D\b|--delete\b.*--force\b|--force\b.*--delete\b)",
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
        return True  # unparseable â†’ fail closed
    return any(re.search(pat, text)
               for text in candidates for pat in RISKY_PATTERNS)

for _d in (DATA_DIR, SESSIONS_DIR, WORKSPACE_DIR):
    os.makedirs(_d, exist_ok=True)


def _bootstrap_master_key() -> None:
    """Ensure CM_MASTER_KEY is available: env var wins, else load or create DATA_DIR/master.key.

    Auto-generating a per-volume key means model/MCP config encrypt at rest with zero
    operator setup. Fly/production may still set CM_MASTER_KEY in env to pin a known key.
    """
    global CM_MASTER_KEY
    if CM_MASTER_KEY:
        return
    if os.path.isfile(MASTER_KEY_FILE):
        try:
            with open(MASTER_KEY_FILE, "r", encoding="utf-8") as f:
                key = f.read().strip()
            if len(key) >= 16:
                CM_MASTER_KEY = key
                return
            _log.warning("master.key exists but is too short; regenerating.")
        except OSError as e:
            _log.warning("Could not read master.key (%s); will try to regenerate.", e)
    key = secrets.token_urlsafe(32)
    try:
        fd, tmp = tempfile.mkstemp(dir=DATA_DIR, prefix=".master_key_")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(key)
                f.flush()
                os.fsync(f.fileno())
        except Exception:
            os.unlink(tmp)
            raise
        os.replace(tmp, MASTER_KEY_FILE)
        os.chmod(MASTER_KEY_FILE, 0o600)
        CM_MASTER_KEY = key
        _log.info(
            "Generated encryption master key at %s â€” API keys encrypt at rest automatically.",
            MASTER_KEY_FILE,
        )
    except OSError as e:
        _log.warning(
            "Could not persist master.key (%s); config files stay plaintext this boot.", e)


_bootstrap_master_key()

# --- startup config validation ------------------------------------------------

def _validate_startup_config() -> list[str]:
    """Validate critical config before app boots. Returns a list of warnings;
    raises RuntimeError on hard-fail conditions that would corrupt data."""
    import logging as _vl
    _lerr = _vl.getLogger(__name__)
    warnings: list[str] = []

    # 1. DATA_DIR must exist and be writable
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=DATA_DIR, prefix=".startup_")
        os.close(fd)
        os.unlink(tmp)
    except OSError as e:
        raise RuntimeError(
            f"DATA_DIR ({DATA_DIR}) is not writable: {e}. "
            "Set DATA_DIR to a writable path or check permissions."
        ) from e

    # 2. Validate numeric env vars are within sane ranges
    _numeric_checks = [
        ("SESSION_BUDGET_USD", SESSION_BUDGET_USD, 0.01, 1000.0),
        ("SESSION_BUDGET_MAX_USD", SESSION_BUDGET_MAX_USD, 0.01, 1000.0),
        ("MEMBER_SESSION_BUDGET_MAX_USD", MEMBER_SESSION_BUDGET_MAX_USD, 0.0, 1000.0),
    ]
    for name, value, lo, hi in _numeric_checks:
        if not (isinstance(value, (int, float)) and not (value != value)):
            warnings.append(f"{name} is not a valid number (got {value!r}); using default")
        elif value < lo or value > hi:
            warnings.append(f"{name}={value} outside [{lo}, {hi}]; verify intent")

    if SPEND_DAILY_CAP_USD != 0.0:
        if not (isinstance(SPEND_DAILY_CAP_USD, (int, float)) and not (SPEND_DAILY_CAP_USD != SPEND_DAILY_CAP_USD)):
            warnings.append(f"SPEND_DAILY_CAP_USD is not a valid number (got {SPEND_DAILY_CAP_USD!r}); cap disabled")
        elif SPEND_DAILY_CAP_USD < 0.01:
            warnings.append(f"SPEND_DAILY_CAP_USD={SPEND_DAILY_CAP_USD} is very low; verify intent")

    # 3. CM_MASTER_KEY consistency
    if CM_MASTER_KEY and not _FERNET_AVAILABLE:
        raise RuntimeError(
            "CM_MASTER_KEY is set but cryptography package is unavailable; "
            "pip install cryptography and restart."
        )
    if CM_MASTER_KEY and len(CM_MASTER_KEY) < 16:
        raise RuntimeError(
            "CM_MASTER_KEY is too short (<16 chars); use a 32+ byte random value."
        )

    # 4. Ensure critical subdirectories exist
    for d in (SESSIONS_DIR, WORKSPACE_DIR):
        try:
            os.makedirs(d, exist_ok=True)
        except OSError as e:
            _lerr.warning("Could not create %s: %s", d, e)

    # 5. Report summary
    _lerr.info(
        "Startup config validated â€” DATA_DIR=%s CM_MASTER_KEY=%s Fernet=%s daily_cap=%s",
        DATA_DIR,
        "set" if CM_MASTER_KEY else "unset",
        "available" if _FERNET_AVAILABLE else "missing",
        f"${SPEND_DAILY_CAP_USD:.2f}" if SPEND_DAILY_CAP_USD else "none",
    )
    return warnings


_STARTUP_WARNINGS = _validate_startup_config()
if _STARTUP_WARNINGS:
    for _w in _STARTUP_WARNINGS:
        _log.warning("Startup config: %s", _w)


app = FastAPI(title="CodeMonkeys", version="0.3.0",
              docs_url="/api/docs", redoc_url="/api/redoc",
              openapi_url="/api/openapi.json")
_BOOT_TIME = int(time.time())


@app.get("/healthz")
def healthz():
    """Unauthenticated liveness/readiness probe for Fly health checks.
    Deliberately leaks NOTHING sensitive: no usernames, keys, repos, or model
    config â€” just that the process is up and how many sessions are loaded."""
    return {"status": "ok", "uptime_s": int(time.time()) - _BOOT_TIME,
            "sessions": len(SESSIONS)}


@app.get("/readyz")
def readyz():
    """Unauthenticated readiness probe â€” returns 200 when all required checks
    pass, 503 when any required check fails.  Leaks NOTHING sensitive: only
    boolean flags, not keys/paths/usernames.

    Checks
    ------
    data_writable     (required) write+delete a temp file under DATA_DIR
    crypto_ok         (required) if CM_MASTER_KEY is set, _FERNET_AVAILABLE
                      must be True; if CM_MASTER_KEY is unset â†’ True (N/A)
    provider_configured (warning-only) at least one callable provider exists;
                      failure makes status "not ready" but does NOT trigger 503
                      so the app is considered ready for traffic even without a
                      configured model (owner may add the key post-deploy)
    """
    from fastapi.responses import JSONResponse

    # -- check: data_writable --------------------------------------------------
    data_writable = False
    try:
        fd, tmp = tempfile.mkstemp(dir=DATA_DIR, prefix=".readyz_")
        os.close(fd)
        os.unlink(tmp)
        data_writable = True
    except Exception:
        pass

    # -- check: crypto_ok ------------------------------------------------------
    # If CM_MASTER_KEY is set the cryptography package must be available,
    # otherwise the app cannot decrypt the session signing secret and will
    # refuse to serve sessions.  If CM_MASTER_KEY is unset this is N/A â†’ True.
    if CM_MASTER_KEY:
        crypto_ok = _FERNET_AVAILABLE
    else:
        crypto_ok = True

    # -- check: provider_configured (warning-only) ----------------------------
    try:
        cfg = load_models()
        provider_configured = bool(_usable(cfg))
    except Exception:
        provider_configured = False

    # -- check: disk_space_ok --------------------------------------------------
    disk_space_ok = False
    try:
        total, used, free = shutil.disk_usage(DATA_DIR)
        disk_space_ok = free > 10 * 1024 * 1024  # at least 10MB
    except Exception:
        disk_space_ok = True  # fallback

    # -- aggregate ------------------------------------------------------------
    # Required checks determine the HTTP status code.
    required_ok = data_writable and crypto_ok and disk_space_ok
    overall = "ready" if (required_ok and provider_configured) else "not ready"

    body = {
        "status": overall,
        "uptime_s": int(time.time()) - _BOOT_TIME,
        "sessions": len(SESSIONS),
        "checks": {
            "data_writable": data_writable,
            "crypto_ok": crypto_ok,
            "disk_space_ok": disk_space_ok,
            "provider_configured": provider_configured,
        },
    }
    status_code = 200 if required_ok else 503
    return JSONResponse(content=body, status_code=status_code)


@app.middleware("http")
async def _security_headers(request, call_next):
    """Baseline browser-hardening for an auth-gated console that fronts a shell.
    Anti-clickjacking (no cross-origin framing of the login/console), no MIME
    sniffing, no referrer leakage. script-src 'self' (Tailwind phase 2): all JS
    is same-origin files â€” the Tailwind CDN <script> is gone (vendored CSS) and
    no page may carry inline <script> (swarm's moved to swarm.js for this)."""
    resp = await call_next(request)
    resp.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("Referrer-Policy", "no-referrer")
    resp.headers.setdefault(
        "Content-Security-Policy",
        "script-src 'self'; frame-ancestors 'self'; object-src 'none'; "
        "base-uri 'self'")
    return resp


@app.middleware("http")
async def _body_size_limit(request: Request, call_next):
    """Reject requests whose body exceeds MAX_REQUEST_BODY_BYTES before reading.
    Checks Content-Length header (best-effort) and falls back to streaming read
    with a hard cap for chunked Transfer-Encoding or missing Content-Length.
    Skips GET/HEAD/OPTIONS â€” they carry no meaningful body."""
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return await call_next(request)

    # Fast path: trust Content-Length when present and within limits
    cl = request.headers.get("content-length")
    if cl is not None:
        try:
            if int(cl) > MAX_REQUEST_BODY_BYTES:
                return JSONResponse(
                    status_code=413,
                    content={"error": "request body too large",
                             "max_bytes": MAX_REQUEST_BODY_BYTES})
        except ValueError:
            pass  # malformed Content-Length â€” fall through to streaming cap

    # Slow path: read body with a hard cap (chunked or missing Content-Length)
    body_chunks: list[bytes] = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > MAX_REQUEST_BODY_BYTES:
            return JSONResponse(
                status_code=413,
                content={"error": "request body too large",
                         "max_bytes": MAX_REQUEST_BODY_BYTES})
        body_chunks.append(chunk)

    # Reconstruct the request body so downstream handlers can read it normally
    async def _cached_body():
        for c in body_chunks:
            yield c

    request._body = b"".join(body_chunks)
    request._receive = _cached_body  # type: ignore[assignment]
    return await call_next(request)


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


@app.on_event("startup")
def _startup_security_warnings():
    """H-3: Warn loudly when secrets-at-rest encryption is inactive.

    Without CM_MASTER_KEY, model_config.json (which contains provider API keys)
    and session_secret.key are stored in plaintext on /data.  The bash tool and
    any prompt-injection payload that reaches the bash tool can exfiltrate them
    with a simple `cat` command.  Setting CM_MASTER_KEY enables Fernet encryption
    and limits the blast radius to the ciphertext (useless without the key)."""
    if not CM_MASTER_KEY:
        _log.warning(
            "SECURITY H-3: CM_MASTER_KEY is unset â€” model_config.json and "
            "session_secret.key are stored UNENCRYPTED on /data.  Set "
            "CM_MASTER_KEY to a high-entropy random value in your Fly secrets "
            "to enable at-rest encryption and protect provider API keys from "
            "prompt-injection exfiltration via the bash tool."
        )


# ----------------------------------------------------------------- storage

_USERS_LOCK = threading.Lock()
_ERASED_LOCK = threading.Lock()   # M-7: serialize tombstone + receipt writes
_MODELS_LOCK = threading.Lock()
_MCP_LOCK = threading.Lock()
_SESSIONS_LOCK = threading.Lock()
# N2 daily spend cap â€” in-memory state (date string + usd float).
# Guarded by _DAILY_LOCK; persisted atomically to DAILY_SPEND_FILE after every
# accrue so a restart doesn't reset the day's total.
_DAILY_LOCK = threading.Lock()
_daily_state: dict = {"date": "", "usd": 0.0}  # mutable, always accessed under lock
_daily_cap_override: float = 0.0  # owner-set in-memory override (0 = not overridden)


def _load_json(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def _save_json(path, data):
    tmp = path + ".tmp." + secrets.token_hex(8)
    try:
        with open(tmp, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, path)
    finally:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass


# ----------------------------------------------------------------- N2 daily spend cap

def _daily_utc_date() -> str:
    """Today's date in UTC as YYYY-MM-DD."""
    import datetime
    return datetime.datetime.utcnow().strftime("%Y-%m-%d")


def _load_daily_spend() -> None:
    """Populate _daily_state from persisted file on boot.

    If the stored date differs from today (UTC), rolls over to zero so yesterday's
    total never pollutes today's cap check. Called once after restore_sessions().
    """
    global _daily_state
    data = _load_json(DAILY_SPEND_FILE, {})
    today = _daily_utc_date()
    with _DAILY_LOCK:
        if data.get("date") == today:
            _daily_state = {"date": today, "usd": float(data.get("usd", 0.0))}
        else:
            _daily_state = {"date": today, "usd": 0.0}


def _persist_daily_spend() -> None:
    """Atomically write _daily_state to disk. Must be called under _DAILY_LOCK."""
    _save_json(DAILY_SPEND_FILE, {"date": _daily_state["date"],
                                  "usd": round(_daily_state["usd"], 6)})


def _accrue_daily(usd: float) -> None:
    """Add usd to today's running total (thread-safe). Rolls over at UTC midnight."""
    global _daily_state
    today = _daily_utc_date()
    with _DAILY_LOCK:
        if _daily_state["date"] != today:
            _daily_state = {"date": today, "usd": 0.0}
        _daily_state["usd"] += usd
        _persist_daily_spend()


def daily_total_usd() -> float:
    """Return today's cumulative spend (USD) across all sessions (thread-safe)."""
    today = _daily_utc_date()
    with _DAILY_LOCK:
        if _daily_state["date"] != today:
            return 0.0
        return _daily_state["usd"]


def effective_daily_cap() -> float:
    """The active daily cap: owner override if set, else SPEND_DAILY_CAP_USD.
    Returns 0.0 when no cap is configured (i.e., unlimited)."""
    if _daily_cap_override > 0:
        return _daily_cap_override
    return max(SPEND_DAILY_CAP_USD, 0.0)


# ----------------------------------------------------------------- auth

def _make_fernet() -> "Fernet | None":
    """Return a Fernet instance derived from CM_MASTER_KEY, or None if it's unset.

    CM_MASTER_KEY is KDF'd SHA-256 â†’ urlsafe-b64 â†’ Fernet key. A single SHA-256 is
    NOT a password-stretching KDF, so **CM_MASTER_KEY must be a high-entropy random
    value** (â‰¥32 bytes, e.g. `python -c "import secrets;print(secrets.token_urlsafe(32))"`),
    NOT a human-chosen passphrase â€” otherwise an attacker holding the on-disk
    ciphertext could brute-force it offline. (Caller fail-closes if the key is set
    but cryptography is unavailable.)
    """
    if not CM_MASTER_KEY:
        return None
    digest = hashlib.sha256(CM_MASTER_KEY.encode()).digest()
    fkey = base64.urlsafe_b64encode(digest)
    return Fernet(fkey)


# Versioned header marking a Fernet-encrypted secret file. Its presence/absence
# is what disambiguates "encrypted-under-this-or-another-key" from "legacy
# plaintext" â€” so a wrong/rotated key fails CLOSED instead of being mistaken for
# plaintext and silently replacing the signing secret (red-team F1/F2).
_ENC_MAGIC = b"CMENC1\n"

# ---- fail-soft config-file encryption helpers --------------------------------
# Unlike session_secret.key (fail-CLOSED), model_config.json and mcp_tokens.json
# are fail-SOFT: wrong/missing key â†’ empty config + UI banner, never a crash.
# The owner can just re-enter their API keys in âš™ Settings.

# True when an encrypted config file couldn't be decrypted (wrong/missing key).
# Surfaced via /api/encryption-status for the UI banner.  Set on read; cleared
# when a successful write happens (key is now correct).
_DECRYPT_FAILED: bool = False
_DECRYPT_FAILED_LOCK = threading.Lock()


def _read_enc_file(path: str, default):
    """Read a JSON config file that may be Fernet-encrypted or legacy plaintext.

    Returns (parsed_object, migrated: bool).

    Fail-soft: if the file carries _ENC_MAGIC but we can't decrypt (missing or
    wrong CM_MASTER_KEY), sets the module _DECRYPT_FAILED flag and returns
    (default, False) â€” the caller keeps running with an empty config.

    Migration: if the file is plaintext and CM_MASTER_KEY is set, the caller
    should re-write it encrypted (pass the result through _write_enc_file).
    """
    global _DECRYPT_FAILED
    if not os.path.exists(path):
        return default, False
    try:
        with open(path, "rb") as f:
            blob = f.read()
    except OSError:
        return default, False

    if blob.startswith(_ENC_MAGIC):
        fernet = _make_fernet()
        if fernet is None:
            # File is encrypted but key is gone â€” fail soft, set flag.
            with _DECRYPT_FAILED_LOCK:
                _DECRYPT_FAILED = True
            _log.warning(
                "Config file %s is encrypted but CM_MASTER_KEY is unset; "
                "returning empty config â€” re-enter keys in âš™ Settings.", path)
            return default, False
        try:
            raw = fernet.decrypt(blob[len(_ENC_MAGIC):])
        except _FernetInvalidToken:
            with _DECRYPT_FAILED_LOCK:
                _DECRYPT_FAILED = True
            _log.warning(
                "Config file %s could not be decrypted with the current "
                "CM_MASTER_KEY (rotated?); returning empty config â€” re-enter "
                "keys in âš™ Settings.", path)
            return default, False
        try:
            return json.loads(raw.decode()), False
        except Exception:
            return default, False

    # Legacy plaintext JSON.
    try:
        data = json.loads(blob.decode())
    except Exception:
        return default, False
    needs_migrate = bool(_make_fernet())   # key set â†’ should encrypt on next write
    return data, needs_migrate


def _fchmod(fd: int, mode: int) -> None:
    """Best-effort file mode; Windows Python has no os.fchmod."""
    if hasattr(os, "fchmod"):
        os.fchmod(fd, mode)  # type: ignore[attr-defined]


def _write_enc_file(path: str, data, mode: int = 0o600,
                    clear_decrypt_failed: bool = False) -> None:
    """Atomic write of a JSON config file, Fernet-encrypted when CM_MASTER_KEY
    is set, otherwise plaintext.  Creates the file at the given mode with no
    0644 window (uses os.open O_CREAT|O_TRUNC with explicit mode).

    clear_decrypt_failed: set True when the caller knows the write represents a
    fresh, valid config (e.g. the owner just re-entered their keys), so the UI
    banner should disappear.  Leave False for internal migrations / default-init
    writes so a prior decrypt failure remains visible.
    """
    global _DECRYPT_FAILED
    payload = json.dumps(data, indent=2).encode()
    fernet = _make_fernet()
    if fernet is not None:
        content = _ENC_MAGIC + fernet.encrypt(payload)
    else:
        content = payload

    dir_ = os.path.dirname(path) or "."
    fd, tmp = tempfile.mkstemp(dir=dir_, prefix=".enc_cfg_")
    try:
        # Apply the desired mode before writing any content (POSIX only).
        _fchmod(fd, mode)
        with os.fdopen(fd, "wb") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    # Safety net (red-team #58 R3): if we're about to OVERWRITE a file we could
    # NOT decrypt this session, preserve the original ciphertext to a .bak first,
    # so an incidental owner save (e.g. toggling a setting while the "can't
    # decrypt â€” re-enter keys" banner is up) can NEVER permanently destroy keys
    # that restoring the correct CM_MASTER_KEY would recover. See docs/RECOVERY.md.
    with _DECRYPT_FAILED_LOCK:
        _df = _DECRYPT_FAILED
    if _df and os.path.exists(path):
        try:
            with open(path, "rb") as _src:
                _orig = _src.read()
            if _orig.startswith(_ENC_MAGIC):
                bfd, btmp = tempfile.mkstemp(dir=dir_, prefix=".enc_bak_")
                _fchmod(bfd, 0o600)
                with os.fdopen(bfd, "wb") as _bf:
                    _bf.write(_orig)
                os.replace(btmp, path + ".undecryptable.bak")
        except OSError:
            pass
    os.replace(tmp, path)
    if clear_decrypt_failed:
        with _DECRYPT_FAILED_LOCK:
            _DECRYPT_FAILED = False

# Module-level singleton â€” _session_secret() is called on every token
# sign/verify, so we load once and cache.
_SESSION_SECRET_CACHE: bytes | None = None
_SESSION_SECRET_LOCK = threading.Lock()


def _session_secret() -> bytes:
    """Return the 32-byte HMAC signing secret (the auth root of trust), loading or
    generating it on first call, then caching.

    File format: an encrypted file is `_ENC_MAGIC + Fernet(secret)`; a legacy file
    is bare plaintext bytes (no header).

    With CM_MASTER_KEY set (+ cryptography available):
      - first boot â†’ generate 32 random bytes, write encrypted (header + ciphertext).
      - encrypted file present â†’ decrypt. **Wrong/rotated key â†’ RAISE (fail closed)**:
        we never regenerate or treat ciphertext as plaintext, because that would
        substitute a disk-leaked value for the signing secret and permanently
        entrench a compromise (red-team F1).
      - legacy plaintext file present â†’ migrate once (re-write encrypted).

    With CM_MASTER_KEY UNSET: original plaintext behaviour (one-time warning), so
    existing deploys are unchanged â€” EXCEPT an already-encrypted file with no key
    RAISES (red-team F2) rather than reading ciphertext as the secret.
    """
    global _SESSION_SECRET_CACHE
    if _SESSION_SECRET_CACHE is not None:
        return _SESSION_SECRET_CACHE
    with _SESSION_SECRET_LOCK:
        if _SESSION_SECRET_CACHE is not None:   # double-checked under lock
            return _SESSION_SECRET_CACHE
        import logging as _logging

        # Operator set a key but crypto is missing â†’ fail closed, never degrade to
        # reading the file as plaintext/ciphertext (red-team F3).
        if CM_MASTER_KEY and not _FERNET_AVAILABLE:
            raise RuntimeError(
                "CM_MASTER_KEY is set but the 'cryptography' package is unavailable; "
                "refusing to boot rather than mishandle the encrypted session secret.")
        if CM_MASTER_KEY and len(CM_MASTER_KEY) < 16:
            # enforce, don't warn â€” a too-short key must not reach production silently
            raise RuntimeError(
                "CM_MASTER_KEY is too short (<16 chars); use a 32+ byte random value "
                "(e.g. python -c \"import secrets;print(secrets.token_urlsafe(32))\").")

        fernet = _make_fernet()            # None iff CM_MASTER_KEY unset
        exists = os.path.exists(SECRET_FILE)
        blob = b""
        if exists:
            with open(SECRET_FILE, "rb") as f:
                blob = f.read()
        is_encrypted = blob.startswith(_ENC_MAGIC)

        def _persist(raw_bytes: bytes, encrypt: bool):
            data = (_ENC_MAGIC + fernet.encrypt(raw_bytes)) if encrypt else raw_bytes
            fd, tmp = tempfile.mkstemp(dir=os.path.dirname(SECRET_FILE) or ".",
                                       prefix=".session_secret_")
            try:
                with os.fdopen(fd, "wb") as f:
                    f.write(data)
            except Exception:
                os.unlink(tmp)
                raise
            os.replace(tmp, SECRET_FILE)
            os.chmod(SECRET_FILE, 0o600)

        # BREAK-GLASS: regenerate a FRESH secret and overwrite, instead of failing
        # closed. Recovers a lost/rotated key or a corrupt file with one env var +
        # redeploy. Generates new random bytes (never adopts the old/leaked file),
        # so it's safe; cost is that everyone must log in again. Loud warning.
        if CM_MASTER_KEY_RESET:
            # Don't let a forgotten key silently downgrade an encrypted file to
            # plaintext (red-team R2) â€” refuse loudly and tell them to set the key.
            if fernet is None and is_encrypted:
                raise RuntimeError(
                    "CM_MASTER_KEY_RESET is set but CM_MASTER_KEY is not, and the "
                    "existing session_secret.key is encrypted â€” refusing to silently "
                    "downgrade it to plaintext. Also set CM_MASTER_KEY to a new value "
                    "(see docs/RECOVERY.md Scenario A), or delete the file to "
                    "intentionally return to plaintext.")
            raw = secrets.token_bytes(32)
            _persist(raw, encrypt=(fernet is not None))
            warn = ("CM_MASTER_KEY_RESET is set â€” GENERATED A FRESH session_secret.key "
                    "(all existing sessions are now invalid; everyone must log in again). "
                    "REMOVE CM_MASTER_KEY_RESET from the environment after this boot.")
            if fernet is None:
                warn += " NOTE: stored UNENCRYPTED â€” no CM_MASTER_KEY set."
            _logging.warning(warn)
            _SESSION_SECRET_CACHE = raw
            return raw

        if fernet is None:
            # Plaintext mode (no key). An encrypted file with no key = fail closed.
            if is_encrypted:
                raise RuntimeError(
                    "session_secret.key is encrypted but CM_MASTER_KEY is unset; set the "
                    "key to boot (refusing to regenerate or read ciphertext as the secret).")
            if not exists:
                raw = secrets.token_bytes(32)
                _persist(raw, encrypt=False)
            else:
                raw = blob
                if len(raw) != 32:
                    raise RuntimeError(
                        "session_secret.key is corrupt (expected 32 plaintext bytes); "
                        "refusing to boot.")
            _logging.warning(
                "session_secret.key stored UNENCRYPTED; set CM_MASTER_KEY to encrypt at rest")
            _SESSION_SECRET_CACHE = raw
            return raw

        # Key set + crypto available.
        if not exists:
            raw = secrets.token_bytes(32)
            _persist(raw, encrypt=True)
        elif is_encrypted:
            try:
                raw = fernet.decrypt(blob[len(_ENC_MAGIC):])
            except _FernetInvalidToken:
                raise RuntimeError(
                    "cannot decrypt session_secret.key with the current CM_MASTER_KEY "
                    "(rotated or wrong key?). Refusing to boot â€” restore the correct key, "
                    "or delete the file to start fresh (this invalidates all sessions).")
        else:
            # Legacy plaintext + key now set â†’ migrate ONCE to encrypted.
            raw = blob
            if len(raw) != 32:
                raise RuntimeError(
                    "session_secret.key is corrupt (expected 32 plaintext bytes); "
                    "refusing to migrate/boot.")
            _persist(raw, encrypt=True)
            _logging.info("session_secret.key migrated from plaintext to Fernet-encrypted")
        _SESSION_SECRET_CACHE = raw
        return raw


def hash_pin(pin: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", pin.encode(), bytes.fromhex(salt), 200_000
    ).hex()


def totp_qr_data_uri(otpauth_uri: str) -> str:
    """Render the otpauth:// URI as a self-contained SVG data URI, generated
    LOCALLY. Previously the frontend posted this URI (which embeds the TOTP
    shared secret) to api.qrserver.com â€” leaking the second factor to a third
    party. Returns "" if segno is unavailable; the UI then shows the secret for
    manual entry rather than ever calling an external service."""
    if not segno or not otpauth_uri:
        return ""
    try:
        buf = io.BytesIO()
        segno.make(otpauth_uri, error="m").save(buf, kind="svg", scale=4, border=2)
        b64 = base64.b64encode(buf.getvalue()).decode()
        return "data:image/svg+xml;base64," + b64
    except Exception:
        return ""


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


def _load_feedback_statuses():
    try:
        if os.path.exists(FEEDBACK_STATUS_FILE):
            with open(FEEDBACK_STATUS_FILE, "r", encoding="utf-8") as f:
                return json.load(f) or {}
    except Exception:
        pass
    return {}


def _save_feedback_statuses(statuses: dict) -> None:
    if len(statuses) > FEEDBACK_STATUS_MAX:
        oldest = sorted(statuses.keys())[0]
        statuses.pop(oldest)
    try:
        os.makedirs(os.path.dirname(FEEDBACK_STATUS_FILE), exist_ok=True)
        with open(FEEDBACK_STATUS_FILE, "w", encoding="utf-8") as f:
            json.dump(statuses, f)
    except Exception:
        raise HTTPException(status_code=500, detail="Could not save status.")


def _find_feedback_report(rid: str):
    for path in (FEEDBACK_FILE, FEEDBACK_FILE + ".1"):
        try:
            if not os.path.exists(path):
                continue
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except Exception:
                        continue
                    if str(rec.get("id") or "") == rid:
                        return rec
        except Exception:
            continue
    return None

def _feedback_rate_ok(user: str) -> bool:
    now = time.time()
    hits = [t for t in _feedback_hits.get(user, []) if now - t < FEEDBACK_RATE_WINDOW]
    if len(hits) >= FEEDBACK_RATE_MAX:
        _feedback_hits[user] = hits
        return False
    hits.append(now)
    _feedback_hits[user] = hits
    return True

def _scrub_feedback(s, cap):
    s = "" if s is None else str(s)
    s = "".join(ch for ch in s if ch in ("\n", "\t") or ord(ch) >= 32)
    return s.strip()[:cap]

def _evict_orphan_shots():
    try:
        referenced = set()
        for path in (FEEDBACK_FILE, FEEDBACK_FILE + ".1"):
            if not os.path.exists(path): continue
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line: continue
                    try:
                        shot = json.loads(line).get("shot")
                        if shot: referenced.add(shot)
                    except Exception: continue
        if os.path.exists(FEEDBACK_SHOT_DIR):
            for e in os.scandir(FEEDBACK_SHOT_DIR):
                if e.is_file() and e.name not in referenced:
                    try: os.remove(e.path)
                    except Exception: pass
    except Exception: pass

def _save_feedback_shot(data_url, report_id):
    if not data_url: return None
    ext, b64 = None, None
    for prefix, e in FEEDBACK_SHOT_PREFIXES.items():
        if data_url.startswith(prefix):
            ext, b64 = e, data_url[len(prefix):]
            break
    if not ext or len(b64) > FEEDBACK_SHOT_MAX_B64: return None
    try:
        raw = base64.b64decode(b64, validate=True)
        if ext == ".png" and not raw.startswith(b"\x89PNG\r\n\x1a\n"): return None
        if ext == ".jpg" and not raw.startswith(b"\xff\xd8"): return None
        os.makedirs(FEEDBACK_SHOT_DIR, exist_ok=True)
        total = sum(e.stat().st_size for e in os.scandir(FEEDBACK_SHOT_DIR) if e.is_file())
        if total >= FEEDBACK_SHOT_DIR_MAX:
            _evict_orphan_shots()
            total = sum(e.stat().st_size for e in os.scandir(FEEDBACK_SHOT_DIR) if e.is_file())
        if total >= FEEDBACK_SHOT_DIR_MAX: return None
        name = report_id + ext
        with open(os.path.join(FEEDBACK_SHOT_DIR, name), "wb") as f:
            f.write(raw)
        return name
    except Exception: return None

def verify_token(authorization: str = Header(default="")):
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing token")
    username = parse_token(authorization[7:])
    if not username or username not in load_users():
        raise HTTPException(401, "Invalid or expired token")
    # C-2: tokens issued to accounts that haven't completed first-time setup
    # must not grant access to any general-purpose endpoint.  Use
    # verify_invite_token below for routes that are legitimately needed during
    # the setup flow (account/setup, WebAuthn enrolment).
    if load_users().get(username, {}).get("must_reset"):
        raise HTTPException(403, "Finish first-time setup before using this endpoint")
    return username


def verify_invite_token(authorization: str = Header(default="")):
    """Like verify_token but ACCEPTS must_reset accounts.
    Only used for the first-login setup flow endpoints (account/setup).
    All other endpoints must use verify_token or verify_user."""
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
    """Any active (non-pending) account â€” Owner or invited Member."""
    user = load_users().get(username, {})
    if user.get("must_reset"):
        raise HTTPException(403, "Finish first-time setup (authenticator) first")
    if user.get("role") not in ("Owner", "Member"):
        raise HTTPException(403, "Not authorized")
    # Commercial gate: when billing is live, Members need an active sub.
    # Owner is always exempt (runs the house). Invited comps can set
    # subscription_status=active manually / via Owner tools later.
    if BILLING_ENABLED and user.get("role") == "Member":
        if (user.get("subscription_status") or "") != "active":
            raise HTTPException(402, "Active $1/mo subscription required")
    return username


def optional_verify_user(authorization: str = Header(default="")) -> str | None:
    """Valid session token if present; None for anonymous callers."""
    if not authorization.startswith("Bearer "):
        return None
    username = parse_token(authorization[7:])
    if not username or username not in load_users():
        return None
    user = load_users().get(username, {})
    if user.get("must_reset") or user.get("role") not in ("Owner", "Member"):
        return None
    return username


class RegisterRequest(BaseModel):
    username: str


class LoginRequest(BaseModel):
    username: str
    mfa_code: str = ""


@app.get("/api/registration-status")
def registration_status():
    users = load_users()
    return {"open": not bool(users) or OPEN_ENROLLMENT}


@app.post("/api/register")
def register(req: RegisterRequest):
    username = req.username.strip()
    if not re.fullmatch(r"[A-Za-z0-9_.-]{2,32}", username):
        raise HTTPException(400, "Bad username")
    with _USERS_LOCK:
        if _is_erased(username):                  # M-7 tombstone guard (in-lock: races erasure)
            raise HTTPException(403, "This account was erased and cannot be re-registered")
        users = load_users()
        if username in users:
            raise HTTPException(409, "Username taken")
        if users and not OPEN_ENROLLMENT:
            raise HTTPException(403, "Enrollment closed")
        role = "Owner" if not users else "Member"
        mfa_secret = pyotp.random_base32()
        users[username] = {
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
        "mfa_qr": totp_qr_data_uri(uri),     # rendered locally; secret never leaves the box
    }


# ---- login brute-force throttle (persistent; three dimensions) -------------
# Three sliding-window lockout dimensions, all the same {key -> {stamps, until}}
# shape so one set of helpers serves them:
#   _login_fails      username -> ...   (per-account; the original #13 lock)
#   _login_ip_fails   client-IP -> ...  (per source IP, from Fly-Client-IP)
#   _login_global     "*"       -> ...  (one system-wide circuit-breaker bucket)
# State is WRITTEN THROUGH to LOGIN_THROTTLE_FILE on every mutation and reloaded
# at startup, so locks/counters survive a restart (no longer fail-open on reboot).
_GLOBAL_KEY = "*"
_login_fails = {}                      # username -> {"stamps": [ts...], "until": ts}
_login_ip_fails = {}                   # client ip -> {"stamps": [ts...], "until": ts}
_login_global = {}                     # {_GLOBAL_KEY: {"stamps": [ts...], "until": ts}}
_LOGIN_LOCK = threading.RLock()        # reentrant: persist() runs inside locked ops


def _client_ip(request) -> str:
    """Best-effort source IP. Prefer Fly-Client-IP (set by Fly's proxy and not
    forgeable from outside it); fall back to the socket peer. Returns None when
    unknowable (e.g. the unit tests call the handlers without a Request) â€” callers
    then simply skip the per-IP dimension. Header spoofing off-Fly is backstopped
    by the global ceiling, which is keyed on nothing the client controls.

    H-1 hardening: when uvicorn is started with --forwarded-allow-ips=* (needed on
    Fly for request.base_url/OAuth), uvicorn may overwrite request.client.host with
    the attacker-controlled X-Forwarded-For value.  To prevent throttle bypass on
    self-hosted / off-Fly deployments, we skip the socket-peer fallback whenever
    X-Forwarded-For is present without a trusted Fly-Client-IP â€” the per-IP
    dimension is then simply inactive (global + per-account dimensions still apply)."""
    if request is None:
        return None
    try:
        ip = request.headers.get("Fly-Client-IP") or request.headers.get("fly-client-ip")
    except Exception:
        ip = None
    if ip:
        return ip
    # H-1: if any X-Forwarded-For is present without Fly-Client-IP, the socket
    # peer may have been overwritten by uvicorn's proxy trust â€” return None to
    # skip the per-IP throttle dimension rather than act on a spoofable value.
    try:
        if request.headers.get("x-forwarded-for") or request.headers.get("X-Forwarded-For"):
            return None
    except Exception:
        pass
    client = getattr(request, "client", None)
    ip = getattr(client, "host", None) if client else None
    return ip or None


def _locked_for_dim(store: dict, key: str, now: float) -> int:
    """Seconds remaining on an active lock for *key* in *store*, else 0."""
    rec = store.get(key)
    if not rec:
        return 0
    remaining = int(rec.get("until", 0) - now)
    return remaining if remaining > 0 else 0


def _prune_dim(store: dict, now: float) -> None:
    """Drop entries with no active lock and no in-window failures. Caller holds
    _LOGIN_LOCK. Bounds memory against an attacker spamming distinct keys."""
    dead = [k for k, r in store.items()
            if r.get("until", 0) <= now
            and not any(now - t < LOGIN_WINDOW_SEC for t in r.get("stamps", []))]
    for k in dead:
        del store[k]


def _note_failure_dim(store: dict, key: str, now: float,
                      max_fails: int, cap) -> None:
    """Record a failed attempt in *store*; arm a lockout once the window
    threshold trips. Caller holds _LOGIN_LOCK. max_fails <= 0 disables the
    dimension (no-op). *cap* (or None) bounds the number of distinct keys."""
    if max_fails <= 0:
        return
    if cap and len(store) >= cap and key not in store:
        _prune_dim(store, now)         # reclaim dead entries first
        if len(store) >= cap:
            # Hard bound: evict the least-valuable entry. Sort key prefers to
            # KEEP (a) actively-locked keys (until>0 sorts last), then (b) keys
            # closest to the threshold (more stamps sorts last), so an attacker
            # flooding 1-stamp junk keys cannot evict and thereby reset a
            # victim's near-threshold counter or armed lock.
            victim = min(store.items(),
                         key=lambda kv: (kv[1].get("until", 0),
                                         len(kv[1].get("stamps") or []),
                                         max(kv[1].get("stamps") or [0])))
            del store[victim[0]]
    rec = store.setdefault(key, {"stamps": [], "until": 0})
    rec["stamps"] = [t for t in rec["stamps"] if now - t < LOGIN_WINDOW_SEC]
    rec["stamps"].append(now)
    if len(rec["stamps"]) >= max_fails:
        rec["until"] = now + LOGIN_LOCKOUT_SEC
        rec["stamps"] = []             # reset window; the lock is the penalty now


def _login_persist() -> None:
    """Write-through snapshot of all three dimensions. Caller MUST hold
    _LOGIN_LOCK. Best-effort: a disk error must never break login â€” the
    in-memory state still enforces the throttle for this process's lifetime."""
    try:
        _save_json(LOGIN_THROTTLE_FILE,
                   {"v": 1, "users": _login_fails,
                    "ips": _login_ip_fails, "global": _login_global})
    except OSError:
        pass


def _login_load() -> None:
    """Reload persisted throttle state at startup so locks survive a restart.
    Expired/stale entries are pruned on the way in."""
    data = _load_json(LOGIN_THROTTLE_FILE, {})
    now = time.time()
    with _LOGIN_LOCK:
        for store, field in ((_login_fails, "users"),
                             (_login_ip_fails, "ips"),
                             (_login_global, "global")):
            store.clear()
            store.update(data.get(field) or {})
            _prune_dim(store, now)


def _login_locked_for(key: str) -> int:
    """Seconds remaining on an active per-username lock (back-compat helper)."""
    with _LOGIN_LOCK:
        return _locked_for_dim(_login_fails, key, time.time())


def _login_check(uname: str, ip: str) -> int:
    """Max seconds remaining across every dimension that applies to this attempt
    (username, source IP, global). 0 means no dimension is currently locked."""
    now = time.time()
    with _LOGIN_LOCK:
        rem = _locked_for_dim(_login_fails, uname, now)
        rem = max(rem, _locked_for_dim(_login_global, _GLOBAL_KEY, now))
        if ip:
            rem = max(rem, _locked_for_dim(_login_ip_fails, ip, now))
        return rem


def _login_register_failure(uname: str, ip: str = None) -> None:
    """Record one failed attempt against username + IP + global, then persist."""
    now = time.time()
    with _LOGIN_LOCK:
        _note_failure_dim(_login_fails, uname, now, LOGIN_MAX_FAILS, LOGIN_TRACK_CAP)
        if ip:
            _note_failure_dim(_login_ip_fails, ip, now,
                              LOGIN_IP_MAX_FAILS, LOGIN_TRACK_CAP)
        _note_failure_dim(_login_global, _GLOBAL_KEY, now,
                          LOGIN_GLOBAL_MAX_FAILS, None)
        _login_persist()


def _login_note_failure(key: str) -> None:
    """Record a per-username failure only (back-compat helper); then persist."""
    now = time.time()
    with _LOGIN_LOCK:
        _note_failure_dim(_login_fails, key, now, LOGIN_MAX_FAILS, LOGIN_TRACK_CAP)
        _login_persist()


def _login_prune(now: float) -> None:
    """Back-compat: prune the per-username store. Caller holds _LOGIN_LOCK."""
    _prune_dim(_login_fails, now)


def _login_note_success(uname: str, ip: str = None) -> None:
    """A full success clears the username's and the source IP's counters (a
    legitimate user must not lock their own IP), but NOT the global bucket â€”
    other attackers' attempts there still count. Then persist."""
    with _LOGIN_LOCK:
        _login_fails.pop(uname, None)
        if ip:
            _login_ip_fails.pop(ip, None)
        _login_persist()


def _login_clear(key: str) -> None:
    """Clear a per-username counter (used by account-setup); then persist."""
    with _LOGIN_LOCK:
        _login_fails.pop(key, None)
        _login_persist()


_login_load()                          # restore persisted locks at startup


@app.post("/api/login")
def login(req: LoginRequest, request: Request = None):
    uname = req.username.strip()
    ip = _client_ip(request)
    # Throttle BEFORE any credential work â€” denies the attacker free PBKDF2 calls
    # and applies even to unknown usernames (no account-existence oracle). Checks
    # the per-account, per-IP and global ceilings together.
    locked = _login_check(uname, ip)
    if locked > 0:
        raise HTTPException(429, f"Too many attempts. Try again in {locked}s.",
                            headers={"Retry-After": str(locked)})
    users = load_users()
    user = users.get(uname)
    if not user:
        _login_register_failure(uname, ip)
        raise HTTPException(401, "Unknown username")
    # Invited accounts: first login is username-only (owner-ratified 2026-07-17,
    # replacing the C-2 setup PIN).  The token issued here is scope-limited:
    # verify_token rejects must_reset accounts, so it only works for
    # /api/account/setup and WebAuthn enrolment.  The login throttle above
    # bounds username guessing.
    if user.get("must_reset"):
        return {"token": make_token(uname), "username": uname,
                "role": user["role"], "must_reset": True}
    secret = user.get("mfa_secret") or ""
    if not secret:
        _login_register_failure(uname, ip)
        raise HTTPException(401, "Authenticator not set up â€” contact the owner")
    if not pyotp.TOTP(secret).verify(req.mfa_code, valid_window=1):
        _login_register_failure(uname, ip)
        raise HTTPException(401, "Bad MFA code")
    _login_note_success(uname, ip)
    return {"token": make_token(uname), "username": uname, "role": user["role"]}


@app.get("/api/me")
def me(username: str = Depends(verify_token)):
    u = load_users()[username]
    mode = _user_vertex_access_mode(username)
    return {
        "username": username,
        "role": u["role"],
        "must_reset": bool(u.get("must_reset")),
        "vertex_access": mode,
        "vertex_ready": _user_can_use_vertex(username),
        "subscription_status": u.get("subscription_status") or (
            "active" if u.get("role") == "Owner" else "none"
        ),
        "billing_enabled": BILLING_ENABLED,
    }


# ------------------------------------------------- invitations (Owner -> dev)

class InviteRequest(BaseModel):
    username: str = ""             # optional; auto-generated if blank


def _gen_invite_username(req_username: str) -> str:
    return req_username.strip() or ("dev-" + secrets.token_hex(3))


@app.post("/api/invite")
def invite(req: InviteRequest, _: str = Depends(verify_owner)):
    with _USERS_LOCK:
        users = load_users()
        uname = _gen_invite_username(req.username)
        if not re.fullmatch(r"[A-Za-z0-9_.-]{2,32}", uname):
            raise HTTPException(400, "Bad username")
        if uname in users:
            raise HTTPException(409, "Username already exists")
        if _is_erased(uname):                     # M-7 tombstone guard
            raise HTTPException(403, "That username was erased and cannot be reused")
        # Owner-ratified 2026-07-17: invites are username-only (no setup PIN).
        # The invite token is scope-limited by verify_token's must_reset gate
        # (only account/setup + WebAuthn enrol accept it), and the login
        # throttle bounds guessing.  Residual risk â€” someone who learns a
        # pending username before its owner logs in can claim it â€” is accepted;
        # auto-generated dev-<hex> names keep that window unguessable.
        users[uname] = {
            "role": "Member",
            "mfa_secret": "", "must_reset": True, "created": int(time.time()),
        }
        save_users(users)
    return {"username": uname}


# ------------------------------------------------- commercial billing (OmniTender â†’ CodeMonkeys)
# Ratified docs/COMMERCIAL.md. Fail-closed: routes that need Stripe raise 503
# unless BILLING_ENABLED (secrets present). Public status always answers.

def _load_subscriptions() -> dict:
    if not os.path.exists(SUBSCRIPTIONS_FILE):
        return {}
    try:
        with open(SUBSCRIPTIONS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _save_subscriptions(data: dict) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = SUBSCRIPTIONS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)
    os.replace(tmp, SUBSCRIPTIONS_FILE)
    try:
        os.chmod(SUBSCRIPTIONS_FILE, 0o600)
    except OSError:
        pass


def _billing_public_info() -> dict:
    return {
        "enabled": BILLING_ENABLED,
        "product": BILLING_PRODUCT,
        "seller": BILLING_SELLER,
        "price_usd": BILLING_PRICE_USD,
        "interval": "month",
        "tagline": "Coding agents as entertainment - free models wired for you.",
    }


def _stripe_form_post(path: str, data: dict) -> dict:
    if not STRIPE_SECRET_KEY:
        raise HTTPException(503, "Billing not configured")
    r = requests.post(
        f"https://api.stripe.com/v1/{path}",
        auth=(STRIPE_SECRET_KEY, ""),
        data=data,
        timeout=30,
    )
    if r.status_code >= 400:
        detail = "Stripe error"
        try:
            detail = r.json().get("error", {}).get("message") or detail
        except Exception:
            pass
        raise HTTPException(502, detail)
    return r.json()


def _verify_stripe_webhook(payload: bytes, sig_header: str) -> dict:
    """Verify Stripe-Signature (t=â€¦,v1=â€¦) without the stripe SDK."""
    if not STRIPE_WEBHOOK_SECRET:
        raise HTTPException(503, "Billing not configured")
    if not sig_header:
        raise HTTPException(400, "Missing Stripe-Signature")
    parts = {}
    for item in sig_header.split(","):
        if "=" in item:
            k, v = item.split("=", 1)
            parts.setdefault(k.strip(), []).append(v.strip())
    try:
        ts = parts["t"][0]
        candidates = parts.get("v1") or []
    except (KeyError, IndexError):
        raise HTTPException(400, "Bad Stripe-Signature")
    try:
        if abs(time.time() - int(ts)) > 300:
            raise HTTPException(400, "Webhook timestamp too old")
    except ValueError:
        raise HTTPException(400, "Bad Stripe-Signature timestamp")
    signed = f"{ts}.".encode() + payload
    expected = hmac.new(
        STRIPE_WEBHOOK_SECRET.encode(), signed, hashlib.sha256
    ).hexdigest()
    if not any(hmac.compare_digest(expected, c) for c in candidates):
        raise HTTPException(400, "Bad Stripe signature")
    try:
        return json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise HTTPException(400, "Bad JSON body")


def _activate_subscriber(username: str, *, customer_id: str = "",
                         subscription_id: str = "", status: str = "active") -> None:
    """Create or refresh a Member seat for a paid username; seed free pack."""
    uname = (username or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_.-]{2,32}", uname):
        _log.warning("billing: ignoring bad username %r", username)
        return
    if _is_erased(uname):
        _log.warning("billing: refusing erased username %s", uname)
        return
    with _USERS_LOCK:
        users = load_users()
        user = users.get(uname)
        if user and user.get("role") == "Owner":
            # Never demote / overwrite the Owner via Stripe metadata.
            user["subscription_status"] = "active"
            users[uname] = user
        elif user:
            user["subscription_status"] = status
            if customer_id:
                user["stripe_customer_id"] = customer_id
            if subscription_id:
                user["stripe_subscription_id"] = subscription_id
            users[uname] = user
        else:
            users[uname] = {
                "role": "Member",
                "mfa_secret": "",
                "must_reset": True,
                "created": int(time.time()),
                "subscription_status": status,
                "stripe_customer_id": customer_id,
                "stripe_subscription_id": subscription_id,
                "source": "stripe",
            }
        save_users(users)
    with _SUBSCRIPTIONS_LOCK:
        subs = _load_subscriptions()
        key = subscription_id or f"user:{uname}"
        subs[key] = {
            "username": uname,
            "customer_id": customer_id,
            "subscription_id": subscription_id,
            "status": status,
            "updated": int(time.time()),
        }
        _save_subscriptions(subs)
    if status == "active":
        try:
            ensure_free_pack_ready()
        except Exception as e:
            _log.error("free pack seed failed: %s", e)


def _deactivate_subscriber(username: str = "", subscription_id: str = "") -> None:
    with _USERS_LOCK:
        users = load_users()
        target = username
        if not target and subscription_id:
            for u, d in users.items():
                if d.get("stripe_subscription_id") == subscription_id:
                    target = u
                    break
        if target and target in users and users[target].get("role") != "Owner":
            users[target]["subscription_status"] = "canceled"
            save_users(users)
    if subscription_id:
        with _SUBSCRIPTIONS_LOCK:
            subs = _load_subscriptions()
            if subscription_id in subs:
                subs[subscription_id]["status"] = "canceled"
                subs[subscription_id]["updated"] = int(time.time())
                _save_subscriptions(subs)


@app.get("/api/billing/status")
def billing_status():
    """Public commercial offer â€” always available (enabled may be false)."""
    return _billing_public_info()


class CheckoutRequest(BaseModel):
    username: str
    success_url: str = ""
    cancel_url: str = ""


@app.post("/api/billing/checkout")
def billing_checkout(req: CheckoutRequest, request: Request):
    """Start Stripe Checkout for a $1/mo CodeMonkeys seat (OmniTender seller)."""
    if not BILLING_ENABLED:
        raise HTTPException(503, "Subscriptions are not enabled on this host")
    uname = req.username.strip()
    if not re.fullmatch(r"[A-Za-z0-9_.-]{2,32}", uname):
        raise HTTPException(400, "Bad username")
    if _is_erased(uname):
        raise HTTPException(403, "That username was erased and cannot be reused")
    users = load_users()
    existing = users.get(uname)
    if existing and existing.get("role") == "Owner":
        raise HTTPException(400, "That username is reserved")
    if existing and not existing.get("must_reset") and (
            existing.get("subscription_status") == "active"):
        raise HTTPException(409, "Username already has an active subscription")
    # Build return URLs from the request host when not supplied.
    base = str(request.base_url).rstrip("/")
    success = (req.success_url or f"{base}/?subscribed=1&u={uname}").strip()
    cancel = (req.cancel_url or f"{base}/?subscribe=cancel").strip()
    session = _stripe_form_post("checkout/sessions", {
        "mode": "subscription",
        "line_items[0][price]": STRIPE_PRICE_ID,
        "line_items[0][quantity]": "1",
        "success_url": success,
        "cancel_url": cancel,
        "client_reference_id": uname,
        "metadata[username]": uname,
        "metadata[product]": BILLING_PRODUCT,
        "metadata[seller]": BILLING_SELLER,
        "subscription_data[metadata][username]": uname,
        "allow_promotion_codes": "true",
    })
    url = session.get("url")
    if not url:
        raise HTTPException(502, "Stripe did not return a checkout URL")
    return {"url": url, "session_id": session.get("id"), "username": uname}


@app.post("/api/billing/webhook")
async def billing_webhook(request: Request):
    if not BILLING_ENABLED:
        raise HTTPException(503, "Billing not configured")
    payload = await request.body()
    sig = request.headers.get("stripe-signature") or request.headers.get("Stripe-Signature") or ""
    event = _verify_stripe_webhook(payload, sig)
    etype = event.get("type") or ""
    obj = (event.get("data") or {}).get("object") or {}
    if etype == "checkout.session.completed":
        uname = (obj.get("client_reference_id")
                 or (obj.get("metadata") or {}).get("username") or "")
        _activate_subscriber(
            uname,
            customer_id=obj.get("customer") or "",
            subscription_id=obj.get("subscription") or "",
            status="active",
        )
    elif etype in ("customer.subscription.updated", "customer.subscription.created"):
        meta = obj.get("metadata") or {}
        uname = meta.get("username") or ""
        status = obj.get("status") or "active"
        mapped = "active" if status in ("active", "trialing") else status
        _activate_subscriber(
            uname,
            customer_id=obj.get("customer") or "",
            subscription_id=obj.get("id") or "",
            status=mapped,
        )
        if mapped not in ("active", "trialing"):
            _deactivate_subscriber(username=uname, subscription_id=obj.get("id") or "")
    elif etype == "customer.subscription.deleted":
        meta = obj.get("metadata") or {}
        _deactivate_subscriber(
            username=meta.get("username") or "",
            subscription_id=obj.get("id") or "",
        )
    return {"ok": True}


@app.post("/api/billing/seed-free-pack")
def billing_seed_free_pack(_: str = Depends(verify_owner)):
    """Owner can re-run free-pack seeding without a Stripe event."""
    return ensure_free_pack_ready()


@app.get("/api/users")
def users_list(_: str = Depends(verify_owner)):
    return {"users": sorted([
        {"username": u, "role": d.get("role"),
         "pending": bool(d.get("must_reset")),
         "has_mfa": bool(d.get("mfa_secret")),
         "subscription_status": d.get("subscription_status") or (
             "active" if d.get("role") == "Owner" else "none"),
         "vertex_access": _user_vertex_access_mode(u),
         "vertex_ready": _user_can_use_vertex(u),
         "vertex_sa_email": d.get("vertex_sa_email", ""),
         "vertex_provisioned": bool(d.get("vertex_provisioned_at")),
         "created": d.get("created", 0)}
        for u, d in load_users().items()], key=lambda x: x["created"])}


class VertexAccessUpdate(BaseModel):
    mode: str = VERTEX_ACCESS_OFF


@app.patch("/api/users/{uname}/vertex")
def users_vertex_access(uname: str, req: VertexAccessUpdate,
                        owner: str = Depends(verify_owner)):
    mode = (req.mode or VERTEX_ACCESS_OFF).strip().lower()
    if mode not in (VERTEX_ACCESS_OFF, VERTEX_ACCESS_ASSIGNED, VERTEX_ACCESS_BYO):
        raise HTTPException(400, "mode must be off, assigned, or byo")
    with _USERS_LOCK:
        users = load_users()
        user = users.get(uname)
        if not user:
            raise HTTPException(404, "No such user")
        if user.get("role") == "Owner":
            raise HTTPException(400, "Owner always has Vertex access when server credentials are configured")
        if mode == VERTEX_ACCESS_OFF:
            user.pop("vertex_access", None)
            for k in ("vertex_sa_email", "vertex_sa_account_id", "vertex_sa_key_name",
                      "vertex_provisioned_at"):
                user.pop(k, None)
        else:
            user["vertex_access"] = mode
            if mode != VERTEX_ACCESS_BYO:
                for k in ("vertex_sa_email", "vertex_sa_account_id", "vertex_sa_key_name",
                          "vertex_provisioned_at"):
                    user.pop(k, None)
        save_users(users)
    if mode != VERTEX_ACCESS_BYO:
        _clear_user_vertex_credentials(uname)
    return {
        "ok": True,
        "username": uname,
        "vertex_access": _user_vertex_access_mode(uname),
        "vertex_ready": _user_can_use_vertex(uname),
    }


@app.post("/api/users/{uname}/vertex/provision")
def users_vertex_provision(uname: str, owner: str = Depends(verify_owner)):
    """One-click: create GCP service account + Vertex role + key for a member.

    Stores the key server-side (member is ready immediately) and returns the
    JSON once for the owner/PA to copy â€” same pattern as starter PIN handoff.
    Requires the server's admin SA to have Service Account Admin + Project IAM Admin.
    """
    with _USERS_LOCK:
        users = load_users()
        if uname not in users:
            raise HTTPException(404, "No such user")
        if users[uname].get("role") == "Owner":
            raise HTTPException(400, "Owner account does not need provisioning")
    result = _provision_member_vertex_sa(uname)
    result["ok"] = True
    return result


def _clear_user_vertex_credentials(username: str) -> None:
    base = _user_vertex_creds_store(username)
    for path in (base, base + ".sa.json"):
        try:
            if os.path.isfile(path):
                os.remove(path)
        except OSError as e:
            _log.warning("vertex BYO clear failed for %r (%s): %s", username, path, e)
    with _VERTEX_TOKEN_LOCK:
        _VERTEX_TOKEN_CACHE.pop(f"byo:{_safe_vertex_username(username)}", None)


class VertexCredentialsUpload(BaseModel):
    credentials_json: str = ""


@app.get("/api/me/vertex")
def me_vertex_status(username: str = Depends(verify_user)):
    mode = _user_vertex_access_mode(username)
    return {
        "mode": mode,
        "ready": _user_can_use_vertex(username),
        "server_vertex_ready": _vertex_credentials_ready(),
        "has_own_credentials": (
            _user_vertex_credentials_ready(username) if mode == VERTEX_ACCESS_BYO else False
        ),
        "project": VERTEX_PROJECT,
        "setup_doc": "projects/shared/vertex-credits/README.md",
    }


@app.post("/api/me/vertex/credentials")
def me_vertex_upload(req: VertexCredentialsUpload, username: str = Depends(verify_user)):
    if _user_vertex_access_mode(username) != VERTEX_ACCESS_BYO:
        raise HTTPException(403, "Your account is not set up for bring-your-own Vertex credentials")
    raw = (req.credentials_json or "").strip()
    if not raw:
        raise HTTPException(400, "credentials_json is required")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        raise HTTPException(400, "Invalid JSON â€” paste the full service account key file")
    if data.get("type") != "service_account":
        raise HTTPException(400, "Expected a Google service account JSON (type: service_account)")
    proj = data.get("project_id") or VERTEX_PROJECT
    if VERTEX_PROJECT and proj != VERTEX_PROJECT:
        raise HTTPException(400, f"Service account must be for project {VERTEX_PROJECT}")
    os.makedirs(VERTEX_USER_CREDS_DIR, mode=0o700, exist_ok=True)
    _write_enc_file(_user_vertex_creds_store(username), data, mode=0o600)
    _user_vertex_sa_materialized(username)
    with _VERTEX_TOKEN_LOCK:
        _VERTEX_TOKEN_CACHE.pop(f"byo:{_safe_vertex_username(username)}", None)
    return {"ok": True, "ready": _user_can_use_vertex(username)}


@app.delete("/api/me/vertex/credentials")
def me_vertex_clear(username: str = Depends(verify_user)):
    if _user_vertex_access_mode(username) != VERTEX_ACCESS_BYO:
        raise HTTPException(403, "Your account is not set up for bring-your-own Vertex credentials")
    _clear_user_vertex_credentials(username)
    return {"ok": True, "ready": False}


# ---------------------------------------------------------------- M-7 erasure
# Constitution invariant M-7 (OWNER-RATIFIED Option A): an erasure request
# HARD-DELETES the subject's record AND every other store keyed to that account,
# writes a tombstone that guards every reactivation path, and emits a receipt.
#
# Stores keyed to a *username* and cleared by the cascade: the users.json record
# (which carries pin_hash/salt/mfa_secret/webauthn credentials), the per-username
# login-throttle counter, the transient in-memory WebAuthn registration
# challenge, the M-4 egress-consent record, and per-user Vertex credentials.
#
# Issue #70 (M-7 follow-up â€” message content): since S6 Layer 1/2 landed, the
# content stores are per-user too, so the cascade also covers them:
#   - sessions are SINGLE-OWNER (session["username"]; only the owner can type
#     into one â€” _session_writable), so the member's sessions are deleted whole
#     (events JSONL + history + index entry) without touching anyone else's;
#   - typed "user" events are additionally tagged with their author at write
#     time (emit()), so any of the member's messages that ever land in a session
#     they do NOT own are found and content-scrubbed individually, leaving the
#     rest of that shared log intact;
#   - uploads, blackboards, per-user KB and cloned repos live under the member's
#     isolated WORKSPACE_DIR/user_<uname>/ subtree, which is deleted whole.
# Residual (disclosed in GOVERNANCE.md): records written BEFORE attribution
# existed â€” legacy username=None sessions and any pre-#70 writes on the
# workspace-root blackboard/KB â€” carry no author and cannot be selectively
# attributed to an erased member; they stay, by design, because deleting those
# shared records would destroy other accounts' (incl. the Owner's) data.
# Feedback reports (data/feedback.jsonl) are anonymous by design (no username
# recorded) and therefore not attributable.

def _load_erased() -> dict:
    """The tombstone map {username: {erased_at, by}}. Caller need not hold a lock
    for a read-only membership test; mutators take _ERASED_LOCK."""
    data = _load_json(ERASED_FILE, {})
    return data if isinstance(data, dict) else {}


def _is_erased(uname: str) -> bool:
    """True if *uname* has been erased â€” guards every reactivation path
    (register, invite, account-setup rename) so an erased id is never reused."""
    return uname in _load_erased()


def _erase_user_data(uname: str, user_snapshot: dict | None = None) -> list:
    """Cascade-delete every DERIVED per-user store for *uname* (the users.json
    record itself is removed by the caller under _USERS_LOCK). Returns the list of
    stores cleared, for the receipt. Best-effort per store: one failure must not
    leave the others behind (and the users.json record is already gone)."""
    cleared = []
    # Per-username login-throttle counter (file + in-memory), reusing the
    # existing serialized helper so a concurrent login can't resurrect it.
    try:
        with _LOGIN_LOCK:
            existed = uname in _login_fails
            _login_fails.pop(uname, None)
            _login_persist()
        if existed:
            cleared.append("login_throttle")
    except Exception as e:                       # never let a derived-store error
        _log.warning("M-7 erasure: login_throttle clear failed for %r: %s", uname, e)
    # Transient WebAuthn registration challenge (in-memory only).
    try:
        if _webauthn_states.pop(uname, None) is not None:
            cleared.append("webauthn_state")
    except Exception as e:
        _log.warning("M-7 erasure: webauthn_state clear failed for %r: %s", uname, e)
    # M-4 cloud-egress consent record (per-user derived store, issue #67).
    try:
        if _clear_egress_consent(uname):
            cleared.append("egress_consent")
    except Exception as e:
        _log.warning("M-7 erasure: egress_consent clear failed for %r: %s", uname, e)
    try:
        rec = user_snapshot if user_snapshot is not None else load_users().get(uname, {})
        if rec.get("vertex_sa_email") or rec.get("vertex_sa_key_name"):
            _gcp_cleanup_member_vertex_sa(uname, rec)
            cleared.append("vertex_gcp_sa")
        elif os.path.isdir(VERTEX_USER_CREDS_DIR):
            base = _user_vertex_creds_store(uname)
            if os.path.isfile(base) or os.path.isfile(base + ".sa.json"):
                _clear_user_vertex_credentials(uname)
                cleared.append("vertex_user_credentials")
    except Exception as e:
        _log.warning("M-7 erasure: vertex_user clear failed for %r: %s", uname, e)
    # Issue #70 â€” message content. Sessions are single-owner, so the member's
    # own sessions go whole; author-tagged strays in OTHER owners' sessions are
    # content-scrubbed in place; the isolated workspace subtree goes whole.
    try:
        if _erase_user_sessions(uname):
            cleared.append("sessions")
    except Exception as e:
        _log.warning("M-7 erasure: sessions clear failed for %r: %s", uname, e)
    try:
        if _scrub_user_authored_events(uname):
            cleared.append("session_events_scrubbed")
    except Exception as e:
        _log.warning("M-7 erasure: event scrub failed for %r: %s", uname, e)
    try:
        if _erase_user_workspace(uname):
            cleared.append("workspace")
    except Exception as e:
        _log.warning("M-7 erasure: workspace clear failed for %r: %s", uname, e)
    return cleared


_M7_ERASED_MARKER = "[erased per M-7]"


def _erase_user_sessions(uname: str) -> int:
    """Hard-delete every session OWNED by *uname* (issue #70). A session is
    single-owner â€” only session["username"] can type into it (_session_writable)
    â€” so the whole record (in-memory entry, events JSONL, history JSON, index
    row) is that member's content and can go without touching any other
    account's data. Legacy username=None sessions are Owner-only and are left
    alone. Returns the number of sessions deleted."""
    if not uname:
        return 0
    doomed = []
    with _SESSIONS_LOCK:
        for sid in [sid for sid, s in SESSIONS.items()
                    if s.get("username") == uname]:
            doomed.append(SESSIONS.pop(sid))
        if doomed:
            _persist_index()
    for s in doomed:
        # Flag first, then stop: emit()/persist_history() check the flag so an
        # in-flight run of this session can no longer re-materialize the files.
        s["_m7_erased"] = True
        try:
            s["stop_flag"].set()
        except Exception:
            pass
        for path in (_events_path(s["id"]),
                     os.path.join(SESSIONS_DIR, f"{s['id']}.history.json")):
            try:
                os.remove(path)
            except OSError:
                pass
    return len(doomed)


def _m7_scrub_event(evt: dict) -> None:
    """Blank every content-bearing string field of an author-tagged event,
    keeping the structural skeleton (i/ts/type) so indices, ordering and the
    surrounding shared log stay intact."""
    for k, v in list(evt.items()):
        if k in ("i", "ts", "type"):
            continue
        if isinstance(v, str):
            evt[k] = _M7_ERASED_MARKER


def _scrub_user_authored_events(uname: str) -> int:
    """Selectively erase *uname*'s author-tagged events from sessions they do
    NOT own (issue #70). Sessions are single-owner today, so after
    _erase_user_sessions this normally finds nothing â€” it is the precise-erasure
    backstop for any tagged message that ever lands in a shared/legacy log.
    Only the tagged events are scrubbed; every other member's (and the Owner's)
    events in the same file are byte-identical afterwards. Returns the number
    of events scrubbed."""
    if not uname:
        return 0
    scrubbed = 0
    with _SESSIONS_LOCK:
        others = {sid: s for sid, s in SESSIONS.items()
                  if s.get("username") != uname}
    for sid, s in others.items():
        # In-memory view (may hold only the restored tail of the log). One
        # malformed session must not abort the scrub of the rest.
        try:
            with s["lock"]:
                for evt in s["events"]:
                    if isinstance(evt, dict) and evt.get("author") == uname:
                        _m7_scrub_event(evt)
        except Exception as e:
            _log.warning("M-7 erasure: in-memory scrub failed for %s: %s", sid, e)
        # Persisted JSONL is the full log â€” rewrite only if a tagged line exists.
        path = _events_path(sid)
        try:
            with open(path, "r", errors="replace") as f:
                lines = f.readlines()
        except OSError:
            continue
        out, hit = [], False
        for line in lines:
            try:
                evt = json.loads(line)
            except ValueError:
                out.append(line)
                continue
            if isinstance(evt, dict) and evt.get("author") == uname:
                _m7_scrub_event(evt)
                hit = True
                scrubbed += 1
                out.append(json.dumps(evt) + "\n")
            else:
                out.append(line)      # untouched lines stay byte-identical
        if hit:
            tmp = path + ".tmp"
            try:
                with open(tmp, "w") as f:
                    f.writelines(out)
                os.replace(tmp, path)
            except OSError as e:
                _log.warning("M-7 erasure: could not rewrite %s: %s", path, e)
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
    return scrubbed


def _erase_user_workspace(uname: str) -> bool:
    """Delete the member's ISOLATED workspace subtree WORKSPACE_DIR/user_<uname>
    (their uploads, per-user blackboards/KB/specs, cloned repos â€” issue #70).
    Strictly guarded so an erasure can never reach shared data: the target must
    be a real directory (not a symlink) whose realpath is a DIRECT child of
    WORKSPACE_DIR named exactly user_<uname>; anything else is refused. The
    workspace ROOT (other members' subtrees, legacy shared files) is never
    touched. Returns True only if the subtree was removed."""
    if not uname:
        return False
    target = os.path.join(WORKSPACE_DIR, f"user_{uname}")
    if not os.path.isdir(target):
        return False
    root = os.path.realpath(WORKSPACE_DIR)
    real = os.path.realpath(target)
    if (os.path.islink(target) or os.path.dirname(real) != root
            or os.path.basename(real) != f"user_{uname}"):
        _log.warning("M-7 erasure: refused workspace delete for %r "
                     "(path did not resolve to a direct user_ subdir)", uname)
        return False
    shutil.rmtree(target, ignore_errors=True)
    return not os.path.isdir(target)


def _write_tombstone(uname: str, by: str) -> int:
    """Mark *uname* erased so it can never be reactivated/re-registered. Called
    while the caller holds _USERS_LOCK so the tombstone lands atomically with the
    record deletion â€” closing the race where a re-register slips in before the
    id is tombstoned. Returns the erased_at timestamp (first erasure wins it)."""
    ts = int(time.time())
    with _ERASED_LOCK:                # lock order is always _USERS_LOCK â†’ _ERASED_LOCK
        erased = _load_erased()
        rec = erased.setdefault(uname, {"erased_at": ts, "by": by})
        _save_json(ERASED_FILE, erased)
        return rec.get("erased_at", ts)


def _write_receipt(uname: str, by: str, stores: list, ts: int) -> None:
    """Append an owner-auditable erasure receipt. Records only the subject's id
    (the M-7-permitted identifier) and the store names â€” never pin/salt/secret/
    credential material."""
    with _ERASED_LOCK:
        try:
            with open(ERASURE_RECEIPTS_FILE, "a") as f:
                f.write(json.dumps({"ts": ts, "event": "erasure", "user": uname,
                                    "by": by, "stores": stores}) + "\n")
        except OSError as e:
            _log.error("M-7 erasure: receipt append failed for %r: %s", uname, e)
    # S-3 (issue #68): commit the receipt to the tamper-evident hash chain too
    # (same minimal fields as the receipt line â€” id + store names only).
    audit_chain_append({"type": "erasure", "ts": ts, "user": uname, "by": by,
                        "stores": list(stores)})
    _log.info("M-7 erasure receipt: user=%s by=%s stores=%s", uname, by, stores)


def _record_erasure(uname: str, by: str, stores: list) -> None:
    """Tombstone + receipt in one call (used by tests / non-locked callers).
    The request path splits these so the tombstone can land under _USERS_LOCK."""
    ts = _write_tombstone(uname, by)
    _write_receipt(uname, by, stores, ts)


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
        user_snapshot = dict(users[uname])
        del users[uname]
        save_users(users)        # primary store gone â†’ tokens for it 401 at once
        # Tombstone INSIDE the users lock: an erased id is unregisterable from the
        # same instant the record vanishes (no re-register/restore race window).
        ts = _write_tombstone(uname, by=owner)
    # Derived per-user stores + receipt can land after the lock is released.
    stores = ["users.json"] + _erase_user_data(uname, user_snapshot=user_snapshot)
    _write_receipt(uname, by=owner, stores=stores, ts=ts)
    return {"ok": True, "erased": uname, "stores": stores}


def _write_role_receipt(uname: str, by: str, old_role: str, new_role: str) -> None:
    """Owner-auditable role-change receipt (multi-admin, 2026-07-20): id + role
    transition + who did it â€” no pin/salt/secret material. Mirrors _write_receipt's
    shape and, like erasures, also lands on the S-3 tamper-evident hash chain."""
    ts = int(time.time())
    entry = {"ts": ts, "event": "role_change", "user": uname, "by": by,
              "old_role": old_role, "new_role": new_role}
    try:
        with open(ROLE_RECEIPTS_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError as e:
        _log.error("role_change: receipt append failed for %r: %s", uname, e)
    audit_chain_append(entry)
    _log.info("role_change receipt: user=%s by=%s %s->%s", uname, by, old_role, new_role)


@app.post("/api/users/{uname}/promote")
def users_promote(uname: str, owner: str = Depends(verify_owner)):
    """Grant Owner (admin) privileges to an existing Member. Owner-only, so
    the very first privilege escalation always requires an already-trusted
    Owner to act â€” self-service accounts (open enrollment or invite) can
    never promote themselves.

    Red-team finding (2026-07-20): a pending invite (must_reset=True) is an
    unclaimed username â€” the invite doc's own accepted residual risk is that
    someone who learns a pending username before its real owner first logs in
    can claim it. That's an accepted risk at Member scope; promoting an
    unclaimed username straight to Owner would let that same race claim Owner
    privileges instead, a much bigger blast radius than what was ever
    accepted. Require the account to have completed setup (must_reset false)
    before it can be promoted."""
    with _USERS_LOCK:
        users = load_users()
        if uname not in users:
            raise HTTPException(404, "No such user")
        if users[uname].get("role") == "Owner":
            raise HTTPException(400, "Already an Owner")
        if users[uname].get("must_reset"):
            raise HTTPException(400, "Can't promote a pending invite that hasn't completed account setup yet")
        users[uname]["role"] = "Owner"
        save_users(users)
    _write_role_receipt(uname, by=owner, old_role="Member", new_role="Owner")
    return {"ok": True, "username": uname, "role": "Owner"}


@app.post("/api/users/{uname}/demote")
def users_demote(uname: str, owner: str = Depends(verify_owner)):
    """Revoke Owner privileges from another admin, back to Member. An Owner
    can never demote themself â€” prevents an accidental zero-Owner lockout,
    same guard shape as users_delete's self-delete block."""
    if uname == owner:
        raise HTTPException(400, "You can't demote your own Owner account")
    with _USERS_LOCK:
        users = load_users()
        if uname not in users:
            raise HTTPException(404, "No such user")
        if users[uname].get("role") != "Owner":
            raise HTTPException(400, "Not an Owner")
        users[uname]["role"] = "Member"
        save_users(users)
    _write_role_receipt(uname, by=owner, old_role="Owner", new_role="Member")
    return {"ok": True, "username": uname, "role": "Member"}


@app.get("/api/erasures")
def erasures_list(_: str = Depends(verify_owner)):
    """Owner-only view of the erasure tombstone trail (M-7 receipt audit): the
    erased id, when, and by whom â€” no other PII."""
    erased = _load_erased()
    return {"erased": sorted(
        ({"username": u, "erased_at": d.get("erased_at"), "by": d.get("by")}
         for u, d in erased.items()),
        key=lambda x: x.get("erased_at") or 0, reverse=True)}


@app.get("/api/role-changes")
def role_changes_list(_: str = Depends(verify_owner)):
    """Owner-only view of the promote/demote receipt trail."""
    entries = []
    try:
        with open(ROLE_RECEIPTS_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        pass
    entries.sort(key=lambda x: x.get("ts") or 0, reverse=True)
    return {"role_changes": entries}


# ------------------------------------------------- M-4 cloud-egress consent
# Recorded, revocable, per-user consent for sending a user's content to a
# third-party model provider. See the EGRESS_CONSENT_FILE comment block (top of
# file) for the two EGRESS_CONSENT_MODE interpretations and the Owner's
# ratified decision (issue #67, 2026-07-13: default is "explicit"). The
# runtime gate lives in call_model / _debate_verify and fails CLOSED: nothing
# is sent when the gate refuses.

_EGRESS_CONSENT_LOCK = threading.Lock()


class EgressConsentError(RuntimeError):
    """M-4: an outbound model call was attempted without effective cloud-egress
    consent for the user. Raised BEFORE any bytes leave the box (fail closed)."""


def _egress_consent_mode() -> str:
    """Current interpretation of an ABSENT consent record. Owner-ratified
    default (2026-07-13, issue #67) is "explicit"; env-tunable back to
    "byok-implied" if ever needed, without a deploy. An unrecognised value
    falls back to the STRICTEST mode â€” never fail open."""
    mode = (os.environ.get("EGRESS_CONSENT_MODE") or "explicit").strip().lower()
    return mode if mode in _EGRESS_CONSENT_MODES else "explicit"


def _load_egress_consent() -> dict:
    """{username: {status, updated_at, history: [{status, ts}, ...]}}"""
    data = _load_json(EGRESS_CONSENT_FILE, {})
    return data if isinstance(data, dict) else {}


def _egress_consent_record(username: str | None) -> dict | None:
    if not username:
        return None
    rec = _load_egress_consent().get(username)
    return rec if isinstance(rec, dict) else None


def _set_egress_consent(username: str, granted: bool) -> dict:
    """Persist a grant/revoke decision (timestamped, with a bounded history so
    the flip-flop trail is auditable). Returns the stored record."""
    ts = int(time.time())
    status = "granted" if granted else "revoked"
    with _EGRESS_CONSENT_LOCK:
        store = _load_egress_consent()
        rec = store.get(username)
        if not isinstance(rec, dict):
            rec = {}
        hist = rec.get("history")
        if not isinstance(hist, list):
            hist = []
        hist.append({"status": status, "ts": ts})
        rec.update({"status": status, "updated_at": ts,
                    "history": hist[-_EGRESS_CONSENT_HISTORY_CAP:]})
        store[username] = rec
        _save_json(EGRESS_CONSENT_FILE, store)
    _log.info("M-4 egress consent %s user=%s", status, username)
    return rec


def _clear_egress_consent(username: str) -> bool:
    """M-7 cascade hook: hard-delete the consent record for an erased account.
    Returns True if a record existed."""
    with _EGRESS_CONSENT_LOCK:
        store = _load_egress_consent()
        if username not in store:
            return False
        store.pop(username, None)
        _save_json(EGRESS_CONSENT_FILE, store)
        return True


def _egress_allowed(username: str | None) -> tuple:
    """(allowed: bool, reason: str). An explicit 'revoked' blocks in EVERY mode;
    an explicit 'granted' allows; an absent record is mode-dependent (see the
    EGRESS_CONSENT_FILE comment block â€” Owner-ratified default is "explicit")."""
    rec = _egress_consent_record(username)
    status = rec.get("status") if rec else None
    if status == "revoked":
        return False, "cloud-egress consent revoked"
    if status == "granted":
        return True, "cloud-egress consent granted"
    if _egress_consent_mode() == "byok-implied":
        return True, "no consent record; byok-implied mode reads owner BYO keys as consent"
    return False, "no cloud-egress consent on record (explicit mode)"


def _require_egress_consent(username: str | None) -> None:
    """The M-4 gate: raise EgressConsentError (fail closed) unless egress of
    *username*'s content to a third-party provider is consented right now."""
    allowed, reason = _egress_allowed(username)
    if not allowed:
        raise EgressConsentError(
            f"Cloud egress blocked (M-4): {reason} for user "
            f"{username or '(unattributed)'!r}. Nothing was sent to the model "
            "provider. Grant consent via POST /api/me/consent/egress "
            '{"granted": true}, or the Owner can review EGRESS_CONSENT_MODE.')


class EgressConsentUpdate(BaseModel):
    granted: bool


@app.get("/api/me/consent/egress")
def me_egress_consent_get(username: str = Depends(verify_user)):
    """The caller's own consent record + what the gate would do right now."""
    rec = _egress_consent_record(username) or {}
    allowed, reason = _egress_allowed(username)
    return {"status": rec.get("status"), "updated_at": rec.get("updated_at"),
            "mode": _egress_consent_mode(),
            "effective_allowed": allowed, "reason": reason}


@app.post("/api/me/consent/egress")
def me_egress_consent_set(req: EgressConsentUpdate,
                          username: str = Depends(verify_user)):
    """Grant or revoke the caller's own cloud-egress consent. Revocation takes
    effect on the next model call, including mid-run (the gate re-checks on
    every call_model invocation)."""
    rec = _set_egress_consent(username, req.granted)
    allowed, _reason = _egress_allowed(username)
    return {"ok": True, "status": rec["status"], "updated_at": rec["updated_at"],
            "mode": _egress_consent_mode(), "effective_allowed": allowed}


# ------------------------------------------------- M-8 backup posture: restore drill
# The drill answers ONE question with a receipt: "would the data tree under
# DATA_DIR actually come back after a restore?" It reads back and validates
# every structured store CM writes (JSON parse + expected shape, JSONL line
# parse, CMENC1 decrypt under the current master key, S-3 chain integrity via
# verify_audit_chain, the sessions tree), then appends the result to
# BACKUP_DRILL_RECEIPTS_FILE and commits a summary to the S-3 hash chain â€”
# the M-7 receipt idiom. It is READ-ONLY over the stores themselves (its only
# write is its own receipt), and failure reasons carry exception class +
# position ONLY, never file bytes, so a corrupted store cannot leak content
# through a receipt or an API response. Run it against the LIVE tree
# (round-trip readability) or a RESTORED snapshot copy via data_dir=
# (scripts/backup_drill.py <dir>) â€” the actual restore drill.

_BACKUP_DRILL_LOCK = threading.Lock()

# Every structured store CM writes under DATA_DIR: (canonical name, the module
# global holding its live path, checker kind). Live runs resolve the global (so
# env overrides like USERS_FILE are honored); data_dir= runs join the canonical
# name under the given tree. The audit chain + sessions tree are checked
# separately below; anything NOT listed here is still caught by the generic
# top-level *.json/*.jsonl sweep in run_backup_drill.
_BACKUP_DRILL_STORES = (
    ("users.json",              "USERS_FILE",             "json-dict"),
    ("erased_accounts.json",    "ERASED_FILE",            "json-dict"),
    ("egress_consent.json",     "EGRESS_CONSENT_FILE",    "json-dict"),
    ("login_throttle.json",     "LOGIN_THROTTLE_FILE",    "json-dict"),
    ("daily_spend.json",        "DAILY_SPEND_FILE",       "json-dict"),
    ("desk_settings.json",      "DESK_SETTINGS_FILE",     "json-dict"),
    ("push_subscriptions.json", "PUSH_SUBS_FILE",         "json-dict"),
    ("subscriptions.json",      "SUBSCRIPTIONS_FILE",     "json-dict"),
    ("push_vapid.json",         "PUSH_VAPID_FILE",        "json"),
    ("feedback_status.json",    "FEEDBACK_STATUS_FILE",   "json"),
    ("model_catalog.json",      "MODEL_CATALOG_FILE",     "json"),
    ("mcp_config.json",         "MCP_CONFIG_FILE",        "json-list"),
    ("feature_flags.json",     "FEATURE_FLAGS_FILE",     "json-dict"),

