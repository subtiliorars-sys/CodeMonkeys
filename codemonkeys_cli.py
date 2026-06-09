#!/usr/bin/env python3
"""
🍌💻 CodeMonkeys CLI
====================
Interactive command-line interface for CodeMonkeys agent system.
Supports prompt submission, /loop commands, and queue management.

Usage:
  python3 codemonkeys_cli.py                    # Interactive REPL
  python3 codemonkeys_cli.py "prompt"           # Single prompt
  echo "prompt" | python3 codemonkeys_cli.py    # Pipe input
"""

import sys
import threading
import time

from queue_manager import _queue, loop_command, get_queue_status, get_active_loops
from gemini_integration import is_ai_available
from config_manager import (
    get_budget_info, is_budget_exhausted, show_config_status,
    get_current_user, get_user_tier, USER_TIERS,
    get_session_budget_info, is_session_exhausted,
    record_session_spend, set_budget_limit, set_session_budget,
)
from feedback_engine import create_issue, list_issues, quote_user_for_feedback, get_pending_feedback
from change_forge import generate_solutions, reroll_solutions, get_undo_commands, apply_solution


# ── Result polling ──────────────────────────────────────────────
# Background thread watches for completed results and prints them
# as they arrive. Tracks already-reported IDs to avoid duplicates.

_reported_results = set()
_reported_lock = threading.Lock()
_polling_active = threading.Event()


def _poll_results():
    """Background thread: watch _queue.results and print new completions."""
    while True:
        try:
            with _queue._results_lock:
                for task_id, result in list(_queue.results.items()):
                    with _reported_lock:
                        if task_id in _reported_results:
                            continue
                        _reported_results.add(task_id)

                    status = result.get("status", "unknown")
                    if status == "completed":
                        text = result.get("result", "")
                        print(f"\n  ✅ [{task_id[:8]}] Result:")
                        for line in text.split("\n"):
                            print(f"     {line}")
                        print()
                        # Refresh the prompt indicator after output
                        print(">>> ", end="", flush=True)
                    elif status == "failed":
                        error = result.get("error", "Unknown error")
                        print(f"\n  ❌ [{task_id[:8]}] Failed: {error}")
                        print()
                        print(">>> ", end="", flush=True)
        except Exception:
            # Swallow poller errors — never crash the background thread
            pass
        _polling_active.wait(0.3)


def _start_result_poller():
    """Start the daemon result-polling background thread."""
    _polling_active.clear()
    t = threading.Thread(target=_poll_results, daemon=True)
    t.start()


# ── Command handlers ────────────────────────────────────────────

def cmd_loop(args_str):
    """/loop <duration> <prompt> — start a repeating loop."""
    try:
        parts = args_str.strip().split(maxsplit=1)
        if len(parts) < 2:
            raise ValueError(
                "Usage: /loop <duration> <prompt>. "
                "Example: /loop 15m 'tell me a joke'"
            )
        duration_str = parts[0]
        prompt_raw = parts[1].strip()
        # Strip matching quotes if present
        if len(prompt_raw) >= 2 and prompt_raw[0] == prompt_raw[-1] and prompt_raw[0] in ('"', "'"):
            prompt = prompt_raw[1:-1]
        else:
            prompt = prompt_raw
        if not prompt:
            raise ValueError("Prompt is empty")

        loop_id = loop_command.start_loop(duration_str, prompt)
        print(f"  🔁 Loop started [{loop_id[:8]}]")
        print(f"     Prompt: {prompt[:60]}{'...' if len(prompt) > 60 else ''}")
        print(f"     Interval: {duration_str}")
    except ValueError as e:
        print(f"  ❌ {e}")


def cmd_queue():
    """/queue — show queue status and active loops."""
    status = get_queue_status()
    print(f"  📊 Queue Status:")
    print(f"     Pending:   {status['queue_size']}")
    print(f"     Active:    {'🔄 Yes' if status['active'] else '💤 No'}")
    print(f"     Completed: {status['completed_count']}")
    print(f"     Failed:    {status['failed_count']}")

    loops = get_active_loops()
    if loops:
        _print_loops(loops)


def cmd_loops():
    """/loops — show all active loops."""
    loops = get_active_loops()
    if not loops:
        print("  🔁 No active loops")
        return
    _print_loops(loops)


