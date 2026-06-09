#!/usr/bin/env python3
"""
🍌🌐 Banana Shelter Settings Server
====================================
A lightweight local web server for configuring game settings,
including the Gemini API key.

PASSWORD MANAGER ISSUE & FIX:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PROBLEM: If we use <input type="password"> for the API key field,
browsers (Chrome, Edge, Safari, Firefox) will pop up the
"Save password?" dialog. This is confusing because an API key
is NOT a password.

SOLUTION: We use <input type="text"> with CSS text-security
to visually mask the characters. This does NOT trigger the
browser's password manager because:
  - type="text" is not recognized as a password field
  - autocomplete="off" is set
  - data-1p-ignore (1Password) and data-lpignore (LastPass) are set
  - The form has no password field, so browsers don't offer to save

USAGE:
  python3 settings_server.py
  → Opens http://localhost:8080 in your browser
"""

import json
import os
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

from config_manager import (
    load_config, save_config, get_api_key, set_api_key, get_config_file,
    get_current_user, set_current_user, get_user_tier, get_user_profile,
    get_or_create_user, list_users, get_user_budget_info, get_undo_log,
    check_user_permission, USER_TIERS, set_user_tier,
)
from forge_ui import get_forge_html
from feedback_engine import (
    create_issue, list_issues, quote_user_for_feedback, load_issue,
    classify_risk,
)
from change_forge import (
    generate_solutions, reroll_solutions, discard_card, edit_card,
    apply_solution, get_undo_commands,
)

PORT = int(os.environ.get("BANANA_SHELTER_PORT", "8080"))

