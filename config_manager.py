#!/usr/bin/env python3
"""
🍌 Config Manager — Banana Shelter Configuration
================================================
Safely stores and manages settings including Gemini API keys.

API keys are stored as a list of objects, each with:
  - id: unique identifier (string)
  - name: human-readable label
  - key: the actual API key string
  - created_at: ISO timestamp of creation
  - last_used_at: ISO timestamp or null
  - is_active: boolean

Existing single-key configs are auto-migrated on load.
"""

import json
import os
import stat
import sys
import time
import uuid

# ── Paths ──────────────────────────────────────────────────────────

def get_config_dir():
    """Get config directory path. Override via BANANA_SHELTER_CONFIG_DIR env var."""
    return os.environ.get("BANANA_SHELTER_CONFIG_DIR") or os.path.expanduser("~/.banana_shelter")

def get_config_file():
    """Get config file path."""
    return os.path.join(get_config_dir(), "config.json")

# ── Test detection ─────────────────────────────────────────────────

IN_TEST = "pytest" in sys.modules or os.environ.get("BANANA_SHELTER_TEST") == "1"

# ── Defaults ───────────────────────────────────────────────────────

DEFAULT_CONFIG = {
    "gemini_api_keys": [],          # list of key objects
    "gemini_model": "gemini-2.0-flash",
    "ai_storytelling": False,
    "ai_kayaker_names": False,
    "theme": "default",
    # Keep the old flat key field so migration can detect it
    "gemini_api_key": "",
    # OpenRouter settings
    "openrouter_api_keys": [],      # list of key objects (same format as gemini_api_keys)
    "model_selection_mode": "auto",
    "openrouter_base_model": "",
    # ── Budget (MONTHLY system-wide cap) ────────────────────
    "budget_limit": 200.0,          # Monthly system-wide spend cap in USD
    "budget_spent": 0.0,            # Spent this month (all sources)
    "budget_month": "",             # Current tracking month "YYYY-MM"
    "session_budget": 50.0,         # Per-session cap in USD (agent self-reports)
    "session_spent": 0.0,           # Spent this session (agent self-reports)
    "provider": "openrouter",
    # ── User system ─────────────────────────────────────────
    "users": {},                     # user_id -> user profile dict
    "current_user": "",              # active session user
    "forge_settings": {
        "markup_multiplier": 2.0,    # 2x API cost for non-admin users
        "auto_apply_trivial": True,  # auto-apply trivial changes
        "auto_apply_safe": True,     # auto-apply safe changes as well
        "undo_history": [],          # list of applied changes (for rollback)
    },
}

# ── Directory / file permissions ───────────────────────────────────

def ensure_config_dir():
    """Create config directory with restricted permissions (700)."""
    config_dir = get_config_dir()
    if not os.path.exists(config_dir):
        os.makedirs(config_dir, mode=0o700, exist_ok=True)
    try:
        os.chmod(config_dir, stat.S_IRWXU)
    except PermissionError:
        pass


# ── Core load/save ─────────────────────────────────────────────────

def load_config():
    """Load config from disk. Returns default config if file missing/corrupt."""
    ensure_config_dir()
    config_file = get_config_file()
    if not os.path.exists(config_file):
        return dict(DEFAULT_CONFIG)
    try:
        with open(config_file, "r") as f:
            data = json.load(f)
        merged = dict(DEFAULT_CONFIG)
        merged.update(data)
        # Run migration on every load (idempotent)
        _migrate_legacy_key(merged)
        return merged
    except (json.JSONDecodeError, IOError):
        return dict(DEFAULT_CONFIG)


def save_config(config):
    """Save config to disk with restricted permissions (600)."""
    ensure_config_dir()
    config_file = get_config_file()
    try:
        with open(config_file, "w") as f:
            json.dump(config, f, indent=2)
        os.chmod(config_file, stat.S_IRUSR | stat.S_IWUSR)  # 0o600
        return True
    except IOError as e:
        print(f"  ❌ Could not save config: {e}", file=sys.stderr)
        return False


# ── Migration ──────────────────────────────────────────────────────