def _print_loops(loops):
    """Print a formatted list of active loops."""
    print(f"  🔁 Active Loops ({len(loops)}):")
    for loop in loops:
        elapsed_str = _format_duration(loop["elapsed"])
        interval_str = _format_duration(loop["interval"])
        print(f"     [{loop['loop_id'][:8]}] iter {loop['iteration']} "
              f"| {interval_str} interval | elapsed {elapsed_str}")
        print(f"       ⤷ {loop['prompt']}")


def cmd_stop(loop_id_str):
    """/stop <loop_id> — stop a specific loop. Accepts full or truncated ID."""
    loop_id_str = loop_id_str.strip()
    if not loop_id_str:
        print("  ❌ Usage: /stop <loop_id>")
        return

    # Try exact match first, then prefix match
    loops = get_active_loops()
    matched = None
    for loop in loops:
        lid = loop["loop_id"]
        if lid == loop_id_str:
            matched = lid
            break
        if lid.startswith(loop_id_str):
            if matched is not None:
                print(f"  ⚠️  Ambiguous: '{loop_id_str}' matches multiple loop IDs")
                return
            matched = lid

    if matched is None:
        print(f"  ⚠️  No active loop found for ID '{loop_id_str}'")
        _print_loops(get_active_loops())
        return

    if loop_command.stop_loop(matched):
        print(f"  🛑 Stopped loop [{matched[:8]}]")
    else:
        print(f"  ⚠️  Could not stop loop [{matched[:8]}]")


def cmd_stopall():
    """/stopall — stop all active loops."""
    count = len(get_active_loops())
    if count == 0:
        print("  🔁 No active loops to stop")
        return
    loop_command.stop_all_loops()
    print(f"  🛑 Stopped all {count} active loop{'s' if count != 1 else ''}")


def cmd_budget(args_str=""):
    """/budget [set <amount>] [session <amount>] — show/set budget caps."""
    parts = args_str.strip().split() if args_str.strip() else []
    if parts:
        if parts[0] == "set" and len(parts) >= 2:
            try:
                val = float(parts[1])
                if val <= 0:
                    print("  ❌ Budget must be positive")
                    return
                if set_budget_limit(val):
                    print(f"  ✅ Monthly budget limit set to ${val:.2f}")
                else:
                    print("  ❌ Failed to set budget")
            except ValueError:
                print("  ❌ Usage: /budget set <amount>. Example: /budget set 5.00")
            return
        elif parts[0] == "session" and len(parts) >= 2:
            try:
                val = float(parts[1])
                if val <= 0:
                    print("  ❌ Session budget must be positive")
                    return
                if set_session_budget(val):
                    print(f"  ✅ Session budget limit set to ${val:.2f}")
                else:
                    print("  ❌ Failed to set session budget")
            except ValueError:
                print("  ❌ Usage: /budget session <amount>. Example: /budget session 2.00")
            return
        else:
            print("  ❌ Usage: /budget [set <amount>] [session <amount>]")
            return

    # Show both budgets
    monthly = get_budget_info()
    session = get_session_budget_info()
    monthly_exhausted = is_budget_exhausted()
    session_exhausted = is_session_exhausted()

    print(f"  📅 Monthly Budget:")
    print(f"     Limit:     ${monthly['limit']:.2f}")
    print(f"     Spent:     ${monthly['spent']:.2f}")
    print(f"     Remaining: ${monthly['remaining']:.2f}")
    print(f"     Period:    {monthly['month'] or 'N/A'}")
    print(f"     Status:    {'💰 EXHAUSTED' if monthly_exhausted else '✅ OK'}")
    print()
    print(f"  🎯 Session Budget (agent self-report):")
    print(f"     Limit:     ${session['limit']:.2f}")
    print(f"     Spent:     ${session['spent']:.2f}")
    print(f"     Remaining: ${session['remaining']:.2f}")
    print(f"     Status:    {'💰 EXHAUSTED' if session_exhausted else '✅ OK'}")
    print()
    print(f"  💡 Set caps: /budget set <amount>  or  /budget session <amount>")


def cmd_clear():
    """/clear — drain all pending prompts from the queue."""
    count = 0
    while True:
        try:
            _queue.queue.get_nowait()
            _queue.queue.task_done()
            count += 1
        except Exception:
            break
    if count:
        print(f"  🧹 Cleared {count} pending prompt{'s' if count != 1 else ''} from queue")
    else:
        print(f"  📭 Queue was already empty")


