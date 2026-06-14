/* Fleet Store panel — governed itch/Steam browser automation via fleet bridge */
"use strict";

const FleetStore = {
  jobId: null,
  pollTimer: null,

  async api(path, method = "GET", body) {
    const token = localStorage.getItem("cm_token") || "";
    const r = await fetch(path, {
      method,
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: "Bearer " + token } : {}),
      },
      ...(body ? { body: JSON.stringify(body) } : {}),
    });
    let d = {};
    try { d = await r.json(); } catch (_) {}
    if (!r.ok) throw new Error(d.detail || d.error || `${r.status}`);
    return d;
  },

  esc(s) {
    return String(s ?? "").replace(/[&<>"]/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  },

  async init(panel) {
    if (!panel) return;
    panel.innerHTML =
      '<div class="p-3 text-xs space-y-3 h-full flex flex-col">' +
        '<div class="text-[var(--gold-bright)] font-bold">🛒 Fleet Store</div>' +
        '<p class="text-slate-500">Opens real Chromium for itch.io / Steam. You approve every click in this panel — not gospel automation.</p>' +
        '<label class="block text-slate-400">Game</label>' +
        '<select id="fs-game" class="input w-full rounded px-2 py-1"></select>' +
        '<label class="block text-slate-400">Platform</label>' +
        '<select id="fs-platform" class="input w-full rounded px-2 py-1">' +
          '<option value="itch">itch.io</option><option value="steam">Steamworks</option><option value="gamejolt">Game Jolt</option>' +
        "</select>" +
        '<label class="flex items-center gap-2 text-slate-400"><input type="checkbox" id="fs-dry"> Dry-run (no mutations after approval)</label>' +
        '<button id="fs-start" class="gold-btn rounded py-2 text-xs w-full">Open browser job</button>' +
        '<div id="fs-status" class="text-slate-500"></div>' +
        '<div id="fs-approval" class="hidden gold-border rounded p-2 bg-yellow-900/10"></div>' +
        '<pre id="fs-logs" class="flex-1 overflow-y-auto bg-black/40 rounded p-2 text-[.65rem] text-slate-400 min-h-[8rem]"></pre>' +
      "</div>";

    document.getElementById("fs-start").onclick = () => this.startJob();
    await this.loadCatalog();
  },

  async loadCatalog() {
    try {
      const d = await this.api("/api/fleet/catalog");
      const sel = document.getElementById("fs-game");
      sel.innerHTML = (d.games || [])
        .map((g) => `<option value="${this.esc(g.id)}">${this.esc(g.title || g.id)}</option>`)
        .join("");
    } catch (e) {
      document.getElementById("fs-status").textContent = "Bridge offline: " + e.message;
    }
  },

  async startJob() {
    const game = document.getElementById("fs-game").value;
    const platform = document.getElementById("fs-platform").value;
    const dry_run = document.getElementById("fs-dry").checked;
    document.getElementById("fs-status").textContent = "Starting…";
    try {
      const d = await this.api("/api/fleet/jobs", "POST", { platform, game, dry_run });
      this.jobId = d.job_id;
      document.getElementById("fs-status").textContent = `Job ${this.jobId} — ${d.status}`;
      this.startPoll();
    } catch (e) {
      document.getElementById("fs-status").textContent = "Failed: " + e.message;
    }
  },

  startPoll() {
    if (this.pollTimer) clearInterval(this.pollTimer);
    this.pollTimer = setInterval(() => this.pollJob(), 1200);
    this.pollJob();
  },

  async pollJob() {
    if (!this.jobId) return;
    try {
      const job = await this.api(`/api/fleet/jobs/${this.jobId}`);
      document.getElementById("fs-logs").textContent = (job.logs || []).join("\n");
      document.getElementById("fs-status").textContent = `Status: ${job.status}`;
      const appr = document.getElementById("fs-approval");
      if (job.pending_approval || job.pendingApproval) {
        const p = job.pending_approval || job.pendingApproval;
        appr.classList.remove("hidden");
        appr.innerHTML =
          `<div class="text-[var(--gold-bright)] font-bold mb-1">Approval required</div>` +
          `<div class="mb-1">${this.esc(p.summary?.action || "action")}</div>` +
          `<div class="text-slate-500 mb-2">digest: <code>${this.esc(p.digest)}</code></div>` +
          `<button id="fs-yes" class="gold-btn rounded px-2 py-1 mr-2">Approve (Y)</button>` +
          `<button id="fs-no" class="rounded px-2 py-1 bg-red-900/60">Deny (N)</button>`;
        document.getElementById("fs-yes").onclick = () => this.approve(p.digest, true);
        document.getElementById("fs-no").onclick = () => this.approve(p.digest, false);
      } else {
        appr.classList.add("hidden");
      }
      if (["completed", "failed", "denied"].includes(job.status)) {
        clearInterval(this.pollTimer);
        this.pollTimer = null;
      }
    } catch (e) {
      document.getElementById("fs-status").textContent = "Poll error: " + e.message;
    }
  },

  async approve(digest, approved) {
    await this.api(`/api/fleet/jobs/${this.jobId}/approve`, "POST", { digest, approved });
    document.getElementById("fs-approval").classList.add("hidden");
    this.pollJob();
  },
};

window.FleetStore = FleetStore;
