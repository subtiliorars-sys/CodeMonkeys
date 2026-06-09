#!/usr/bin/env python3
"""
🐙 GitHub Bridge — GitHub Integration for CodeMonkeys
=====================================================
Allows users to connect their GitHub accounts via Personal Access Tokens (PATs)
and perform common git operations directly from the CodeMonkeys CLI/Settings UI.

GitHub API via stdlib urllib only — zero pip dependencies.

USAGE (from codemonkeys_cli.py):
  /github login <token>       → Store token and test connection
  /github status              → Show GitHub connection status
  /github push [remote] [branch] → Push to GitHub
  /github repos               → List user repos
  /github token list|add|remove → Manage tokens

PAT Requirements:
  - Classic PAT with: repo, workflow, user:email scopes
  - Fine-grained PAT with: Contents (R/W), Metadata (R), Workflows (R/W)
  - Token is stored in user's profile in config.json (same permissions as API keys)
"""

import base64
import json
import os
import re
import subprocess
import sys
import time
import uuid
from typing import Optional

# ── GitHub API Endpoints ─────────────────────────────────────────

GITHUB_API_BASE = "https://api.github.com"
GITHUB_API_VERSION = "2022-11-28"

# ── Token Validation ─────────────────────────────────────────────


def validate_token(token: str) -> dict:
    """
    Validate a GitHub PAT by calling the /user API endpoint.
    
    Returns a dict with:
      - valid: bool
      - user: str (login name) or None
      - scopes: list of scopes or None
      - error: error message if invalid
      - rate_limit_remaining: int
    """
    if not token or not token.strip():
        return {"valid": False, "error": "Token is empty"}
    
    result = _github_api_get("/user", token)
    
    if result.get("http_status") == 200:
        data = result.get("data", {})
        # Get rate limit info from headers
        headers = result.get("headers", {})
        scopes_str = headers.get("X-OAuth-Scopes", "")
        scopes = [s.strip() for s in scopes_str.split(",") if s.strip()]
        rate_remaining = int(headers.get("X-RateLimit-Remaining", 0))
        
        return {
            "valid": True,
            "user": data.get("login"),
            "name": data.get("name", ""),
            "avatar_url": data.get("avatar_url", ""),
            "scopes": scopes,
            "rate_limit_remaining": rate_remaining,
        }
    elif result.get("http_status") == 401:
        return {"valid": False, "error": "Invalid token (401 Unauthorized)"}
    elif result.get("http_status") == 403:
        body = result.get("data", {})
        msg = body.get("message", "Rate limited or forbidden")
        return {"valid": False, "error": f"Access denied: {msg}"}
    else:
        error = result.get("error", "Connection failed")
        return {"valid": False, "error": str(error)}


# ── GitHub API Core ─────────────────────────────────────────────


def _github_api_get(endpoint: str, token: str) -> dict:
    """
    Make a GET request to the GitHub API.
    Returns dict with: data, http_status, headers, error
    """
    import urllib.request
    import urllib.error
    
    url = f"{GITHUB_API_BASE}{endpoint}"
    
    req = urllib.request.Request(url)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", GITHUB_API_VERSION)
    req.add_header("User-Agent", "CodeMonkeys/1.0")
    
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = resp.read().decode("utf-8")
            data = json.loads(body) if body else {}
            return {
                "data": data,
                "http_status": resp.status,
                "headers": dict(resp.headers),
                "error": None,
            }
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode("utf-8")
            data = json.loads(body) if body else {}
        except (json.JSONDecodeError, UnicodeDecodeError):
            data = {}
        return {
            "data": data,
            "http_status": e.code,
            "headers": dict(e.headers),
            "error": data.get("message", str(e)),
        }
    except (urllib.error.URLError, OSError) as e:
        return {
            "data": {},
            "http_status": 0,
            "headers": {},
            "error": f"Network error: {e}",
        }