def cmd_feedback(args_str):
    """/feedback <text> [--screenshot path] — submit change request feedback."""
    parts = args_str.strip().split(" --screenshot ", maxsplit=1)
    text = parts[0].strip()
    screenshot_path = parts[1].strip() if len(parts) > 1 else None

    if not text:
        # Interactive mode — prompt for feedback
        print("  📝 Describe what you'd like changed:")
        text = input("  > ").strip()
        if not text:
            print("  ❌ No feedback entered.")
            return
        print("  📷 Paste screenshot path (or press Enter to skip):")
        ss = input("  > ").strip()
        if ss:
            screenshot_path = ss

    user_id = get_current_user()
    tier = get_user_tier(user_id)
    tier_config = USER_TIERS.get(tier, {})

    # Show cost quote
    quote = quote_user_for_feedback(text, user_id)
    if not quote.get("can_submit"):
        print(f"  ❌ {quote.get('reason', 'Cannot submit')}")
        return

    print(f"\n  📬 Feedback Quote:")
    print(f"     Risk: {quote['risk_icon']} {quote['risk_level']}")
    print(f"     Generation: ${quote['cost']['generation']:.4f}")
    print(f"     Apply: ${quote['cost']['apply']:.4f}")
    print(f"     Markup: {quote['cost']['markup_multiplier']:.0f}x")
    print(f"     Total charged: ${quote['cost']['total_charged']:.4f}")
    print(f"     Budget remaining: ${quote['budget']['remaining']:.4f}")
    print()
    confirm = input("  Submit? (y/N): ").strip().lower()
    if confirm != "y":
        print("  Cancelled.")
        return

    # Create the issue
    issue = create_issue(
        feedback_text=text,
        screenshot_path=screenshot_path,
        user_id=user_id,
    )
    print(f"\n  ✅ Issue created [{issue['issue_id'][:8]}]")
    print(f"     Risk: {issue['risk_icon']} {issue['risk_level']}")
    print(f"     Status: {issue['status']}")

    # Auto-generate for admins
    if tier_config.get("can_apply_direct"):
        print("  🔨 Generating solution cards...")
        updated, err = generate_solutions(issue["issue_id"], user_id)
        if err:
            print(f"  ⚠️  Generation: {err}")
        else:
            cards = updated.get("solution_cards", [])
            print(f"     Generated {len(cards)} cards:")
            for c in cards:
                print(f"       🃏 [{c['card_id'][:8]}] {c['risk_icon']} {c['title']}")
    else:
        print("  ⏳ Queued for admin review.")


