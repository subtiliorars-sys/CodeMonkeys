/* CodeMonkeys forge shell — extracted from index.html inline <script> blocks
   so CSP can use script-src 'self' (Tailwind phase 2). Logic unchanged. */
"use strict";

/* ── Settings modal: tab-bar click wiring ──────────────────────────── */
document.getElementById("settings-tabs")?.addEventListener("click", function (e) {
  const btn = e.target.closest(".settings-tab");
  if (!btn) return;
  const tab = btn.dataset.tab;
  document.querySelectorAll(".settings-tab").forEach((b) => b.classList.remove("active"));
  document.querySelectorAll(".settings-panel").forEach((p) => p.classList.add("hidden"));
  btn.classList.add("active");
  document.getElementById("stab-" + tab)?.classList.remove("hidden");
});

/* ── Tab Bar: mirrors session list into #tab-bar ─────────────────────── */
(function () {
  const tabBar = document.getElementById("tab-bar");
  const newTabBtn = document.getElementById("btn-new-tab");
  if (!tabBar || !newTabBtn) return;

  newTabBtn.addEventListener("click", function () {
    document.getElementById("btn-new-session")?.click();
  });

  function syncTabs() {
    const sessionList = document.getElementById("session-list");
    if (!sessionList) return;
    tabBar.querySelectorAll(".tab-item").forEach((t) => t.remove());

    const items = Array.from(sessionList.querySelectorAll('.session-item, [class*="session"]'));
    const seen = new Set();
    items.forEach((item) => {
      const sid = item.dataset.sid || item.textContent.trim().substring(0, 20);
      if (seen.has(sid)) return;
      seen.add(sid);
      const isActive =
        item.classList.contains("active") ||
        item.getAttribute("aria-selected") === "true" ||
        item.style.color === "var(--gold)";
      const label =
        item.querySelector(".session-title, .flex-1")?.textContent?.trim() ||
        item.textContent.trim().substring(0, 24);
      const tab = document.createElement("button");
      tab.className = "tab-item" + (isActive ? " active" : "");
      tab.title = label;
      tab.textContent = label.length > 18 ? label.substring(0, 17) + "…" : label;
      tab.addEventListener("click", () => {
        const clickTarget = item.querySelector("button:not(.session-del), .flex-1") || item;
        clickTarget.click();
      });
      tabBar.insertBefore(tab, newTabBtn);
    });

    if (seen.size === 0) {
      const empty = document.createElement("span");
      empty.className = "tab-item tab-empty";
      empty.textContent = "No sessions";
      empty.style.opacity = "0.35";
      empty.style.fontSize = "0.65rem";
      empty.style.cursor = "default";
      tabBar.insertBefore(empty, newTabBtn);
    }
  }

  const sessionList = document.getElementById("session-list");
  if (sessionList) {
    const obs = new MutationObserver(syncTabs);
    obs.observe(sessionList, { childList: true, subtree: true, attributes: true });
  }

  const hdrTitle = document.getElementById("hdr-title");
  if (hdrTitle) {
    const obs2 = new MutationObserver(syncTabs);
    obs2.observe(hdrTitle, { childList: true, characterData: true, subtree: true });
  }

  setTimeout(syncTabs, 1500);
  setTimeout(syncTabs, 3000);
})();

/* ── Left Taskbar: contextual tool shortcuts ─────────────────────────── */
(function () {
  const taskbar = document.getElementById("left-taskbar");
  if (!taskbar) return;

  const TOOLS = [
    { id: "tb-terminal", emoji: "⌨", label: "Terminal", action: () => document.getElementById("wb-toggle-term")?.click() },
    { id: "tb-browser", emoji: "🌐", label: "Browser", action: () => document.getElementById("wb-toggle-browser")?.click() },
    { id: "tb-agents", emoji: "🤖", label: "Agents", action: () => document.getElementById("btn-agents-hub")?.click() },
    { id: "tb-gremlins", emoji: "👹", label: "Gremlins", action: () => document.getElementById("btn-gremlin-raid")?.click() },
  ];

  function buildTaskbar(sessionActive) {
    taskbar.querySelectorAll(".taskbar-item").forEach((el) => el.remove());
    if (!sessionActive) return;

    TOOLS.forEach((tool) => {
      const btn = document.createElement("button");
      btn.id = tool.id;
      btn.className = "taskbar-item";
      btn.title = tool.label;
      btn.setAttribute("aria-label", tool.label);
      btn.textContent = tool.emoji;
      btn.addEventListener("click", tool.action);
      const spacer = taskbar.querySelector(".taskbar-spacer");
      taskbar.insertBefore(btn, spacer || null);
    });
  }

  const hdrTitle = document.getElementById("hdr-title");

  function checkSessionState() {
    const title = hdrTitle?.textContent?.trim() || "";
    const isActive = title !== "no session" && title !== "";
    buildTaskbar(isActive);
  }

  if (hdrTitle) {
    const obs = new MutationObserver(checkSessionState);
    obs.observe(hdrTitle, { childList: true, characterData: true, subtree: true });
  }

  setTimeout(checkSessionState, 2000);
})();

/* ── Account tab: sync proxy element updates to Settings modal ─────── */
(function () {
  function watchAndSync(srcId, dstId) {
    const src = document.getElementById(srcId);
    const dst = document.getElementById(dstId);
    if (!src || !dst) return;
    const obs = new MutationObserver(() => {
      dst.textContent = src.textContent;
    });
    obs.observe(src, { childList: true, characterData: true, subtree: true });
  }
  watchAndSync("passkey-msg", "stn-passkey-msg");
  watchAndSync("push-msg", "stn-push-msg");

  function watchAndSyncHTML(srcId, dstId) {
    const src = document.getElementById(srcId);
    const dst = document.getElementById(dstId);
    if (!src || !dst) return;
    const obs = new MutationObserver(() => {
      dst.innerHTML = src.innerHTML;
    });
    obs.observe(src, { childList: true, subtree: true });
  }
  watchAndSyncHTML("passkey-list", "stn-passkey-list");
  watchAndSyncHTML("memory-list", "memory-list-modal");

  document.getElementById("stn-btn-passkey")?.addEventListener("click", () => {
    document.getElementById("btn-passkey")?.click();
  });

  document.getElementById("stn-btn-push-alerts")?.addEventListener("click", () => {
    document.getElementById("btn-push-alerts")?.click();
    setTimeout(() => {
      const msg = document.getElementById("push-msg")?.textContent;
      const dst = document.getElementById("stn-push-msg");
      if (msg && dst) dst.textContent = msg;
    }, 500);
  });

  document.getElementById("stn-btn-memory")?.addEventListener("click", () => {
    document.getElementById("btn-memory")?.click();
  });
})();
