// Field Report — the admin inbox for feedback.
const FieldReport = {
  INP: "w-full bg-slate-950 border border-slate-800 rounded px-3 py-2 text-xs text-slate-200 focus:ring-1 focus:ring-yellow-600 focus:outline-none",

  esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"]/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  },

  init() {
    const panel = document.getElementById("field-report-panel");
    if (!panel) return;
    this.render(panel);
  },

  render(panel) {
    const inp = this.INP;
    panel.innerHTML =
      '<div class="bg-slate-900 border border-slate-800 rounded-xl p-6 space-y-5">' +
        '<div><h4 class="text-sm font-bold text-slate-100 uppercase tracking-wider">Reports Inbox</h4>' +
          '<p class="text-xs text-slate-400 leading-relaxed mt-1">Review user feedback and screenshots. Reports are filed <span class="text-yellow-500">anonymously</span>.</p></div>' +
        '<div id="fr-inbox" class="space-y-2"></div>' +
      "</div>";
    this.loadInbox();
  },

  _status(msg, kind) {
    // optional status for inbox actions
  },

  _context() {
    return "ua=" + (navigator.userAgent || "").slice(0, 180) + " | vp=" + window.innerWidth + "x" + window.innerHeight;
  },

  async loadInbox() {
    const box = document.getElementById("fr-inbox");
    if (!box) return;
    let data;
    try { data = await api("/api/feedback/list"); }
    catch (e) { return; }
    this._reports = (data && data.reports) || [];
    if (this._filter == null) this._filter = "all";
    if (this._search == null) this._search = "";
    this._renderInbox();
  },

  _renderInbox() {
    const box = document.getElementById("fr-inbox");
    if (!box) return;
    const reports = this._reports || [];
    const counts = { all: reports.length, bug: 0, improvement: 0, question: 0 };
    reports.forEach((r) => { if (Object.prototype.hasOwnProperty.call(counts, r.category)) counts[r.category]++; });
    const chip = (val, label) =>
      '<button data-fr-filter="' + val + '" class="px-2 py-1 rounded text-[11px] transition ' +
        (this._filter === val ? "bg-yellow-700 text-white" : "bg-slate-800 text-slate-300 hover:bg-slate-700") + '">' + label + "</button>";
    const controls =
      '<div class="flex flex-wrap items-center gap-1.5">' +
        chip("all", "All " + counts.all) + chip("bug", "🐞 " + counts.bug) +
        chip("improvement", "✨ " + counts.improvement) + chip("question", "❓ " + counts.question) +
      "</div>" +
      '<div class="mt-1.5"><input id="fr-search" type="search" placeholder="Search reports…" value="' +
        this.esc(this._search) + '" class="' + this.INP + '"></div>';

    const q = (this._search || "").toLowerCase();
    let rows = reports.filter((r) => this._filter === "all" || r.category === this._filter);
    if (q) rows = rows.filter((r) => ((r.message || "") + " " + (r.context || "")).toLowerCase().includes(q));

    box.innerHTML = controls +
      '<h5 class="text-xs font-bold text-yellow-500 uppercase tracking-wide mt-3">Reports (' + rows.length + "/" + reports.length + ")</h5>" +
      '<div class="space-y-2 mt-1.5">' +
        (rows.length
          ? rows.map((r) => this._reportRow(r)).join("")
          : '<p class="text-[11px] text-slate-500">' + (reports.length ? "No matching reports." : "No reports yet.") + "</p>") +
      '</div>';
    this._bindInbox(box);
    this._bindFilters(box);
  },

  _bindFilters(box) {
    box.querySelectorAll("[data-fr-filter]").forEach((b) =>
      b.addEventListener("click", () => { this._filter = b.getAttribute("data-fr-filter"); this._renderInbox(); }));
    const s = box.querySelector("#fr-search");
    if (s) s.addEventListener("input", () => {
      const pos = s.selectionStart;
      this._search = s.value;
      this._renderInbox();
      const s2 = document.getElementById("fr-search");
      if (s2) { s2.focus(); try { s2.setSelectionRange(pos, pos); } catch (e) {} }
    });
  },

  _bindInbox(box) {
    box.querySelectorAll("select[data-fb-id]").forEach((sel) =>
      sel.addEventListener("change", async () => {
        sel.disabled = true;
        try {
          await api("/api/feedback/status", "POST",
            { id: sel.getAttribute("data-fb-id"), status: sel.value });
        } catch (e) {}
        sel.disabled = false;
      }));

    box.querySelectorAll("button[data-fb-shot]").forEach((btn) =>
      btn.addEventListener("click", async () => {
        const name = btn.getAttribute("data-fb-shot");
        const img = document.getElementById("fr-shot-" + name.replace(/\W/g, ""));
        if (!img) return;
        if (!img.classList.contains("hidden")) {
          img.classList.add("hidden");
          return;
        }
        btn.textContent = "loading…";
        try {
          img.src = "/api/feedback/shot/" + encodeURIComponent(name);
          img.classList.remove("hidden");
          btn.textContent = "🖼 view screenshot";
        } catch (e) {
          btn.textContent = "⚠ error";
        }
      }));
  },

  _reportRow(r) {
    const tags = { bug: "🐞 Bug", improvement: "✨ Improvement", question: "❓ Question" };
    const tag = tags[r.category] || this.esc(r.category);
    const ctx = r.context
      ? '<div class="text-[10px] text-slate-600 font-mono mt-1 break-words">' + this.esc(r.context) + "</div>"
      : "";
    const STATUSES = ["new", "planned", "fixed", "dismissed"];
    const cur = STATUSES.indexOf(r.status) >= 0 ? r.status : "new";
    const triage = r.id
      ? '<div class="flex items-center gap-2 mt-1.5">' +
          '<select data-fb-id="' + this.esc(r.id) + '" class="bg-slate-900 border border-slate-800 rounded px-1.5 py-0.5 text-[10px] text-slate-300">' +
            STATUSES.map((s) => '<option value="' + s + '"' + (s === cur ? " selected" : "") + ">" + s + "</option>").join("") +
          "</select>" +
          (r.shot
            ? '<button data-fb-shot="' + this.esc(r.shot) + '" class="text-[10px] text-yellow-500 hover:text-yellow-400 underline">🖼 view screenshot</button>'
            : "") +
        "</div>" +
        (r.shot
          ? '<img id="fr-shot-' + this.esc(String(r.shot)).replace(/\W/g, "") + '" alt="Report screenshot" class="hidden mt-2 rounded border border-slate-700 max-w-full">'
          : "")
      : "";
    return '<div class="bg-slate-950 border border-slate-800 rounded p-2.5 text-xs">' +
      '<div class="flex items-center justify-between gap-2">' +
        '<span class="text-slate-300 font-medium">' + tag + "</span>" +
        '<span class="text-slate-600 text-[10px] font-mono">' + this.esc(r.ts || "") + "</span></div>" +
      '<div class="text-slate-200 mt-1 whitespace-pre-wrap break-words">' + this.esc(r.message || "") + "</div>" +
      ctx + triage + "</div>";
  },
};