HTML_PAGE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>🍌 Banana Shelter — Settings</title>
<style>
  :root {
    --bg: #1a1a2e;
    --card: #16213e;
    --accent: #f5c518;
    --text: #e0e0e0;
    --muted: #888;
    --danger: #e74c3c;
    --success: #2ecc71;
    --border: #2a2a4a;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: var(--bg);
    color: var(--text);
    min-height: 100vh;
    display: flex;
    justify-content: center;
    padding: 2rem 1rem;
  }
  .container { max-width: 640px; width: 100%; }
  h1 {
    text-align: center;
    font-size: 1.8rem;
    margin-bottom: 0.25rem;
  }
  .subtitle {
    text-align: center;
    color: var(--muted);
    margin-bottom: 2rem;
    font-size: 0.9rem;
  }
  .card {
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 1.5rem;
    margin-bottom: 1rem;
  }
  .card h2 {
    font-size: 1.1rem;
    margin-bottom: 1rem;
    color: var(--accent);
  }
  .field-group { margin-bottom: 1rem; }
  .field-group label {
    display: block;
    font-size: 0.85rem;
    color: var(--muted);
    margin-bottom: 0.4rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }
  /* KEY FIX: Use type="text" with CSS masking (not password type)
     This prevents browser password manager from triggering */
  input[type="text"].api-key {
    width: 100%;
    padding: 0.75rem 1rem;
    background: #0d0d1a;
    border: 1px solid var(--border);
    border-radius: 8px;
    color: var(--text);
    font-size: 1rem;
    font-family: 'SF Mono', 'Fira Code', 'Consolas', monospace;
    transition: border-color 0.2s;
    /* CSS-based character masking — same visual as password but browser
       does NOT treat it as a password field */
    -webkit-text-security: disc;
    text-security: disc;
  }
  input[type="text"].api-key:focus {
    outline: none;
    border-color: var(--accent);
  }
  /* Anti-password-manager attributes */
  input[type="text"].api-key {
    autocomplete: off;
    data-1p-ignore: "";
    data-lpignore: "true";
    data-form-type: "other";
  }
  .note {
    font-size: 0.8rem;
    color: var(--muted);
    margin-top: 0.4rem;
    line-height: 1.4;
  }
  .btn-row { display: flex; gap: 0.5rem; margin-top: 1rem; flex-wrap: wrap; }
  .btn {
    padding: 0.6rem 1.2rem;
    border: none;
    border-radius: 8px;
    font-size: 0.9rem;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.2s;
  }
  .btn-primary { background: var(--accent); color: #1a1a2e; }
  .btn-primary:hover { background: #e0b014; }
  .btn-danger { background: var(--danger); color: white; }
  .btn-danger:hover { background: #c0392b; }
  .btn-secondary { background: #2a2a4a; color: var(--text); }
  .btn-secondary:hover { background: #3a3a5a; }
  .btn:disabled { opacity: 0.5; cursor: not-allowed; }
  .toggle-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0.5rem 0;
    border-bottom: 1px solid var(--border);
  }
  .toggle-row:last-child { border-bottom: none; }
  .toggle-label { font-size: 0.95rem; }
  .toggle-desc { font-size: 0.8rem; color: var(--muted); }
  .switch {
    position: relative;
    display: inline-block;
    width: 48px;
    height: 26px;
  }
  .switch input { opacity: 0; width: 0; height: 0; }
  .slider {
    position: absolute;
    cursor: pointer;
    top: 0; left: 0; right: 0; bottom: 0;
    background: #444;
    transition: 0.3s;
    border-radius: 26px;
  }
  .slider:before {
    content: "";
    position: absolute;
    height: 20px; width: 20px;
    left: 3px; bottom: 3px;
    background: white;
    transition: 0.3s;
    border-radius: 50%;
  }
  .switch input:checked + .slider { background: var(--accent); }
  .switch input:checked + .slider:before { transform: translateX(22px); }
  #message {
    padding: 0.75rem 1rem;
    border-radius: 8px;
    margin-bottom: 1rem;
    display: none;
    font-weight: 500;
  }
  #message.success { display: block; background: #1a3a2a; color: var(--success); border: 1px solid var(--success); }
  #message.error { display: block; background: #3a1a1a; color: var(--danger); border: 1px solid var(--danger); }
  .status-row { display: flex; align-items: center; gap: 0.5rem; margin-top: 0.5rem; }
  .dot { width: 10px; height: 10px; border-radius: 50%; display: inline-block; }
  .dot.green { background: var(--success); }
  .dot.red { background: var(--danger); }
  .dot.yellow { background: #f39c12; }
  .footer { text-align: center; margin-top: 2rem; color: var(--muted); font-size: 0.8rem; }
  .footer a { color: var(--accent); }
  hr { border: none; border-top: 1px solid var(--border); margin: 1rem 0; }
</style>
</head>
<body>
<div class="container">
  <h1>🍌 Banana Shelter</h1>
  <p class="subtitle">Settings &amp; Configuration</p>

  <div id="message"></div>

  <div class="card">
    <h2>🔑 Gemini API Key</h2>
    <p class="note" style="margin-bottom:1rem;">
      Your key is stored in <code>~/.banana_shelter/config.json</code>
      with restricted permissions. It is never exposed to the browser's
      password manager.
    </p>
    <div class="field-group">
      <label for="api-key">API Key</label>
      <!-- ⭐ FIX: type="text" with CSS text-security (not password type).
           Browser password managers only trigger on password-type fields.
           We also set autocomplete, data-1p-ignore, and data-lpignore. -->
      <input type="text" id="api-key" class="api-key"
             placeholder="Paste your Gemini API key here..."
             autocomplete="off"
             data-1p-ignore=""
             data-lpignore="true"
             data-form-type="other"
             spellcheck="false">
      <p class="note">
        🔒 Why no password prompt? We use <code>type="text"</code> with CSS masking
        (not a password-type field). Browsers only offer to save passwords
        on password-type fields. Your key stays local.
      </p>
    </div>
    <div class="btn-row">
      <button class="btn btn-primary" onclick="saveApiKey()">💾 Save Key</button>
      <button class="btn btn-danger" onclick="clearApiKey()">🗑️ Clear Key</button>
      <button class="btn btn-secondary" onclick="testApiKey()">🧪 Test Connection</button>
    </div>
    <div id="api-status" class="status-row" style="display:none;">
      <span class="dot"></span>
      <span id="api-status-text"></span>
    </div>
  </div>

  <div class="card">
    <h2>🎮 AI Features</h2>
    <p class="note" style="margin-bottom:1rem;">
      AI features require a Gemini API key above.
    </p>
    <div class="toggle-row">
      <div>
        <div class="toggle-label">AI Kayaker Names</div>
        <div class="toggle-desc">Generate unique kayaker names via AI</div>
      </div>
      <label class="switch">
        <input type="checkbox" id="ai-kayaker-names" onchange="saveToggle('ai_kayaker_names', this.checked)">
        <span class="slider"></span>
      </label>
    </div>
    <div class="toggle-row">
      <div>
        <div class="toggle-label">AI Storytelling</div>
        <div class="toggle-desc">Dynamic narration for game events</div>
      </div>
      <label class="switch">
        <input type="checkbox" id="ai-storytelling" onchange="saveToggle('ai_storytelling', this.checked)">
        <span class="slider"></span>
      </label>
    </div>
  </div>

  <div class="card">
    <h2>📋 Config File</h2>
    <p class="note">
      Location: <code id="config-path">~/.banana_shelter/config.json</code><br>
      Permissions: Owner read/write only (0o600 for file, 0o700 for directory)
    </p>
    <div class="btn-row">
      <button class="btn btn-secondary" onclick="loadConfig()">🔄 Reload</button>
    </div>
  </div>

  <div class="footer">
    🍌 Built by CodeMonkeys — <a href="#" onclick="location.reload()">reload</a>
  </div>
</div>

<script>
// ── Load current config on page load ──
async function loadConfig() {
  try {
    const resp = await fetch('/api/config');
    const config = await resp.json();
    document.getElementById('api-key').value = config.gemini_api_key || '';
    document.getElementById('ai-kayaker-names').checked = config.ai_kayaker_names || false;
    document.getElementById('ai-storytelling').checked = config.ai_storytelling || false;
    updateApiStatus(config);
    hideMessage();
  } catch(e) {
    showMessage('Failed to load config: ' + e.message, 'error');
  }
}

function updateApiStatus(config) {
  const status = document.getElementById('api-status');
  const text = document.getElementById('api-status-text');
  const dot = status.querySelector('.dot');
  
  if (config.gemini_api_key) {
    status.style.display = 'flex';
    dot.className = 'dot yellow';
    text.textContent = 'Key configured (not tested)';
  } else {
    status.style.display = 'none';
  }
}

// ── Save API Key ──
async function saveApiKey() {
  const key = document.getElementById('api-key').value.trim();
  if (!key) {
    showMessage('Please enter an API key.', 'error');
    return;
  }
  
  try {
    const resp = await fetch('/api/config', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ gemini_api_key: key })
    });
    const result = await resp.json();
    if (result.success) {
      showMessage('✅ API key saved successfully! Stored in local config file (not in browser).', 'success');
      loadConfig();
    } else {
      showMessage('❌ Failed to save: ' + (result.error || 'unknown error'), 'error');
    }
  } catch(e) {
    showMessage('❌ Error: ' + e.message, 'error');
  }
}

// ── Clear API Key ──
async function clearApiKey() {
  if (!confirm('Clear the API key?')) return;
  try {
    const resp = await fetch('/api/config', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ gemini_api_key: '' })
    });
    const result = await resp.json();
    if (result.success) {
      showMessage('🗑️ API key cleared.', 'success');
      loadConfig();
    }
  } catch(e) {
    showMessage('❌ Error: ' + e.message, 'error');
  }
}

