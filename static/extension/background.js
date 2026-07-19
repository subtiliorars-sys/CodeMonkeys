// background.js — CodeMonkeys Companion service worker
const DEFAULT_SERVER = 'https://codemonkeys.fly.dev';

// ── Install / Update ──────────────────────────────────────
chrome.runtime.onInstalled.addListener((details) => {
  console.log('[CodeMonkeys] Extension installed:', details.reason);

  // Set default server URL if not already stored
  chrome.storage.local.get(['serverUrl'], (data) => {
    if (!data.serverUrl) {
      chrome.storage.local.set({ serverUrl: DEFAULT_SERVER });
    }
  });

  // Set default preferences
  chrome.storage.local.get(['prefs'], (data) => {
    if (!data.prefs) {
      chrome.storage.local.set({
        prefs: {
          bubbleEnabled: true,
          bubblePosition: 'bottom-right', // 'bottom-right' | 'bottom-left'
          theme: 'dark'
        }
      });
    }
  });
});

// ── Icon click already handled by default_popup ───────────
// Toolbar click opens popup.html automatically

// ── Message relay: content scripts ↔ popup ↔ server ──────
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  switch (message.type) {
    // Content script requests server URL
    case 'GET_SERVER_URL':
      chrome.storage.local.get(['serverUrl'], (data) => {
        sendResponse({ serverUrl: data.serverUrl || DEFAULT_SERVER });
      });
      return true; // async response

    // Content script requests preferences
    case 'GET_PREFS':
      chrome.storage.local.get(['prefs'], (data) => {
        sendResponse({ prefs: data.prefs || { bubbleEnabled: true, bubblePosition: 'bottom-right', theme: 'dark' } });
      });
      return true;

    // Popup or content script requests a server-side call
    case 'API_PROXY':
      handleApiProxy(message.payload).then(sendResponse).catch(err => sendResponse({ error: err.message }));
      return true;

    // Toggle bubble visibility
    case 'TOGGLE_BUBBLE':
      chrome.storage.local.get(['prefs'], (data) => {
        const prefs = data.prefs || {};
        prefs.bubbleEnabled = !prefs.bubbleEnabled;
        chrome.storage.local.set({ prefs }, () => {
          // Notify all content scripts
          chrome.tabs.query({}, (tabs) => {
            tabs.forEach(tab => {
              if (tab.id && tab.url && !tab.url.startsWith('chrome://') && !tab.url.startsWith('about:')) {
                chrome.tabs.sendMessage(tab.id, { type: 'PREFS_UPDATED', prefs }).catch(() => {});
              }
            });
          });
          sendResponse({ prefs });
        });
      });
      return true;

    default:
      sendResponse({ error: 'Unknown message type' });
      return false;
  }
});

// ── Proxy API calls to CodeMonkeys server ─────────────────
async function handleApiProxy({ endpoint, method, body }) {
  const data = await chrome.storage.local.get(['serverUrl']);
  const baseUrl = data.serverUrl || DEFAULT_SERVER;
  const url = `${baseUrl}${endpoint}`;

  const options = {
    method: method || 'GET',
    headers: {
      'Content-Type': 'application/json',
      'Accept': 'application/json'
    }
  };

  if (body && method !== 'GET') {
    options.body = JSON.stringify(body);
  }

  const resp = await fetch(url, options);
  if (!resp.ok) {
    throw new Error(`API error: ${resp.status} ${resp.statusText}`);
  }
  return { data: await resp.json() };
}

// ── Keyboard shortcut logging ─────────────────────────────
chrome.commands.onCommand.addListener((command) => {
  console.log('[CodeMonkeys] Command:', command);
});
