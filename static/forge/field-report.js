// Field Report — admin inbox with canonical three-card triage UX.
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
    panel.innerHTML =
      '<div class="space-y-4">' +
        '<div><h4 class="text-sm font-bold text-slate-100 uppercase tracking-wider">Reports Inbox</h4>' +
          '<p class="text-xs text-slate-400 leading-relaxed mt-1">Three-card triage — approve on a card or apply a custom fix.</p></div>' +
        '<div id="fr-inbox" class="triage-wrap space-y-4"></div>' +
      "</div>";
    this.loadInbox();
  },

  _triagePick: {},
  _triageBound: false,

  _archived(r) {
    return r.status === "fixed" || r.status === "dismissed";
  },

  _patchReport(item) {
    if (!item || !item.id) return;
    const idx = (this._reports || []).findIndex((x) => x.id === item.id);
    if (idx >= 0) this._reports[idx] = item;
    this._renderInbox();
  },

  async loadInbox() {
    const box = document.getElementById("fr-inbox");
    if (!box) return;
    let data;
    try { data = await api("/api/feedback/list"); }
    catch (e) {
      box.innerHTML = '<p class="text-[11px] text-slate-500">Could not load reports.</p>';
      return;
    }
    this._reports = (data && data.reports) || [];
    if (this._filter == null) this._filter = "all";
    if (this._search == null) this._search = "";
    if (typeof ThreeCardTriage !== "undefined" && !this._triageBound) {
      this._triageBound = true;
      ThreeCardTriage.bindContainer(box, {
        picks: this._triagePick,
        getItem: (id) => (this._reports || []).find((x) => x.id === id),
        patchItem: (item) => this._patchReport(item),
        apiPost: (path, body) => api(path, "POST", body),
        onToast: (msg, err) => {
          if (typeof showToast === "function") showToast(msg, err);
        },
        rerender: () => this._renderInbox(),
        labels: {
          approveRecommended: "✓ Approve recommended fix",
          approveOption: "✓ Approve option",
          custom: "Custom fix",
        },
        acceptStatus: "planned",
        acceptToast: "Fix accepted — filed for implementation.",
      });
    }
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
      '<div class="space-y-4 mt-3">' +
        (rows.length
          ? rows.map((r) => this._triageRow(r)).join("")
          : '<p class="text-[11px] text-slate-500">' + (reports.length ? "No matching reports." : "No reports yet.") + "</p>") +
      "</div>";
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
    box.querySelectorAll("button[data-fb-shot]").forEach((btn) =>
      btn.addEventListener("click", async () => {
        const name = btn.getAttribute("data-fb-shot");
        const img = document.getElementById("fr-shot-" + name.replace(/\W/g, ""));
        if (!img) return;
        if (!img.classList.contains("hidden")) {
          img.classList.add("hidden");
          img.removeAttribute("src");
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

  _triageRow(r) {
    const T = typeof ThreeCardTriage !== "undefined" ? ThreeCardTriage : null;
    const esc = T ? T.esc : this.esc.bind(this);
    const tags = { bug: "🐞 Bug", improvement: "✨ Improvement", question: "❓ Question" };
    const tag = tags[r.category] || esc(r.category);
    const ctx = r.context
      ? '<div class="triage-meta mt-1">Context: ' + esc(r.context) + "</div>"
      : "";
    const shotBtn = r.shot
      ? '<button data-fb-shot="' + esc(r.shot) + '" class="triage-btn text-[10px] text-yellow-500 underline mt-2">🖼 view screenshot</button>' +
        '<img id="fr-shot-' + esc(String(r.shot)).replace(/\W/g, "") + '" alt="Report screenshot" class="hidden mt-2 rounded border border-slate-700 max-w-full">'
      : "";
    if (this._archived(r)) {
      return '<article class="triage-item archived">' +
        '<div class="flex justify-between gap-2 flex-wrap"><span>' + tag + '</span><span class="triage-meta">' + esc(r.ts || "") + "</span></div>" +
        '<div class="triage-body">' + esc(r.message || "") + "</div>" + ctx +
        (r.chosenSolution ? '<div class="text-xs mt-2 text-emerald-400"><strong>Accepted:</strong> ' + esc(r.chosenSolution) + "</div>" : "") +
        '<div class="fb-toolbar mt-3"><button type="button" class="triage-btn" data-triage-status="' + esc(r.id) + '" data-status="new">Reopen</button></div>' +
        "</article>";
    }
    const pick = (this._triagePick[r.id]) || (T ? T.defaultPick(r) : { text: "", slot: null });
    const cardLabels = { approveRecommended: "✓ Approve recommended fix", approveOption: "✓ Approve option" };
    const cards = T
      ? T.renderProposalCard(r, 0, pick, { labels: cardLabels }) +
        T.renderProposalCard(r, 1, pick, { labels: cardLabels }) +
        T.renderProposalCard(r, 2, pick, { labels: cardLabels })
      : "";
    const preview = T ? T.renderAcceptPreview(r, pick, { previewLabel: "Fix preview (one only)" }) : "";
    const noteVal = esc(r.reviewNote || r.status_note || "");
    return '<article class="triage-item" data-report="' + esc(r.id) + '">' +
      '<div class="flex justify-between gap-2 flex-wrap mb-2"><span class="font-semibold text-slate-200">' + tag + '</span><span class="triage-meta">' + esc(r.ts || "") + "</span></div>" +
      '<div class="triage-body">' + esc(r.message || "") + "</div>" + ctx + shotBtn +
      '<div class="triage-section-label">Three proposed fixes — approve on a card (★ = recommended)</div>' +
      '<div class="fb-proposals">' + cards + "</div>" +
      preview +
      '<label class="text-[11px] text-slate-400 block mt-2">Custom fix</label>' +
      '<textarea class="fb-custom-solution" id="triage-custom-' + esc(r.id) + '" placeholder="Write your own fix…">' + esc(pick.text || "") + "</textarea>" +
      '<input type="text" class="fb-note-input" id="triage-note-' + esc(r.id) + '" placeholder="Review note (optional)" value="' + noteVal + '">' +
      '<div class="fb-toolbar">' +
        '<button type="button" class="triage-btn" data-triage-reroll-all="' + esc(r.id) + '">↻ Reroll all three</button>' +
        '<button type="button" class="triage-btn triage-btn-go" data-triage-accept-custom="' + esc(r.id) + '">✓ Apply custom fix</button>' +
        '<button type="button" class="triage-btn triage-btn-no" data-triage-status="' + esc(r.id) + '" data-status="dismissed">Decline</button>' +
        '<button type="button" class="triage-btn" data-triage-status="' + esc(r.id) + '" data-status="fixed">Mark fixed</button>' +
      "</div></article>";
  },
};