def _migrate_legacy_key(config):
    """
    Migrate old single-key format to new key-list format.
    Idempotent: safe to call on every load.
    
    Old format: {"gemini_api_key": "AI-xxx"}
    New format: {"gemini_api_keys": [{"id": "...", "name": "Default Key", "key": "AI-xxx", ...}]}
    """
    old_key = config.get("gemini_api_key", "").strip()
    keys_list = config.get("gemini_api_keys", [])

    # If there's an old key AND the new list is empty, migrate
    if old_key and not keys_list:
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        key_obj = {
            "id": str(uuid.uuid4()),
            "name": "Default Key",
            "key": old_key,
            "created_at": now,
            "last_used_at": None,
            "is_active": True,
        }
        config["gemini_api_keys"] = [key_obj]
        # Clear the legacy field so we don't re-migrate
        config["gemini_api_key"] = ""
        save_config(config)

    # If the old key is empty but we had keys (edge case: re-migration guard)
    # Do nothing — already migrated


# ── API Key CRUD ───────────────────────────────────────────────────

def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def get_all_keys():
    """Return list of all API key objects."""
    config = load_config()
    return config.get("gemini_api_keys", [])


def get_active_key():
    """Get the first active API key string, or empty string if none."""
    keys = get_all_keys()
    for k in keys:
        if k.get("is_active", True) and k.get("key", "").strip():
            return k["key"]
    return ""


def add_key(name, key_value):
    """
    Add a new API key.
    Returns the new key object (including its generated id) or None on failure.
    """
    if not key_value or not key_value.strip():
        return None
    config = load_config()
    keys = config.get("gemini_api_keys", [])
    now = _now()
    key_obj = {
        "id": str(uuid.uuid4()),
        "name": name.strip() or f"Key {len(keys) + 1}",
        "key": key_value.strip(),
        "created_at": now,
        "last_used_at": None,
        "is_active": True,
    }
    keys.append(key_obj)
    config["gemini_api_keys"] = keys
    if save_config(config):
        return key_obj
    return None


def update_key(key_id, updates):
    """
    Update fields of an existing API key.
    `updates` is a dict with optional keys: name, is_active, last_used_at
    Returns True on success.
    """
    config = load_config()
    keys = config.get("gemini_api_keys", [])
    for k in keys:
        if k["id"] == key_id:
            for field in ("name", "is_active", "last_used_at"):
                if field in updates:
                    k[field] = updates[field]
            config["gemini_api_keys"] = keys
            return save_config(config)
    return False


def delete_key(key_id):
    """Remove an API key by id. Returns True on success."""
    config = load_config()
    keys = config.get("gemini_api_keys", [])
    new_keys = [k for k in keys if k["id"] != key_id]
    if len(new_keys) == len(keys):
        return False  # nothing removed
    config["gemini_api_keys"] = new_keys
    return save_config(config)


def has_api_key():
    """Check if at least one active API key is configured."""
    return bool(get_active_key())


# ── OpenRouter API Key CRUD ────────────────────────────────────────

def get_all_openrouter_keys():
    """Return list of all OpenRouter key objects."""
    config = load_config()
    return config.get("openrouter_api_keys", [])


def get_openrouter_active_key():
    """Get the first active OpenRouter API key string, or empty string if none."""
    keys = get_all_openrouter_keys()
    for k in keys:
        if k.get("is_active", True) and k.get("key", "").strip():
            return k["key"]
    return ""


def add_openrouter_key(name, key_value):
    """
    Add a new OpenRouter API key.
    Returns the new key object (including its generated id) or None on failure.
    """
    if not key_value or not key_value.strip():
        return None
    config = load_config()
    keys = config.get("openrouter_api_keys", [])
    now = _now()
    key_obj = {
        "id": str(uuid.uuid4()),
        "name": name.strip() or f"OpenRouter Key {len(keys) + 1}",
        "key": key_value.strip(),
        "created_at": now,
        "last_used_at": None,
        "is_active": True,
    }
    keys.append(key_obj)
    config["openrouter_api_keys"] = keys
    if save_config(config):
        return key_obj
    return None


def update_openrouter_key(key_id, updates):
    """
    Update fields of an existing OpenRouter API key.
    `updates` is a dict with optional keys: name, is_active, last_used_at
    Returns True on success.
    """
    config = load_config()
    keys = config.get("openrouter_api_keys", [])
    for k in keys:
        if k["id"] == key_id:
            for field in ("name", "is_active", "last_used_at"):
                if field in updates:
                    k[field] = updates[field]
            config["openrouter_api_keys"] = keys
            return save_config(config)
    return False


