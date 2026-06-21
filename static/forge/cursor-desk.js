/* Cursor Desk — browser panel, screenshots, settings hub (forge console) */
"use strict";

const CursorDesk = {
  app: "codemonkeys",
  settings: {
    browser_home: "https://console.cloud.google.com/welcome?project=codemonkeys-498819",
    open_browser_on_start: false,
    allow_localhost_browser: false,
  },
  status: null,
  _h2c: null,
  LS_KEY: "cursor_desk_prefs",

  init(opts) {
    opts = opts || {};
    this.app = opts.app || "codemonkeys";
    this._loadLocalPrefs();
    this._ensureModal();
    if (this.app === "codemonkeys") this._initCM();
    else this._initMM();
    this._refreshStatus();
    if (this.settings.open_browser_on_start) this.toggleBrowser(true);
  },

  _loadLocalPrefs() {
    try {
      const raw = localStorage.getItem(this.LS_KEY);
      if (raw) Object.assign(this.settings, JSON.parse(raw));
    } catch (_) {}
  },

  _saveLocalPrefs() {
    try { localStorage.setItem(this.LS_KEY, JSON.stringify(this.settings)); } catch (_) {}
  },

  async _api(path, method, body) {
    if (this.app === "codemonkeys" && typeof window.api === "function") {
      return window.api(path, method, body);
    }
    if (typeof api !== "undefined" && api.request) {
      return api.request(path, method, body);
    }
    throw new Error("No API helper");
  },

  async _refreshStatus() {
    try {
      this.status = await this._api("/api/desk/status");
      if (this.status && this.status.desk_settings) {
        Object.assign(this.settings, this.status.desk_settings);
        this._saveLocalPrefs();
      }
    } catch (_) {
      this.status = null;
    }
    this._renderStatus();
  },

  _ensureModal() {
    if (document.getElementById("modal-desk-hub")) return;
    const wrap = document.createElement("div");
    wrap.id = "modal-desk-hub";
    wrap.className = "hidden fixed inset-0 bg-black/70 flex items-center justify-center z-[60] p-4";
    wrap.innerHTML =
      '<div class="gold-border rounded-xl bg-[var(--panel)] w-full max-w-lg max-h-[90vh] overflow-y-auto p-4 text-xs">' +
        '<div class="flex items-center gap-2 mb-3">' +
          '<h2 class="wordmark font-bold flex-1 text-sm">🖥 Cursor Desk</h2>' +
          '<button id="desk-hub-close" class="text-slate-400 hover:text-white">✕</button>' +
        "</div>" +
        '<p class="text-slate-500 mb-3">Browser, screenshots, and safe in-app settings — Cursor-style desk inside your app.</p>' +
        '<div id="desk-hub-status" class="rounded border border-yellow-900/30 bg-black/30 p-2 mb-3 text-[.7rem] text-slate-400"></div>' +
        '<div class="space-y-3">' +
          '<label class="block text-slate-400">Browser home URL</label>' +
          '<input id="desk-browser-home" type="url" class="input w-full rounded px-2 py-1" placeholder="https://…">' +
          '<label class="flex items-center gap-2 text-slate-400">' +
            '<input id="desk-open-on-start" type="checkbox" class="accent-yellow-500"> Open browser panel on login' +
          "</label>" +
          '<label class="flex items-center gap-2 text-slate-400">' +
            '<input id="desk-allow-localhost" type="checkbox" class="accent-yellow-500"> Allow localhost in embedded browser' +
          "</label>" +
          '<div class="flex flex-wrap gap-2 pt-1">' +
            '<button id="desk-save-prefs" class="gold-btn rounded px-3 py-1">Save desk prefs</button>' +
            '<button id="desk-open-browser" class="gold-border rounded px-3 py-1 text-slate-300">Open browser</button>' +
            '<button id="desk-shot-now" class="gold-border rounded px-3 py-1 text-slate-300">Screenshot → composer</button>' +
          "</div>" +
          '<hr class="border-yellow-900/30">' +
          '<p class="text-slate-500">Quick links (safe settings only — no secrets exposed here)</p>' +
          '<div id="desk-quick-links" class="flex flex-wrap gap-2"></div>' +
        "</div>" +
        '<p id="desk-hub-msg" class="text-[.65rem] mt-3 text-slate-500"></p>' +
      "</div>";
    document.body.appendChild(wrap);
    document.getElementById("desk-hub-close").onclick = () => this.closeHub();
    document.getElementById("desk-save-prefs").onclick = () => this.savePrefs();
    document.getElementById("desk-open-browser").onclick = () => { this.closeHub(); this.toggleBrowser(true); };
    document.getElementById("desk-shot-now").onclick = () => this.captureScreenshot();
    wrap.addEventListener("click", (e) => { if (e.target === wrap) this.closeHub(); });
  },

  _renderStatus() {
    const el = document.getElementById("desk-hub-status");
    if (!el) return;
    const home = document.getElementById("desk-browser-home");
    const onStart = document.getElementById("desk-open-on-start");
    const localhost = document.getElementById("desk-allow-localhost");
    if (home) home.value = this.settings.browser_home || "";
    if (onStart) onStart.checked = !!this.settings.open_browser_on_start;
    if (localhost) localhost.checked = !!this.settings.allow_localhost_browser;

    const st = this.status || {};
    const lines = [];
    if (st.vertex_ready != null) {
      lines.push(st.vertex_ready
        ? "✓ Vertex Gemini (GCP credits) — ADC ready"
        : "○ Vertex — run <code class=\"text-yellow-500/80\">gcloud auth application-default login</code>");
      if (st.vertex_project) lines.push("Project: " + st.vertex_project);
    }
    if (st.gemini_configured != null) {
      lines.push(st.gemini_configured ? "✓ Gemini API key configured" : "○ Gemini API key not set");
    }
    if (!lines.length) lines.push("Desk ready — configure models in your app settings.");
    el.innerHTML = lines.join("<br>");
    this._renderQuickLinks();
  },

  _renderQuickLinks() {
    const box = document.getElementById("desk-quick-links");
    if (!box) return;
    const links = this.app === "codemonkeys"
      ? [
          { label: "Models & keys", id: "btn-models" },
          { label: "MCP", id: "btn-mcp" },
          { label: "Cost", id: "btn-cost-dashboard" },
          { label: "Fleet / Automations", id: "btn-agents-hub-settings" },
          { label: "Cursor Desk", id: "btn-desk-hub" },
          { label: "Code Gremlins", id: "btn-gremlins" },
          { label: "Agent Corps", id: "btn-corps" },
        ]
      : [
          { label: "Cloud Sync & Keys", tab: "cloud-config" },
          { label: "Secure Access", tab: "secure-access" },
          { label: "Fleet Store", tab: "fleet-store" },
        ];
    box.innerHTML = links.map((l) =>
      `<button type="button" class="desk-ql gold-border rounded px-2 py-1 text-slate-300" data-id="${l.id || ""}" data-tab="${l.tab || ""}">${l.label}</button>`
    ).join("");
    box.querySelectorAll(".desk-ql").forEach((btn) => {
      btn.onclick = () => {
        this.closeHub();
        const id = btn.dataset.id;
        const tab = btn.dataset.tab;
        if (id) document.getElementById(id)?.click();
        if (tab) document.querySelector('[data-tab="' + tab + '"]')?.click();
      };
    });
  },

  openHub() {
    this._ensureModal();
    this._renderStatus();
    document.getElementById("modal-desk-hub")?.classList.remove("hidden");
  },

  closeHub() {
    document.getElementById("modal-desk-hub")?.classList.add("hidden");
  },

  async savePrefs() {
    const msg = document.getElementById("desk-hub-msg");
    const home = (document.getElementById("desk-browser-home")?.value || "").trim();
    const openOnStart = !!document.getElementById("desk-open-on-start")?.checked;
    const allowLocal = !!document.getElementById("desk-allow-localhost")?.checked;
    if (home && !this._urlOk(home, allowLocal)) {
      if (msg) { msg.className = "text-[.65rem] mt-3 text-red-400"; msg.textContent = "Invalid URL — use https:// (or localhost if enabled)."; }
      return;
    }
    this.settings.browser_home = home || this.settings.browser_home;
    this.settings.open_browser_on_start = openOnStart;
    this.settings.allow_localhost_browser = allowLocal;
    this._saveLocalPrefs();
    try {
      const saved = await this._api("/api/desk/settings", "POST", {
        browser_home: this.settings.browser_home,
        open_browser_on_start: openOnStart,
        allow_localhost_browser: allowLocal,
      });
      if (saved) Object.assign(this.settings, saved);
    } catch (_) { /* owner-only server save; local prefs still stick */ }
    if (msg) { msg.className = "text-[.65rem] mt-3 text-green-500"; msg.textContent = "Saved ✓"; }
    setTimeout(() => { if (msg && msg.textContent === "Saved ✓") msg.textContent = ""; }, 2000);
  },

  _urlOk(url, allowLocal) {
    try {
      const u = new URL(url);
      if (u.protocol === "https:") return true;
      if (allowLocal && u.protocol === "http:" && (u.hostname === "localhost" || u.hostname === "127.0.0.1")) return true;
      return false;
    } catch (_) { return false; }
  },

  _initCM() {
    const bar = document.getElementById("wb-toolbar");
    if (bar && !document.getElementById("wb-toggle-browser")) {
      const termBtn = document.getElementById("wb-toggle-term");
      const browserBtn = document.createElement("button");
      browserBtn.id = "wb-toggle-browser";
      browserBtn.className = "gold-border rounded px-2 py-0.5 text-slate-400 hover:text-[var(--gold)]";
      browserBtn.textContent = "🌐 Browser";
      browserBtn.onclick = () => this.toggleBrowser();
      const shotBtn = document.createElement("button");
      shotBtn.id = "wb-toggle-shot";
      shotBtn.className = "gold-border rounded px-2 py-0.5 text-slate-400 hover:text-[var(--gold)]";
      shotBtn.title = "Screenshot to composer";
      shotBtn.textContent = "📷 Shot";
      shotBtn.onclick = () => this.captureScreenshot();
      const deskBtn = document.createElement("button");
      deskBtn.id = "wb-toggle-desk";
      deskBtn.className = "gold-border rounded px-2 py-0.5 text-slate-400 hover:text-[var(--gold)]";
      deskBtn.textContent = "🖥 Desk";
      deskBtn.onclick = () => this.openHub();
      if (termBtn) termBtn.after(browserBtn, shotBtn, deskBtn);
      else bar.prepend(browserBtn, shotBtn, deskBtn);
    }
    this._ensureBrowserPanel();
    const menu = document.getElementById("settings-menu");
    if (menu && !document.getElementById("btn-desk-hub")) {
      const b = document.createElement("button");
      b.id = "btn-desk-hub";
      b.className = "owner-only w-full text-left text-slate-400 hover:text-[var(--gold)]";
      b.textContent = "🖥 Cursor Desk";
      b.onclick = () => this.openHub();
      menu.insertBefore(b, menu.firstChild);
    }
  },

  _initMM() {
    const chatTab = document.getElementById("tab-chat");
    if (!chatTab || document.getElementById("mm-desk-toolbar")) return;
    const bar = document.createElement("div");
    bar.id = "mm-desk-toolbar";
    bar.className = "flex flex-wrap gap-2 mb-3 text-[10px]";
    bar.innerHTML =
      '<button type="button" id="mm-toggle-browser" class="bg-slate-800 hover:bg-slate-700 text-slate-200 px-3 py-1.5 rounded-lg font-semibold">🌐 Browser</button>' +
      '<button type="button" id="mm-toggle-shot" class="bg-slate-800 hover:bg-slate-700 text-slate-200 px-3 py-1.5 rounded-lg font-semibold">📷 Screenshot</button>' +
      '<button type="button" id="mm-toggle-desk" class="bg-slate-800 hover:bg-slate-700 text-slate-200 px-3 py-1.5 rounded-lg font-semibold">🖥 Desk</button>';
    const chatBox = chatTab.querySelector(".bg-slate-900");
    if (chatBox) chatBox.insertBefore(bar, chatBox.firstChild);
    document.getElementById("mm-toggle-browser")?.addEventListener("click", () => this.toggleBrowser());
    document.getElementById("mm-toggle-shot")?.addEventListener("click", () => this.captureScreenshot());
    document.getElementById("mm-toggle-desk")?.addEventListener("click", () => this.openHub());
    this._ensureBrowserPanelMM();
  },

  _ensureBrowserPanel() {
    const center = document.getElementById("wb-body");
    if (!center || document.getElementById("panel-browser")) return;
    const panel = document.createElement("aside");
    panel.id = "panel-browser";
    panel.className = "hidden w-[min(480px,45vw)] shrink-0 border-l border-yellow-900/40 flex flex-col min-h-0 bg-black/20";
    panel.innerHTML = this._browserPanelHtml("cm");
    center.appendChild(panel);
    this._bindBrowser(panel, "cm_wb_browser");
  },

  _ensureBrowserPanelMM() {
    const chatTab = document.getElementById("tab-chat");
    if (!chatTab || document.getElementById("panel-browser-mm")) return;
    const panel = document.createElement("div");
    panel.id = "panel-browser-mm";
    panel.className = "hidden mt-3 rounded-xl border border-slate-800 overflow-hidden flex flex-col";
    panel.style.height = "420px";
    panel.innerHTML = this._browserPanelHtml("mm");
    chatTab.appendChild(panel);
    this._bindBrowser(panel, "mm_wb_browser");
  },

  _browserPanelHtml(prefix) {
    return (
      '<div class="flex items-center gap-1 p-1 border-b border-yellow-900/30 bg-black/40 text-[.65rem]">' +
        `<button type="button" class="desk-nav-back gold-border rounded px-1.5 py-0.5 text-slate-400" data-prefix="${prefix}">←</button>` +
        `<button type="button" class="desk-nav-fwd gold-border rounded px-1.5 py-0.5 text-slate-400" data-prefix="${prefix}">→</button>` +
        `<input type="url" class="desk-url input flex-1 rounded px-2 py-0.5 min-w-0" data-prefix="${prefix}" placeholder="https://…">` +
        `<button type="button" class="desk-nav-go gold-btn rounded px-2 py-0.5" data-prefix="${prefix}">Go</button>` +
        `<button type="button" class="desk-nav-ext gold-border rounded px-1.5 py-0.5 text-slate-400" data-prefix="${prefix}" title="Open in new tab">↗</button>` +
      "</div>" +
      `<iframe class="desk-iframe flex-1 w-full min-h-0 bg-white" data-prefix="${prefix}" sandbox="allow-scripts allow-same-origin allow-forms allow-popups allow-downloads" referrerpolicy="no-referrer"></iframe>` +
      '<p class="text-[.6rem] text-slate-600 p-1">Embedded browser — many sites block iframes; use ↗ for full window. Screenshots capture this app UI (not cross-origin iframe content).</p>'
    );
  },

  _bindBrowser(panel, lsKey) {
    const urlInput = panel.querySelector(".desk-url");
    const iframe = panel.querySelector(".desk-iframe");
    const go = (raw) => {
      const allowLocal = !!this.settings.allow_localhost_browser;
      const url = (raw || "").trim() || this.settings.browser_home;
      if (!this._urlOk(url, allowLocal)) return;
      iframe.src = url;
      if (urlInput) urlInput.value = url;
      try { localStorage.setItem(lsKey + "_url", url); } catch (_) {}
    };
    panel.querySelector(".desk-nav-go")?.addEventListener("click", () => go(urlInput?.value));
    urlInput?.addEventListener("keydown", (e) => { if (e.key === "Enter") go(urlInput.value); });
    panel.querySelector(".desk-nav-ext")?.addEventListener("click", () => {
      const u = urlInput?.value || iframe?.src;
      if (u) window.open(u, "_blank", "noopener,noreferrer");
    });
    panel.querySelector(".desk-nav-back")?.addEventListener("click", () => { try { iframe.contentWindow.history.back(); } catch (_) {} });
    panel.querySelector(".desk-nav-fwd")?.addEventListener("click", () => { try { iframe.contentWindow.history.forward(); } catch (_) {} });
    const saved = localStorage.getItem(lsKey + "_url");
    if (saved) go(saved);
    else if (this.settings.browser_home) urlInput.value = this.settings.browser_home;
  },

  toggleBrowser(forceOpen) {
    const id = this.app === "codemonkeys" ? "panel-browser" : "panel-browser-mm";
    const p = document.getElementById(id);
    if (!p) return;
    const open = forceOpen === true ? true : p.classList.contains("hidden");
    p.classList.toggle("hidden", !open);
    const lsKey = this.app === "codemonkeys" ? "cm_wb_browser" : "mm_wb_browser";
    localStorage.setItem(lsKey + "_open", open ? "1" : "0");
    if (open) {
      const iframe = p.querySelector(".desk-iframe");
      const urlInput = p.querySelector(".desk-url");
      if (iframe && !iframe.src && this.settings.browser_home) {
        iframe.src = this.settings.browser_home;
        if (urlInput) urlInput.value = this.settings.browser_home;
      }
    }
  },

  _loadH2C() {
    if (window.html2canvas) return Promise.resolve();
    if (this._h2c) return this._h2c;
    this._h2c = new Promise((resolve, reject) => {
      const s = document.createElement("script");
      s.src = this.app === "codemonkeys" ? "/static/forge/vendor-html2canvas.min.js" : "/static/vendor-html2canvas.min.js";
      s.onload = resolve;
      s.onerror = () => { this._h2c = null; reject(new Error("html2canvas failed to load")); };
      document.head.appendChild(s);
    });
    return this._h2c;
  },

  _shotTarget() {
    if (this.app === "codemonkeys") {
      const main = document.getElementById("view-main");
      return main || document.body;
    }
    const chat = document.getElementById("tab-chat");
    return (chat && !chat.classList.contains("hidden") ? chat : document.getElementById("app-screen")) || document.body;
  },

  async captureScreenshot() {
    try {
      await this._loadH2C();
      const target = this._shotTarget();
      const canvas = await window.html2canvas(target, { logging: false, useCORS: true, allowTaint: true });
      const MAX_W = 1280;
      let out = canvas;
      if (canvas.width > MAX_W) {
        out = document.createElement("canvas");
        out.width = MAX_W;
        out.height = Math.round(canvas.height * (MAX_W / canvas.width));
        out.getContext("2d").drawImage(canvas, 0, 0, out.width, out.height);
      }
      out.toBlob((blob) => {
        if (!blob) return;
        const name = "screenshot-" + new Date().toISOString().replace(/[:.]/g, "-") + ".jpg";
        if (this.app === "codemonkeys" && typeof window.__cmAddFile === "function") {
          window.__cmAddFile(new File([blob], name, { type: "image/jpeg" }));
        } else if (typeof window.__mmAttachBlob === "function") {
          window.__mmAttachBlob(blob, name);
        } else {
          const a = document.createElement("a");
          a.href = URL.createObjectURL(blob);
          a.download = name;
          a.click();
        }
      }, "image/jpeg", 0.85);
    } catch (e) {
      alert("Screenshot failed: " + (e.message || e));
    }
  },
};

window.CursorDesk = CursorDesk;
