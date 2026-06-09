#!/usr/bin/env python3
"""
🍌🔨 Forge UI — Change Forge Web Interface
===========================================
The card-game UI for the Change Forge review system.
Provides the HTML/JS for the 3-card solution display with
reroll, edit, discard, and apply mechanics.

Integrated into settings_server.py via /forge route.
"""

import json


def get_forge_html():
    """Return the Change Forge HTML page as a string."""
    return FORGE_PAGE_HTML


FORGE_PAGE_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>🔨 Change Forge — CodeMonkeys</title>
<style>
  :root {
    --bg: #1a1a2e; --card: #16213e; --accent: #f5c518;
    --text: #e0e0e0; --muted: #888; --danger: #e74c3c;
    --success: #2ecc71; --border: #2a2a4a; --warning: #f39c12;
    --trivial: #2ecc71; --safe: #f39c12; --review: #e67e22; --critical: #e74c3c;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: var(--bg); color: var(--text); min-height: 100vh; padding: 1rem; }
  .container { max-width: 1100px; margin: 0 auto; }
  h1 { text-align: center; font-size: 1.6rem; margin-bottom: 0.25rem; }
  h1 span { color: var(--accent); }
  .subtitle { text-align: center; color: var(--muted); margin-bottom: 1.5rem; font-size: 0.9rem; }
  .top-bar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem; flex-wrap: wrap; gap: 0.5rem; }
  .user-badge { background: var(--card); border: 1px solid var(--border); border-radius: 20px; padding: 0.3rem 0.8rem; font-size: 0.85rem; }
  .stats { display: flex; gap: 1rem; font-size: 0.85rem; color: var(--muted); }
  .tab-bar { display: flex; gap: 0; margin-bottom: 1.5rem; border-bottom: 1px solid var(--border); }
  .tab { padding: 0.6rem 1.2rem; cursor: pointer; border: none; background: none; color: var(--muted); font-size: 0.9rem; border-bottom: 2px solid transparent; transition: all 0.2s; }
  .tab:hover { color: var(--text); }
  .tab.active { color: var(--accent); border-bottom-color: var(--accent); }
  .tab-content { display: none; }
  .tab-content.active { display: block; }
  .forge-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 1rem; margin-bottom: 1rem; }
  .card { background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 1.2rem; position: relative; transition: all 0.2s; }
  .card:hover { border-color: var(--accent); transform: translateY(-2px); }
  .card.discarded { opacity: 0.4; order: 10; }
  .card.applied { border-color: var(--success); }
  .card .ribbon { position: absolute; top: 0.5rem; right: 0.5rem; padding: 0.2rem 0.6rem; border-radius: 4px; font-size: 0.7rem; font-weight: 700; text-transform: uppercase; }
  .ribbon.trivial { background: var(--trivial); color: #000; }
  .ribbon.safe { background: var(--safe); color: #000; }
  .ribbon.review { background: var(--review); color: #fff; }
  .ribbon.critical { background: var(--critical); color: #fff; }
  .card h3 { font-size: 1rem; margin-bottom: 0.4rem; padding-right: 60px; }
  .card .desc { font-size: 0.85rem; color: var(--muted); margin-bottom: 0.6rem; line-height: 1.4; }
  .card .files { font-size: 0.75rem; color: #666; margin-bottom: 0.6rem; }
  .card .files span { background: #0d0d1a; padding: 0.1rem 0.4rem; border-radius: 3px; font-family: monospace; }
  .card .diff { background: #0d0d1a; border: 1px solid var(--border); border-radius: 6px; padding: 0.6rem; font-family: 'SF Mono', 'Fira Code', monospace; font-size: 0.78rem; margin-bottom: 0.6rem; max-height: 100px; overflow-y: auto; white-space: pre-wrap; }
  .card .cost { font-size: 0.8rem; color: var(--muted); margin-bottom: 0.5rem; }
  .card .actions { display: flex; gap: 0.4rem; flex-wrap: wrap; }
  .btn { padding: 0.4rem 0.8rem; border: none; border-radius: 6px; font-size: 0.8rem; font-weight: 600; cursor: pointer; transition: all 0.2s; }
  .btn-apply { background: var(--success); color: #000; }
  .btn-apply:hover { background: #27ae60; }
  .btn-edit { background: var(--accent); color: #1a1a2e; }
  .btn-edit:hover { background: #e0b014; }
  .btn-discard { background: var(--danger); color: white; }
  .btn-discard:hover { background: #c0392b; }
  .btn-reroll { background: #8e44ad; color: white; }
  .btn-reroll:hover { background: #7d3c98; }
  .btn-secondary { background: #2a2a4a; color: var(--text); }
  .btn-secondary:hover { background: #3a3a5a; }
  .btn:disabled { opacity: 0.4; cursor: not-allowed; }
  .btn-sm { padding: 0.3rem 0.6rem; font-size: 0.75rem; }
  .action-bar { display: flex; gap: 0.5rem; margin: 1rem 0; flex-wrap: wrap; justify-content: center; }
  .quote-box { background: var(--card); border: 1px solid var(--warning); border-radius: 8px; padding: 1rem; margin-bottom: 1rem; }
  .quote-box .cost-row { display: flex; justify-content: space-between; padding: 0.2rem 0; font-size: 0.85rem; }
  .quote-box .total { font-weight: 700; color: var(--accent); font-size: 1rem; border-top: 1px solid var(--border); padding-top: 0.4rem; margin-top: 0.4rem; }
  #message { padding: 0.75rem 1rem; border-radius: 8px; margin-bottom: 1rem; display: none; font-weight: 500; }
  #message.success { display: block; background: #1a3a2a; color: var(--success); border: 1px solid var(--success); }
  #message.error { display: block; background: #3a1a1a; color: var(--danger); border: 1px solid var(--danger); }
  #message.info { display: block; background: #1a2a3a; color: #5dade2; border: 1px solid #5dade2; }
  .empty-state { text-align: center; padding: 3rem 1rem; color: var(--muted); }
  .empty-state .big { font-size: 3rem; margin-bottom: 1rem; }
  .empty-state h2 { color: var(--text); margin-bottom: 0.5rem; }
  .feedback-form textarea { width: 100%; background: #0d0d1a; border: 1px solid var(--border); border-radius: 8px; color: var(--text); padding: 0.75rem; font-size: 0.9rem; resize: vertical; min-height: 80px; font-family: inherit; }
  .feedback-form textarea:focus { outline: none; border-color: var(--accent); }
  .feedback-form .file-input { margin: 0.5rem 0; font-size: 0.85rem; color: var(--muted); }
  .feedback-form .file-input input { background: #0d0d1a; border: 1px solid var(--border); border-radius: 4px; color: var(--text); padding: 0.3rem; }
  .feedback-form .preview-img { max-width: 200px; max-height: 150px; border-radius: 6px; margin: 0.5rem 0; border: 1px solid var(--border); }
  .screenshot-paste-zone { border: 2px dashed var(--border); border-radius: 8px; padding: 1rem; text-align: center; margin: 0.5rem 0; cursor: pointer; transition: all 0.2s; }
  .screenshot-paste-zone:hover { border-color: var(--accent); background: rgba(245,197,24,0.05); }
  .screenshot-paste-zone.has-image { border-color: var(--success); }
  .screenshot-paste-zone img { max-width: 100%; max-height: 200px; border-radius: 4px; }
  .edit-modal-overlay { display: none; position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.7); z-index: 100; justify-content: center; align-items: center; }
  .edit-modal-overlay.active { display: flex; }
  .edit-modal { background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 1.5rem; max-width: 600px; width: 90%; max-height: 80vh; overflow-y: auto; }
  .edit-modal h2 { margin-bottom: 1rem; color: var(--accent); }
  .edit-modal label { display: block; font-size: 0.8rem; color: var(--muted); margin-bottom: 0.3rem; font-weight: 600; text-transform: uppercase; }
  .edit-modal input, .edit-modal textarea { width: 100%; background: #0d0d1a; border: 1px solid var(--border); border-radius: 6px; color: var(--text); padding: 0.5rem; margin-bottom: 0.8rem; font-family: inherit; font-size: 0.9rem; }
  .edit-modal textarea { min-height: 80px; resize: vertical; font-family: monospace; }
  .edit-modal .btn-row { display: flex; gap: 0.5rem; justify-content: flex-end; }
  .history-item { display: flex; justify-content: space-between; align-items: center; padding: 0.5rem 0; border-bottom: 1px solid var(--border); font-size: 0.85rem; }
  .history-item:last-child { border-bottom: none; }
  .footer { text-align: center; margin-top: 2rem; color: var(--muted); font-size: 0.8rem; }
</style>
</head>
<body>
<div class="container">
  <h1>🔨 <span>Change Forge</span></h1>
  <p class="subtitle">AI-Powered Change Cards — Review, Edit, Reroll, Apply</p>

  <div class="top-bar">
    <div class="user-badge" id="user-badge">👤 Loading...</div>
    <div class="stats">
      <span id="stat-budget">💰 $0.00</span>
      <span id="stat-tokens">⚡ 0 tokens</span>
      <span id="stat-pending">📋 0 pending</span>
    </div>
  </div>

  <div id="message"></div>

  <div class="tab-bar">
    <button class="tab active" onclick="switchTab('forge')">🔨 Forge</button>
    <button class="tab" onclick="switchTab('feedback')">📬 New Feedback</button>
    <button class="tab" onclick="switchTab('history')">📋 History</button>
    <button class="tab" onclick="switchTab('users')">👥 Users</button>
  </div>

  <!-- ═══ FORGE TAB ═══ -->
  <div id="tab-forge" class="tab-content active">
    <div id="forge-content">
      <div class="empty-state">
        <div class="big">🔨</div>
        <h2>No active forge items</h2>
        <p>Submit feedback to generate solution cards, or switch to the Feedback tab.</p>
      </div>
    </div>
  </div>

  <!-- ═══ FEEDBACK TAB ═══ -->
  <div id="tab-feedback" class="tab-content">
    <div class="card">
      <h3 style="margin-bottom:0.8rem;color:var(--accent)">📬 Submit Change Request</h3>
      <div class="feedback-form">
        <textarea id="feedback-text" placeholder="Describe what you want changed... e.g., 'The nav bar breaks on mobile, the links stack badly'"></textarea>
        <div class="screenshot-paste-zone" id="paste-zone" onclick="document.getElementById('screenshot-file').click()">
          <p id="paste-text">📷 Paste a screenshot (Ctrl+V) or click to select a file</p>
          <img id="screenshot-preview" class="preview-img" style="display:none">
        </div>
        <input type="file" id="screenshot-file" accept="image/*" style="display:none" onchange="handleFileSelect(event)">
        <div id="cost-quote" style="display:none"></div>
        <div class="action-bar" style="justify-content:flex-start">
          <button class="btn btn-apply" onclick="submitFeedback()">🚀 Generate Solutions</button>
        </div>
      </div>
    </div>
  </div>

  <!-- ═══ HISTORY TAB ═══ -->
  <div id="tab-history" class="tab-content">
    <div id="history-content">
      <div class="empty-state">
        <div class="big">📋</div>
        <h2>No change history yet</h2>
      </div>
    </div>
  </div>

  <!-- ═══ USERS TAB ═══ -->
  <div id="tab-users" class="tab-content">
    <div id="users-content">
      <div class="empty-state">
        <div class="big">👥</div>
        <h2>Loading users...</h2>
      </div>
    </div>
  </div>

  <!-- ═══ EDIT MODAL ═══ -->
  <div class="edit-modal-overlay" id="edit-modal">
    <div class="edit-modal">
      <h2>✏️ Edit Solution</h2>
      <label>Title</label>
      <input type="text" id="edit-title">
      <label>Description</label>
      <textarea id="edit-desc" rows="2"></textarea>
      <label>Diff Preview (code changes)</label>
      <textarea id="edit-diff" rows="4" style="font-family:monospace"></textarea>
      <div class="btn-row">
        <button class="btn btn-secondary" onclick="closeEditModal()">Cancel</button>
        <button class="btn btn-primary" onclick="saveEdit()" style="background:var(--accent);color:#1a1a2e">💾 Save Changes</button>
      </div>
    </div>
  </div>

  <div class="footer">🍌🔨 CodeMonkeys Change Forge</div>
</div>

<script>
// ── State ──
let _editCtx = {};

// ── Helpers ──
function escapeHtml(str) {
  if (!str) return '';
  var d = document.createElement('div');
  d.textContent = str;
  return d.innerHTML;
}

function showMessage(msg, type) {
  var el = document.getElementById('message');
  el.textContent = msg;
  el.className = type;
  el.style.display = 'block';
}

function hideMessage() {
  document.getElementById('message').style.display = 'none';
}

// ── SECTION: NAV ──

function switchTab(tabName) {
  document.querySelectorAll('.tab').forEach(function(t) { t.classList.remove('active'); });
  document.querySelectorAll('.tab-content').forEach(function(c) { c.classList.remove('active'); });
  var tabBtn = document.querySelector('.tab[onclick*="' + tabName + '"]');
  if (tabBtn) tabBtn.classList.add('active');
  var tabContent = document.getElementById('tab-' + tabName);
  if (tabContent) tabContent.classList.add('active');
  if (tabName === 'forge') loadForge();
  if (tabName === 'history') loadHistory();
  if (tabName === 'users') loadUsers();
}

function loadForge() {
  fetch('/api/forge/list')
    .then(function(r) { return r.json(); })
    .then(function(data) {
      var container = document.getElementById('forge-content');
      var issues = data.issues || [];
      if (!issues.length) {
        container.innerHTML =
          '<div class="empty-state"><div class="big">🔨</div>' +
          '<h2>No active forge items</h2>' +
          '<p>Submit feedback to generate solution cards, or switch to the Feedback tab.</p></div>';
        return;
      }
      var html = '';
      issues.forEach(function(issue) {
        var cards = issue.solution_cards || [];
        if (!cards.length) return;
        html += '<div class="forge-grid">';
        cards.forEach(function(card) {
          html += renderCard(issue, card);
        });
        html += '</div>';
        if (issue.status === 'forge_ready') {
          html += '<div class="action-bar"><button class="btn btn-reroll" onclick="rerollAll(\'' +
            escapeHtml(issue.issue_id) + '\')">🎲 Reroll All</button></div>';
        }
      });
      container.innerHTML = html;
    })
    .catch(function(err) { showMessage('Failed to load forge: ' + err.message, 'error'); });
}

function renderCard(issue, card) {
  var rid = escapeHtml(card.risk_level || 'review');
  var rIcon = card.risk_icon || '🟠';
  var title = escapeHtml(card.title || 'Untitled');
  var desc = escapeHtml(card.description || '');
  var files = (card.files_changed || []).map(function(f) {
    return '<span>' + escapeHtml(f) + '</span>';
  }).join(' ');
  var diff = escapeHtml(card.diff_preview || '');
  var cost = card.cost_estimate || {};
  var costStr = '$' + (cost.total_charged || 0).toFixed(4);
  var issueId = escapeHtml(issue.issue_id);
  var cardId = escapeHtml(card.card_id || '');
  var appliedClass = card.status === 'applied' ? ' applied' : '';
  var discardedClass = card.status === 'rejected' ? ' discarded' : '';

  return '<div class="card' + appliedClass + discardedClass + '">' +
    '<div class="ribbon ' + rid + '">' + rIcon + ' ' + rid.toUpperCase() + '</div>' +
    '<h3>' + title + '</h3>' +
    '<div class="desc">' + desc + '</div>' +
    '<div class="files">' + files + '</div>' +
    (diff ? '<div class="diff">' + diff + '</div>' : '') +
    '<div class="cost">💰 ' + costStr + '</div>' +
    '<div class="actions">' +
    (card.status === 'pending' || card.status === 'edited' ?
      '<button class="btn btn-apply btn-sm" onclick="applyCard(\'' + issueId + '\',\'' + cardId + '\')">✅ Apply</button>' +
      '<button class="btn btn-edit btn-sm" onclick="editCard(\'' + issueId + '\',\'' + cardId + '\',\'' +
        title.replace(/'/g, "\\'") + '\',\'' +
        (card.description || '').replace(/'/g, "\\'") + '\',\'' +
        (card.diff_preview || '').replace(/'/g, "\\'") + '\')">✏️ Edit</button>' +
      '<button class="btn btn-discard btn-sm" onclick="discardCard(\'' + issueId + '\',\'' + cardId + '\')">🗑️ Discard</button>'
    : '') +
    '</div></div>';
}

function applyCard(issueId, cardId) {
  fetch('/api/forge/apply', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({issue_id: issueId, card_id: cardId})
  })
  .then(function(r) { return r.json(); })
  .then(function(data) {
    if (data.success) {
      showMessage('✅ ' + (data.message || 'Applied!'), 'success');
      loadForge();
    } else {
      showMessage('❌ ' + (data.message || 'Apply failed'), 'error');
    }
  })
  .catch(function(err) { showMessage('❌ Error: ' + err.message, 'error'); });
}

function discardCard(issueId, cardId) {
  if (!confirm('Discard this solution card?')) return;
  fetch('/api/forge/discard', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({issue_id: issueId, card_id: cardId})
  })
  .then(function(r) { return r.json(); })
  .then(function(data) {
    if (data.success) {
      showMessage('🗑️ Card discarded', 'info');
      loadForge();
    } else {
      showMessage('❌ ' + (data.message || 'Discard failed'), 'error');
    }
  })
  .catch(function(err) { showMessage('❌ Error: ' + err.message, 'error'); });
}

function rerollAll(issueId) {
  if (!confirm('Reroll all cards for this issue? This costs another API call.')) return;
  showMessage('🎲 Rerolling...', 'info');
  fetch('/api/forge/reroll', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({issue_id: issueId})
  })
  .then(function(r) { return r.json(); })
  .then(function(data) {
    if (data.success) {
      showMessage('🎲 New cards generated!', 'success');
      loadForge();
    } else {
      showMessage('❌ ' + (data.message || 'Reroll failed'), 'error');
    }
  })
  .catch(function(err) { showMessage('❌ Error: ' + err.message, 'error'); });
}

// ── SECTION: FEEDBACK ──

var _quoteTimer = null;

function handleFileSelect(event) {
  var file = event.target.files[0];
  if (!file) return;
  if (file.size > 1048576) { showMessage('⚠️ Image too large (max 1MB)', 'error'); return; }
  var reader = new FileReader();
  reader.onload = function(e) {
    window.screenshotDataUrl = e.target.result;
    var preview = document.getElementById('screenshot-preview');
    preview.src = e.target.result;
    preview.style.display = 'block';
    document.getElementById('paste-text').textContent = '📷 Screenshot attached';
    document.getElementById('paste-zone').classList.add('has-image');
  };
  reader.readAsDataURL(file);
}

document.addEventListener('paste', function(e) {
  var items = (e.clipboardData || e.originalEvent.clipboardData || {}).items;
  if (!items) return;
  for (var i = 0; i < items.length; i++) {
    if (items[i].type.indexOf('image') !== -1) {
      var file = items[i].getAsFile();
      if (!file) continue;
      if (file.size > 1048576) { showMessage('⚠️ Image too large (max 1MB)', 'error'); return; }
      var reader = new FileReader();
      reader.onload = function(ev) {
        window.screenshotDataUrl = ev.target.result;
        var preview = document.getElementById('screenshot-preview');
        preview.src = ev.target.result;
        preview.style.display = 'block';
        document.getElementById('paste-text').textContent = '📷 Screenshot pasted';
        document.getElementById('paste-zone').classList.add('has-image');
      };
      reader.readAsDataURL(file);
      break;
    }
  }
});

function fetchQuote() {
  var text = document.getElementById('feedback-text').value.trim();
  var quoteEl = document.getElementById('cost-quote');
  if (!text) { quoteEl.style.display = 'none'; return; }
  fetch('/api/forge/quote?text=' + encodeURIComponent(text))
    .then(function(r) {
      if (!r.ok) { quoteEl.style.display = 'none'; return null; }
      return r.json();
    })
    .then(function(data) {
      if (!data) { quoteEl.style.display = 'none'; return; }
      if (!data.can_submit) {
        quoteEl.innerHTML = '<div class="note" style="color:var(--danger)">⚠️ ' +
          escapeHtml(data.reason || 'Cannot submit') + '</div>';
        quoteEl.style.display = 'block';
        return;
      }
      var cost = data.cost || {};
      var budget = data.budget || {};
      quoteEl.innerHTML =
        '<div class="quote-box">' +
        '<div class="cost-row"><span>Risk</span><span>' + (data.risk_icon || '') + ' ' +
          escapeHtml(data.risk_level || '?') + '</span></div>' +
        '<div class="cost-row"><span>Generation cost</span><span>$' + (cost.generation || 0).toFixed(4) + '</span></div>' +
        '<div class="cost-row"><span>Apply cost</span><span>$' + (cost.apply || 0).toFixed(4) + '</span></div>' +
        '<div class="total"><span>Total charged</span><span>$' + (cost.total_charged || 0).toFixed(4) + '</span></div>' +
        '<div class="cost-row" style="color:var(--muted);font-size:0.8rem;margin-top:0.3rem">' +
        '<span>Remaining budget</span><span>$' + (budget.remaining || 0).toFixed(4) + '</span></div>' +
        '</div>';
      quoteEl.style.display = 'block';
    })
    .catch(function() { quoteEl.style.display = 'none'; });
}

function debouncedQuote() {
  if (_quoteTimer) clearTimeout(_quoteTimer);
  _quoteTimer = setTimeout(fetchQuote, 600);
}

function submitFeedback() {
  var text = document.getElementById('feedback-text').value.trim();
  if (!text) { showMessage('Please describe what you want changed.', 'error'); return; }
  var payload = {feedback_text: text};
  if (window.screenshotDataUrl) payload.screenshot = window.screenshotDataUrl;

  showMessage('🚀 Submitting...', 'info');
  fetch('/api/forge/submit', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(payload)
  })
  .then(function(r) { return r.json(); })
  .then(function(data) {
    if (data.success) {
      showMessage('✅ Feedback submitted! Solutions generated.' , 'success');
      document.getElementById('feedback-text').value = '';
      window.screenshotDataUrl = null;
      document.getElementById('screenshot-preview').style.display = 'none';
      document.getElementById('screenshot-preview').src = '';
      document.getElementById('paste-text').textContent = '📷 Paste a screenshot (Ctrl+V) or click to select a file';
      document.getElementById('paste-zone').classList.remove('has-image');
      document.getElementById('cost-quote').style.display = 'none';
      switchTab('forge');
    } else {
      showMessage('❌ ' + (data.message || 'Submission failed'), 'error');
    }
  })
  .catch(function(err) { showMessage('❌ Error: ' + err.message, 'error'); });
}

// ── SECTION: SHELL ──

function loadHistory() {
  fetch('/api/forge/history')
    .then(function(r) { return r.json(); })
    .then(function(data) {
      var container = document.getElementById('history-content');
      var entries = data.entries || [];
      if (!entries.length) {
        container.innerHTML =
          '<div class="empty-state"><div class="big">📋</div><h2>No change history yet</h2></div>';
        return;
      }
      var html = '<div class="card"><h2 style="color:var(--accent)">📋 Recent Changes</h2>';
      entries.forEach(function(e) {
        var riskIcon = {'trivial':'🟢','safe':'🟡','review':'🟠','critical':'🔴'}[e.risk_level] || '⚪';
        html += '<div class="history-item">' +
          '<span>' + riskIcon + ' ' + escapeHtml(e.title || 'Untitled') + '</span>' +
          '<span style="font-size:0.8rem;color:var(--muted)">by ' + escapeHtml(e.applied_by || '?') +
          ' · ' + escapeHtml(e.applied_at || '') + '</span>' +
          '</div>';
      });
      html += '</div>';
      container.innerHTML = html;
    })
    .catch(function() {});
}

function loadUsers() {
  fetch('/api/forge/users')
    .then(function(r) { return r.json(); })
    .then(function(data) {
      var container = document.getElementById('users-content');
      var users = data.users || [];
      if (!users.length) {
        container.innerHTML =
          '<div class="empty-state"><div class="big">👥</div><h2>No users found</h2></div>';
        return;
      }
      var html = '<div class="card"><h2 style="color:var(--accent)">👥 Users</h2>';
      users.forEach(function(u) {
        html += '<div class="history-item">' +
          '<span>' + escapeHtml(u.tier_title || u.tier || '?') + ' <strong>' +
          escapeHtml(u.display_name || u.user_id) + '</strong></span>' +
          '<span style="font-size:0.8rem;color:var(--muted)">💰 $' + (u.spent || 0).toFixed(2) +
          ' / $' + (u.limit || 0).toFixed(2) + '</span></div>';
      });
      html += '</div>';
      container.innerHTML = html;
    })
    .catch(function() {});
}

function loadUserBadge() {
  fetch('/api/forge/user')
    .then(function(r) { return r.json(); })
    .then(function(data) {
      var badge = document.getElementById('user-badge');
      if (badge && data.tier_title) {
        badge.textContent = '👤 ' + data.display_name + ' (' + data.tier_title + ')';
      }
    })
    .catch(function() {});
}

function loadStats() {
  fetch('/api/forge/user')
    .then(function(r) { return r.json(); })
    .then(function(data) {
      var b = data.budget || {};
      document.getElementById('stat-budget').textContent = '💰 $' + (b.remaining || 0).toFixed(2);
    })
    .catch(function() {});
  fetch('/api/forge/stats')
    .then(function(r) { return r.json(); })
    .then(function(data) {
      var count = (data.forge_ready || 0) + (data.pending_review || 0);
      document.getElementById('stat-pending').textContent = '📋 ' + count + ' pending';
    })
    .catch(function() {});
}

function pollStats() {
  setInterval(loadStats, 15000);
}

function editCard(issueId, cardId, title, desc, diff) {
  _editCtx = {issueId: issueId, cardId: cardId};
  document.getElementById('edit-title').value = title || '';
  document.getElementById('edit-desc').value = desc || '';
  document.getElementById('edit-diff').value = diff || '';
  document.getElementById('edit-modal').classList.add('active');
}

function closeEditModal() {
  document.getElementById('edit-modal').classList.remove('active');
  _editCtx = {};
}

function saveEdit() {
  var title = document.getElementById('edit-title').value.trim();
  var desc = document.getElementById('edit-desc').value.trim();
  var diff = document.getElementById('edit-diff').value.trim();
  if (!_editCtx.issueId || !_editCtx.cardId) { closeEditModal(); return; }
  fetch('/api/forge/edit', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
      issue_id: _editCtx.issueId,
      card_id: _editCtx.cardId,
      updates: {title: title, description: desc, diff_preview: diff}
    })
  })
  .then(function(r) { return r.json(); })
  .then(function(data) {
    closeEditModal();
    if (data.success) {
      showMessage('✅ Card updated', 'success');
      loadForge();
    } else {
      showMessage('❌ ' + (data.message || 'Edit failed'), 'error');
    }
  })
  .catch(function(err) { showMessage('❌ Error: ' + err.message, 'error'); });
}

document.addEventListener('DOMContentLoaded', function() {
  loadUserBadge();
  loadForge();
  pollStats();
});

</script>
</body>
</html>"""