def delete_openrouter_key(key_id):
    """Remove an OpenRouter API key by id. Returns True on success."""
    config = load_config()
    keys = config.get("openrouter_api_keys", [])
    new_keys = [k for k in keys if k["id"] != key_id]
    if len(new_keys) == len(keys):
        return False
    config["openrouter_api_keys"] = new_keys
    return save_config(config)


def clear_openrouter_keys():
    """Clear all OpenRouter API keys."""
    config = load_config()
    config["openrouter_api_keys"] = []
    return save_config(config)


# ── Budget Tracking ────────────────────────────────────────────────

def get_budget_info():
    """
    Return a dict with current budget state:
    limit, spent, remaining, month.
    """
    config = load_config()
    limit = config.get("budget_limit", 200.0)
    spent = config.get("budget_spent", 0.0)
    month = config.get("budget_month", "")
    remaining = max(0.0, limit - spent)
    return {
        "limit": limit,
        "spent": spent,
        "remaining": remaining,
        "month": month,
    }


def _current_month():
    """Return ISO month string 'YYYY-MM' for now."""
    return time.strftime("%Y-%m", time.gmtime())


def record_spend(amount):
    """
    Add to budget_spent. Resets spent to 0 if the current month
    differs from the stored budget_month.
    """
    config = load_config()
    current_month = _current_month()
    stored_month = config.get("budget_month", "")

    if stored_month != current_month:
        config["budget_spent"] = amount
        config["budget_month"] = current_month
    else:
        config["budget_spent"] = config.get("budget_spent", 0.0) + amount

    return save_config(config)


def is_budget_exhausted():
    """Return True if monthly budget_spent >= budget_limit."""
    config = load_config()
    limit = config.get("budget_limit", 200.0)
    return spent >= limit


# ── Session Budget (agent self-reports against this) ──────────────

def get_session_budget_info():
    """
    Return dict with session budget state:
    limit, spent, remaining.
    """
    config = load_config()
    limit = config.get("session_budget", 50.0)
    spent = config.get("session_spent", 0.0)
    remaining = max(0.0, limit - spent)
    return {
        "limit": limit,
        "spent": spent,
        "remaining": remaining,
    }


def record_session_spend(amount):
    """
    Agent self-reports spend against the session budget.
    Also records against the monthly budget.
    Returns (session_remaining, monthly_remaining) or None on failure.
    """
    config = load_config()

    # Session budget
    session_spent = config.get("session_spent", 0.0) + amount
    config["session_spent"] = session_spent

    # Also roll into monthly spend
    current_month = _current_month()
    stored_month = config.get("budget_month", "")
    if stored_month != current_month:
        config["budget_spent"] = amount
        config["budget_month"] = current_month
    else:
        config["budget_spent"] = config.get("budget_spent", 0.0) + amount

    if save_config(config):
        return (
            max(0.0, config.get("session_budget", 50.0) - session_spent),
            max(0.0, config.get("budget_limit", 200.0) - config["budget_spent"]),
        )
    return None


def is_session_exhausted():
    """Return True if session_spent >= session_budget."""
    config = load_config()
    limit = config.get("session_budget", 50.0)
    spent = config.get("session_spent", 0.0)
    return spent >= limit


def reset_session_budget():
    """Reset session_spent to 0 (called when starting a new session)."""
    config = load_config()
    config["session_spent"] = 0.0
    return save_config(config)


def set_budget_limit(new_limit):
    """Set monthly budget limit. Returns True on success."""
    try:
        val = float(new_limit)
        if val < 0:
            return False
        config = load_config()
        config["budget_limit"] = val
        return save_config(config)
    except (ValueError, TypeError):
        return False


def set_session_budget(new_limit):
    """Set session budget limit. Returns True on success."""
    try:
        val = float(new_limit)
        if val < 0:
            return False
        config = load_config()
        config["session_budget"] = val
        return save_config(config)
    except (ValueError, TypeError):
        return False


# ── Model Selection Mode ───────────────────────────────────────────