def _github_api_post(endpoint: str, token: str, body_data: dict = None) -> dict:
    """
    Make a POST request to the GitHub API.
    Returns dict with: data, http_status, headers, error
    """
    import urllib.request
    import urllib.error
    
    url = f"{GITHUB_API_BASE}{endpoint}"
    
    req = urllib.request.Request(url, method="POST")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", GITHUB_API_VERSION)
    req.add_header("User-Agent", "CodeMonkeys/1.0")
    req.add_header("Content-Type", "application/json")
    
    if body_data is not None:
        data_bytes = json.dumps(body_data).encode("utf-8")
        req.data = data_bytes
    
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = resp.read().decode("utf-8")
            data = json.loads(body) if body else {}
            return {
                "data": data,
                "http_status": resp.status,
                "headers": dict(resp.headers),
                "error": None,
            }
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode("utf-8")
            data = json.loads(body) if body else {}
        except (json.JSONDecodeError, UnicodeDecodeError):
            data = {}
        return {
            "data": data,
            "http_status": e.code,
            "headers": dict(e.headers),
            "error": data.get("message", str(e)),
        }
    except (urllib.error.URLError, OSError) as e:
        return {
            "data": {},
            "http_status": 0,
            "headers": {},
            "error": f"Network error: {e}",
        }


# ── Repository Operations ────────────────────────────────────────


def list_user_repos(token: str, per_page: int = 30) -> dict:
    """
    List repositories for the authenticated user.
    Returns dict with: repos (list), error (str or None)
    """
    result = _github_api_get(f"/user/repos?per_page={per_page}&sort=updated", token)
    
    if result.get("http_status") == 200:
        repos = []
        for r in result.get("data", []):
            repos.append({
                "name": r.get("name"),
                "full_name": r.get("full_name"),
                "description": r.get("description", ""),
                "private": r.get("private", False),
                "fork": r.get("fork", False),
                "language": r.get("language"),
                "updated_at": r.get("updated_at"),
                "clone_url": r.get("clone_url"),
                "ssh_url": r.get("ssh_url"),
                "default_branch": r.get("default_branch", "main"),
            })
        return {"repos": repos, "error": None}
    
    error = result.get("error", "Failed to list repos")
    return {"repos": [], "error": error}


def list_repo_branches(token: str, repo_full_name: str) -> dict:
    """
    List branches for a repository.
    repo_full_name: "owner/repo"
    Returns dict with: branches (list), error (str or None)
    """
    result = _github_api_get(f"/repos/{repo_full_name}/branches", token)
    
    if result.get("http_status") == 200:
        branches = []
        for b in result.get("data", []):
            branches.append({
                "name": b.get("name"),
                "sha": b.get("commit", {}).get("sha", ""),
            })
        return {"branches": branches, "error": None}
    
    error = result.get("error", "Failed to list branches")
    return {"branches": [], "error": error}


def create_repo(token: str, name: str, description: str = "",
                private: bool = False, auto_init: bool = False) -> dict:
    """
    Create a new repository on GitHub for the authenticated user.
    Returns dict with: repo (dict or None), error (str or None)
    """
    body = {
        "name": name,
        "description": description,
        "private": private,
        "auto_init": auto_init,
    }
    
    result = _github_api_post("/user/repos", token, body)
    
    if result.get("http_status") in (201, 200):
        data = result.get("data", {})
        return {
            "repo": {
                "name": data.get("name"),
                "full_name": data.get("full_name"),
                "clone_url": data.get("clone_url"),
                "ssh_url": data.get("ssh_url"),
                "html_url": data.get("html_url"),
            },
            "error": None,
        }
    
    error = result.get("error", "Failed to create repo")
    return {"repo": None, "error": error}


# ── Git Operations (local) ───────────────────────────────────────


def get_git_remote_url(remote_name: str = "origin") -> Optional[str]:
    """
    Get the remote URL for a given remote.
    Returns None if not found.
    """
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", remote_name],
            capture_output=True, text=True, timeout=10,
            cwd=_get_git_root(),
        )
        if result.returncode == 0:
            return result.stdout.strip()
        return None
    except (subprocess.SubprocessError, FileNotFoundError):
        return None


def set_git_remote_url(remote_name: str, url: str) -> dict:
    """
    Set a remote URL. Creates remote if it doesn't exist.
    Returns dict with: success (bool), error (str or None)
    """
    root = _get_git_root()
    try:
        # Check if remote exists
        existing = get_git_remote_url(remote_name)
        if existing:
            cmd = ["git", "remote", "set-url", remote_name, url]
        else:
            cmd = ["git", "remote", "add", remote_name, url]
        
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=10, cwd=root,
        )
        if result.returncode == 0:
            return {"success": True, "error": None}
        return {"success": False, "error": result.stderr.strip()}
    except (subprocess.SubprocessError, FileNotFoundError) as e:
        return {"success": False, "error": str(e)}