def cmd_forge(args_str):
    """/forge [list|show <id>|generate <id>|reroll <id>|apply <id> <card_id>] — Change Forge management."""
    if not args_str.strip():
        # Show forge overview
        print("\n  🔨 Change Forge")
        print("  ──────────────")

        forge_ready = list_issues(status="forge_ready")
        if forge_ready:
            print(f"\n  🟠 Ready for Review ({len(forge_ready)}):")
            for issue in forge_ready:
                cards = issue.get("solution_cards", [])
                print(f"     [{issue['issue_id'][:8]}] {issue['feedback_text'][:60]}")
                for c in cards:
                    cs = "✅" if c.get("status") == "applied" else "🃏"
                    print(f"       {cs} {c['risk_icon']} {c['title'][:50]}")

        pending = list_issues(status="pending_review")
        if pending:
            print(f"\n  ⏳ Pending Review ({len(pending)}):")
            for issue in pending:
                print(f"     [{issue['issue_id'][:8]}] {issue['feedback_text'][:60]} by {issue.get('user_id', '?')}")

        # Undo log
        undo = get_undo_commands(5)
        if undo:
            print(f"\n  ↩️  Recent Changes:")
            for e in undo:
                print(f"     {e['title'][:50]} by {e['applied_by']}")

        print()
        return

    subcmd = args_str.split(maxsplit=1)
    action = subcmd[0].lower()

    if action == "list":
        cmd_forge("")  # same as no args
    elif action == "generate" or action == "gen":
        issue_id = subcmd[1] if len(subcmd) > 1 else ""
        if not issue_id:
            print("  ❌ Usage: /forge generate <issue_id>")
            return
        print(f"  🔨 Generating solutions for [{issue_id[:8]}]...")
        issue, err = generate_solutions(issue_id)
        if err:
            print(f"  ❌ {err}")
        else:
            cards = issue.get("solution_cards", [])
            print(f"  ✅ Generated {len(cards)} cards")
            for c in cards:
                print(f"     🃏 {c['risk_icon']} {c['title']}")
    elif action == "reroll":
        issue_id = subcmd[1] if len(subcmd) > 1 else ""
        if not issue_id:
            print("  ❌ Usage: /forge reroll <issue_id>")
            return
        print(f"  🔄 Rerolling [{issue_id[:8]}]...")
        issue, err = reroll_solutions(issue_id)
        if err:
            print(f"  ❌ {err}")
        else:
            cards = issue.get("solution_cards", [])
            print(f"  ✅ {len(cards)} new cards")
            for c in cards:
                print(f"     🃏 {c['risk_icon']} {c['title']}")
    elif action == "show":
        issue_id = subcmd[1] if len(subcmd) > 1 else ""
        if not issue_id:
            print("  ❌ Usage: /forge show <issue_id>")
            return
        from feedback_engine import load_issue
        issue = load_issue(issue_id)
        if not issue:
            print(f"  ❌ Issue not found: {issue_id}")
            return
        print(f"\n  📬 Issue: {issue['feedback_text']}")
        print(f"     Risk: {issue['risk_icon']} {issue['risk_level']}")
        print(f"     Status: {issue['status']}")
        print(f"     User: {issue.get('user_id', '?')}")
        print(f"     Screenshot: {'✅' if issue.get('has_screenshot') else '❌'}")
        for c in issue.get("solution_cards", []):
            print(f"\n     🃏 [{c['card_id'][:8]}] {c['risk_icon']} {c['title']}")
            print(f"        {c['description'][:100]}")
            print(f"        Files: {', '.join(c['files_changed'])}")
            print(f"        Cost: ${c.get('cost_estimate', {}).get('total_charged', 0):.4f}")
            print(f"        Status: {c['status']}")
    elif action == "apply":
        parts = subcmd[1].split() if len(subcmd) > 1 else []
        if len(parts) < 2:
            print("  ❌ Usage: /forge apply <issue_id> <card_id>")
            return
        issue_id, card_id = parts[0], parts[1]
        result, err = apply_solution(issue_id, card_id)
        if err:
            print(f"  {err}")
        else:
            print(f"  ✅ Applied")
    elif action == "undo":
        from config_manager import get_undo_log
        entries = get_undo_log(10)
        print(f"\n  ↩️  Undo Log (last {len(entries)}):")
        for e in entries:
            print(f"     {e.get('title', '?')[:50]} by {e.get('applied_by', '?')} at {e.get('applied_at', '?')}")
    else:
        print(f"  ❌ Unknown forge command: {action}")
        print("     Usage: /forge [list|show|generate|reroll|apply|undo]")


def cmd_user(args_str):
    """/user [id] — show or set current user."""
    if not args_str.strip():
        user_id = get_current_user()
        tier = get_user_tier(user_id)
        tier_config = USER_TIERS.get(tier, {})
        print(f"\n  👤 Current User: {user_id}")
        print(f"     Tier: {tier_config.get('title', tier)}")
        print(f"     Can apply directly: {'✅' if tier_config.get('can_apply_direct') else '❌'}")
        print(f"     Needs review: {'✅' if tier_config.get('needs_review') else '❌'}")
        print(f"     Set with: /user <user_id>")
        print(f"     Or env: CODEMONKEYS_USER=<user_id>")
    else:
        new_user = args_str.strip()
        from config_manager import set_current_user
        if set_current_user(new_user):
            print(f"  ✅ Switched to user: {new_user}")
            # Show their info
            cmd_user("")
        else:
            print(f"  ❌ Failed to set user: {new_user}")


# ── GitHub Commands ────────────────────────────────────────────