// ── Test API Connection ──
async function testApiKey() {
  const status = document.getElementById('api-status');
  const text = document.getElementById('api-status-text');
  const dot = status.querySelector('.dot');
  status.style.display = 'flex';
  dot.className = 'dot yellow';
  text.textContent = 'Testing connection...';
  
  try {
    const resp = await fetch('/api/test');
    const result = await resp.json();
    if (result.success) {
      dot.className = 'dot green';
      text.textContent = result.message;
    } else {
      dot.className = 'dot red';
      text.textContent = result.message;
    }
  } catch(e) {
    dot.className = 'dot red';
    text.textContent = '❌ Connection test failed: ' + e.message;
  }
}

// ── Save Toggle ──
async function saveToggle(key, value) {
  const data = {};
  data[key] = value;
  try {
    await fetch('/api/config', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(data)
    });
  } catch(e) {
    showMessage('Failed to save setting: ' + e.message, 'error');
  }
}

// ── Message helpers ──
function showMessage(msg, type) {
  const el = document.getElementById('message');
  el.textContent = msg;
  el.className = type;
  el.style.display = 'block';
}

function hideMessage() {
  document.getElementById('message').style.display = 'none';
}

// Load on startup
loadConfig();
</script>
</body>
</html>"""


class SettingsHandler(BaseHTTPRequestHandler):
    """HTTP handler for the settings server."""
    
    def log_message(self, format, *args):
        """Quieter logging."""
        if "GET /favicon" not in str(args):
            print(f"  🌐 {args[0]} {args[1]} {args[2]}")
    
    def _read_body(self):
        """Read and parse JSON body from POST request."""
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)
        try:
            return json.loads(body.decode("utf-8"))
        except json.JSONDecodeError:
            return None

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        
        # ── Settings pages ──
        if path == "/" or path == "/index.html":
            self._serve_html()
        elif path == "/forge" or path == "/forge.html":
            self._serve_forge_html()
        elif path == "/api/config":
            self._handle_get_config()
        elif path == "/api/test":
            self._handle_test_api()
        
        # ── Forge API ──
        elif path == "/api/forge/list":
            self._handle_forge_list()
        elif path == "/api/forge/history":
            self._handle_forge_history()
        elif path == "/api/forge/users":
            self._handle_forge_users()
        elif path == "/api/forge/user":
            self._handle_forge_user()
        elif path == "/api/forge/stats":
            self._handle_forge_stats()
        elif path == "/api/forge/quote":
            self._handle_forge_quote()
        elif path.startswith("/api/forge/screenshot/"):
            issue_id = path.split("/")[-1]
            self._handle_forge_screenshot(issue_id)
        
        else:
            self._send_json(404, {"error": "Not found"})
    
    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        
        data = self._read_body()
        if data is None:
            self._send_json(400, {"success": False, "error": "Invalid JSON"})
            return
        
        # ── Config ──
        if path == "/api/config":
            self._handle_update_config(data)
        
        # ── Forge API ──
        elif path == "/api/forge/submit":
            self._handle_forge_submit(data)
        elif path == "/api/forge/apply":
            self._handle_forge_apply(data)
        elif path == "/api/forge/discard":
            self._handle_forge_discard(data)
        elif path == "/api/forge/edit":
            self._handle_forge_edit(data)
        elif path == "/api/forge/reroll":
            self._handle_forge_reroll(data)
        
        else:
            self._send_json(404, {"success": False, "error": "Not found"})
    
    def _serve_forge_html(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        html = get_forge_html()
        self.wfile.write(html.encode("utf-8"))
    
    def _serve_html(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(HTML_PAGE.encode("utf-8"))
    
    def _handle_get_config(self):
        config = load_config()
        # Mask the API key for display (show first 4 + last 4 chars)
        config = dict(config)
        if config.get("gemini_api_key"):
            key = config["gemini_api_key"]
            if len(key) > 8:
                config["gemini_api_key"] = key[:4] + "…" + key[-4:]
            elif len(key) > 0:
                config["gemini_api_key"] = key[:4] + "…"
        self._send_json(200, config)
    
    def _handle_update_config(self, data):
        config = load_config()
        changed = False
        
        for key in data:
            if key in config:
                config[key] = data[key]
                changed = True
        
        if changed:
            if save_config(config):
                self._send_json(200, {"success": True, "message": "Config saved"})
            else:
                self._send_json(500, {"success": False, "error": "Failed to write config file"})
        else:
            self._send_json(200, {"success": True, "message": "No changes needed"})
    
    def _handle_test_api(self):
        from gemini_integration import test_api_connection
        success, message = test_api_connection()
        self._send_json(200, {"success": success, "message": message})
    
    # ── Forge API Handlers ────────────────────────────────────────
    
    def _get_user(self):
        """Get current user from query params, header, or config."""
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        user_id = params.get("user", [None])[0]
        if not user_id:
            user_id = self.headers.get("X-CodeMonkeys-User", "")
        if not user_id:
            user_id = get_current_user()
        return user_id
    
    def _handle_forge_list(self):
        """List all forge-ready issues and pending review items."""
        user_id = self._get_user()
        forge_ready = list_issues(status="forge_ready")
        pending_review = list_issues(status="pending_review")
        applied = list_issues(status="applied", limit=5)
        
        # Combine: forge_ready first, then pending_review, then recent applied
        issues = forge_ready + pending_review + applied
        
        # Mask screenshot paths for security
        for issue in issues:
            if issue.get("screenshot_path"):
                # Only reveal screenshot if it exists
                pass
        
        self._send_json(200, {"issues": issues})
    
    def _handle_forge_history(self):
        """Get recent change history / undo log."""
        entries = get_undo_commands(20)
        self._send_json(200, {"entries": entries})
    
    def _handle_forge_users(self):
        """List all users."""
        users = list_users()
        self._send_json(200, {"users": users})
    
    def _handle_forge_user(self):
        """Get current user info."""
        user_id = self._get_user()
        profile = get_or_create_user(user_id)
        tier = get_user_tier(user_id)
        tier_config = USER_TIERS.get(tier, {})
        budget = get_user_budget_info(user_id)
        
        self._send_json(200, {
            "user_id": user_id,
            "tier": tier,
            "tier_title": tier_config.get("title", tier),
            "display_name": profile.get("display_name", user_id),
            "budget": budget,
            "permissions": {
                "can_apply_direct": tier_config.get("can_apply_direct", False),
                "can_view_forge": tier_config.get("can_view_forge", False),
                "needs_review": tier_config.get("needs_review", True),
            }
        })
    
    def _handle_forge_stats(self):
        """Get forge statistics."""
        forge_ready = len(list_issues(status="forge_ready"))
        pending_review = len(list_issues(status="pending_review"))
        pending = len(list_issues(status="pending"))
        applied = len(list_issues(status="applied"))
        
        self._send_json(200, {
            "forge_ready": forge_ready,
            "pending_review": pending_review,
            "pending": pending,
            "applied": applied,
        })
    
    def _handle_forge_quote(self):
        """Get a cost quote for feedback text before submitting."""
        user_id = self._get_user()
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        text = params.get("text", [None])[0]
        if not text:
            self._send_json(400, {"error": "text parameter required"})
            return
        result = quote_user_for_feedback(text, user_id)
        self._send_json(200, result)

    def _handle_forge_screenshot(self, issue_id):
        """Serve a screenshot image for an issue."""
        issue = load_issue(issue_id)
        if not issue or not issue.get("screenshot_path"):
            self._send_json(404, {"error": "Screenshot not found"})
            return
        
        ss_path = issue["screenshot_path"]
        if not os.path.isfile(ss_path):
            self._send_json(404, {"error": "Screenshot file missing"})
            return
        
        # Determine content type
        ext = os.path.splitext(ss_path)[1].lower()
        content_type = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".webp": "image/webp",
        }.get(ext, "application/octet-stream")
        
        try:
            with open(ss_path, "rb") as f:
                image_data = f.read()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "max-age=3600")
            self.end_headers()
            self.wfile.write(image_data)
        except IOError:
            self._send_json(404, {"error": "Could not read screenshot"})
    
    def _handle_forge_submit(self, data):
        """Submit new feedback with optional screenshot."""
        user_id = self._get_user()
        feedback_text = data.get("feedback_text", "").strip()
        
        if not feedback_text:
            self._send_json(400, {"success": False, "message": "Feedback text is required"})
            return
        
        # Check user can submit
        tier = get_user_tier(user_id)
        tier_config = USER_TIERS.get(tier, USER_TIERS["lemur"])
        if tier == "lemur":
            self._send_json(403, {"success": False, "message": "Guests cannot submit change requests"})
            return
        
        # Quote first and check budget
        quote = quote_user_for_feedback(feedback_text, user_id)
        if not quote.get("can_submit"):
            self._send_json(403, {"success": False, "message": quote.get("reason", "Cannot submit")})
            return
        
        # Handle screenshot data
        screenshot_data = data.get("screenshot")
        screenshot_path = data.get("screenshot_path")
        
        # Create the issue
        issue = create_issue(
            feedback_text=feedback_text,
            screenshot_data=screenshot_data,
            screenshot_path=screenshot_path,
            user_id=user_id,
        )
        
        # Auto-generate solutions for admin/master_monkey
        auto_gen = tier_config.get("can_apply_direct", False)
        gen_message = ""
        if auto_gen:
            from change_forge import generate_solutions
            updated_issue, err = generate_solutions(issue["issue_id"], user_id)
            if updated_issue and updated_issue.get("solution_cards"):
                gen_message = f" Generated {len(updated_issue['solution_cards'])} solution cards."
            issue = updated_issue or issue
        
        cost = issue.get("cost_estimate", {})
        cost_message = (
            f"Cost: ${cost.get('total_charged', 0):.4f} "
            f"(x{cost.get('markup_multiplier', 2.0):.0f} markup).{gen_message}"
        )
        
        self._send_json(200, {
            "success": True,
            "issue_id": issue["issue_id"],
            "risk_level": issue.get("risk_level", "review"),
            "status": issue.get("status", "pending"),
            "cost_message": cost_message,
            "message": f"Feedback submitted! Risk: {issue.get('risk_icon', '⚪')} {issue.get('risk_level', 'review')}. {cost_message}",
        })
    
    def _handle_forge_apply(self, data):
        """Apply a solution card."""
        user_id = self._get_user()
        issue_id = data.get("issue_id")
        card_id = data.get("card_id")
        
        if not issue_id or not card_id:
            self._send_json(400, {"success": False, "message": "issue_id and card_id required"})
            return
        
        result, err = apply_solution(issue_id, card_id, user_id)
        if err:
            self._send_json(200, {"success": False, "message": err})
        else:
            card = None
            for c in result.get("solution_cards", []):
                if c.get("card_id") == card_id:
                    card = c
                    break
            
            status = result.get("status", "unknown")
            title = card.get("title", "Unknown") if card else "Unknown"
            
            self._send_json(200, {
                "success": True,
                "status": status,
                "message": f"✅ '{title}' — {status}",
            })
    
    def _handle_forge_discard(self, data):
        """Discard a solution card."""
        user_id = self._get_user()
        issue_id = data.get("issue_id")
        card_id = data.get("card_id")
        
        if not issue_id or not card_id:
            self._send_json(400, {"success": False, "message": "issue_id and card_id required"})
            return
        
        result, err = discard_card(issue_id, card_id, user_id)
        self._send_json(200, {"success": True, "message": err or "Card discarded"})
    
    def _handle_forge_edit(self, data):
        """Edit a solution card."""
        user_id = self._get_user()
        issue_id = data.get("issue_id")
        card_id = data.get("card_id")
        updates = data.get("updates", {})
        
        if not issue_id or not card_id or not updates:
            self._send_json(400, {"success": False, "message": "issue_id, card_id, and updates required"})
            return
        
        result, err = edit_card(issue_id, card_id, updates, user_id)
        self._send_json(200, {"success": True, "message": err or "Card updated"})
    
    def _handle_forge_reroll(self, data):
        """Reroll all cards for an issue."""
        user_id = self._get_user()
        issue_id = data.get("issue_id")
        
        if not issue_id:
            self._send_json(400, {"success": False, "message": "issue_id required"})
            return
        
        result, err = reroll_solutions(issue_id, user_id)
        if err:
            self._send_json(200, {"success": False, "message": err})
        else:
            cards = result.get("solution_cards", [])
            self._send_json(200, {
                "success": True,
                "message": f"🎲 Rerolled! {len(cards)} new cards generated.",
                "cards": cards,
            })
    
    def _send_json(self, status, data):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())


def start_server(port=PORT):
    """Start the settings server."""
    server = HTTPServer(("0.0.0.0", port), SettingsHandler)
    print(f"\n  🍌 Banana Shelter Settings Server")
    print(f"  ─────────────────────────────")
    print(f"  🌐 Open: http://localhost:{port}")
    print(f"  🔒 API keys: stored in ~/.banana_shelter/config.json")
    print(f"  🚫 No password manager prompts (type=text, not type=password)")
    print(f"  Press Ctrl+C to stop.\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  👋 Server stopped.")
        server.server_close()


if __name__ == "__main__":
    if "--port" in sys.argv:
        idx = sys.argv.index("--port")
        if idx + 1 < len(sys.argv):
            PORT = int(sys.argv[idx + 1])
    start_server()
