/* Cursor-like workbench: toggle fleet store panel + embedded terminal + layout persist */
"use strict";

const WB_MOBILE = () => window.matchMedia("(max-width: 767px)").matches;

const Workbench = {
  init() {
    const main = document.querySelector("#view-main main");
    if (!main) return;

    const header = main.querySelector("header");
    if (header && !document.getElementById("wb-toolbar")) {
      const bar = document.createElement("div");
      bar.id = "wb-toolbar";
      bar.className = "px-4 py-1 border-b border-yellow-900/30 flex gap-2 text-[.65rem]";
      bar.innerHTML =
        '<button id="wb-toggle-term" class="gold-border rounded px-2 py-0.5 text-slate-400 hover:text-[var(--gold)]">⌨ Terminal</button>' +
        '<span class="text-slate-600 flex-1 text-right hidden lg:inline">drag terminal edge to resize</span>';
      header.after(bar);
    }

    if (!document.getElementById("panel-fleet")) {
      const center = document.createElement("div");
      center.id = "wb-body";
      center.className = "flex-1 flex min-h-0";
      const stream = document.getElementById("stream");
      const composer = document.getElementById("composer");
      const chatWrap = document.createElement("div");
      chatWrap.id = "panel-chat";
      chatWrap.className = "flex-1 flex flex-col min-w-0 min-h-0";
      if (stream && composer) {
        stream.parentNode.insertBefore(center, stream);
        chatWrap.appendChild(stream);
        chatWrap.appendChild(composer);
        center.appendChild(chatWrap);
      }
      const fleet = document.createElement("aside");
      fleet.id = "panel-fleet";
      fleet.className = "hidden w-72 shrink-0 border-l border-yellow-900/40 overflow-y-auto";
      center.appendChild(fleet);
    }

    if (!document.getElementById("panel-terminal")) {
      const term = document.createElement("div");
      term.id = "panel-terminal";
      term.className = "hidden flex flex-col border-t border-yellow-900/40 bg-black/30";
      term.style.height = "180px";
      term.innerHTML =
        '<div id="wb-term-resize" class="h-1 cursor-ns-resize bg-yellow-900/30 hover:bg-yellow-700/50" title="Drag to resize"></div>' +
        '<div id="term-scrollback" class="flex-1 overflow-y-auto p-2 text-[.72rem] text-slate-300 font-mono"></div>' +
        '<div class="flex border-t border-yellow-900/30 p-1 gap-1">' +
          '<span class="text-[var(--gold)] px-1">&gt;</span>' +
          '<input id="term-cmd" class="input flex-1 rounded px-2 py-1 text-[.72rem]" placeholder="message or /help" autocomplete="off">' +
        "</div>";
      main.appendChild(term);
      EmbeddedTerminal.init();
      this.bindResize();
    }

    document.getElementById("wb-toggle-term")?.addEventListener("click", () => this.toggleTerminal());

    this.applyMobileLayout();
    window.addEventListener("resize", () => this.applyMobileLayout());

    if (!WB_MOBILE()) {
      this.restoreLayout();
      if (localStorage.getItem("cm_wb_fleet") === "1") this.toggleFleet(true);
      if (localStorage.getItem("cm_wb_term") === "1") this.toggleTerminal(true);
    }
  },

  applyMobileLayout() {
    const mobile = WB_MOBILE();
    document.getElementById("wb-toolbar")?.classList.toggle("hidden", mobile);
    if (mobile) {
      document.getElementById("panel-fleet")?.classList.add("hidden");
      document.getElementById("panel-terminal")?.classList.add("hidden");
    }
  },

  toggleFleet(forceOpen) {
    if (WB_MOBILE()) return;
    const p = document.getElementById("panel-fleet");
    if (!p) return;
    const open = forceOpen === true ? true : p.classList.contains("hidden");
    p.classList.toggle("hidden", !open);
    localStorage.setItem("cm_wb_fleet", open ? "1" : "0");
    if (open && window.FleetStore) FleetStore.init(p);
  },

  toggleTerminal(forceOpen) {
    if (WB_MOBILE()) return;
    const p = document.getElementById("panel-terminal");
    if (!p) return;
    const open = forceOpen === true ? true : p.classList.contains("hidden");
    p.classList.toggle("hidden", !open);
    localStorage.setItem("cm_wb_term", open ? "1" : "0");
  },

  bindResize() {
    const handle = document.getElementById("wb-term-resize");
    const panel = document.getElementById("panel-terminal");
    if (!handle || !panel) return;
    let dragging = false;
    handle.addEventListener("mousedown", (e) => {
      dragging = true;
      e.preventDefault();
    });
    window.addEventListener("mousemove", (e) => {
      if (!dragging) return;
      const rect = panel.parentElement.getBoundingClientRect();
      const h = Math.max(100, Math.min(rect.height - 120, rect.bottom - e.clientY));
      panel.style.height = h + "px";
      localStorage.setItem("cm_wb_term_h", String(h));
    });
    window.addEventListener("mouseup", () => { dragging = false; });
  },

  restoreLayout() {
    const h = localStorage.getItem("cm_wb_term_h");
    const panel = document.getElementById("panel-terminal");
    if (h && panel) panel.style.height = h + "px";
  },
};

