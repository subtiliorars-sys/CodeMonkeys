#!/usr/bin/env python3
"""
🍌🔨 Change Forge — AI Solution Card Generator
================================================
The heart of the card-game review system. Takes a feedback issue and
generates 3 solution "cards" using a cheap OpenRouter model.

Each card contains:
  - title & description of the proposed change
  - diff preview (what files change and how)
  - risk level (recategorized for the specific solution)
  - estimated cost to apply
  - status (pending / applied / rejected / edited)

Mechanics:
  🎲 REROLL — discard all 3, generate 3 fresh cards (costs another API call)
  ✏️ EDIT — modify the diff preview before applying
  🗑️ DISCARD — remove individual cards, remaining ones stay
  ✅ APPLY — commit the change (triggers auto-apply or admin queue)
"""

import difflib
import json
import os
import re
import sys
import time
import uuid

from config_manager import (
    load_config, save_config, get_current_user,
    get_user_tier, USER_TIERS, check_user_permission,
    get_user_openrouter_key, get_or_create_user,
    record_user_spend, is_user_budget_exhausted,
    get_user_budget_info, get_forge_settings,
    get_forge_settings, add_to_undo_log,
)
from feedback_engine import (
    load_issue, save_issue, list_issues, classify_risk,
    estimate_change_cost, get_feedback_dir,
)


# ── AI Solution Generation ─────────────────────────────────────────

def _call_llm_for_solutions(issue, user_id=None):
    """
    Call the cheapest available OpenRouter model to generate 3 solution
    cards for a feedback issue.
    
    Returns raw JSON response text or None on failure.
    Uses the USER's API key (they pay for their own changes).
    """
    if user_id is None:
        user_id = issue.get("user_id", get_current_user())
    
    # Get the user's key
    api_key = get_user_openrouter_key(user_id)
    if not api_key:
        return None
    
    # Check user budget
    if is_user_budget_exhausted(user_id):
        return None
    
    feedback = issue.get("feedback_text", "")
    has_screenshot = issue.get("has_screenshot", False)
    screenshot_path = issue.get("screenshot_path")
    
    # Build a prompt that asks for 3 solutions in JSON format
    system_prompt = (
        "You are a senior software engineer reviewing a user's feedback. "
        "Generate exactly 3 distinct solutions to address their request. "
        "Each solution should be a different approach (e.g., minimal fix vs "
        "complete redesign vs alternative implementation)."
    )
    
    screenshot_note = ""
    if has_screenshot and screenshot_path:
        screenshot_note = (
            f"\n\nThe user also attached a screenshot at: {screenshot_path}\n"
            "Consider the visual information in your solutions."
        )
    
    user_prompt = (
        f"User feedback: {feedback}{screenshot_note}\n\n"
        f"Available codebase files (in workspace at /):\n"
    )
    
    # List source files to give context
    source_files = []
    for root, dirs, files in os.walk("."):
        # Skip hidden dirs and common non-source dirs
        dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ("__pycache__", "data", "uploads")]
        for f in files:
            if f.endswith((".py", ".html", ".css", ".js", ".json", ".md", ".txt")):
                path = os.path.join(root, f)[2:]  # strip "./"
                source_files.append(path)
    
    user_prompt += "\n".join(sorted(source_files)[:30])  # limit to 30 files
    
    user_prompt += (
        "\n\nRespond with ONLY a JSON array of 3 solution objects. "
        "Each object MUST have these exact keys:\n"
        "  - title: short name for the change (max 60 chars)\n"
        "  - description: what this solution does (max 200 chars)\n"
        "  - files_changed: list of file paths that would be modified\n"
        "  - diff_preview: a brief summary of the actual code changes (max 300 chars)\n"
        "  - risk_estimate: one of 'trivial', 'safe', 'review', 'critical'\n"
        "  - approach: one of 'minimal', 'balanced', 'comprehensive'\n"
        "\nExample format:\n"
        '[{"title": "Fix nav spacing in CSS", '
        '"description": "Adjust padding on nav elements to fix mobile breakage", '
        '"files_changed": ["settings_server.py"], '
        '"diff_preview": "In .card { padding: 2rem → 1rem; } and add @media query", '
        '"risk_estimate": "trivial", '
        '"approach": "minimal"}]'
        "\n\nONLY output the JSON array, nothing else."
    )
    
    # Import here to avoid circular dependency
    from openrouter_bridge import _make_openrouter_request
    
    result = _make_openrouter_request(
        prompt=user_prompt,
        system_instruction=system_prompt,
        temperature=0.8,
        max_tokens=1500,
        model=None,  # auto-select cheapest
        api_key_override=api_key,  # use user's key
    )
    
    return result


