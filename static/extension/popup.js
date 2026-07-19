// popup.js — CodeMonkeys Companion popup logic
const DEFAULT_SERVER = 'https://codemonkeys.fly.dev';

// ── DOM refs ──────────────────────────────────────────────
const $statusDot = document.getElementById('status-dot');
const $statusMsg = document.getElementById('status-msg');
const $serverUrl = document.getElementById('server-url');
const $btnSaveUrl = document.getElementById('btn-save-url');
const $btnOpenApp = document.getElementById('btn-open-app');
const $pageInfo = document.getElementById('page-info');

// ── Init ──────────────────────────────────────────────────
(async function init() {
  // Load saved server URL
  const stored = await chrome.storage.local.get(['serverUrl']);
  const serverUrl = stored.serverUrl || DEFAULT_SERVER;
  $serverUrl.value = serverUrl;

  // Check connection
  checkServerStatus(serverUrl);

  // Load page context
  loadPageContext();

  // ── Event handlers
  $btnSaveUrl.addEventListener('click', async () => {
    const url = $serverUrl.value.trim() || DEFAULT_SERVER;
    await chrome.storage.local.set({ serverUrl: url });
    $btnSaveUrl.textContent = '✓';
    $btnSaveUrl.style.color = '#22c55e';
    setTimeout(() => { $btnSaveUrl.textContent = 'Save'; $btnSaveUrl.style.color = ''; }, 1500);
    checkServerStatus(url);
  });

  $btnOpenApp.addEventListener('click', () => {
    chrome.storage.local.get(['serverUrl'], (data) => {
      const url = data.serverUrl || DEFAULT_SERVER;
      chrome.tabs.create({ url });
    });
  });
})();

// ── Server status check ───────────────────────────────────
async function checkServerStatus(url) {
  setStatus('checking', 'Checking…');
  try {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 5000);
    const resp = await fetch(`${url}/api/health`, {
      signal: controller.signal,
      headers: { 'Accept': 'application/json' }
    });
    clearTimeout(timeout);
    if (resp.ok) {
      setStatus('online', `Connected — ${url.replace('https://', '')}`);
    } else {
      setStatus('offline', `Server responded ${resp.status}`);
    }
  } catch (e) {
    setStatus('offline', e.name === 'AbortError' ? 'Timeout — server unreachable' : 'Cannot reach server');
  }
}

function setStatus(state, message) {
  $statusDot.className = `status-dot ${state}`;
  $statusMsg.textContent = message;
}

// ── Page context ──────────────────────────────────────────
async function loadPageContext() {
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab || !tab.url) {
      $pageInfo.textContent = 'No page loaded.';
      return;
    }
    const isSpecial = tab.url.startsWith('chrome://') || tab.url.startsWith('about:') || tab.url.startsWith('edge://');
    if (isSpecial) {
      $pageInfo.textContent = `⚠ Cannot interact with browser system pages.`;
      return;
    }
    const u = new URL(tab.url);
    $pageInfo.innerHTML = `
      <strong>${escapeHtml(tab.title || 'Untitled')}</strong><br>
      <span style="color:var(--dim)">${escapeHtml(u.hostname)}</span>
    `;
  } catch (e) {
    $pageInfo.textContent = 'Could not read page info.';
  }
}

function escapeHtml(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}