def _get_git_root() -> str:
    """Get the git working tree root."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.SubprocessError, FileNotFoundError):
        pass
    # Fallback: assume cwd is the workspace
    return os.getcwd()


def get_git_status() -> dict:
    """
    Get the current git status.
    Returns dict with: branch, ahead, behind, modified, staged, untracked, error
    """
    root = _get_git_root()
    status = {
        "branch": None,
        "ahead": 0,
        "behind": 0,
        "modified": [],
        "staged": [],
        "untracked": [],
        "is_clean": True,
        "error": None,
    }
    
    try:
        # Current branch
        br_result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, timeout=5, cwd=root,
        )
        if br_result.returncode == 0:
            status["branch"] = br_result.stdout.strip()
        
        # Status (porcelain)
        st_result = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True, text=True, timeout=5, cwd=root,
        )
        if st_result.returncode == 0:
            for line in st_result.stdout.splitlines():
                if not line.strip():
                    continue
                code = line[:2]
                filepath = line[3:]
                if code == "??":
                    status["untracked"].append(filepath)
                elif code[0] != " ":
                    status["staged"].append((code, filepath))
                else:
                    status["modified"].append((code, filepath))
        
        # Check ahead/behind
        if status["branch"]:
            # Get the remote tracking branch
            rev_result = subprocess.run(
                ["git", "rev-list", "--left-right", "--count",
                 f"{status['branch']}@{{upstream}}", "HEAD"],
                capture_output=True, text=True, timeout=5, cwd=root,
            )
            if rev_result.returncode == 0:
                parts = rev_result.stdout.strip().split()
                if len(parts) == 2:
                    status["behind"] = int(parts[0])
                    status["ahead"] = int(parts[1])
        
        status["is_clean"] = (
            not status["modified"]
            and not status["staged"]
            and not status["untracked"]
        )
        
    except (subprocess.SubprocessError, FileNotFoundError) as e:
        status["error"] = str(e)
    
    return status


def git_push(remote: str = "origin", branch: str = None,
             force: bool = False, token: str = None) -> dict:
    """
    Push to a remote repository.
    
    If token is provided, embeds it in the remote URL for authentication
    (transient — does not modify the stored remote URL).
    
    Returns dict with: success (bool), output (str), error (str or None)
    """
    root = _get_git_root()
    
    if branch is None:
        # Get current branch
        try:
            br_result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                capture_output=True, text=True, timeout=5, cwd=root,
            )
            if br_result.returncode != 0:
                return {"success": False, "output": "", "error": "Cannot determine current branch"}
            branch = br_result.stdout.strip()
        except (subprocess.SubprocessError, FileNotFoundError) as e:
            return {"success": False, "output": "", "error": str(e)}
    
    try:
        if token:
            # Use token-authenticated URL (HTTPS with embedded token)
            # Build a temporary remote URL with token
            remote_url = get_git_remote_url(remote)
            if not remote_url:
                return {"success": False, "output": "", "error": f"Remote '{remote}' not found"}
            
            # Embed token into the URL for authentication
            authed_url = _embed_token_in_url(remote_url, token)
            
            # Push using the authenticated URL directly
            cmd = ["git", "push", authed_url, f"HEAD:{branch}"]
            if force:
                cmd.append("--force")
        else:
            cmd = ["git", "push", remote, branch]
            if force:
                cmd.append("--force")
        
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=60, cwd=root,
        )
        
        if result.returncode == 0:
            return {
                "success": True,
                "output": result.stdout.strip(),
                "error": None,
            }
        else:
            return {
                "success": False,
                "output": result.stdout.strip(),
                "error": result.stderr.strip(),
            }
    except (subprocess.SubprocessError, FileNotFoundError) as e:
        return {"success": False, "output": "", "error": str(e)}


def git_pull(remote: str = "origin", branch: str = None,
             token: str = None) -> dict:
    """
    Pull from a remote repository.
    
    If token is provided, embeds it in the remote URL for authentication.
    
    Returns dict with: success (bool), output (str), error (str or None)
    """
    root = _get_git_root()
    
    if branch is None:
        try:
            br_result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                capture_output=True, text=True, timeout=5, cwd=root,
            )
            if br_result.returncode != 0:
                return {"success": False, "output": "", "error": "Cannot determine current branch"}
            branch = br_result.stdout.strip()
        except (subprocess.SubprocessError, FileNotFoundError) as e:
            return {"success": False, "output": "", "error": str(e)}
    
    try:
        if token:
            remote_url = get_git_remote_url(remote)
            if not remote_url:
                return {"success": False, "output": "", "error": f"Remote '{remote}' not found"}
            authed_url = _embed_token_in_url(remote_url, token)
            cmd = ["git", "pull", authed_url, branch]
        else:
            cmd = ["git", "pull", remote, branch]
        
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=60, cwd=root,
        )
        
        if result.returncode == 0:
            return {
                "success": True,
                "output": result.stdout.strip(),
                "error": None,
            }
        else:
            return {
                "success": False,
                "output": result.stdout.strip(),
                "error": result.stderr.strip(),
            }
    except (subprocess.SubprocessError, FileNotFoundError) as e:
        return {"success": False, "output": "", "error": str(e)}


def git_clone(url: str, dest_dir: str = None, token: str = None) -> dict:
    """
    Clone a repository.
    
    If token is provided, embeds it in the URL for authentication.
    
    Returns dict with: success (bool), path (str), error (str or None)
    """
    try:
        if token:
            url = _embed_token_in_url(url, token)
        
        cmd = ["git", "clone", url]
        if dest_dir:
            cmd.append(dest_dir)
        
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=120,
        )
        
        if result.returncode == 0:
            return {
                "success": True,
                "path": dest_dir or url.rstrip("/").split("/")[-1].replace(".git", ""),
                "error": None,
            }
        else:
            return {
                "success": False,
                "path": None,
                "error": result.stderr.strip(),
            }
    except (subprocess.SubprocessError, FileNotFoundError) as e:
        return {"success": False, "path": None, "error": str(e)}


def git_add_all() -> dict:
    """Stage all changes."""
    root = _get_git_root()
    try:
        result = subprocess.run(
            ["git", "add", "-A"],
            capture_output=True, text=True, timeout=10, cwd=root,
        )
        if result.returncode == 0:
            return {"success": True, "error": None}
        return {"success": False, "error": result.stderr.strip()}
    except (subprocess.SubprocessError, FileNotFoundError) as e:
        return {"success": False, "error": str(e)}


def git_commit(message: str, author: str = None) -> dict:
    """
    Commit staged changes.
    author: "Name <email>" format (optional)
    """
    root = _get_git_root()
    try:
        cmd = ["git", "commit", "-m", message]
        if author:
            cmd.extend(["--author", author])
        
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=10, cwd=root,
        )
        
        if result.returncode == 0:
            return {
                "success": True,
                "sha": _extract_sha(result.stdout),
                "error": None,
            }
        # "nothing to commit" is not a real error
        if "nothing to commit" in result.stderr:
            return {"success": True, "sha": None, "error": None}
        return {"success": False, "sha": None, "error": result.stderr.strip()}
    except (subprocess.SubprocessError, FileNotFoundError) as e:
        return {"success": False, "sha": None, "error": str(e)}


def git_create_branch(branch_name: str, base_branch: str = None) -> dict:
    """Create and switch to a new branch."""
    root = _get_git_root()
    try:
        if base_branch:
            # Ensure we're on the base branch first
            checkout = subprocess.run(
                ["git", "checkout", base_branch],
                capture_output=True, text=True, timeout=10, cwd=root,
            )
            if checkout.returncode != 0:
                return {"success": False, "error": checkout.stderr.strip()}
        
        result = subprocess.run(
            ["git", "checkout", "-b", branch_name],
            capture_output=True, text=True, timeout=10, cwd=root,
        )
        if result.returncode == 0:
            return {"success": True, "error": None}
        return {"success": False, "error": result.stderr.strip()}
    except (subprocess.SubprocessError, FileNotFoundError) as e:
        return {"success": False, "error": str(e)}


# ── URL Helpers ──────────────────────────────────────────────────


def _embed_token_in_url(url: str, token: str) -> str:
    """
    Embed a token into a git remote URL for authentication.
    
    https://github.com/user/repo.git
    → https://x-access-token:TOKEN@github.com/user/repo.git
    
    ssh style URLs are NOT modified (use SSH keys instead).
    """
    # Only embed in HTTPS URLs
    if url.startswith("https://"):
        # Check if token already embedded
        if "@" in url.replace("https://", ""):
            return url  # Already authenticated
        # Insert token
        authed = url.replace("https://", f"https://x-access-token:{token}@")
        return authed
    return url  # SSH URLs unchanged


def _extract_sha(commit_output: str) -> Optional[str]:
    """Extract commit SHA from git commit output."""
    match = re.search(r'\[([\w/.-]+) ([a-f0-9]{7,40})\]', commit_output)
    if match:
        return match.group(2)
    return None


# ── Token Storage (via Config Manager) ──────────────────────────


def _get_config_manager():
    """Lazy import to avoid circular deps."""
    import config_manager
    return config_manager


def add_token(user_id: str, name: str, token_value: str) -> Optional[dict]:
    """
    Add a GitHub token to a user's profile.
    Returns the token object or None on failure.
    """
    if not token_value or not token_value.strip():
        return None
    
    cm = _get_config_manager()
    profile = cm.get_or_create_user(user_id)
    
    tokens = profile.get("github_tokens", [])
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    token_obj = {
        "id": str(uuid.uuid4()),
        "name": name.strip() or f"GitHub Token {len(tokens) + 1}",
        "token": token_value.strip(),
        "created_at": now,
        "last_used_at": None,
        "is_active": True,
    }
    tokens.append(token_obj)
    
    # Save via config_manager
    config = cm.load_config()
    users = config.get("users", {})
    if user_id not in users:
        users[user_id] = dict(cm.DEFAULT_USER_PROFILE)
    users[user_id]["github_tokens"] = tokens
    config["users"] = users
    if cm.save_config(config):
        return token_obj
    return None


def get_tokens(user_id: str) -> list:
    """Get all GitHub tokens for a user."""
    cm = _get_config_manager()
    profile = cm.get_user_profile(user_id)
    if profile is None:
        return []
    return profile.get("github_tokens", [])


def get_active_token(user_id: str) -> str:
    """Get the first active GitHub token string, or empty string."""
    tokens = get_tokens(user_id)
    for t in tokens:
        if t.get("is_active", True) and t.get("token", "").strip():
            return t["token"]
    return ""


def delete_token(user_id: str, token_id: str) -> bool:
    """Remove a GitHub token by id."""
    tokens = get_tokens(user_id)
    new_tokens = [t for t in tokens if t.get("id") != token_id]
    if len(new_tokens) == len(tokens):
        return False  # Nothing changed
    
    cm = _get_config_manager()
    config = cm.load_config()
    users = config.get("users", {})
    if user_id in users:
        users[user_id]["github_tokens"] = new_tokens
        config["users"] = users
        return cm.save_config(config)
    return False


def update_token(user_id: str, token_id: str, updates: dict) -> bool:
    """Update fields of an existing token."""
    tokens = get_tokens(user_id)
    for t in tokens:
        if t.get("id") == token_id:
            for field in ("name", "is_active", "last_used_at"):
                if field in updates:
                    t[field] = updates[field]
            cm = _get_config_manager()
            config = cm.load_config()
            users = config.get("users", {})
            if user_id in users:
                users[user_id]["github_tokens"] = tokens
                config["users"] = users
                return cm.save_config(config)
    return False


# ── Convenience: Push current branch to origin ──────────────────


def push_current_branch(user_id: str, remote: str = "origin",
                        branch: str = None, force: bool = False) -> dict:
    """
    Push current branch to GitHub using the user's active token.
    High-level convenience wrapper.
    
    Returns dict with: success, output, error, pushed_to
    """
    token = get_active_token(user_id)
    if not token:
        return {
            "success": False,
            "output": "",
            "error": "No GitHub token configured. Use /github login <token> first.",
        }
    
    # Validate token first
    validation = validate_token(token)
    if not validation.get("valid"):
        return {
            "success": False,
            "output": "",
            "error": f"Token invalid: {validation.get('error')}",
        }
    
    # Get current branch if not specified
    if branch is None:
        status = get_git_status()
        branch = status.get("branch")
        if not branch:
            return {"success": False, "output": "", "error": "Cannot determine current branch"}
    
    result = git_push(remote, branch, force, token)
    
    if result.get("success"):
        result["pushed_to"] = f"{remote}/{branch}"
        # Update last_used_at
        tokens = get_tokens(user_id)
        for t in tokens:
            if t.get("is_active", True) and t.get("token", "").strip() == token:
                update_token(user_id, t["id"], {
                    "last_used_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                })
                break
    
    return result


# ── GitHub API Core (continued) ─────────────────────────────────


def _github_api_put(endpoint: str, token: str, body_data: dict = None) -> dict:
    """
    Make a PUT request to the GitHub API.
    Returns dict with: data, http_status, headers, error
    """
    import urllib.request
    import urllib.error
    
    url = f"{GITHUB_API_BASE}{endpoint}"
    
    req = urllib.request.Request(url, method="PUT")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", GITHUB_API_VERSION)
    req.add_header("User-Agent", "CodeMonkeys/1.0")
    req.add_header("Content-Type", "application/json")
    
    if body_data is not None:
        data_bytes = json.dumps(body_data).encode("utf-8")
        req.data = data_bytes
    
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = resp.read().decode("utf-8")
            data = json.loads(body) if body else {}
            return {
                "data": data,
                "http_status": resp.status,
                "headers": dict(resp.headers),
                "error": None,
            }
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode("utf-8")
            data = json.loads(body) if body else {}
        except (json.JSONDecodeError, UnicodeDecodeError):
            data = {}
        return {
            "data": data,
            "http_status": e.code,
            "headers": dict(e.headers),
            "error": data.get("message", str(e)),
        }
    except (urllib.error.URLError, OSError) as e:
        return {
            "data": {},
            "http_status": 0,
            "headers": {},
            "error": f"Network error: {e}",
        }


# ── Pull Request API ─────────────────────────────────────────────


def create_pull_request(token: str, repo_full_name: str, title: str, head: str,
                        base: str, body: str = "") -> dict:
    """
    Create a pull request.
    Returns dict with: pr (dict or None), error (str or None)
    """
    endpoint = f"/repos/{repo_full_name}/pulls"
    payload = {"title": title, "head": head, "base": base, "body": body}
    result = _github_api_post(endpoint, token, payload)
    
    if result.get("http_status") == 201:
        data = result.get("data", {})
        return {
            "pr": {
                "number": data.get("number"),
                "title": data.get("title"),
                "html_url": data.get("html_url"),
                "state": data.get("state"),
                "head": data.get("head", {}).get("ref"),
                "base": data.get("base", {}).get("ref"),
            },
            "error": None,
        }
    error = result.get("error", "Failed to create pull request")
    return {"pr": None, "error": error}


def list_pull_requests(token: str, repo_full_name: str, state: str = "open") -> dict:
    """
    List pull requests for a repo.
    Returns dict with: prs (list), error (str or None)
    """
    endpoint = f"/repos/{repo_full_name}/pulls?state={state}&per_page=30"
    result = _github_api_get(endpoint, token)
    
    if result.get("http_status") == 200:
        prs = []
        for p in result.get("data", []):
            prs.append({
                "number": p.get("number"),
                "title": p.get("title"),
                "state": p.get("state"),
                "html_url": p.get("html_url"),
                "user": p.get("user", {}).get("login"),
                "head": p.get("head", {}).get("ref"),
                "base": p.get("base", {}).get("ref"),
                "created_at": p.get("created_at"),
            })
        return {"prs": prs, "error": None}
    error = result.get("error", "Failed to list pull requests")
    return {"prs": [], "error": error}


def merge_pull_request(token: str, repo_full_name: str, pr_number: int,
                       merge_method: str = "merge") -> dict:
    """
    Merge a pull request.
    Returns dict with: merged (bool), sha (str or None), error (str or None)
    """
    endpoint = f"/repos/{repo_full_name}/pulls/{pr_number}/merge"
    payload = {"merge_method": merge_method}
    result = _github_api_post(endpoint, token, payload)
    
    if result.get("http_status") == 200:
        data = result.get("data", {})
        return {"merged": True, "sha": data.get("sha"), "error": None}
    if result.get("http_status") == 405:
        return {"merged": False, "sha": None, "error": "PR is not mergeable"}
    error = result.get("error", "Failed to merge pull request")
    return {"merged": False, "sha": None, "error": error}


# ── Issues API ───────────────────────────────────────────────────


def create_issue(token: str, repo_full_name: str, title: str, body: str = "",
                 labels: list = None) -> dict:
    """
    Create an issue.
    Returns dict with: issue (dict or None), error (str or None)
    """
    endpoint = f"/repos/{repo_full_name}/issues"
    payload = {"title": title, "body": body}
    if labels:
        payload["labels"] = labels
    result = _github_api_post(endpoint, token, payload)
    
    if result.get("http_status") == 201:
        data = result.get("data", {})
        return {
            "issue": {
                "number": data.get("number"),
                "title": data.get("title"),
                "html_url": data.get("html_url"),
                "state": data.get("state"),
            },
            "error": None,
        }
    error = result.get("error", "Failed to create issue")
    return {"issue": None, "error": error}


def list_issues(token: str, repo_full_name: str, state: str = "open") -> dict:
    """
    List issues (excluding PRs) for a repo.
    Returns dict with: issues (list), error (str or None)
    """
    endpoint = f"/repos/{repo_full_name}/issues?state={state}&per_page=30"
    result = _github_api_get(endpoint, token)
    
    if result.get("http_status") == 200:
        issues = []
        for i in result.get("data", []):
            if "pull_request" in i:
                continue  # filter out PRs
            issues.append({
                "number": i.get("number"),
                "title": i.get("title"),
                "state": i.get("state"),
                "html_url": i.get("html_url"),
                "user": i.get("user", {}).get("login"),
                "created_at": i.get("created_at"),
            })
        return {"issues": issues, "error": None}
    error = result.get("error", "Failed to list issues")
    return {"issues": [], "error": error}


# ── Commits/Log API ──────────────────────────────────────────────


def get_commits(token: str, repo_full_name: str, branch: str = "main",
                per_page: int = 20) -> dict:
    """
    List commits on a branch.
    Returns dict with: commits (list), error (str or None)
    """
    endpoint = f"/repos/{repo_full_name}/commits?sha={branch}&per_page={per_page}"
    result = _github_api_get(endpoint, token)
    
    if result.get("http_status") == 200:
        commits = []
        for c in result.get("data", []):
            commit = c.get("commit", {})
            commits.append({
                "sha": c.get("sha"),
                "message": commit.get("message"),
                "author": commit.get("author", {}).get("name"),
                "date": commit.get("author", {}).get("date"),
                "html_url": c.get("html_url"),
            })
        return {"commits": commits, "error": None}
    error = result.get("error", "Failed to get commits")
    return {"commits": [], "error": error}


def compare_commits(token: str, repo_full_name: str, base: str, head: str) -> dict:
    """
    Compare two commits/branches.
    Returns dict with: ahead_by, behind_by, files, error
    """
    endpoint = f"/repos/{repo_full_name}/compare/{base}...{head}"
    result = _github_api_get(endpoint, token)
    
    if result.get("http_status") == 200:
        data = result.get("data", {})
        files = []
        for f in data.get("files", []):
            files.append({
                "filename": f.get("filename"),
                "status": f.get("status"),
                "additions": f.get("additions"),
                "deletions": f.get("deletions"),
            })
        return {
            "ahead_by": data.get("ahead_by", 0),
            "behind_by": data.get("behind_by", 0),
            "files": files,
            "error": None,
        }
    error = result.get("error", "Failed to compare commits")
    return {"ahead_by": 0, "behind_by": 0, "files": [], "error": error}


# ── Content API ──────────────────────────────────────────────────


def get_file_content(token: str, repo_full_name: str, file_path: str,
                     ref: str = None) -> dict:
    """
    Get file content (base64 encoded).
    Returns dict with: content_b64, sha, size, html_url, error
    """
    endpoint = f"/repos/{repo_full_name}/contents/{file_path}"
    if ref:
        endpoint += f"?ref={ref}"
    result = _github_api_get(endpoint, token)
    
    if result.get("http_status") == 200:
        data = result.get("data", {})
        return {
            "content_b64": data.get("content", ""),
            "sha": data.get("sha"),
            "size": data.get("size"),
            "html_url": data.get("html_url"),
            "error": None,
        }
    error = result.get("error", "Failed to get file content")
    return {"content_b64": None, "sha": None, "size": 0, "html_url": None, "error": error}


def create_or_update_file(token: str, repo_full_name: str, file_path: str,
                          commit_message: str, content_b64: str, sha: str = None,
                          branch: str = None) -> dict:
    """
    Create or update a file via Contents API.
    Returns dict with: committed (bool), sha, html_url, error
    """
    # Validate base64
    try:
        base64.b64decode(content_b64, validate=True)
    except Exception:
        return {"committed": False, "sha": None, "html_url": None,
                "error": "Invalid base64 content"}
    
    endpoint = f"/repos/{repo_full_name}/contents/{file_path}"
    payload = {"message": commit_message, "content": content_b64}
    if sha is not None:
        payload["sha"] = sha
    if branch:
        payload["branch"] = branch
    
    result = _github_api_put(endpoint, token, payload)
    
    if result.get("http_status") in (200, 201):
        data = result.get("data", {})
        return {
            "committed": True,
            "sha": data.get("content", {}).get("sha") if isinstance(data.get("content"), dict) else data.get("sha"),
            "html_url": data.get("content", {}).get("html_url") if isinstance(data.get("content"), dict) else data.get("html_url"),
            "error": None,
        }
    error = result.get("error", "Failed to commit file")
    return {"committed": False, "sha": None, "html_url": None, "error": error}


# ── Workflow/Actions API ─────────────────────────────────────────


def list_workflow_runs(token: str, repo_full_name: str, workflow_id: str = None,
                       per_page: int = 20) -> dict:
    """
    List workflow runs.
    Returns dict with: runs (list), error (str or None)
    """
    if workflow_id:
        endpoint = f"/repos/{repo_full_name}/actions/workflows/{workflow_id}/runs?per_page={per_page}"
    else:
        endpoint = f"/repos/{repo_full_name}/actions/runs?per_page={per_page}"
    result = _github_api_get(endpoint, token)
    
    if result.get("http_status") == 200:
        runs = []
        for r in result.get("data", {}).get("workflow_runs", []):
            runs.append({
                "id": r.get("id"),
                "name": r.get("name"),
                "status": r.get("status"),
                "conclusion": r.get("conclusion"),
                "head_branch": r.get("head_branch"),
                "created_at": r.get("created_at"),
                "html_url": r.get("html_url"),
            })
        return {"runs": runs, "error": None}
    error = result.get("error", "Failed to list workflow runs")
    return {"runs": [], "error": error}


# ── Self-test ────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n  🐙 GitHub Bridge — Self-Test\n")
    
    # Test URL embedding
    print("  📡 URL Helpers:")
    url = "https://github.com/user/repo.git"
    embedded = _embed_token_in_url(url, "ghp_test123")
    print(f"     Original: {url}")
    print(f"     Embedded: {embedded[:40]}...")
    
    # Test token validation (no token)
    print("\n  🔑 Token Validation:")
    result = validate_token("")
    print(f"     Empty token: valid={result.get('valid')}, error={result.get('error')}")
    
    # Test git status
    print("\n  📊 Git Status:")
    status = get_git_status()
    print(f"     Branch: {status.get('branch')}")
    print(f"     Clean: {status.get('is_clean')}")
    print(f"     Ahead: {status.get('ahead')}, Behind: {status.get('behind')}")
    if not status.get('is_clean'):
        print(f"     Modified: {len(status.get('modified', []))}")
        print(f"     Untracked: {len(status.get('untracked', []))}")
    
    # Test remote URL
    print("\n  🌐 Remote URL:")
    url = get_git_remote_url("origin")
    print(f"     origin: {url or 'Not found'}")
    
    print("\n  ✅ GitHub Bridge ready")
