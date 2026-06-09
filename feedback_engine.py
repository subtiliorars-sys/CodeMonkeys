#!/usr/bin/env python3
"""
🍌📬 Feedback Engine — Risk Classification & Issue Capture
===========================================================
Accepts user feedback (text + optional screenshot), classifies it by
risk level, and produces structured Issue objects for the Change Forge.

Risk Levels:
  🟢 trivial    — typos, CSS nudges, copy edits (auto-apply)
  🟡 safe       — docs, tests, refactors w/ no behavior change (auto-apply)
  🟠 review     — logic changes, new features, config changes (needs admin)
  🔴 critical   — auth, data, irreversible actions (needs admin + red-team)

Screenshot support: users paste/capture an image, we store it in uploads/
as base64-encoded data URIs and pass a reference to the AI.
"""

import base64
import hashlib
import json
import os
import re
import sys
import time
import uuid
from datetime import datetime

from config_manager import (
    load_config, save_config, get_current_user,
    get_user_tier, USER_TIERS, check_user_permission,
    get_user_openrouter_key, get_or_create_user,
    record_user_spend, is_user_budget_exhausted,
    get_user_budget_info, get_forge_settings,
)

# ── Paths ──────────────────────────────────────────────────────────

def get_data_dir():
    """Get the data directory for storing feedback and screenshots."""
    return os.path.join(
        os.environ.get("BANANA_SHELTER_CONFIG_DIR") or
        os.path.expanduser("~/.banana_shelter"),
        "data"
    )

def get_feedback_dir():
    """Directory for feedback JSON files."""
    fb_dir = os.path.join(get_data_dir(), "feedback")
    os.makedirs(fb_dir, mode=0o700, exist_ok=True)
    return fb_dir

def get_screenshots_dir():
    """Directory for uploaded screenshots."""
    ss_dir = os.path.join(get_data_dir(), "screenshots")
    os.makedirs(ss_dir, mode=0o700, exist_ok=True)
    return ss_dir


# ── Risk Classification ────────────────────────────────────────────

RISK_INDICATORS = {
    "trivial": [
        r"\btypo\b", r"\bspelling\b", r"\bgrammar\b", r"\bcopy\b",
        r"\bspacing\b", r"\bpadding\b", r"\bmargin\b", r"\balign\b",
        r"\bcolor\b", r"\bfont\b", r"\bsize\b", r"\bcomment\b",
        r"\bwording\b", r"\bcapitaliz\w+\b",
    ],
    "safe": [
        r"\bdoc\w*\b", r"\btest\b", r"\brefactor\b", r"\bclean\b",
        r"\blog\w*\b", r"\bcomment\b", r"\breorganiz\w+\b",
        r"\brename\b", r"\bformat\b", r"\bwhitespace\b",
    ],
    "review": [
        r"\bfeature\b", r"\badd\b", r"\bchange\b", r"\bnew\b",
        r"\bconfig\w*\b", r"\bsetting\b", r"\boption\b",
        r"\btoggle\b", r"\bswitch\b", r"\bbutton\b", r"\bpage\b",
        r"\bform\b", r"\binput\b", r"\bmenu\b", r"\bnav\b",
        r"\blayout\b", r"\bdesign\b", r"\bstyl\w+\b",
        r"\bresponsive\b", r"\bmobile\b", r"\bdark mode\b",
        r"\btheme\b", r"\bapi\b", r"\bendpoint\b",
    ],
    "critical": [
        r"\bauth\b", r"\blogin\b", r"\bpassword\b", r"\bkey\b",
        r"\bsecret\b", r"\btoken\b", r"\bpermission\b",
        r"\badmin\b", r"\bdelete\b", r"\bremove\b", r"\bdrop\b",
        r"\bmigrat\w+\b", r"\bdatabase\b", r"\bdata\b",
        r"\bpayment\b", r"\bcharge\b", r"\bmoney\b",
        r"\bfile\b", r"\bdisk\b", r"\bsecurity\b",
        r"\bprivacy\b", r"\bexport\b", r"\bimport\b",
    ],
}


def classify_risk(feedback_text, screenshot_path=None):
    """
    Classify feedback text into a risk level.
    
    Uses keyword matching (fast, no API call needed).
    Returns one of: "trivial", "safe", "review", "critical"
    
    The highest risk indicator wins. If nothing matches, defaults
    to "review" (conservative — always flag for review if unsure).
    """
    if not feedback_text:
        return "review"
    
    text_lower = feedback_text.lower()
    
    # Check critical first (highest priority)
    for pattern in RISK_INDICATORS["critical"]:
        if re.search(pattern, text_lower):
            return "critical"
    
    # Then review-level
    for pattern in RISK_INDICATORS["review"]:
        if re.search(pattern, text_lower):
            return "review"
    
    # Then safe
    for pattern in RISK_INDICATORS["safe"]:
        if re.search(pattern, text_lower):
            return "safe"
    
    # Then trivial
    for pattern in RISK_INDICATORS["trivial"]:
        if re.search(pattern, text_lower):
            return "trivial"
    
    # Conservative default
    return "review"


