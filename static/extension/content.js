// content.js -- CodeMonkeys Companion floating chat bubble
// Injects a minimal chat widget onto any page (except CodeMonkeys itself)

(function () {
  'use strict';

  var state = {
    serverUrl: 'https://codemonkeys.fly.dev',
    bubbleEnabled: true,
    bubblePosition: 'bottom-right',
    theme: 'dark',
    open: false,
    messages: [],
    connected: false
  };

  var host = null, bubble = null, panel = null, inputEl = null, msgList = null;

  async function init() {
    try {
      var urlRes = await chrome.runtime.sendMessage({ type: 'GET_SERVER_URL' });
      var prefsRes = await chrome.runtime.sendMessage({ type: 'GET_PREFS' });
      state.serverUrl = urlRes.serverUrl || state.serverUrl;
      if (prefsRes.prefs) {
        state.bubbleEnabled = prefsRes.prefs.bubbleEnabled ?? state.bubbleEnabled;
        state.bubblePosition = prefsRes.prefs.bubblePosition || state.bubblePosition;
        state.theme = prefsRes.prefs.theme || state.theme;
      }
    } catch (e) {
      console.warn('[CodeMonkeys] Could not load prefs:', e);
    }
    if (!state.bubbleEnabled) return;
    injectUI();
  }

  function injectUI() {
    host = document.createElement('div');
    host.id = 'cm-extension-root';
    document.body.appendChild(host);
    var shadow = host.attachShadow({ mode: 'open' });
    var styleEl = document.createElement('style');
    styleEl.textContent = getStyles(state.bubblePosition);
    shadow.appendChild(styleEl);
    bubble = document.createElement('button');
    bubble.id = 'cm-bubble';
    bubble.setAttribute('aria-label', 'Open CodeMonkeys chat');
    bubble.innerHTML = '\u{1F98D}';
    bubble.addEventListener('click', togglePanel);
    shadow.appendChild(bubble);
    panel = document.createElement('div');
    panel.id = 'cm-panel';
    panel.setAttribute('aria-hidden', 'true');
    panel.innerHTML = buildPanelHTML();
    shadow.appendChild(panel);
    panel.querySelector('#cm-close').addEventListener('click', closePanel);
    inputEl = panel.querySelector('#cm-input');
    msgList = panel.querySelector('#cm-messages');
    inputEl.addEventListener('keydown', function(e) {
      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
    });
    panel.querySelector('#cm-send').addEventListener('click', sendMessage);
    chrome.runtime.onMessage.addListener(function(msg) {
      if (msg.type === 'PREFS_UPDATED' && msg.prefs) {
        state.bubbleEnabled = msg.prefs.bubbleEnabled ?? state.bubbleEnabled;
        state.bubblePosition = msg.prefs.bubblePosition || state.bubblePosition;
        host.style.display = state.bubbleEnabled ? '' : 'none';
      }
    });
  }

  function buildPanelHTML() {
    return '<div class="cm-panel-header"><span class="cm-panel-title">\u{1F98D} CodeMonkeys</span><button id="cm-close" aria-label="Close chat">&times;</button></div>' +
      '<div id="cm-messages" class="cm-messages"></div>' +
      '<div class="cm-input-row"><textarea id="cm-input" rows="1" placeholder="Ask an agent\u2026"></textarea><button id="cm-send" aria-label="Send">\u27A4</button></div>' +
      '<div class="cm-panel-footer"><a id="cm-open-full" href="#" target="_blank">Open full app \u2192</a></div>';
  }

  function togglePanel() { state.open ? closePanel() : openPanel(); }

  function openPanel() {
    state.open = true;
    panel.setAttribute('aria-hidden', 'false');
    bubble.classList.add('cm-hidden');
    inputEl.focus();
    panel.querySelector('#cm-open-full').href = state.serverUrl;
    if (state.messages.length === 0) {
      addMessage('bot', '\u{1F44B} Hello! I''m the CodeMonkeys companion. Ask me anything \u2014 your agents are standing by.');
    }
  }

  function closePanel() {
    state.open = false;
    panel.setAttribute('aria-hidden', 'true');
    bubble.classList.remove('cm-hidden');
  }

  function addMessage(role, text) {
    state.messages.push({ role: role, text: text, time: Date.now() });
    var el = document.createElement('div');
    el.className = 'cm-msg cm-msg-' + role;
    el.textContent = text;
    msgList.appendChild(el);
    msgList.scrollTop = msgList.scrollHeight;
  }

  async function sendMessage() {
    var text = inputEl.value.trim();
    if (!text) return;
    addMessage('user', text);
    inputEl.value = '';
    inputEl.style.height = 'auto';
    var typingEl = document.createElement('div');
    typingEl.className = 'cm-msg cm-msg-bot cm-typing';
    typingEl.textContent = '\u2026thinking\u2026';
    msgList.appendChild(typingEl);
    msgList.scrollTop = msgList.scrollHeight;
    try {
      var resp = await chrome.runtime.sendMessage({
        type: 'API_PROXY',
        payload: { endpoint: '/api/chat', method: 'POST',
          body: { message: text, source: 'extension', url: window.location.href, title: document.title }
        }
      });
      typingEl.remove();
      if (resp.error) { addMessage('bot', '\u26A0 ' + resp.error); }
      else if (resp.data) {
        var reply = resp.data.response || resp.data.message || JSON.stringify(resp.data);
        addMessage('bot', reply);
      }
    } catch (e) {
      typingEl.remove();
      addMessage('bot', '\u26A0 Cannot reach CodeMonkeys server. Check your connection in the extension popup.');
    }
  }

  function getStyles(position) {
    var isLeft = position === 'bottom-left';
    return [
      ':host { all: initial; }',
      ':host, :host * { box-sizing: border-box; font-family: ui-monospace, "Cascadia Code", "Source Code Pro", monospace; }',
      '#cm-bubble { position: fixed; ' + (isLeft ? 'left: 20px;' : 'right: 20px;') + ' bottom: 20px; width: 48px; height: 48px; border-radius: 50%; border: none; background: linear-gradient(135deg, #f0c75e, #a67c12); color: #17130a; font-size: 22px; cursor: pointer; box-shadow: 0 4px 16px rgba(212,175,55,.35); z-index: 2147483646; display: flex; align-items: center; justify-content: center; transition: transform .2s, box-shadow .2s; }',
      '#cm-bubble:hover { transform: scale(1.08); box-shadow: 0 6px 20px rgba(212,175,55,.5); }',
      '#cm-bubble.cm-hidden { display: none; }',
      '#cm-panel { position: fixed; ' + (isLeft ? 'left: 20px;' : 'right: 20px;') + ' bottom: 76px; width: 360px; height: 480px; max-height: calc(100vh - 100px); background: #0a0a0f; border: 1px solid rgba(212,175,55,.25); border-radius: 12px; box-shadow: 0 8px 40px rgba(0,0,0,.6), 0 0 20px rgba(212,175,55,.1); z-index: 2147483645; display: flex; flex-direction: column; overflow: hidden; color: #e2e8f0; font-size: 13px; line-height: 1.4; }',
      '#cm-panel[aria-hidden="true"] { display: none; }',
      '.cm-panel-header { display: flex; align-items: center; justify-content: space-between; padding: 10px 14px; background: linear-gradient(180deg, #17130a, #0a0a0f); border-bottom: 1px solid rgba(212,175,55,.15); }',
      '.cm-panel-title { color: #d4af37; font-weight: 700; font-size: 13px; letter-spacing: .05em; }',
      '#cm-close { background: none; border: none; color: #94a3b8; font-size: 20px; cursor: pointer; line-height: 1; padding: 0 4px; }',
      '#cm-close:hover { color: #ef4444; }',
      '.cm-messages { flex: 1; overflow-y: auto; padding: 12px; display: flex; flex-direction: column; gap: 8px; }',
      '.cm-msg { max-width: 85%; padding: 8px 12px; border-radius: 10px; font-size: 12px; word-break: break-word; white-space: pre-wrap; }',
      '.cm-msg-user { align-self: flex-end; background: rgba(212,175,55,.15); border: 1px solid rgba(212,175,55,.2); color: #f0c75e; }',
      '.cm-msg-bot { align-self: flex-start; background: rgba(34,211,238,.06); border: 1px solid rgba(34,211,238,.15); color: #e2e8f0; }',
      '.cm-typing { opacity: .6; font-style: italic; }',
      '.cm-input-row { display: flex; gap: 6px; padding: 10px 12px; border-top: 1px solid rgba(212,175,55,.1); }',
      '#cm-input { flex: 1; resize: none; padding: 8px 10px; border-radius: 8px; background: #17130a; border: 1px solid rgba(212,175,55,.2); color: #e2e8f0; font-family: inherit; font-size: 12px; outline: none; max-height: 80px; }',
      '#cm-input:focus { border-color: #d4af37; }',
      '#cm-send { width: 34px; height: 34px; border-radius: 50%; border: none; background: linear-gradient(135deg, #f0c75e, #a67c12); color: #17130a; font-size: 14px; cursor: pointer; flex-shrink: 0; display: flex; align-items: center; justify-content: center; }',
      '#cm-send:hover { filter: brightness(1.1); }',
      '.cm-panel-footer { padding: 6px 14px; border-top: 1px solid rgba(212,175,55,.08); text-align: right; font-size: 11px; }',
      '.cm-panel-footer a { color: #22d3ee; text-decoration: none; }',
      '.cm-panel-footer a:hover { text-decoration: underline; }'
    ].join('\n');
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