def cmd_github(args_str):
    """/github <subcommand> [args...] — GitHub integration.
    
    Subcommands:
      login <token> [name]    → Store a GitHub PAT and test connection
      status                  → Show GitHub connection and git status
      push [remote] [branch]  → Push current branch to GitHub
      pull [remote] [branch]  → Pull from GitHub
      repos                   → List user repos on GitHub
      token list              → List stored tokens
      token add <token> [name] → Add a token
      token remove <id>       → Remove a token
      branch <name>           → Create and switch to a new branch
      commit <message>        → Stage all and commit
      remote [name]           → Show remote URL
    """
    from github_bridge import (
        validate_token, add_token, get_tokens, get_active_token,
        delete_token, get_git_status, git_push, git_pull,
        list_user_repos, get_git_remote_url, git_add_all,
        git_commit, git_create_branch, push_current_branch,
    )
    from config_manager import get_current_user
    
    parts = args_str.strip().split(maxsplit=2)
    subcmd = parts[0].lower() if parts else ""
    
    if not subcmd or subcmd in ("help", "--help"):
        print()
        print("  🐙 GitHub Integration Commands")
        print("  ────────────────────────────────")
        print("  /github login <token> [name]   Store & test a GitHub PAT")
        print("  /github status                 Show git + GitHub status")
        print("  /github push [remote] [branch]  Push to GitHub")
        print("  /github pull [remote] [branch]  Pull from GitHub")
        print("  /github repos                  List your GitHub repos")
        print("  /github token list             Show stored tokens")
        print("  /github token add <token> [n]  Store a token")
        print("  /github token remove <id>      Remove a token")
        print("  /github commit <message>       Stage all & commit locally")
        print("  /github branch <name>          Create & switch branch")
        print("  /github remote [name]          Show remote URL")
        print()
        return
    
    user_id = get_current_user()
    
    if subcmd == "login":
        token = parts[1] if len(parts) > 1 else ""
        if not token:
            print("  ❌ Usage: /github login <token> [name]")
            return
        name = parts[2] if len(parts) > 2 else "GitHub PAT"
        print("  🔑 Validating token...")
        validation = validate_token(token)
        if validation.get("valid"):
            # Store it
            token_obj = add_token(user_id, name, token)
            if token_obj:
                print(f"  ✅ Logged in as: {validation.get('user')} ({validation.get('name', '')})")
                print(f"     Scopes: {', '.join(validation.get('scopes', ['unknown']))}")
                print(f"     Rate limit remaining: {validation.get('rate_limit_remaining', '?')}")
                print(f"     Token saved: {token_obj['id'][:8]}")
            else:
                print("  ❌ Failed to save token")
        else:
            print(f"  ❌ {validation.get('error', 'Token validation failed')}")
        return
    
    elif subcmd == "status":
        print()
        # GitHub connection status
        token = get_active_token(user_id)
        if token:
            validation = validate_token(token)
            if validation.get("valid"):
                print(f"  ✅ GitHub: connected as {validation.get('user')}")
                print(f"     Scopes: {', '.join(validation.get('scopes', ['unknown']))}")
            else:
                print(f"  ❌ GitHub: token invalid — {validation.get('error')}")
        else:
            print(f"  ⚠️  GitHub: no token configured")
            print(f"     Use: /github login <token>")
        
        # Local git status
        print()
        status = get_git_status()
        if status.get("error"):
            print(f"  ❌ Git: {status['error']}")
        else:
            print(f"  📂 Git: branch={status.get('branch')}")
            print(f"     Clean: {'✅' if status.get('is_clean') else '❌'}")
            if status.get("ahead") or status.get("behind"):
                print(f"     Ahead: {status.get('ahead')} | Behind: {status.get('behind')}")
            if not status.get("is_clean"):
                mods = status.get("modified", [])
                staged = status.get("staged", [])
                untracked = status.get("untracked", [])
                if staged:
                    print(f"     Staged: {len(staged)} file(s)")
                if mods:
                    print(f"     Modified: {len(mods)} file(s)")
                if untracked:
                    print(f"     Untracked: {len(untracked)} file(s)")
            
            # Remote info
            remote_url = get_git_remote_url("origin")
            if remote_url:
                print(f"     Remote origin: {_mask_url(remote_url)}")
        
        # Token list
        tokens = get_tokens(user_id)
        if tokens:
            print(f"\n  🔑 Stored tokens ({len(tokens)}):")
            for t in tokens:
                active = "✅" if t.get("is_active", True) else "⏸️"
                print(f"     {active} [{t['id'][:8]}] {t['name']}")
        print()
        return
    
    elif subcmd == "push":
        remote = parts[1] if len(parts) > 1 else "origin"
        branch = parts[2] if len(parts) > 2 else None
        print(f"  📤 Pushing {remote}/{branch or 'current'}...")
        result = push_current_branch(user_id, remote, branch)
        if result.get("success"):
            print(f"  ✅ Pushed to {result.get('pushed_to', remote)}")
            if result.get("output"):
                print(f"     {result['output']}")
        else:
            print(f"  ❌ Push failed: {result.get('error', 'Unknown error')}")
        return
    
    elif subcmd == "pull":
        remote = parts[1] if len(parts) > 1 else "origin"
        branch = parts[2] if len(parts) > 2 else None
        token = get_active_token(user_id)
        if not token:
            print("  ❌ No GitHub token configured. Use /github login <token>")
            return
        print(f"  📥 Pulling {remote}/{branch or 'current'}...")
        result = git_pull(remote, branch, token)
        if result.get("success"):
            print(f"  ✅ Pulled successfully")
            if result.get("output"):
                for line in result["output"].split("\n"):
                    print(f"     {line}")
        else:
            print(f"  ❌ Pull failed: {result.get('error', 'Unknown error')}")
        return
    
    elif subcmd == "repos":
        token = get_active_token(user_id)
        if not token:
            print("  ❌ No GitHub token configured. Use /github login <token>")
            return
        print("  📋 Fetching repos...")
        result = list_user_repos(token)
        if result.get("error"):
            print(f"  ❌ {result['error']}")
        else:
            repos = result.get("repos", [])
            if not repos:
                print("  📭 No repos found")
            else:
                print(f"  📋 Repos ({len(repos)}):")
                for r in repos:
                    icon = "🔒" if r.get("private") else "🌍"
                    lang = r.get("language") or "?"
                    print(f"     {icon} {r['full_name']} ({lang})")
        return
    
    elif subcmd == "token":
        action = parts[1].lower() if len(parts) > 1 else ""
        if action == "list":
            tokens = get_tokens(user_id)
            if not tokens:
                print("  📭 No tokens stored")
            else:
                print(f"  🔑 Stored tokens ({len(tokens)}):")
                for t in tokens:
                    active = "✅" if t.get("is_active", True) else "⏸️"
                    created = t.get("created_at", "?")[:10]
                    print(f"     {active} [{t['id'][:8]}] {t['name']} (added {created})")
        elif action == "add":
            token = parts[2] if len(parts) > 2 else ""
            if not token:
                print("  ❌ Usage: /github token add <token> [name]")
                return
            name = parts[3] if len(parts) > 3 else "GitHub PAT"
            # Validate first
            validation = validate_token(token)
            if not validation.get("valid"):
                print(f"  ❌ Token invalid: {validation.get('error')}")
                return
            token_obj = add_token(user_id, name, token)
            if token_obj:
                print(f"  ✅ Token saved [{token_obj['id'][:8]}] as '{name}'")
                print(f"     GitHub user: {validation.get('user')}")
            else:
                print("  ❌ Failed to save token")
        elif action == "remove":
            tid = parts[2] if len(parts) > 2 else ""
            if not tid:
                print("  ❌ Usage: /github token remove <id>")
                return
            if delete_token(user_id, tid):
                print(f"  ✅ Token [{tid[:8]}] removed")
            else:
                print(f"  ❌ Token not found: {tid}")
        else:
            print("  ❌ Usage: /github token list | add <token> [name] | remove <id>")
        return
    
    elif subcmd == "commit":
        message = parts[1] if len(parts) > 1 else ""
        if not message:
            print("  ❌ Usage: /github commit <message>")
            return
        # Stage all first
        stage_result = git_add_all()
        if not stage_result.get("success"):
            print(f"  ❌ Stage failed: {stage_result.get('error')}")
            return
        commit_result = git_commit(message)
        if commit_result.get("success"):
            sha = commit_result.get("sha")
            if sha:
                print(f"  ✅ Committed [{sha[:8]}] {message}")
            else:
                print(f"  ℹ️  Nothing to commit")
        else:
            print(f"  ❌ Commit failed: {commit_result.get('error')}")
        return
    
    elif subcmd == "branch":
        name = parts[1] if len(parts) > 1 else ""
        if not name:
            print("  ❌ Usage: /github branch <name>")
            return
        base = parts[2] if len(parts) > 2 else None
        result = git_create_branch(name, base)
        if result.get("success"):
            print(f"  🌿 Switched to new branch: {name}")
        else:
            print(f"  ❌ Branch failed: {result.get('error')}")
        return
    
    elif subcmd == "remote":
        remote_name = parts[1] if len(parts) > 1 else "origin"
        url = get_git_remote_url(remote_name)
        if url:
            print(f"  🌐 {remote_name}: {_mask_url(url)}")
        else:
            print(f"  ⚠️  No remote '{remote_name}' configured")
        return
    
    else:
        print(f"  ❌ Unknown github subcommand: {subcmd}")
        print("     Type /github help for available commands")