const EmbeddedTerminal = {
  streamDiv: null,
  init() {
    const input = document.getElementById("term-cmd");
    if (!input) return;
    input.addEventListener("keydown", async (e) => {
      if (e.key !== "Enter") return;
      const cmd = input.value.trim();
      input.value = "";
      if (!cmd) return;
      this.line("> " + cmd, "text-[var(--gold)]");
      if (cmd === "/help") {
        this.line("Send a message to the active session, or /new /approve /deny", "text-slate-500");
        return;
      }
      if (!window.state?.sid) {
        this.line("No active session — start one from the sidebar", "text-red-400");
        return;
      }
      try {
        if (cmd.startsWith("/")) {
          if (cmd === "/new") {
            const d = await window.api("/api/sessions", "POST", {});
            window.state.sid = d.id;
            window.state.after = -1;
            this.line("new session " + d.id, "text-slate-500");
            return;
          }
        }
        await window.api(`/api/sessions/${window.state.sid}/message`, "POST", { text: cmd });
      } catch (err) {
        this.line("✗ " + err.message, "text-red-400");
      }
    });
    setInterval(() => this.pollEvents(), 1500);
  },

  line(text, cls) {
    const sb = document.getElementById("term-scrollback");
    if (!sb) return;
    const div = document.createElement("div");
    if (cls) div.className = cls;
    div.textContent = text;
    sb.appendChild(div);
    sb.scrollTop = sb.scrollHeight;
    return div;
  },

  async pollEvents() {
    if (!window.state?.sid || !window.api) return;
    try {
      const d = await window.api(`/api/sessions/${window.state.sid}/events?after=${window.state.after}`);
      d.events.forEach((e) => {
        if (e.type === "text_delta") {
          if (!this.streamDiv) this.streamDiv = this.line("", "text-cyan-300");
          this.streamDiv.textContent += e.text || "";
        } else if (e.type === "text") {
          if (this.streamDiv) {
            this.streamDiv.textContent = (e.agent ? `[${e.agent}] ` : "") + (e.text || "");
            this.streamDiv = null;
          } else {
            this.line((e.agent ? `[${e.agent}] ` : "") + (e.text || ""), "text-cyan-300");
          }
        } else if (e.type === "done") {
          this.streamDiv = null;
        }
      });
      window.state.after = d.next;
    } catch (_) {}
  },
};

window.Workbench = Workbench;
document.addEventListener("DOMContentLoaded", () => {
  Workbench.init();
  if (window.CursorDesk) CursorDesk.init({ app: "codemonkeys" });
});