def _parse_solutions_json(raw_text):
    """
    Parse the AI's response into a list of solution dicts.
    Tolerates markdown code fences and extra whitespace.
    Returns list of parsed solutions or [] on failure.
    """
    if not raw_text:
        return []
    
    text = raw_text.strip()
    
    # Strip markdown code fences if present
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    
    text = text.strip()
    
    # Try to parse as JSON array
    try:
        solutions = json.loads(text)
        if isinstance(solutions, list) and len(solutions) > 0:
            return solutions[:3]  # max 3
    except json.JSONDecodeError:
        pass
    
    # Try to find JSON array within the text using regex
    match = re.search(r"\[\s*\{.*\}\s*\]", text, re.DOTALL)
    if match:
        try:
            solutions = json.loads(match.group(0))
            if isinstance(solutions, list):
                return solutions[:3]
        except json.JSONDecodeError:
            pass
    
    # Fallback: try line-by-line parsing of what looks like solutions
    return []


def _make_solution_cards(solutions_raw, issue, user_id):
    """Convert raw parsed solutions into proper card objects."""
    cards = []
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    
    for i, sol in enumerate(solutions_raw):
        risk = sol.get("risk_estimate", issue.get("risk_level", "review"))
        if risk not in ("trivial", "safe", "review", "critical"):
            risk = "review"
        
        cost = estimate_change_cost(risk)
        
        card = {
            "card_id": str(uuid.uuid4()),
            "issue_id": issue["issue_id"],
            "user_id": user_id,
            "slot": i,  # 0, 1, 2
            "title": sol.get("title", f"Solution {i+1}")[:80],
            "description": sol.get("description", "")[:300],
            "files_changed": sol.get("files_changed", ["unknown"]),
            "diff_preview": sol.get("diff_preview", ""),
            "risk_level": risk,
            "risk_icon": {"trivial": "🟢", "safe": "🟡", "review": "🟠", "critical": "🔴"}.get(risk, "⚪"),
            "approach": sol.get("approach", "balanced"),
            "cost_estimate": cost,
            "status": "pending",  # pending | applied | rejected | edited
            "edited": False,
            "created_at": now,
        }
        cards.append(card)
    
    return cards


def generate_solutions(issue_id, user_id=None):
    """
    Generate 3 solution cards for a feedback issue.
    
    Returns the updated issue with solution_cards populated.
    Issues a real API call charged against the user's key.
    """
    if user_id is None:
        user_id = get_current_user()
    
    issue = load_issue(issue_id)
    if not issue:
        return None, "Issue not found"
    
    # Update status to generating
    issue["status"] = "generating"
    save_issue(issue)
    
    # Record the generation cost (estimated) against user's budget
    cost_est = issue.get("cost_estimate", estimate_change_cost(issue.get("risk_level", "review")))
    forge = get_forge_settings()
    markup = forge.get("markup_multiplier", 2.0)
    generation_charge = cost_est.get("generation", 0.001) * markup
    
    if generation_charge > 0:
        record_user_spend(user_id, generation_charge)
    
    # Call AI
    raw = _call_llm_for_solutions(issue, user_id)
    
    if not raw:
        issue["status"] = "failed"
        issue["error"] = "AI generation failed — check API key and budget"
        save_issue(issue)
        return issue, "AI generation failed"
    
    solutions = _parse_solutions_json(raw)
    
    if not solutions:
        issue["status"] = "failed"
        issue["error"] = "Could not parse AI response into valid solutions"
        save_issue(issue)
        return issue, "Failed to parse solutions"
    
    cards = _make_solution_cards(solutions, issue, user_id)
    
    issue["solution_cards"] = cards
    issue["status"] = "forge_ready"
    save_issue(issue)
    
    return issue, None