def estimate_change_cost(risk_level):
    """
    Rough estimate of the API cost to generate solutions for this
    feedback item. Used to quote the user before they proceed.
    
    Returns (generation_cost, apply_cost, total_cost_with_markup)
    """
    # Generating 3 solutions: ~500 tokens input + ~800 tokens output
    # Using cheap model (~$0.00015/1k in, ~$0.0006/1k out)
    gen_input_tokens = 500
    gen_output_tokens = 800
    generation_cost = (gen_input_tokens / 1000) * 0.00015 + (gen_output_tokens / 1000) * 0.0006
    
    # Applying the selected solution: similar cost for validation
    apply_cost = generation_cost * 0.5  # less work to apply
    
    # Markup from forge settings
    forge = get_forge_settings()
    markup = forge.get("markup_multiplier", 2.0)
    total_with_markup = (generation_cost + apply_cost) * markup
    
    return {
        "generation": round(generation_cost, 6),
        "apply": round(apply_cost, 6),
        "total_raw": round(generation_cost + apply_cost, 6),
        "markup_multiplier": markup,
        "total_charged": round(total_with_markup, 6),
    }


# ── Issue Data Model ───────────────────────────────────────────────

def create_issue(feedback_text, screenshot_data=None, screenshot_path=None, user_id=None):
    """
    Create a structured issue from user feedback.
    
    Args:
        feedback_text: The user's feedback text
        screenshot_data: base64-encoded image data (from clipboard paste)
        screenshot_path: local file path to a screenshot
        user_id: the user submitting (default: current user)
    
    Returns:
        dict with issue_id, risk_level, cost_estimate, all metadata
    """
    if user_id is None:
        user_id = get_current_user()
    
    issue_id = str(uuid.uuid4())
    timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    risk = classify_risk(feedback_text, screenshot_path)
    cost = estimate_change_cost(risk)
    
    # Handle screenshot
    saved_screenshot_path = None
    if screenshot_data:
        # Decode and save base64 image
        saved_screenshot_path = _save_screenshot_data(issue_id, screenshot_data)
    elif screenshot_path and os.path.isfile(screenshot_path):
        # Copy file to our screenshots dir
        saved_screenshot_path = _save_screenshot_file(issue_id, screenshot_path)
    
    # Determine user's tier info
    tier = get_user_tier(user_id)
    tier_config = USER_TIERS.get(tier, USER_TIERS["lemur"])
    
    issue = {
        "issue_id": issue_id,
        "user_id": user_id,
        "user_tier": tier,
        "feedback_text": feedback_text,
        "screenshot_path": saved_screenshot_path,
        "has_screenshot": saved_screenshot_path is not None,
        "risk_level": risk,
        "risk_icon": {"trivial": "🟢", "safe": "🟡", "review": "🟠", "critical": "🔴"}.get(risk, "⚪"),
        "cost_estimate": cost,
        "status": "pending",  # pending | generating | forge_ready | applied | rejected | failed
        "created_at": timestamp,
        "can_auto_apply": risk in ("trivial", "safe") and tier_config.get("can_apply_direct", False),
        "needs_review": risk not in ("trivial", "safe") or tier_config.get("needs_review", True),
        "solution_cards": [],    # populated by change_forge
        "applied_solution": None,
        "undo_entry": None,
    }
    
    # Persist the issue
    _save_issue(issue)
    
    return issue


def _save_screenshot_data(issue_id, base64_data):
    """Save a base64-encoded screenshot to disk."""
    ss_dir = get_screenshots_dir()
    # Try to detect image type from data URI
    image_data = base64_data
    ext = ".png"
    
    if base64_data.startswith("data:image/"):
        # Parse data URI: data:image/png;base64,<data>
        header, _, b64 = base64_data.partition(",")
        ext_match = re.search(r"data:image/(\w+)", header)
        if ext_match:
            ext = f".{ext_match.group(1)}"
        image_data = b64
    
    try:
        decoded = base64.b64decode(image_data)
    except Exception:
        # If not valid base64, just store as-is
        decoded = image_data.encode("utf-8")
        ext = ".txt"
    
    filename = f"{issue_id}{ext}"
    filepath = os.path.join(ss_dir, filename)
    with open(filepath, "wb") as f:
        f.write(decoded)
    return filepath


def _save_screenshot_file(issue_id, source_path):
    """Copy a screenshot file to the managed directory."""
    import shutil
    ss_dir = get_screenshots_dir()
    _, ext = os.path.splitext(source_path)
    if not ext:
        ext = ".png"
    filename = f"{issue_id}{ext}"
    dest = os.path.join(ss_dir, filename)
    try:
        shutil.copy2(source_path, dest)
        return dest
    except (IOError, OSError):
        return None


def _save_issue(issue):
    """Persist an issue to disk as JSON."""
    fb_dir = get_feedback_dir()
    filepath = os.path.join(fb_dir, f"{issue['issue_id']}.json")
    with open(filepath, "w") as f:
        json.dump(issue, f, indent=2)
    # Restrict permissions
    os.chmod(filepath, 0o600)
    return filepath


# ── Issue CRUD ─────────────────────────────────────────────────────