def _mask_url(url: str) -> str:
    """Mask credentials in a URL for display."""
    if "@" in url:
        # https://user:pass@host/path → https://***@host/path
        scheme_rest = url.split("://", 1)
        if len(scheme_rest) == 2:
            scheme, rest = scheme_rest
            if "@" in rest:
                # Hide everything before @
                host_part = rest.split("@", 1)[1]
                return f"{scheme}://***@{host_part}"
    return url


def cmd_report_spend(args_str):
    """/report_spend <amount> — Agent self-reports API spend for session tracking.
    This is how the Daystrom agent tells the system how much it cost to run.
    """
    try:
        amount = float(args_str.strip())
        if amount < 0:
            print("  ❌ Spend must be non-negative")
            return
        result = record_session_spend(amount)
        if result:
            session_rem, monthly_rem = result
            print(f"  💰 Agent reported ${amount:.6f} spend")
            print(f"     Session remaining: ${session_rem:.4f}")
            print(f"     Monthly remaining: ${monthly_rem:.4f}")
            if is_session_exhausted():
                print(f"  ⚠️  SESSION BUDGET EXHAUSTED — free models only from now on")
            if is_budget_exhausted():
                print(f"  ⚠️  MONTHLY BUDGET EXHAUSTED — free models only from now on")
        else:
            print(f"  ❌ Failed to record spend")
    except ValueError:
        print(f"  ❌ Usage: /report_spend <amount>. Example: /report_spend 0.0015")