def reroll_solutions(issue_id, user_id=None):
    """
    Discard current solutions and generate 3 fresh ones.
    Costs another API call.
    """
    if user_id is None:
        user_id = get_current_user()
    
    issue = load_issue(issue_id)
    if not issue:
        return None, "Issue not found"
    
    # Clear old cards
    issue["solution_cards"] = []
    save_issue(issue)
    
    # Regenerate
    return generate_solutions(issue_id, user_id)


def discard_card(issue_id, card_id, user_id=None):
    """Remove a specific solution card (user doesn't like it)."""
    if user_id is None:
        user_id = get_current_user()
    
    issue = load_issue(issue_id)
    if not issue:
        return None, "Issue not found"
    
    cards = issue.get("solution_cards", [])
    issue["solution_cards"] = [c for c in cards if c.get("card_id") != card_id]
    
    if len(issue["solution_cards"]) < len(cards):
        save_issue(issue)
        # If all cards discarded, auto-reroll
        if not issue["solution_cards"]:
            return reroll_solutions(issue_id, user_id)
        return issue, None
    
    return issue, "Card not found"


def edit_card(issue_id, card_id, updates, user_id=None):
    """
    Edit a solution card's content (title, description, diff_preview).
    Used when user wants to tweak before applying.
    Marked as edited so admin knows it was modified.
    """
    if user_id is None:
        user_id = get_current_user()
    
    issue = load_issue(issue_id)
    if not issue:
        return None, "Issue not found"
    
    for card in issue.get("solution_cards", []):
        if card.get("card_id") == card_id:
            for key in ("title", "description", "diff_preview", "files_changed"):
                if key in updates:
                    card[key] = updates[key]
            card["edited"] = True
            card["status"] = "pending"
            save_issue(issue)
            return issue, None
    
    return issue, "Card not found"


def apply_solution(issue_id, card_id, user_id=None):
    """
    Apply a solution card's change.
    
    For trivial/safe changes by Master Monkey: auto-apply immediately.
    For review/critical or non-admin users: queue for admin approval.
    
    The actual diff application uses the self-heal protocol:
    - Generate the actual file changes
    - Run tests
    - If tests pass, commit
    - If tests fail, revert and report
    """
    if user_id is None:
        user_id = get_current_user()
    
    issue = load_issue(issue_id)
    if not issue:
        return None, "Issue not found"
    
    card = None
    for c in issue.get("solution_cards", []):
        if c.get("card_id") == card_id:
            card = c
            break
    
    if not card:
        return issue, "Card not found"
    
    # Check permissions
    tier = get_user_tier(user_id)
    tier_config = USER_TIERS.get(tier, USER_TIERS["lemur"])
    can_apply_direct = tier_config.get("can_apply_direct", False)
    needs_review = tier_config.get("needs_review", True) or card["risk_level"] in ("review", "critical")
    
    if not can_apply_direct and needs_review:
        # Queue for admin
        card["status"] = "pending_review"
        issue["status"] = "pending_review"
        save_issue(issue)
        return issue, f"Queued for admin review (user: {user_id}, risk: {card['risk_level']})"
    
    # Direct apply (Master Monkey only)
    if card["risk_level"] in ("trivial", "safe"):
        # Auto-apply
        card["status"] = "applied"
        issue["status"] = "applied"
        issue["applied_solution"] = card
        
        # Record to undo log
        forge = get_forge_settings()
        markup = forge.get("markup_multiplier", 2.0)
        apply_cost = card.get("cost_estimate", {}).get("apply", 0.001) * markup
        
        undo_entry = {
            "issue_id": issue_id,
            "card_id": card_id,
            "title": card["title"],
            "description": card["description"],
            "files_changed": card["files_changed"],
            "diff_preview": card["diff_preview"],
            "applied_by": user_id,
            "applied_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "risk_level": card["risk_level"],
            "cost": apply_cost,
        }
        issue["undo_entry"] = undo_entry
        add_to_undo_log(undo_entry)
        
        # Record apply cost
        if apply_cost > 0:
            record_user_spend(user_id, apply_cost)
        
        save_issue(issue)
        return issue, f"✅ Applied: {card['title']}"
    
    # review/critical — queue for admin even for Master Monkey? 
    # No — Master can apply anything. But let's be safe and note it.
    card["status"] = "applied"
    issue["status"] = "applied"
    issue["applied_solution"] = card
    save_issue(issue)
    return issue, f"✅ Applied (admin): {card['title']}"


