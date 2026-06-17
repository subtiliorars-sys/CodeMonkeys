const OmniSearch = {
  _visible: false,
  _results: [],
  _index: 0,

  init() {
    if (document.getElementById("omni-wrap")) return;
    this._render();
    window.addEventListener("keydown", (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "k") {
        e.preventDefault();
        this.toggle();
      }
      if (this._visible && e.key === "Escape") this.toggle();
    });
  },

  _render() {
    const wrap = document.createElement("div");
    wrap.id = "omni-wrap";
    wrap.className = "hidden fixed inset-0 z-[100] flex items-start justify-center pt-[15vh] px-4 bg-black/60 backdrop-blur-sm";
    wrap.innerHTML =
      '<div class="w-full max-w-xl bg-slate-900 border border-yellow-600/50 rounded-xl shadow-2xl overflow-hidden">' +
        '<div class="p-4 border-b border-yellow-900/30">' +
          '<input id="omni-input" type="text" class="w-full bg-transparent text-slate-100 placeholder-slate-500 outline-none text-lg font-medium" placeholder="Search sessions, tabs, settings... (Ctrl+K)" autocomplete="off">' +
        '</div>' +
        '<div id="omni-results" class="max-h-[50vh] overflow-y-auto p-2 space-y-1"></div>' +
        '<div class="p-2 border-t border-yellow-900/20 flex justify-between text-[10px] text-slate-500 uppercase tracking-widest bg-black/20">' +
          '<span>↑↓ to navigate • Enter to select</span>' +
          '<span>Esc to close</span></div>' +
      '</div>';
    document.body.appendChild(wrap);

    const inp = document.getElementById("omni-input");
    inp.addEventListener("input", () => this._search(inp.value));
    inp.addEventListener("keydown", (e) => this._handleKey(e));
    wrap.addEventListener("click", (e) => { if (e.target === wrap) this.toggle(); });
  },

  toggle() {
    this._visible = !this._visible;
    const wrap = document.getElementById("omni-wrap");
    wrap.classList.toggle("hidden", !this._visible);
    if (this._visible) {
      const inp = document.getElementById("omni-input");
      inp.value = "";
      inp.focus();
      this._search("");
    }
  },

  _search(q) {
    q = q.toLowerCase().trim();
    const items = this._getItems();
    this._results = items.filter(it => 
      it.label.toLowerCase().includes(q) || (it.meta && it.label.toLowerCase().includes(q))
    ).slice(0, 10);
    this._index = 0;
    this._renderResults();
  },

  _getItems() {
    const items = [
      { id: "btn-models", label: "⚙ Settings: Models & Keys", cat: "Setting" },
      { id: "btn-corps", label: "⚙ Settings: Agent Corps (Personas)", cat: "Setting" },
      { id: "btn-mcp", label: "🔌 Settings: MCP Connectors", cat: "Setting" },
      { id: "btn-invite", label: "👥 Settings: Invite Developers", cat: "Setting" },
      { id: "btn-agents-hub", label: "🤖 Agents & Automations", cat: "View" },
      { id: "btn-cost-dashboard", label: "💰 Cost Dashboard", cat: "View" },
      { id: "btn-feedback-inbox", label: "📥 Feedback Inbox", cat: "View" },
      { id: "btn-new-session", label: "+ New Session", cat: "Action" },
      { action: () => document.getElementById("session-filter")?.focus(), label: "🔍 Focus session filter", cat: "Action" },
    ];

    // Add sessions from DOM (heuristic since they are there)
    document.querySelectorAll("#session-list button").forEach(b => {
      items.push({ id: b.id, label: "💬 Session: " + b.textContent.trim(), cat: "Session", action: () => b.click() });
    });

    return items;
  },

  _renderResults() {
    const box = document.getElementById("omni-results");
    if (!this._results.length) {
      box.innerHTML = '<p class="p-4 text-center text-slate-500 text-xs italic">No results found.</p>';
      return;
    }
    box.innerHTML = this._results.map((res, i) => 
      '<div class="omni-res p-3 rounded-lg flex items-center justify-between transition cursor-pointer ' + 
        (i === this._index ? "bg-yellow-600/20 border border-yellow-500/30" : "hover:bg-slate-800") + '" data-idx="' + i + '">' +
        '<div class="flex items-center gap-3">' +
          '<span class="text-xs text-slate-400 font-bold uppercase tracking-tighter w-16">' + res.cat + "</span>" +
          '<span class="text-sm ' + (i === this._index ? "text-yellow-400" : "text-slate-200") + '">' + res.label + "</span>" +
        "</div>" +
        (i === this._index ? '<span class="text-[10px] text-yellow-600">⏎</span>' : "") +
      "</div>"
    ).join("");

    box.querySelectorAll(".omni-res").forEach(el => {
      el.addEventListener("click", () => {
        this._index = parseInt(el.getAttribute("data-idx"));
        this._select();
      });
    });
  },

  _handleKey(e) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      this._index = (this._index + 1) % this._results.length;
      this._renderResults();
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      this._index = (this._index - 1 + this._results.length) % this._results.length;
      this._renderResults();
    } else if (e.key === "Enter") {
      e.preventDefault();
      this._select();
    }
  },

  _select() {
    const res = this._results[this._index];
    if (!res) return;
    this.toggle();
    if (res.action) res.action();
    else {
      const el = document.getElementById(res.id);
      if (el) el.click();
    }
  }
};

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", () => OmniSearch.init());
} else {
  OmniSearch.init();
}
