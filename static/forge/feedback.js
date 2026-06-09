// Feedback FAB — a floating "send feedback" button available on every screen.
const FeedbackFab = {
  _shot: null,        // captured data URL; kept only until send/close
  _h2c: null,         // html2canvas loader promise
  _tool: "mark",      // "mark" or "redact"

  esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  },

  init() {
    if (document.getElementById("fb-fab")) return;
    const btn = document.createElement("button");
    btn.id = "fb-fab";
    btn.title = "Send feedback";
    btn.setAttribute("aria-label", "Send feedback");
    btn.className = "fixed bottom-4 right-4 z-40 w-12 h-12 rounded-full " +
      "bg-slate-900/90 backdrop-blur-sm border border-yellow-600/30 hover:border-yellow-500/70 " +
      "text-yellow-500 text-lg flex items-center justify-center shadow-lg transition";
    btn.textContent = "💬";
    btn.addEventListener("click", () => this.open());
    document.body.appendChild(btn);
  },

  _loadH2C() {
    if (window.html2canvas) return Promise.resolve();
    if (this._h2c) return this._h2c;
    this._h2c = new Promise((resolve, reject) => {
      const s = document.createElement("script");
      s.src = "/static/vendor-html2canvas.min.js";
      s.onload = resolve;
      s.onerror = () => { this._h2c = null; reject(new Error("capture lib failed")); };
      document.head.appendChild(s);
    });
    return this._h2c;
  },

  async _capture() {
    try {
      await this._loadH2C();
      const canvas = await window.html2canvas(document.body, { logging: false });
      const MAX_W = 1280;
      let out = canvas;
      if (canvas.width > MAX_W) {
        out = document.createElement("canvas");
        out.width = MAX_W;
        out.height = Math.round(canvas.height * (MAX_W / canvas.width));
        out.getContext("2d").drawImage(canvas, 0, 0, out.width, out.height);
      }
      return out.toDataURL("image/jpeg", 0.75);
    } catch (e) {
      return null;
    }
  },

  async open() {
    if (document.getElementById("fb-modal")) return;
    this._shot = await this._capture();
    this._render();
  },

  close() {
    const m = document.getElementById("fb-modal");
    if (m) m.remove();
    this._shot = null;
  },

  _render() {
    const inp = "w-full bg-slate-950 border border-slate-800 rounded px-3 py-2 text-xs " +
      "text-slate-200 focus:ring-1 focus:ring-yellow-600 focus:outline-none";
    const wrap = document.createElement("div");
    wrap.id = "fb-modal";
    wrap.className = "fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm";
    wrap.innerHTML =
      '<div class="bg-slate-900 border border-slate-700 rounded-xl p-5 w-full max-w-md space-y-4 max-h-[90vh] overflow-y-auto">' +
        '<div class="flex items-center justify-between">' +
          '<h4 class="text-sm font-bold text-slate-100 uppercase tracking-wider">💬 Send feedback</h4>' +
          '<button id="fb-close" class="text-slate-500 hover:text-slate-300 text-lg leading-none" aria-label="Close">✕</button></div>' +
        '<p class="text-xs text-slate-400 leading-relaxed">Your report text is filed anonymously — no identity attached.' +
          (this._shot ? ' You can <span class="text-yellow-500">draw</span> on the preview below to redact private data or highlight bugs.' : '') +
          ' Reviewed before any change ships.</p>' +
        (this._shot
          ? '<div id="fb-shot-box" class="space-y-1.5">' +
              '<div class="relative group cursor-crosshair">' +
                '<canvas id="fb-shot-canvas" class="rounded border border-slate-700 w-full touch-none"></canvas>' +
                '<div class="absolute top-2 right-2 flex gap-1 opacity-0 group-hover:opacity-100 transition">' +
                  '<button id="fb-tool-mark" class="bg-yellow-500 text-black text-[10px] font-bold px-2 py-1 rounded border border-yellow-400 shadow-lg">Highlight</button>' +
                  '<button id="fb-tool-redact" class="bg-black text-white text-[10px] font-bold px-2 py-1 rounded border border-slate-700 shadow-lg">Redact</button>' +
                '</div>' +
              '</div>' +
              '<p class="text-[11px] text-yellow-500/90">⚠ This screenshot shows your screen. Redact sensitive info before sending.</p>' +
              '<button id="fb-shot-remove" class="text-[11px] text-rose-400 hover:text-rose-300 underline">Remove screenshot</button></div>'
          : '<p class="text-[11px] text-slate-500">No screenshot attached.</p>') +
        '<label class="text-[11px] text-slate-400 block">Type' +
          '<select id="fb-category" class="' + inp + ' mt-1">' +
            '<option value="bug">🐞 Bug — something is broken</option>' +
            '<option value="improvement">✨ Improvement — make this better</option>' +
            '<option value="question">❓ Question — how does this work?</option>' +
          '</select></label>' +
        '<label class="text-[11px] text-slate-400 block">What happened?' +
          '<textarea id="fb-message" rows="4" maxlength="4000" class="' + inp + ' mt-1" placeholder="Describe the problem or idea."></textarea></label>' +
        '<button id="fb-send" class="w-full bg-gradient-to-r from-yellow-700 to-yellow-900 hover:from-yellow-600 hover:to-yellow-800 text-white font-medium py-2 rounded text-xs transition">Send report</button>' +
        '<p id="fb-status" class="text-[11px] text-center hidden"></p>' +
      '</div>';
    document.body.appendChild(wrap);

    const canvas = document.getElementById("fb-shot-canvas");
    if (canvas && this._shot) {
      const ctx = canvas.getContext("2d");
      const img = new Image();
      img.onload = () => {
        canvas.width = img.width;
        canvas.height = img.height;
        ctx.drawImage(img, 0, 0);
        this._initDrawing(canvas);
      };
      img.src = this._shot;
    }

    document.getElementById("fb-close").addEventListener("click", () => this.close());
    wrap.addEventListener("click", (e) => { if (e.target === wrap) this.close(); });

    const markBtn = document.getElementById("fb-tool-mark");
    const redactBtn = document.getElementById("fb-tool-redact");
    if (markBtn && redactBtn) {
      const updateBtns = () => {
        markBtn.classList.toggle("ring-2", this._tool === "mark");
        markBtn.classList.toggle("ring-yellow-300", this._tool === "mark");
        redactBtn.classList.toggle("ring-2", this._tool === "redact");
        redactBtn.classList.toggle("ring-white", this._tool === "redact");
      };
      markBtn.addEventListener("click", () => { this._tool = "mark"; updateBtns(); });
      redactBtn.addEventListener("click", () => { this._tool = "redact"; updateBtns(); });
      updateBtns();
    }

    const rm = document.getElementById("fb-shot-remove");
    if (rm) rm.addEventListener("click", () => {
      this._shot = null;
      const box = document.getElementById("fb-shot-box");
      if (box) box.innerHTML = '<p class="text-[11px] text-slate-500">Screenshot removed.</p>';
    });
    document.getElementById("fb-send").addEventListener("click", () => this.submit());
  },

  _initDrawing(canvas) {
    const ctx = canvas.getContext("2d");
    let drawing = false;

    const getPos = (e) => {
      const rect = canvas.getBoundingClientRect();
      const scaleX = canvas.width / rect.width;
      const scaleY = canvas.height / rect.height;
      const clientX = e.touches ? e.touches[0].clientX : e.clientX;
      const clientY = e.touches ? e.touches[0].clientY : e.clientY;
      return { x: (clientX - rect.left) * scaleX, y: (clientY - rect.top) * scaleY };
    };

    const draw = (e) => {
      if (!drawing) return;
      const pos = getPos(e);
      ctx.lineWidth = Math.max(12, canvas.width / 40);
      ctx.lineCap = "round";
      ctx.lineJoin = "round";
      ctx.strokeStyle = this._tool === "redact" ? "#000" : "rgba(234, 179, 8, 0.4)";
      ctx.lineTo(pos.x, pos.y);
      ctx.stroke();
      ctx.beginPath();
      ctx.moveTo(pos.x, pos.y);
      if (e.cancelable) e.preventDefault();
    };

    const start = (e) => { drawing = true; ctx.beginPath(); const p = getPos(e); ctx.moveTo(p.x, p.y); draw(e); };
    const stop = () => { drawing = false; };

    canvas.addEventListener("mousedown", start);
    canvas.addEventListener("mousemove", draw);
    window.addEventListener("mouseup", stop);
    canvas.addEventListener("touchstart", start, { passive: false });
    canvas.addEventListener("touchmove", draw, { passive: false });
    canvas.addEventListener("touchend", stop);
  },

  _status(msg, kind) {
    const el = document.getElementById("fb-status");
    if (!el) return;
    el.className = "text-[11px] text-center " +
      (kind === "error" ? "text-rose-400" : kind === "ok" ? "text-emerald-400" : "text-slate-400");
    el.textContent = msg;
    el.classList.toggle("hidden", !msg);
  },

  async submit() {
    if (typeof api === "undefined" || (typeof state !== "undefined" && !state.token)) {
      this._status("Please sign in first.", "error"); return;
    }
    const category = (document.getElementById("fb-category") || {}).value || "bug";
    const message = ((document.getElementById("fb-message") || {}).value || "").trim();
    if (!message) { this._status("Add a few details first.", "error"); return; }
    
    const canvas = document.getElementById("fb-shot-canvas");
    const shot = canvas ? canvas.toDataURL("image/jpeg", 0.75) : this._shot;

    this._status("Sending…", "");
    try {
      const ctx = (typeof FieldReport !== "undefined") ? FieldReport._context() : "";
      await api("/api/feedback", "POST",
        { category: category, message: message, context: ctx, screenshot: shot || null });
      this._status("✓ Report filed — thank you.", "ok");
      const m = document.getElementById("fb-message"); if (m) m.value = "";
      setTimeout(() => this.close(), 1500);
    } catch (e) {
      this._status((e && e.message) || "Could not send — try again.", "error");
    }
  },
};

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", () => FeedbackFab.init());
} else {
  FeedbackFab.init();
}