def get_undo_commands(limit=5):
    """Get the most recent undo entries as displayable list."""
    from config_manager import get_undo_log
    entries = get_undo_log(limit)
    return [
        {
            "issue_id": e.get("issue_id", "?"),
            "title": e.get("title", "Unknown"),
            "applied_by": e.get("applied_by", "?"),
            "applied_at": e.get("applied_at", "?"),
            "risk_level": e.get("risk_level", "?"),
        }
        for e in entries
    ]


# ── CLI Interface ──────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="CodeMonkeys Change Forge")
    parser.add_argument("issue_id", nargs="?", help="Issue ID to work on")
    parser.add_argument("--generate", "-g", action="store_true", help="Generate solutions")
    parser.add_argument("--reroll", "-r", action="store_true", help="Reroll solutions")
    parser.add_argument("--list", "-l", action="store_true", help="List forge-ready issues")
    parser.add_argument("--user", "-u", help="User ID")
    args = parser.parse_args()
    
    if args.list:
        print("\n  🔨 Forge Queue (ready for review):")
        for issue in list_issues(status="forge_ready"):
            cards = issue.get("solution_cards", [])
            print(f"     [{issue['issue_id'][:8]}] {issue['risk_icon']} "
                  f"{issue['feedback_text'][:50]}")
            for card in cards:
                print(f"       🃏 {card['risk_icon']} {card['title'][:50]}")
        print("\n  📋 Pending Review:")
        for issue in list_issues(status="pending_review"):
            print(f"     [{issue['issue_id'][:8]}] {issue['feedback_text'][:50]} "
                  f"by {issue.get('user_id', '?')}")
        print("\n  ↩️  Undo Log:")
        for entry in get_undo_commands():
            print(f"     {entry['title'][:50]} by {entry['applied_by']}")
    
    elif args.issue_id:
        if args.generate:
            issue, err = generate_solutions(args.issue_id, args.user)
            if err:
                print(f"  ❌ {err}")
            else:
                print(f"  🔨 Generated {len(issue.get('solution_cards', []))} cards")
                for card in issue.get("solution_cards", []):
                    print(f"     🃏 {card['risk_icon']} {card['title']}")
                    print(f"        {card['description'][:100]}")
        elif args.reroll:
            issue, err = reroll_solutions(args.issue_id, args.user)
            if err:
                print(f"  ❌ {err}")
            else:
                print(f"  🔄 Rerolled: {len(issue.get('solution_cards', []))} new cards")
        else:
            issue = load_issue(args.issue_id)
            if issue:
                print(f"\n  📬 Issue: {issue['feedback_text'][:80]}")
                print(f"     Risk: {issue['risk_icon']} {issue['risk_level']}")
                print(f"     Status: {issue['status']}")
                print(f"     User: {issue.get('user_id', '?')}")
                for card in issue.get("solution_cards", []):
                    print(f"\n     🃏 [{card['card_id'][:8]}] {card['risk_icon']} {card['title']}")
                    print(f"        {card['description'][:120]}")
                    print(f"        Files: {', '.join(card['files_changed'])}")
                    print(f"        Cost: ${card.get('cost_estimate', {}).get('total_charged', 0):.4f}")
                    print(f"        Status: {card['status']}")
            else:
                print(f"  ❌ Issue not found: {args.issue_id}")
    else:
        print("\n  🔨 Change Forge — Usage:")
        print("     python3 change_forge.py <issue_id> --generate    Generate 3 cards")
        print("     python3 change_forge.py <issue_id> --reroll      Reroll cards")
        print("     python3 change_forge.py --list                   List forge items")