def get_model_selection_mode():
    """Return 'auto' or 'manual'."""
    config = load_config()
    return config.get("model_selection_mode", "auto")


def set_model_selection_mode(mode):
    """Set model selection mode ('auto' or 'manual'). Returns True on success."""
    if mode not in ("auto", "manual"):
        return False
    config = load_config()
    config["model_selection_mode"] = mode
    return save_config(config)


# ── User System ──────────────────────────────────────────────────
# Tiers: "master_monkey" (admin/you), "silverback" (trusted devs),
#        "howler" (paying users), "lemur" (guests/read-only)

USER_TIERS = {
    "master_monkey": {
        "title": "🐒 Master Monkey",
        "can_apply_direct": True,
        "can_manage_users": True,
        "can_bypass_budget": True,
        "needs_review": False,
        "can_view_forge": True,
        "pay_markup": False,
        "priority": 0,
    },
    "silverback": {
        "title": "🦍 Silverback",
        "can_apply_direct": False,     # changes queue for admin review
        "can_manage_users": False,
        "can_bypass_budget": False,
        "needs_review": True,          # Silverback changes need Master Monkey review
        "can_view_forge": True,
        "pay_markup": True,            # pays markup (but lower than howler)
        "priority": 1,
    },
    "howler": {
        "title": "🐵 Howler",
        "can_apply_direct": False,
        "can_manage_users": False,
        "can_bypass_budget": False,
        "needs_review": True,
        "can_view_forge": False,       # only sees their own feedback, not the forge
        "pay_markup": True,
        "priority": 2,
    },
    "lemur": {
        "title": "🐒 Lemur",
        "can_apply_direct": False,
        "can_manage_users": False,
        "can_bypass_budget": False,
        "needs_review": True,
        "can_view_forge": False,
        "pay_markup": False,           # can't submit changes at all
        "priority": 3,
    },
}

DEFAULT_USER_PROFILE = {
    "tier": "howler",
    "display_name": "",
    "openrouter_api_keys": [],
    "github_tokens": [],           # GitHub Personal Access Tokens
    "budget": {
        "monthly_limit": 5.00,
        "per_change_max": 0.50,
        "spent_this_month": 0.0,
        "budget_month": "",
    },
    "preferences": {
        "theme": "default",
        "model_preference": "auto",
    },
    "created_at": "",
    "feedback_count": 0,
    "change_count": 0,
}


def get_current_user():
    """Get current session user ID from config or env."""
    config = load_config()
    user_id = config.get("current_user", "")
    # Fall back to env var
    if not user_id:
        user_id = os.environ.get("CODEMONKEYS_USER", "")
    # Last fallback: "local" user
    if not user_id:
        user_id = "local"
    return user_id


def set_current_user(user_id):
    """Set the active session user ID."""
    config = load_config()
    config["current_user"] = user_id.strip()
    return save_config(config)


def get_user_profile(user_id=None):
    """Get a user profile. Returns None if not found."""
    if user_id is None:
        user_id = get_current_user()
    config = load_config()
    users = config.get("users", {})
    profile = users.get(user_id)
    if profile is None:
        return None
    # Merge with defaults
    merged = dict(DEFAULT_USER_PROFILE)
    merged.update(profile)
    return merged


def get_or_create_user(user_id=None):
    """Get a user profile, creating it if missing."""
    if user_id is None:
        user_id = get_current_user()
    config = load_config()
    users = config.get("users", {})
    
    if user_id not in users:
        now = _now()
        profile = dict(DEFAULT_USER_PROFILE)
        profile["display_name"] = user_id
        profile["created_at"] = now
        users[user_id] = profile
        config["users"] = users
        save_config(config)
    
    return get_user_profile(user_id)


def set_user_tier(user_id, tier):
    """Set a user's tier. Returns True on success."""
    if tier not in USER_TIERS:
        return False
    config = load_config()
    users = config.get("users", {})
    if user_id not in users:
        users[user_id] = dict(DEFAULT_USER_PROFILE)
    users[user_id]["tier"] = tier
    config["users"] = users
    return save_config(config)


def get_user_tier(user_id=None):
    """Get a user's tier string ('master_monkey', 'silverback', etc)."""
    profile = get_user_profile(user_id)
    if profile is None:
        return "lemur"  # unknown users are guests
    tier = profile.get("tier", "howler")
    if tier not in USER_TIERS:
        return "howler"
    return tier