def cmd_help():
    """/help — show available commands."""
    print()
    print("  🍌💻 CodeMonkeys CLI Commands")
    print("  ────────────────────────────────")
    print("  <prompt>          Enqueue a prompt for AI processing")
    print("  /loop D P         Start a loop: /loop 15m 'tell me a joke'")
    print("  /queue            Show queue status (pending, active, completed)")
    print("  /loops            List all active loops")
    print("  /stop ID          Stop a specific loop by ID (prefix OK)")
    print("  /stopall          Stop all active loops")
    print("  /budget           Show/set budget caps")
    print("  /budget set N     Set monthly budget cap (e.g. /budget set 5.00)")
    print("  /budget session N Set session budget cap (e.g. /budget session 2.00)")
    print("  /report_spend N   Agent self-reports API spend (internal)")
    print("  /clear            Clear all pending prompts from queue")
    print("  /feedback         Submit change request to the Change Forge")
    print("  /forge            Show Change Forge status / manage solutions")
    print("  /user [id]        Show or set current user identity")
    print("  /github           GitHub integration (login, push, pull, repos, tokens)
  /help             Show this help")
    print("  Ctrl+C / Ctrl+D   Exit")
    print()


def _show_queue_status():
    """Print a one-line queue status summary."""
    status = get_queue_status()
    parts = []
    parts.append(f"📊 {status['queue_size']} pending")
    parts.append(f"{'🔄' if status['active'] else '💤'}")
    parts.append(f"✅ {status['completed_count']}")
    parts.append(f"❌ {status['failed_count']}")
    loops = get_active_loops()
    if loops:
        parts.append(f"🔁 {len(loops)} loop{'s' if len(loops) != 1 else ''}")
    print(f"  {' | '.join(parts)}")


def _format_duration(seconds):
    """Format a duration in seconds to a human-readable string."""
    if seconds < 60:
        return f"{seconds:.0f}s"
    elif seconds < 3600:
        return f"{seconds / 60:.0f}m"
    else:
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        return f"{h}h{m:02d}m" if m else f"{h}h"


# ── Prompt processing ──────────────────────────────────────────

def process_prompt(prompt):
    """Enqueue a prompt and return immediately."""
    task_id = _queue.enqueue(prompt)
    print(f"  📝 Enqueued [{task_id[:8]}]")
    _show_queue_status()


def process_noninteractive(prompt):
    """Handle a single prompt from argv or pipe input."""
    task_id = _queue.enqueue(prompt)
    print(f"  📝 Enqueued [{task_id[:8]}]")
    _show_queue_status()

    # In non-interactive mode, wait for this task to complete
    result = _queue.get_result(task_id, block=True, timeout=120)
    status = result.get("status", "unknown")
    if status == "completed":
        text = result.get("result", "")
        print(f"\n  ✅ Result:")
        for line in text.split("\n"):
            print(f"     {line}")
        print()
    elif status == "failed":
        error = result.get("error", "Unknown error")
        print(f"\n  ❌ Failed: {error}")
        sys.exit(1)


# ── Command dispatcher ─────────────────────────────────────────

def dispatch_command(line):
    """Parse and dispatch a command line. Returns True to continue, False to exit."""
    line = line.strip()
    if not line:
        return True

    # ── Slash commands ──────────────────────────────────────────
    if line.startswith("/"):
        parts = line.split(maxsplit=1)
        cmd = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        if cmd == "/loop":
            cmd_loop(args)
        elif cmd == "/queue":
            cmd_queue()
        elif cmd == "/loops":
            cmd_loops()
        elif cmd == "/stop":
            cmd_stop(args)
        elif cmd == "/stopall":
            cmd_stopall()
        elif cmd == "/budget":
            cmd_budget(args)
        elif cmd == "/report_spend":
            cmd_report_spend(args)
        elif cmd == "/clear":
            cmd_clear()
        elif cmd == "/feedback":
            cmd_feedback(args)
        elif cmd == "/forge":
            cmd_forge(args)
        elif cmd == "/user":
            cmd_user(args)
        elif cmd == "/github":
            cmd_github(args)
        elif cmd == "/help":
            cmd_help()
        else:
            print(f"  ❌ Unknown command: {cmd}")
            print(f"     Type /help for available commands")
        return True

    # ── Regular prompt ──────────────────────────────────────────
    process_prompt(line)
    return True


# ── Main entry point ───────────────────────────────────────────

def main():
    # Start the background result poller
    _start_result_poller()

    # ── Non-interactive: single prompt from argv or pipe ────────
    if len(sys.argv) > 1:
        prompt = " ".join(sys.argv[1:])
        process_noninteractive(prompt)
        # Wait a moment for the poller to print any trailing output
        time.sleep(0.3)
        return

    if not sys.stdin.isatty():
        # Pipe mode: read all lines
        for line in sys.stdin:
            line = line.strip()
            if line:
                process_noninteractive(line)
        time.sleep(0.3)
        return

    # ── Interactive REPL ────────────────────────────────────────
    # Check for --user flag
    if "--user" in sys.argv:
        idx = sys.argv.index("--user")
        if idx + 1 < len(sys.argv):
            from config_manager import set_current_user
            set_current_user(sys.argv[idx + 1])

    user_id = get_current_user()
    tier = get_user_tier(user_id)
    tier_title = USER_TIERS.get(tier, {}).get("title", tier)

    print()
    print(f"  🍌💻  CodeMonkeys Agent CLI  —  👤 {user_id} ({tier_title})")
    print("  ──────────────────────────")
    print("  Type a prompt and press Enter to enqueue it.")
    print("  Use /help to see available commands.")
    print("  Press Ctrl+C or Ctrl+D to exit.")
    print()

    _show_queue_status()
    print()

    while True:
        try:
            line = input(">>> ")
        except EOFError:
            # Ctrl+D
            print()
            print("  👋 Goodbye!")
            break
        except KeyboardInterrupt:
            # Ctrl+C
            print()
            print("  👋 Goodbye!")
            break

        try:
            if not dispatch_command(line):
                break
        except KeyboardInterrupt:
            print()
            print("  👋 Goodbye!")
            break
        except Exception as exc:
            print(f"  ❌ Unexpected error: {exc}")

    # Brief pause so the poller can flush any final output
    _polling_active.set()
    time.sleep(0.3)


if __name__ == "__main__":
    main()
