/* Agents Hub — Cursor-style Agents Window + Automations (sessions, fleet, personas) */
"use strict";

const AgentsHub = {
  tab: "sessions",
  sessions: [],
  specs: [],
  fleetJobs: [],
  personas: [],
  skills: [],
  selectedSid: null,
  selectedPersona: null,
  selectedSkill: null,
  hooksContent: "",
  selectedFleetJobId: null,
  fleetJobDetail: null,
  pollTimer: null,
  _fleetJobId: null,

  init() {
    this._ensureModal();
    document.getElementById("btn-agents-hub")?.addEventListener("click", () => this.open("sessions"));
    document.getElementById("btn-agents-hub-settings")?.addEventListener("click", () => this.open("sessions"));
    document.addEventListener("keydown", (e) => {
      if (e.ctrlKey && e.shiftKey && e.key === "A") {
        e.preventDefault();
        const m = document.getElementById("modal-agents-hub");
        if (m?.classList.contains("hidden")) this.open("sessions");
        else this.close();
      }
    });
  },

  esc(s) {
    return String(s ?? "").replace(/[&<>"']/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  },

  async api(path, method, body) {
    if (typeof window.api !== "function") throw new Error("Not logged in");
    return window.api(path, method, body);
  },

  open(tab) {
    this.tab = tab || "sessions";
    document.getElementById("modal-agents-hub")?.classList.remove("hidden");
    document.body.classList.add("agents-hub-open");
    this.refresh();
    if (this.pollTimer) clearInterval(this.pollTimer);
    this.pollTimer = setInterval(() => this.refresh(true), 4000);
  },

  close() {
    document.getElementById("modal-agents-hub")?.classList.add("hidden");
    document.body.classList.remove("agents-hub-open");
    if (this.pollTimer) clearInterval(this.pollTimer);
    this.pollTimer = null;
  },

  async refresh(quiet) {
    try {
      const d = await this.api("/api/sessions");
      this.sessions = d.sessions || [];
      if (!this.selectedSid && this.sessions.length) {
        this.selectedSid = window.state?.sid || this.sessions[0].id;
      }
    } catch (e) {
      if (!quiet) this._msg(e.message, true);
    }
    if (this.tab === "automations" && window.state?.role === "Owner") {
      try {
        const sp = await this.api("/api/specs");
        this.specs = sp.specs || [];
      } catch (_) { this.specs = []; }
      try {
        const fj = await this.api("/api/fleet/jobs");
        this.fleetJobs = fj.jobs || fj || [];
        if (!Array.isArray(this.fleetJobs)) this.fleetJobs = [];
      } catch (_) { this.fleetJobs = []; }
      if (this.selectedFleetJobId) {
        try {
          this.fleetJobDetail = await this.api(`/api/fleet/jobs/${this.selectedFleetJobId}`);
        } catch (_) { this.fleetJobDetail = null; }
      }
    }
    if (this.tab === "personas" && window.state?.role === "Owner") {
      try {
        const c = await this.api("/api/corps/list");
        this.personas = c.files || [];
      } catch (_) { this.personas = []; }
    }
    if (this.tab === "skills" && window.state?.role === "Owner") {
      try {
        const s = await this.api("/api/agents/skills");
        this.skills = s.skills || [];
      } catch (_) { this.skills = []; }
    }
    if (this.tab === "hooks" && window.state?.role === "Owner") {
      try {
        const h = await this.api("/api/agents/hooks");
        this.hooksContent = h.content || "";
      } catch (_) { this.hooksContent = ""; }
    }
    if (quiet && (this.tab === "hooks" || this.tab === "personas" || this.tab === "skills")) {
      return;
    }
    this._render();
  },

  setTab(tab) {
    this.tab = tab;
    this.refresh();
  },

  statusDot(status) {
    const s = status || "idle";
    const cls = s === "running" ? "ah-dot-run"
      : s === "waiting_approval" ? "ah-dot-wait"
      : s === "interrupted" ? "ah-dot-warn"
      : "ah-dot-idle";
    return `<span class="ah-dot ${cls}" title="${this.esc(s)}"></span>`;
  },

  async openSession(sid) {
    if (typeof window.openSession === "function") window.openSession(sid);
    this.close();
  },

  async newSession() {
    try {
      const d = await this.api("/api/sessions", "POST", { title: "New agent" });
      await this.openSession(d.id);
    } catch (e) { this._msg(e.message, true); }
  },

  async stopSession(sid) {
    try {
      await this.api(`/api/sessions/${sid}/stop`, "POST", {});
      this.refresh();
    } catch (e) { this._msg(e.message, true); }
  },

  async resumeSession(sid) {
    try {
      await this.api(`/api/sessions/${sid}/resume`, "POST", {});
      await this.openSession(sid);
    } catch (e) { this._msg(e.message, true); }
  },

  spawnPersona(name) {
    const prompt = `Spawn agent using persona corps/agents/${name} — follow its doctrine. State your role in one line, then ask what to do.`;
    if (typeof window.openSession === "function" && window.state?.sid) {
      const msg = document.getElementById("msg");
      if (msg) msg.value = prompt;
      this.close();
      msg?.focus();
    } else {
      this.newSession().then(() => {
        const msg = document.getElementById("msg");
        if (msg) msg.value = prompt;
        msg?.focus();
      });
    }
  },

  async loadPersona(name) {
    this.selectedPersona = name;
    try {
      const d = await this.api(`/api/corps/read/${encodeURIComponent(name)}`);
      document.getElementById("ah-persona-editor").value = d.content || "";
      document.getElementById("ah-persona-name").textContent = name;
      document.getElementById("ah-persona-save").classList.remove("hidden");
    } catch (e) { this._msg(e.message, true); }
  },

  async savePersona() {
    const name = this.selectedPersona;
    if (!name) return;
    const content = document.getElementById("ah-persona-editor")?.value || "";
    try {
      await this.api("/api/corps/write", "POST", { name, content });
      this._msg("Persona saved ✓");
    } catch (e) { this._msg(e.message, true); }
  },

  async loadHooks() {
    try {
      const h = await this.api("/api/agents/hooks");
      this.hooksContent = h.content || "";
      const ed = document.getElementById("ah-hooks-editor");
      if (ed) ed.value = this.hooksContent;
    } catch (e) { this._msg(e.message, true); }
  },

  async saveHooks() {
    const content = document.getElementById("ah-hooks-editor")?.value || "";
    try {
      await this.api("/api/agents/hooks", "PUT", { content });
      this.hooksContent = content;
      this._msg("Hooks saved ✓");
    } catch (e) { this._msg(e.message, true); }
  },

  async loadSkill(id) {
    this.selectedSkill = id;
    try {
      const d = await this.api(`/api/agents/skills/${encodeURIComponent(id)}`);
      document.getElementById("ah-skill-editor").value = d.content || "";
      document.getElementById("ah-skill-name").textContent = id;
      document.getElementById("ah-skill-save").classList.remove("hidden");
    } catch (e) { this._msg(e.message, true); }
  },

  async saveSkill() {
    const id = this.selectedSkill;
    if (!id) return;
    const content = document.getElementById("ah-skill-editor")?.value || "";
    try {
      await this.api(`/api/agents/skills/${encodeURIComponent(id)}`, "PUT", { content });
      this._msg("Skill saved ✓");
      this.refresh(true);
    } catch (e) { this._msg(e.message, true); }
  },

  async newSkill() {
    const id = (document.getElementById("ah-skill-new-id")?.value || "").trim().toLowerCase();
    if (!id || !/^[a-z][a-z0-9_-]{0,31}$/.test(id)) {
      this._msg("Skill id: lowercase letter then a-z, 0-9, _, -", true);
      return;
    }
    const content = `# ${id}\n\nDescribe when to use this skill and what the agent should do.\n`;
    try {
      await this.api("/api/agents/skills", "POST", { id, content });
      this.selectedSkill = id;
      await this.refresh(true);
      await this.loadSkill(id);
      this._msg("Skill created ✓");
    } catch (e) { this._msg(e.message, true); }
  },

  selectFleetJob(jobId) {
    this.selectedFleetJobId = jobId;
    this.fleetJobDetail = null;
    this.refresh(true);
  },

  async approveFleetJob(digest, approved) {
    if (!this.selectedFleetJobId) return;
    try {
      await this.api(`/api/fleet/jobs/${this.selectedFleetJobId}/approve`, "POST", { digest, approved });
      await this.refresh(true);
    } catch (e) { this._msg(e.message, true); }
  },

  async runSpec(slug) {
    try {
      const d = await this.api(`/api/specs/${encodeURIComponent(slug)}/execute`, "POST", {});
      await this.openSession(d.id);
    } catch (e) { this._msg(e.message, true); }
  },

  async startFleetJob() {
    const game = document.getElementById("ah-fs-game")?.value;
    const platform = document.getElementById("ah-fs-platform")?.value || "itch";
    const dry_run = !!document.getElementById("ah-fs-dry")?.checked;
    try {
      const cat = await this.api("/api/fleet/catalog");
      const sel = document.getElementById("ah-fs-game");
      if (sel && sel.options.length === 0 && cat.games?.length) {
        sel.innerHTML = cat.games.map((g) =>
          `<option value="${this.esc(g.id)}">${this.esc(g.title || g.id)}</option>`).join("");
      }
      const d = await this.api("/api/fleet/jobs", "POST", { platform, game, dry_run });
      this._fleetJobId = d.job_id;
      this.selectedFleetJobId = d.job_id;
      this._msg(`Fleet job ${d.job_id} started`);
      this.refresh();
    } catch (e) { this._msg(e.message, true); }
  },

  _msg(text, isErr) {
    const el = document.getElementById("ah-msg");
    if (!el) return;
    el.textContent = text;
    el.className = "ah-msg " + (isErr ? "text-red-400" : "text-green-400/90");
    if (!isErr) setTimeout(() => { if (el.textContent === text) el.textContent = ""; }, 2500);
  },

  _renderSessionsList() {
    const q = (document.getElementById("ah-session-search")?.value || "").toLowerCase();
    const filtered = this.sessions.filter((s) =>
      !q || s.title.toLowerCase().includes(q) || s.id.includes(q));
    const running = filtered.filter((s) => s.status === "running" || s.status === "waiting_approval");
    const rest = filtered.filter((s) => s.status !== "running" && s.status !== "waiting_approval");

    const row = (s) => {
      const active = s.id === this.selectedSid ? " ah-session-active" : "";
      return `<button type="button" class="ah-session-row${active}" data-sid="${this.esc(s.id)}">`
        + `${this.statusDot(s.status)}`
        + `<span class="ah-session-title">${this.esc(s.title)}</span>`
        + `<span class="ah-session-meta">$${Number(s.spent_usd).toFixed(2)} · ${this.esc(s.status)}</span>`
        + `</button>`;
    };

    let html = "";
    if (running.length) {
      html += `<div class="ah-group-label">Running</div>${running.map(row).join("")}`;
    }
    if (rest.length) {
      html += `<div class="ah-group-label">Recent</div>${rest.map(row).join("")}`;
    }
    if (!html) html = `<p class="text-slate-600 text-xs px-2 py-4">No sessions yet.</p>`;
    return html;
  },

  _renderSessionDetail() {
    const s = this.sessions.find((x) => x.id === this.selectedSid);
    if (!s) {
      return `<div class="ah-empty"><p class="text-slate-500">Select a session or start a new agent.</p></div>`;
    }
    const isCurrent = window.state?.sid === s.id;
    return `<div class="ah-detail">`
      + `<h3 class="ah-detail-title">${this.statusDot(s.status)} ${this.esc(s.title)}</h3>`
      + `<dl class="ah-detail-grid">`
      + `<dt>Status</dt><dd>${this.esc(s.status)}</dd>`
      + `<dt>Spend</dt><dd>$${Number(s.spent_usd).toFixed(4)} / $${Number(s.budget_usd).toFixed(2)}</dd>`
      + `<dt>Repo</dt><dd>${this.esc(s.repo || "—")}</dd>`
      + `<dt>ID</dt><dd><code class="text-yellow-600/80">${this.esc(s.id)}</code></dd>`
      + `</dl>`
      + `<div class="ah-detail-actions">`
      + `<button type="button" class="gold-btn rounded px-3 py-1.5 text-xs" data-ah-open="${this.esc(s.id)}">${isCurrent ? "Focused in chat" : "Open in chat"}</button>`
      + (s.status === "running"
        ? `<button type="button" class="rounded px-3 py-1.5 text-xs bg-red-900/50 hover:bg-red-800" data-ah-stop="${this.esc(s.id)}">Stop</button>`
        : "")
      + (s.status === "interrupted"
        ? `<button type="button" class="gold-border rounded px-3 py-1.5 text-xs" data-ah-resume="${this.esc(s.id)}">Resume</button>`
        : "")
      + `</div>`
      + `<p class="text-slate-600 text-[.65rem] mt-4">Like Cursor&apos;s Agents window — pick any session across your repos, then jump into the chat stream.</p>`
      + `</div>`;
  },

  _fleetStatusClass(status) {
    const s = status || "unknown";
    if (s === "running" || s === "pending") return "ah-fleet-run";
    if (s === "waiting_approval" || s === "awaiting_approval") return "ah-fleet-wait";
    if (s === "completed") return "ah-fleet-ok";
    if (s === "failed" || s === "denied") return "ah-fleet-err";
    return "ah-fleet-idle";
  },

  _renderFleetJobDetail() {
    const j = this.fleetJobDetail;
    if (!j) {
      return `<p class="text-slate-600 text-[.65rem] mt-2">Select a job for live logs and approval prompts.</p>`;
    }
    const pending = j.pending_approval || j.pendingApproval;
    let approval = "";
    if (pending) {
      approval = `<div class="ah-fleet-approval gold-border rounded p-2 mt-2 bg-yellow-900/10">`
        + `<div class="text-[var(--gold-bright)] font-bold text-[.65rem] mb-1">Approval required</div>`
        + `<div class="text-[.65rem] mb-1">${this.esc(pending.summary?.action || "action")}</div>`
        + `<div class="text-slate-500 text-[.65rem] mb-2">digest: <code>${this.esc(pending.digest)}</code></div>`
        + `<button type="button" class="gold-btn rounded px-2 py-1 text-[.65rem] mr-2" data-ah-fleet-yes="${this.esc(pending.digest)}">Approve</button>`
        + `<button type="button" class="rounded px-2 py-1 text-[.65rem] bg-red-900/60" data-ah-fleet-no="${this.esc(pending.digest)}">Deny</button>`
        + `</div>`;
    }
    const logs = (j.logs || []).join("\n") || "(no logs yet)";
    return `<div class="ah-fleet-detail mt-3 gold-border rounded p-2 bg-black/20">`
      + `<div class="flex flex-wrap gap-2 items-center text-[.65rem] mb-2">`
      + `<strong class="text-slate-300">${this.esc(j.job_id || j.id || "?")}</strong>`
      + `<span class="ah-fleet-badge ${this._fleetStatusClass(j.status)}">${this.esc(j.status || "?")}</span>`
      + `<span class="text-slate-500">${this.esc(j.platform || "")} · ${this.esc(j.game || "")}</span>`
      + `</div>`
      + approval
      + `<pre class="ah-fleet-logs">${this.esc(logs)}</pre>`
      + `</div>`;
  },

  _renderAutomations() {
    if (window.state?.role !== "Owner") {
      return `<p class="text-slate-500 text-xs">Automations (Fleet Store + saved plans) are owner-only.</p>`;
    }
    const specRows = (this.specs || []).map((sp) => {
      const slug = sp.slug || sp;
      const title = sp.title || slug;
      return `<div class="ah-auto-row">`
        + `<div><strong class="text-slate-300">${this.esc(title)}</strong>`
        + `<div class="text-slate-600 text-[.65rem]">${this.esc(slug)}</div></div>`
        + `<button type="button" class="gold-border rounded px-2 py-1 text-[.65rem]" data-ah-run-spec="${this.esc(slug)}">Run plan</button>`
        + `</div>`;
    }).join("") || `<p class="text-slate-600 text-xs">No saved plans in <code>.codemonkeys/specs/</code></p>`;

    const jobRows = (this.fleetJobs || []).slice(0, 12).map((j) => {
      const id = j.job_id || j.id || "?";
      const active = id === this.selectedFleetJobId ? " ah-fleet-row-active" : "";
      return `<button type="button" class="ah-auto-row ah-fleet-row${active} text-[.7rem] w-full text-left" data-ah-fleet-job="${this.esc(id)}">`
        + `<span class="ah-fleet-badge ${this._fleetStatusClass(j.status)}">${this.esc(j.status || "?")}</span>`
        + `<span>${this.esc(id.slice(0, 8))}… · ${this.esc(j.platform || "")} · ${this.esc(j.game || "")}</span>`
        + `</button>`;
    }).join("");

    return `<div class="ah-auto-section">`
      + `<h4 class="ah-section-title">Saved plans</h4>`
      + `<p class="text-slate-500 text-[.65rem] mb-2">Execute a plan-mode spec in a new default session — Cursor Plan Mode parity.</p>`
      + specRows
      + `<h4 class="ah-section-title mt-4">Fleet Store jobs</h4>`
      + `<p class="text-slate-500 text-[.65rem] mb-2">Browser automations for itch / Steam — every click needs your approval in-panel.</p>`
      + `<div class="ah-fleet-form">`
      + `<select id="ah-fs-game" class="input rounded px-2 py-1 text-xs flex-1"></select>`
      + `<select id="ah-fs-platform" class="input rounded px-2 py-1 text-xs">`
      + `<option value="itch">itch.io</option><option value="steam">Steam</option><option value="gamejolt">Game Jolt</option>`
      + `</select>`
      + `<label class="flex items-center gap-1 text-slate-500 text-[.65rem]"><input type="checkbox" id="ah-fs-dry"> dry-run</label>`
      + `<button type="button" id="ah-fs-start" class="gold-btn rounded px-2 py-1 text-xs">Start</button>`
      + `</div>`
      + (jobRows ? `<div class="mt-2 space-y-1">${jobRows}</div>` : `<p class="text-slate-600 text-xs mt-2">No fleet jobs yet.</p>`)
      + this._renderFleetJobDetail()
      + `</div>`;
  },

  _renderPersonas() {
    if (window.state?.role !== "Owner") {
      return `<p class="text-slate-500 text-xs">Persona editor is owner-only.</p>`;
    }
    const list = this.personas.map((f) =>
      `<button type="button" class="ah-persona-pick${f === this.selectedPersona ? " active" : ""}" data-ah-persona="${this.esc(f)}">${this.esc(f)}</button>`
    ).join("") || `<p class="text-slate-600 text-xs">No personas in corps/agents/</p>`;

    return `<div class="ah-personas-layout">`
      + `<div class="ah-persona-list">${list}</div>`
      + `<div class="ah-persona-editor-wrap">`
      + `<div class="flex justify-between items-center mb-2">`
      + `<code id="ah-persona-name" class="text-yellow-500/90 text-xs">select a persona</code>`
      + `<div class="flex gap-2">`
      + `<button type="button" id="ah-persona-spawn" class="gold-border rounded px-2 py-1 text-[.65rem] hidden">Spawn in chat</button>`
      + `<button type="button" id="ah-persona-save" class="gold-btn rounded px-2 py-1 text-[.65rem] hidden">Save</button>`
      + `</div></div>`
      + `<textarea id="ah-persona-editor" class="ah-persona-editor" spellcheck="false" placeholder="Subagent prompt (Cursor .cursor/agents/*.md style)…"></textarea>`
      + `</div></div>`;
  },

  _renderRules() {
    return `<div class="ah-rules">`
      + `<p class="text-slate-400 text-xs mb-3">Project rules and skills live in <code>corps/</code> — injected into agent context. Cursor parity: User Rules + Subagents + Skills.</p>`
      + `<div class="ah-rule-cards">`
      + `<div class="ah-rule-card"><strong>Doctrine</strong><span>CORPS_COMMANDER.md · echelon scoring</span></div>`
      + `<div class="ah-rule-card"><strong>Tiers</strong><span>CORPS_MODEL_TIERS.md · T0–T3 routing</span></div>`
      + `<div class="ah-rule-card"><strong>Treasury</strong><span>CORPS_TREASURY.md · budgets &amp; reserve</span></div>`
      + `<div class="ah-rule-card"><strong>Playbooks</strong><span>corps/playbooks/ · debate-verify, self-heal</span></div>`
      + `</div>`
      + `<div class="mt-4 flex flex-wrap gap-2">`
      + `<button type="button" id="ah-gremlins" class="gold-border rounded px-3 py-1.5 text-xs text-red-300/90">👹 Unleash Code Gremlins</button>`
      + `<button type="button" id="ah-open-corps-old" class="gold-border rounded px-3 py-1.5 text-xs text-slate-400">Legacy persona modal</button>`
      + `</div></div>`;
  },

  _renderHooks() {
    if (window.state?.role !== "Owner") {
      return `<p class="text-slate-500 text-xs">Hooks editor is owner-only.</p>`;
    }
    return `<div class="ah-hooks-layout">`
      + `<p class="text-slate-400 text-xs mb-2">Cursor-compatible hook config stored at <code>corps/hooks.json</code>. Git guards in <code>.githooks/</code> still run on commit/push separately.</p>`
      + `<div class="flex justify-end mb-2">`
      + `<button type="button" id="ah-hooks-save" class="gold-btn rounded px-2 py-1 text-[.65rem]">Save hooks</button>`
      + `</div>`
      + `<textarea id="ah-hooks-editor" class="ah-persona-editor ah-hooks-editor" spellcheck="false" placeholder='{"version": 1, "hooks": {}}'></textarea>`
      + `<div class="ah-rule-cards mt-3">`
      + `<div class="ah-rule-card"><strong>Secret scan</strong><span>Pre-commit — blocks credentials</span></div>`
      + `<div class="ah-rule-card"><strong>Brand lint</strong><span>Pre-push on marketing paths</span></div>`
      + `</div></div>`;
  },

  _renderSkills() {
    if (window.state?.role !== "Owner") {
      return `<p class="text-slate-500 text-xs">Skills editor is owner-only.</p>`;
    }
    const list = this.skills.map((s) =>
      `<button type="button" class="ah-persona-pick${s.id === this.selectedSkill ? " active" : ""}" data-ah-skill="${this.esc(s.id)}" title="${this.esc(s.description || "")}">${this.esc(s.title || s.id)}</button>`
    ).join("") || `<p class="text-slate-600 text-xs">No skills yet.</p>`;

    return `<div class="ah-personas-layout">`
      + `<div class="ah-persona-list">${list}`
      + `<div class="mt-3 pt-2 border-t border-yellow-900/20">`
      + `<input type="text" id="ah-skill-new-id" class="input w-full rounded px-2 py-1 text-[.65rem] mb-1" placeholder="new-skill-id">`
      + `<button type="button" id="ah-skill-new" class="gold-border rounded px-2 py-1 text-[.65rem] w-full">+ New skill</button>`
      + `</div></div>`
      + `<div class="ah-persona-editor-wrap">`
      + `<div class="flex justify-between items-center mb-2">`
      + `<code id="ah-skill-name" class="text-yellow-500/90 text-xs">select a skill</code>`
      + `<button type="button" id="ah-skill-save" class="gold-btn rounded px-2 py-1 text-[.65rem] hidden">Save</button>`
      + `</div>`
      + `<textarea id="ah-skill-editor" class="ah-persona-editor" spellcheck="false" placeholder="SKILL.md — when to use this skill and steps to follow…"></textarea>`
      + `</div></div>`;
  },

  _renderMain() {
    switch (this.tab) {
      case "automations": return this._renderAutomations();
      case "personas": return this._renderPersonas();
      case "skills": return this._renderSkills();
      case "rules": return this._renderRules();
      case "hooks": return this._renderHooks();
      default: return this._renderSessionDetail();
    }
  },

  _render() {
    const list = document.getElementById("ah-session-list");
    if (list) list.innerHTML = this._renderSessionsList();
    const main = document.getElementById("ah-main");
    if (main) main.innerHTML = this._renderMain();
    document.querySelectorAll(".ah-tab").forEach((b) => {
      b.classList.toggle("active", b.dataset.tab === this.tab);
    });
    this._bindDynamic();
    if (this.tab === "automations" && window.state?.role === "Owner") {
      this._loadFleetCatalog();
    }
  },

  async _loadFleetCatalog() {
    try {
      const d = await this.api("/api/fleet/catalog");
      const sel = document.getElementById("ah-fs-game");
      if (sel && d.games?.length) {
        sel.innerHTML = d.games.map((g) =>
          `<option value="${this.esc(g.id)}">${this.esc(g.title || g.id)}</option>`).join("");
      }
    } catch (_) {}
  },

  _bindDynamic() {
    document.querySelectorAll(".ah-session-row").forEach((b) => {
      b.onclick = () => { this.selectedSid = b.dataset.sid; this.tab = "sessions"; this._render(); };
    });
    document.querySelectorAll("[data-ah-open]").forEach((b) => {
      b.onclick = () => this.openSession(b.dataset.ahOpen);
    });
    document.querySelectorAll("[data-ah-stop]").forEach((b) => {
      b.onclick = () => this.stopSession(b.dataset.ahStop);
    });
    document.querySelectorAll("[data-ah-resume]").forEach((b) => {
      b.onclick = () => this.resumeSession(b.dataset.ahResume);
    });
    document.querySelectorAll("[data-ah-run-spec]").forEach((b) => {
      b.onclick = () => this.runSpec(b.dataset.ahRunSpec);
    });
    document.querySelectorAll("[data-ah-persona]").forEach((b) => {
      b.onclick = () => this.loadPersona(b.dataset.ahPersona);
    });
    document.querySelectorAll("[data-ah-skill]").forEach((b) => {
      b.onclick = () => this.loadSkill(b.dataset.ahSkill);
    });
    document.querySelectorAll("[data-ah-fleet-job]").forEach((b) => {
      b.onclick = () => this.selectFleetJob(b.dataset.ahFleetJob);
    });
    document.querySelectorAll("[data-ah-fleet-yes]").forEach((b) => {
      b.onclick = () => this.approveFleetJob(b.dataset.ahFleetYes, true);
    });
    document.querySelectorAll("[data-ah-fleet-no]").forEach((b) => {
      b.onclick = () => this.approveFleetJob(b.dataset.ahFleetNo, false);
    });
    document.getElementById("ah-fs-start") && (document.getElementById("ah-fs-start").onclick = () => this.startFleetJob());
    document.getElementById("ah-persona-save") && (document.getElementById("ah-persona-save").onclick = () => this.savePersona());
    document.getElementById("ah-hooks-save") && (document.getElementById("ah-hooks-save").onclick = () => this.saveHooks());
    document.getElementById("ah-skill-save") && (document.getElementById("ah-skill-save").onclick = () => this.saveSkill());
    document.getElementById("ah-skill-new") && (document.getElementById("ah-skill-new").onclick = () => this.newSkill());
    if (this.tab === "hooks") {
      const hooksEd = document.getElementById("ah-hooks-editor");
      if (hooksEd) {
        hooksEd.value = this.hooksContent || '{\n  "version": 1,\n  "hooks": {}\n}\n';
      }
    }
    document.getElementById("ah-persona-spawn") && (document.getElementById("ah-persona-spawn").onclick = () => {
      if (this.selectedPersona) this.spawnPersona(this.selectedPersona);
    });
    if (this.selectedPersona) {
      document.getElementById("ah-persona-spawn")?.classList.remove("hidden");
    }
    const gremlinsBtn = document.getElementById("ah-gremlins");
    if (gremlinsBtn) gremlinsBtn.onclick = () => {
      this.close();
      document.getElementById("modal-gremlins")?.classList.remove("hidden");
    };
    const corpsBtn = document.getElementById("ah-open-corps-old");
    if (corpsBtn) corpsBtn.onclick = () => {
      this.close();
      document.getElementById("modal-corps")?.classList.remove("hidden");
      if (typeof window.loadCorpsFiles === "function") window.loadCorpsFiles();
    };
  },

  _ensureModal() {
    if (document.getElementById("modal-agents-hub")) return;
    const wrap = document.createElement("div");
    wrap.id = "modal-agents-hub";
    wrap.className = "hidden fixed inset-0 z-[70] ah-backdrop flex";
    wrap.innerHTML =
      `<div class="ah-shell flex flex-col w-full h-full max-w-6xl mx-auto my-0 md:my-4 md:h-[calc(100%-2rem)] rounded-none md:rounded-xl overflow-hidden gold-border">`
      + `<header class="ah-header flex items-center gap-3 px-4 py-3 border-b border-yellow-900/40">`
      + `<h2 class="wordmark font-bold text-sm flex-1">Agents</h2>`
      + `<span class="text-slate-600 text-[.65rem] hidden sm:inline">Ctrl+Shift+A</span>`
      + `<button type="button" id="ah-close" class="text-slate-400 hover:text-white text-lg leading-none" aria-label="Close">✕</button>`
      + `</header>`
      + `<div class="flex flex-1 min-h-0">`
      + `<aside class="ah-sidebar flex flex-col w-56 shrink-0 border-r border-yellow-900/30">`
      + `<button type="button" id="ah-new" class="gold-btn mx-3 mt-3 mb-2 rounded py-2 text-xs font-bold">+ New Agent</button>`
      + `<input type="search" id="ah-session-search" class="input mx-3 mb-2 rounded px-2 py-1 text-[.65rem]" placeholder="Search sessions…">`
      + `<div id="ah-session-list" class="flex-1 overflow-y-auto px-1 pb-2"></div>`
      + `</aside>`
      + `<div class="flex-1 flex flex-col min-w-0 min-h-0">`
      + `<nav class="ah-tabs flex gap-1 px-3 pt-2 border-b border-yellow-900/20 text-[.7rem]">`
      + `<button type="button" class="ah-tab active" data-tab="sessions">Session</button>`
      + `<button type="button" class="ah-tab owner-only" data-tab="automations">Automations</button>`
      + `<button type="button" class="ah-tab owner-only" data-tab="personas">Personas</button>`
      + `<button type="button" class="ah-tab owner-only" data-tab="skills">Skills</button>`
      + `<button type="button" class="ah-tab" data-tab="rules">Rules</button>`
      + `<button type="button" class="ah-tab owner-only" data-tab="hooks">Hooks</button>`
      + `</nav>`
      + `<div id="ah-main" class="flex-1 overflow-y-auto p-4 text-sm"></div>`
      + `<p id="ah-msg" class="ah-msg px-4 pb-2 text-[.65rem] min-h-[1rem]"></p>`
      + `</div></div></div>`;
    document.body.appendChild(wrap);

    wrap.querySelector("#ah-close").onclick = () => this.close();
    wrap.querySelector("#ah-new").onclick = () => this.newSession();
    wrap.querySelector("#ah-session-search")?.addEventListener("input", () => {
      document.getElementById("ah-session-list").innerHTML = this._renderSessionsList();
      this._bindDynamic();
    });
    wrap.querySelectorAll(".ah-tab").forEach((b) => {
      b.onclick = () => this.setTab(b.dataset.tab);
    });
    wrap.addEventListener("click", (e) => {
      if (e.target === wrap) this.close();
    });
  },
};

window.AgentsHub = AgentsHub;
document.addEventListener("DOMContentLoaded", () => AgentsHub.init());