def check_user_permission(user_id, permission):
    """Check if a user has a specific permission. Returns bool."""
    tier = get_user_tier(user_id)
    tier_config = USER_TIERS.get(tier, USER_TIERS["lemur"])
    return tier_config.get(permission, False)


def get_user_openrouter_key(user_id=None):
    """Get a user's active OpenRouter key (their own BYOK)."""
    if user_id is None:
        user_id = get_current_user()
    
    profile = get_user_profile(user_id)
    if profile is None:
        return ""
    
    keys = profile.get("openrouter_api_keys", [])
    for k in keys:
        if k.get("is_active", True) and k.get("key", "").strip():
            return k["key"]
    return ""


def add_user_openrouter_key(user_id, name, key_value, profile=None):
    """Add an OpenRouter key to a user's profile."""
    if not key_value or not key_value.strip():
        return None
    if profile is None:
        profile = get_or_create_user(user_id)
    
    keys = profile.get("openrouter_api_keys", [])
    now = _now()
    key_obj = {
        "id": str(uuid.uuid4()),
        "name": name.strip() or f"Key {len(keys) + 1}",
        "key": key_value.strip(),
        "created_at": now,
        "last_used_at": None,
        "is_active": True,
    }
    keys.append(key_obj)
    
    config = load_config()
    users = config.get("users", {})
    if user_id not in users:
        users[user_id] = dict(DEFAULT_USER_PROFILE)
    users[user_id]["openrouter_api_keys"] = keys
    config["users"] = users
    if save_config(config):
        return key_obj
    return None


def get_user_budget_info(user_id=None):
    """Get a user's budget state: limit, spent, remaining, month."""
    profile = get_or_create_user(user_id)
    budget = profile.get("budget", {})
    limit = budget.get("monthly_limit", 5.00)
    spent = budget.get("spent_this_month", 0.0)
    month = budget.get("budget_month", "")
    remaining = max(0.0, limit - spent)
    return {
        "limit": limit,
        "spent": spent,
        "remaining": remaining,
        "month": month,
    }


def record_user_spend(user_id, amount, profile=None):
    """Record spend against a user's budget. Resets monthly."""
    if profile is None:
        profile = get_or_create_user(user_id)
    
    current_month = time.strftime("%Y-%m", time.gmtime())
    budget = profile.get("budget", dict(DEFAULT_USER_PROFILE["budget"]))
    stored_month = budget.get("budget_month", "")
    
    if stored_month != current_month:
        budget["spent_this_month"] = amount
        budget["budget_month"] = current_month
    else:
        budget["spent_this_month"] = budget.get("spent_this_month", 0.0) + amount
    
    profile["budget"] = budget
    
    config = load_config()
    users = config.get("users", {})
    users[user_id] = profile
    config["users"] = users
    return save_config(config)


def is_user_budget_exhausted(user_id=None):
    """Check if a user has hit their budget cap."""
    info = get_user_budget_info(user_id)
    return info["spent"] >= info["limit"]


def list_users():
    """Return list of {user_id, tier, display_name, spent} for all users."""
    config = load_config()
    users = config.get("users", {})
    result = []
    for user_id, profile in users.items():
        tier = profile.get("tier", "howler")
        budget = profile.get("budget", {})
        result.append({
            "user_id": user_id,
            "tier": tier,
            "tier_title": USER_TIERS.get(tier, {}).get("title", tier),
            "display_name": profile.get("display_name", user_id),
            "spent": budget.get("spent_this_month", 0.0),
            "limit": budget.get("monthly_limit", 5.00),
        })
    return result


def add_to_undo_log(entry):
    """Add a change entry to the undo history (keeps last 50)."""
    config = load_config()
    forge = config.get("forge_settings", dict(DEFAULT_CONFIG["forge_settings"]))
    history = forge.get("undo_history", [])
    history.append(entry)
    if len(history) > 50:
        history = history[-50:]
    forge["undo_history"] = history
    config["forge_settings"] = forge
    return save_config(config)


def get_undo_log(limit=10):
    """Get recent undo log entries."""
    config = load_config()
    forge = config.get("forge_settings", {})
    history = forge.get("undo_history", [])
    return list(reversed(history))[:limit]