def load_issue(issue_id):
    """Load a single issue."""
    fb_dir = get_feedback_dir()
    filepath = os.path.join(fb_dir, f"{issue_id}.json")
    if not os.path.exists(filepath):
        return None
    try:
        with open(filepath, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None


def save_issue(issue):
    """Update and persist an existing issue."""
    return _save_issue(issue)


def list_issues(status=None, user_id=None, risk_level=None, limit=50):
    """List issues, optionally filtered."""
    fb_dir = get_feedback_dir()
    if not os.path.isdir(fb_dir):
        return []
    
    files = sorted(os.listdir(fb_dir), reverse=True)[:limit * 2]  # grab extra, filter
    issues = []
    
    for fname in files:
        if not fname.endswith(".json"):
            continue
        try:
            with open(os.path.join(fb_dir, fname), "r") as f:
                issue = json.load(f)
        except (json.JSONDecodeError, IOError):
            continue
        
        if status and issue.get("status") != status:
            continue
        if user_id and issue.get("user_id") != user_id:
            continue
        if risk_level and issue.get("risk_level") != risk_level:
            continue
        
        issues.append(issue)
        if len(issues) >= limit:
            break
    
    return issues


def get_pending_feedback(user_id=None):
    """Get feedback items needing attention for a user."""
    if user_id is None:
        user_id = get_current_user()
    return list_issues(status="pending", user_id=user_id)


def get_forge_queue():
    """Get all issues that are forge-ready (waiting for admin review)."""
    return list_issues(status="forge_ready", risk_level="review")


def get_auto_applied():
    """Get recently auto-applied changes."""
    return list_issues(status="applied")[:20]


# ── Generate a cost quote for user ─────────────────────────────────

def quote_user_for_feedback(feedback_text, user_id=None):
    """
    Generate a cost quote for submitting feedback.
    Returns a dict the UI can display to the user before they confirm.
    """
    if user_id is None:
        user_id = get_current_user()
    
    tier = get_user_tier(user_id)
    tier_config = USER_TIERS.get(tier, USER_TIERS["lemur"])
    
    if not tier_config.get("pay_markup", True):
        # Lemurs can't submit at all
        return {
            "can_submit": False,
            "reason": f"Your tier ({tier}) cannot submit change requests.",
        }
    
    # Check if they have an API key configured
    user_key = get_user_openrouter_key(user_id)
    if not user_key:
        return {
            "can_submit": False,
            "reason": "No OpenRouter API key configured. Add one via settings or CLI.",
        }
    
    # Check budget
    budget = get_user_budget_info(user_id)
    if budget["spent"] >= budget["limit"]:
        return {
            "can_submit": False,
            "reason": f"Monthly budget exhausted (${budget['spent']:.2f}/${budget['limit']:.2f}). Wait for reset or contact admin.",
        }
    
    # Generate cost estimate
    risk = classify_risk(feedback_text)
    cost = estimate_change_cost(risk)
    
    return {
        "can_submit": True,
        "risk_level": risk,
        "risk_icon": {"trivial": "🟢", "safe": "🟡", "review": "🟠", "critical": "🔴"}.get(risk, "⚪"),
        "cost": cost,
        "budget": budget,
        "message": (
            f"This looks like a **{risk}** change.\n"
            f"Cost to generate solutions: ${cost['generation']:.4f}\n"
            f"Cost to apply if selected: ${cost['apply']:.4f}\n"
            f"Total charged (x{cost['markup_multiplier']:.0f} markup): ${cost['total_charged']:.4f}\n"
            f"Your remaining budget: ${budget['remaining']:.4f}"
        ),
    }


# ── Entry point ────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="CodeMonkeys Feedback Engine")
    parser.add_argument("feedback", nargs="?", help="Feedback text")
    parser.add_argument("--screenshot", "-s", help="Path to screenshot")
    parser.add_argument("--user", "-u", help="User ID (default: current)")
    parser.add_argument("--quote", "-q", action="store_true", help="Just show cost quote")
    args = parser.parse_args()
    
    if args.quote and args.feedback:
        q = quote_user_for_feedback(args.feedback, args.user)
        print(json.dumps(q, indent=2))
    elif args.feedback:
        issue = create_issue(args.feedback, screenshot_path=args.screenshot, user_id=args.user)
        print(f"  📬 Issue created: {issue['issue_id'][:8]}")
        print(f"     Risk: {issue['risk_icon']} {issue['risk_level']}")
        print(f"     Cost: ${issue['cost_estimate']['total_charged']:.4f}")
        print(f"     Screenshot: {'✅' if issue['has_screenshot'] else '❌'}")
    else:
        print("\n  📬 Pending Feedback:")
        for issue in list_issues(status="pending"):
            print(f"     [{issue['issue_id'][:8]}] {issue['risk_icon']} "
                  f"{issue['feedback_text'][:60]} | {issue['user_id']}")
        print(f"\n  📋 Forge Queue (needs review):")
        for issue in get_forge_queue():
            print(f"     [{issue['issue_id'][:8]}] {issue['risk_icon']} "
                  f"{issue['feedback_text'][:60]} | {issue['user_id']}")