def get_forge_settings():
    """Get forge configuration."""
    config = load_config()
    forge = config.get("forge_settings", dict(DEFAULT_CONFIG["forge_settings"]))
    return forge


def set_forge_setting(key, value):
    """Set a single forge setting."""
    config = load_config()
    forge = config.get("forge_settings", dict(DEFAULT_CONFIG["forge_settings"]))
    if key in forge:
        forge[key] = value
    config["forge_settings"] = forge
    return save_config(config)


# ── Convenience wrappers (backward compat) ────────────────────────

def get_api_key():
    """Legacy: get the first active API key string."""
    return get_active_key()


def set_api_key(key_value):
    """
    Legacy: set/replace the sole API key.
    If keys already exist, replaces the first active one.
    If no keys exist, creates one with name 'Default Key'.
    """
    keys = get_all_keys()
    if keys:
        # Update the first key
        first = keys[0]
        config = load_config()
        for k in config.get("gemini_api_keys", []):
            if k["id"] == first["id"]:
                k["key"] = key_value.strip()
                k["last_used_at"] = None
                break
        return save_config(config)
    else:
        return bool(add_key("Default Key", key_value))


def clear_api_key():
    """Legacy: clear all API keys."""
    config = load_config()
    config["gemini_api_keys"] = []
    return save_config(config)


# ── Interactive CLI ────────────────────────────────────────────────

def configure_api_key_interactive():
    """
    Interactive CLI prompt for entering an API key.
    Offers a choice between Gemini and OpenRouter key setup.
    """
    print("\n  ─── API Key Setup ───")
    print()
    print("  Which provider would you like to configure?")
    print("  1. Google Gemini")
    print("  2. OpenRouter")
    print("  3. Cancel")
    choice = input("\n  > ").strip()
    
    if choice == "1":
        return _configure_gemini_key_interactive()
    elif choice == "2":
        return _configure_openrouter_key_interactive()
    else:
        print("  Cancelled.")
        return False


def _configure_gemini_key_interactive():
    """
    Interactive CLI prompt for entering a Gemini API key.
    """
    print("\n  ─── Gemini API Key Setup ───")
    print()
    print("  Enter your Google Gemini API key.")
    print("  (Get one at https://aistudio.google.com/app/apikey)")
    print()
    print("  Why doesn't this trigger my password manager?")
    print("  → Because this is a terminal app. Browser password managers")
    print("    only activate on web <input type='password'> fields.")
    print("    Your key is stored in a local config file, not in a browser.")
    print()
    
    keys = get_all_keys()
    if keys:
        print(f"  You have {len(keys)} key(s) configured:")
        for k in keys:
            key_val = k.get("key", "")
            masked = key_val[:6] + "…" + key_val[-4:] if len(key_val) > 10 else "…"
            status = "✅ Active" if k.get("is_active", True) else "⛔ Inactive"
            print(f"    {k['name']}: {masked}  ({status})")
        print()
        print("  1. Add another key")
        print("  2. Clear all keys")
        print("  3. Cancel")
        choice = input("\n  > ").strip()
        if choice == "2":
            clear_api_key()
            print("  🗑️  All keys cleared.")
            return True
        elif choice != "1":
            print("  Cancelled.")
            return False
    
    print("  Give this key a name (e.g. 'My Laptop', 'CI Server'):")
    name = input("  Name: ").strip()
    print("  Paste your API key below and press Enter:")
    new_key = input("  API Key: ").strip()
    
    if new_key:
        obj = add_key(name or "CLI Key", new_key)
        if obj:
            print(f"  ✅ API key '{obj['name']}' saved.")
            print(f"  🔒 File permissions: owner-read/write only (0o600)")
            return True
        else:
            print("  ❌ Failed to save key.")
            return False
    else:
        print("  ❌ No key entered.")
        return False


def _configure_openrouter_key_interactive():
    """
    Interactive CLI prompt for entering an OpenRouter API key.
    """
    print("\n  ─── OpenRouter API Key Setup ───")
    print()
    print("  Enter your OpenRouter API key.")
    print("  (Get one at https://openrouter.ai/keys)")
    print()
    
    keys = get_all_openrouter_keys()
    if keys:
        print(f"  You have {len(keys)} key(s) configured:")
        for k in keys:
            key_val = k.get("key", "")
            masked = key_val[:6] + "…" + key_val[-4:] if len(key_val) > 10 else "…"
            status = "✅ Active" if k.get("is_active", True) else "⛔ Inactive"
            print(f"    {k['name']}: {masked}  ({status})")
        print()
        print("  1. Add another key")
        print("  2. Clear all keys")
        print("  3. Cancel")
        choice = input("\n  > ").strip()
        if choice == "2":
            clear_openrouter_keys()
            print("  🗑️  All OpenRouter keys cleared.")
            return True
        elif choice != "1":
            print("  Cancelled.")
            return False
    
    print("  Give this key a name (e.g. 'My Laptop', 'CI Server'):")
    name = input("  Name: ").strip()
    print("  Paste your API key below and press Enter:")
    new_key = input("  API Key: ").strip()
    
    if new_key:
        obj = add_openrouter_key(name or "CLI Key", new_key)
        if obj:
            print(f"  ✅ OpenRouter key '{obj['name']}' saved.")
            print(f"  🔒 File permissions: owner-read/write only (0o600)")
            return True
        else:
            print("  ❌ Failed to save key.")
            return False
    else:
        print("  ❌ No key entered.")
        return False


def show_config_status():
    """Display current config status."""
    config = load_config()
    gemini_keys = config.get("gemini_api_keys", [])
    or_keys = config.get("openrouter_api_keys", [])
    
    print("\n  ─── Config Status ───")
    # Gemini keys
    if gemini_keys:
        print(f"  Gemini API Keys: {'✅' if any(k.get('is_active', True) for k in gemini_keys) else '❌ No active'}")
        for k in gemini_keys:
            key_val = k.get("key", "")
            masked = key_val[:6] + "…" + key_val[-4:] if len(key_val) > 10 else "…"
            status = "✅ Active" if k.get("is_active", True) else "⛔ Inactive"
            print(f"    {k['name']}: {masked}  ({status})")
    else:
        print(f"  Gemini API Keys: ❌ None configured")
    # OpenRouter keys
    if or_keys:
        print(f"  OpenRouter API Keys: {'✅' if any(k.get('is_active', True) for k in or_keys) else '❌ No active'}")
        for k in or_keys:
            key_val = k.get("key", "")
            masked = key_val[:6] + "…" + key_val[-4:] if len(key_val) > 10 else "…"
            status = "✅ Active" if k.get("is_active", True) else "⛔ Inactive"
            print(f"    {k['name']}: {masked}  ({status})")
    else:
        print(f"  OpenRouter API Keys: ❌ None configured")
    # Provider & model info
    print(f"  Provider: {config.get('provider', 'openrouter')}")
    print(f"  Model Selection: {config.get('model_selection_mode', 'auto')}")
    print(f"  Gemini Model: {config.get('gemini_model', 'gemini-2.0-flash')}")
    print(f"  OpenRouter Base Model: {config.get('openrouter_base_model') or '(auto-selected)'}")
    # Budget info
    budget = get_budget_info()
    print(f"  Budget: ${budget['spent']:.2f} / ${budget['limit']:.2f} spent "
          f"({'✅ OK' if not is_budget_exhausted() else '💰 Exhausted'}) "
          f"in {budget['month'] or '(no period)'}")
    # Feature toggles
    print(f"  AI Storytelling: {'✅ On' if config.get('ai_storytelling') else '❌ Off'}")
    print(f"  AI Kayaker Names: {'✅ On' if config.get('ai_kayaker_names') else '❌ Off'}")
    # User info
    current = get_current_user()
    tier = get_user_tier(current)
    tier_title = USER_TIERS.get(tier, {}).get("title", tier)
    print(f"  👤 Current User: {current} ({tier_title})")
    users = list_users()
    if users:
        print(f"  👥 All Users ({len(users)}):")
        for u in users:
            print(f"     {u['user_id']:15s} {u['tier_title']:20s} "
                  f"${u['spent']:.2f}/${u['limit']:.2f}")
    print(f"  Config file: {get_config_file()}")
    print()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--status":
        show_config_status()
    else:
        configure_api_key_interactive()
