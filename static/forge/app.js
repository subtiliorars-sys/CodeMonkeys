/* CodeMonkeys console — vanilla JS, no build step. */
"use strict";

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g,
  (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const state = {
  token: localStorage.getItem("cm_token") || "",
  username: localStorage.getItem("cm_username") || "",
  role: localStorage.getItem("cm_role") || "",
  sid: null, after: -1, status: "idle", timer: null, pollMs: 0,
  files: [], registering: false,
  mode: localStorage.getItem("cm_mode") || "default",
};

const MODE_HINTS = {
  plan: "read-only — investigates & proposes a plan, changes nothing",
  default: "implements; pushes/deploys/destructive commands ask first",
  auto: "full autonomy — runs everything, no approval prompts",
};

async function api(path, method = "GET", body = null) {
  const r = await fetch(path, {
    method,
    headers: { "Content-Type": "application/json",
               ...(state.token ? { Authorization: "Bearer " + state.token } : {}) },
    body: body ? JSON.stringify(body) : null,
  });
  if (r.status === 401) { logout(); throw new Error("Session expired — log in again"); }
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.detail || r.statusText);
  return data;
}

/* ---------------- auth ---------------- */

function hideAll() {
  ["view-login", "view-setup", "view-main"].forEach((v) => $(v).classList.add("hidden"));
}
function showLogin() { hideAll(); $("view-login").classList.remove("hidden"); }
function showSetup() { hideAll(); $("view-setup").classList.remove("hidden"); }
function showMain() {
  hideAll(); $("view-main").classList.remove("hidden");
  $("who").textContent = state.username;
  // Owner-only controls hidden for invited Members
  document.querySelectorAll(".owner-only").forEach((el) =>
    el.classList.toggle("hidden", state.role !== "Owner"));
  refreshSessions(); refreshSpecs(); refreshRepos(); listPasskeys();
  if (state.role === "Owner") checkEncryptionBanner();
}

// Encryption-status banner: non-blocking warning when model keys are stored
// unencrypted (CM_MASTER_KEY unset) or couldn't be decrypted (wrong key).
async function checkEncryptionBanner() {
  try {
    const d = await api("/api/encryption-status");
    let msg = "";
    if (d.decrypt_failed) {
      msg = "Could not decrypt saved model API keys (master key missing or changed). Re-enter your keys in ⚙ Settings > Models & keys.";
    } else if (!d.encrypted) {
      msg = "Model API keys are stored unencrypted. Set CM_MASTER_KEY to encrypt them at rest (see docs/RECOVERY.md).";
    }
    if (msg) {
      $("enc-banner-msg").textContent = msg;
      $("enc-banner").classList.remove("hidden");
    } else {
      $("enc-banner").classList.add("hidden");
    }
  } catch (_) {
    // Non-critical — swallow errors silently (e.g. auth failure on non-owner)
  }
}
$("enc-banner-close").onclick = () => $("enc-banner").classList.add("hidden");
function logout() {
  ["cm_token", "cm_username", "cm_role"].forEach((k) => localStorage.removeItem(k));
  state.token = ""; stopPolling(); showLogin();
}

function saveAuth(d) {
  state.token = d.token; state.username = d.username; state.role = d.role;
  localStorage.setItem("cm_token", d.token);
  localStorage.setItem("cm_username", d.username);
  localStorage.setItem("cm_role", d.role);
}

$("lg-toggle").onclick = () => {
  state.registering = !state.registering;
  $("lg-submit").textContent = state.registering ? "Register" : "Log in";
  $("lg-mfa").classList.toggle("hidden", state.registering);
  $("lg-toggle").textContent = state.registering
    ? "Have an account? Log in" : "First time? Register the Owner account";
};

$("lg-submit").onclick = async () => {
  $("lg-msg").textContent = "";
  try {
    if (state.registering) {
      const d = await api("/api/register", "POST",
        { username: $("lg-user").value, pin: $("lg-pin").value });
      saveAuth(d);
      $("lg-uri").textContent = d.mfa_otpauth_uri;
      // QR rendered locally by the server (data URI); never sent to a CDN.
      if (d.mfa_qr) { $("lg-qr").src = d.mfa_qr; $("lg-qr").classList.remove("hidden"); }
      else { $("lg-qr").classList.add("hidden"); }   // fall back to manual-entry of the URI above
      $("lg-mfa-setup").classList.remove("hidden");
    } else {
      const d = await api("/api/login", "POST", {
        username: $("lg-user").value, pin: $("lg-pin").value, mfa_code: $("lg-mfa").value,
      });
      saveAuth(d);
      if (d.must_reset) showSetup(); else showMain();
    }
  } catch (e) { $("lg-msg").textContent = e.message; }
};
$("lg-continue").onclick = () => showMain();
$("btn-logout").onclick = logout;

/* ---------------- first-time setup (invited dev) ---------------- */

$("su-submit").onclick = async () => {
  $("su-msg").textContent = "";
  const pin = $("su-pin").value, pin2 = $("su-pin2").value;
  if (pin.length < 4) { $("su-msg").textContent = "PIN must be at least 4 digits."; return; }
  if (pin !== pin2) { $("su-msg").textContent = "PINs don't match."; return; }
  try {
    const d = await api("/api/account/setup", "POST",
      { new_username: $("su-user").value.trim(), new_pin: pin });
    saveAuth(d);
    $("su-uri").textContent = d.mfa_otpauth_uri;
    // QR rendered locally by the server (data URI); never sent to a CDN.
    if (d.mfa_qr) { $("su-qr").src = d.mfa_qr; $("su-qr").classList.remove("hidden"); }
    else { $("su-qr").classList.add("hidden"); }
    $("setup-step1").classList.add("hidden");
    $("setup-step2").classList.remove("hidden");
  } catch (e) { $("su-msg").textContent = e.message; }
};
$("su-done").onclick = () => showMain();

/* ---------------- memory boards (Owner) ---------------- */

const _mb = $("btn-memory");
if (_mb) _mb.onclick = listBlackboards;

async function listBlackboards() {
  const box = $("memory-list");
  if (!box) return;
  try {
    const r = await api("/api/blackboard", "GET");
    if (!r.blackboards.length) { box.innerHTML = `<div class="text-[.6rem] text-slate-600 pl-2">no boards yet</div>`; return; }
    box.innerHTML = r.blackboards.map((b) =>
      `<div class="flex items-center justify-between text-[.65rem] text-slate-500 pl-2">`
      + `<span>📋 ${esc(b.slug)} <span class="text-slate-700">${b.bytes}b</span></span>`
      + `<button data-slug="${esc(b.slug)}" class="mb-rm text-red-400 hover:text-red-300">delete</button>`
      + `</div>`).join("");
    box.querySelectorAll(".mb-rm").forEach((btn) => {
      btn.onclick = async () => {
        if (!confirm(`Delete memory board "${btn.dataset.slug}"?`)) return;
        try { await api("/api/blackboard/" + encodeURIComponent(btn.dataset.slug), "DELETE"); listBlackboards(); }
        catch (e) { alert(e.message); }
      };
    });
  } catch (_) { /* not owner / none */ }
}

/* ---------------- cost dashboard (Owner) ---------------- */

const _cd = $("btn-cost-dashboard");
if (_cd) _cd.onclick = openCostDashboard;

$("cost-close").onclick = () => $("modal-cost").classList.add("hidden");

function fmtUsd(v) { return "$" + Number(v || 0).toFixed(4); }
function fmtK(n) { return n >= 1000 ? (n / 1000).toFixed(1) + "k" : String(n || 0); }

async function openCostDashboard() {
  $("modal-cost").classList.remove("hidden");
  $("cd-err").classList.add("hidden");
  // reset displays
  ["cd-total-usd", "cd-total-sessions", "cd-total-tokens"].forEach(
    (id) => { $(id).textContent = "…"; });
  ["cd-by-day", "cd-by-model", "cd-sessions"].forEach(
    (id) => { $(id).innerHTML = `<p class="text-slate-600 text-xs">Loading…</p>`; });

  let data;
  try {
    data = await api("/api/usage");
  } catch (e) {
    $("cd-err").textContent = e.message || "Failed to load usage data";
    $("cd-err").classList.remove("hidden");
    ["cd-total-usd", "cd-total-sessions", "cd-total-tokens"].forEach(
      (id) => { $(id).textContent = "—"; });
    ["cd-by-day", "cd-by-model", "cd-sessions"].forEach(
      (id) => { $(id).innerHTML = `<p class="text-slate-600 text-xs">No data</p>`; });
    return;
  }

  const tot = data.total || {};
  $("cd-total-usd").textContent = fmtUsd(tot.usd);
  $("cd-total-sessions").textContent = tot.sessions ?? 0;
  $("cd-total-tokens").textContent = fmtK(tot.in_tokens) + " / " + fmtK(tot.out_tokens);

  // spend-by-day bars
  const days = data.by_day || [];
  if (!days.length) {
    $("cd-by-day").innerHTML = `<p class="text-slate-600 text-xs">No cost events yet</p>`;
  } else {
    const maxUsd = Math.max(...days.map((d) => d.usd), 0.000001);
    $("cd-by-day").innerHTML = days.map((d) => {
      const pct = Math.max(2, Math.round((d.usd / maxUsd) * 100));
      return `<div class="flex items-center gap-2 text-xs">`
        + `<span class="text-slate-400 w-24 shrink-0">${esc(d.day)}</span>`
        + `<div class="flex-1 bg-slate-800 rounded h-3 overflow-hidden">`
        + `<div class="bg-[var(--gold)] h-3 rounded" style="width:${pct}%"></div></div>`
        + `<span class="text-[var(--gold-bright)] w-16 text-right shrink-0">${fmtUsd(d.usd)}</span>`
        + `</div>`;
    }).join("");
  }

  // spend-by-model
  const models = data.by_model || [];
  if (!models.length) {
    $("cd-by-model").innerHTML = `<p class="text-slate-600 text-xs">No cost events yet</p>`;
  } else {
    const maxM = Math.max(...models.map((m) => m.usd), 0.000001);
    $("cd-by-model").innerHTML = models.map((m) => {
      const pct = Math.max(2, Math.round((m.usd / maxM) * 100));
      return `<div class="flex items-center gap-2 text-xs">`
        + `<span class="text-slate-400 truncate w-40 shrink-0">${esc(m.model)}</span>`
        + `<div class="flex-1 bg-slate-800 rounded h-3 overflow-hidden">`
        + `<div class="bg-[var(--cyan)] h-3 rounded" style="width:${pct}%"></div></div>`
        + `<span class="text-[var(--cyan-soft)] w-16 text-right shrink-0">${fmtUsd(m.usd)}</span>`
        + `<span class="text-slate-600 w-10 text-right shrink-0">${m.calls}×</span>`
        + `</div>`;
    }).join("");
  }

  // per-session table
  const sessions = data.sessions || [];
  if (!sessions.length) {
    $("cd-sessions").innerHTML = `<p class="text-slate-600 text-xs">No sessions</p>`;
  } else {
    $("cd-sessions").innerHTML = `<table class="w-full text-xs border-collapse">`
      + `<thead><tr class="text-slate-500 text-left border-b border-slate-800">`
      + `<th class="pb-1 pr-2 font-normal">Session</th>`
      + `<th class="pb-1 pr-2 font-normal text-right">Calls</th>`
      + `<th class="pb-1 pr-2 font-normal text-right">In tok</th>`
      + `<th class="pb-1 font-normal text-right">Spend</th></tr></thead>`
      + `<tbody>`
      + sessions.map((s) =>
        `<tr class="border-b border-slate-800/50">`
        + `<td class="py-1 pr-2 truncate max-w-[10rem] text-slate-300">${esc(s.title)}</td>`
        + `<td class="py-1 pr-2 text-right text-slate-400">${s.calls}</td>`
        + `<td class="py-1 pr-2 text-right text-slate-400">${fmtK(s.in_tokens)}</td>`
        + `<td class="py-1 text-right text-[var(--gold-bright)]">${fmtUsd(s.usd)}</td>`
        + `</tr>`).join("")
      + `</tbody></table>`;
  }

  // gracefully attempt today's spend from /api/spend/today (may be absent)
  try {
    const td = await api("/api/spend/today");
    if (td && typeof td.spend_today_usd === "number") {
      $("cd-total-usd").title = `Today: ${fmtUsd(td.spend_today_usd)}`;
    }
  } catch (_) { /* endpoint absent — degrade gracefully */ }
}

/* ---------------- invite developers (Owner) ---------------- */

$("btn-invite").onclick = () => { $("modal-invite").classList.remove("hidden"); loadUsers(); };
$("invite-close").onclick = () => $("modal-invite").classList.add("hidden");

$("inv-create").onclick = async () => {
  try {
    const d = await api("/api/invite", "POST", { username: $("inv-user").value.trim() });
    $("inv-u").textContent = d.username;
    $("inv-p").textContent = d.starter_pin;
    $("inv-result").classList.remove("hidden");
    $("inv-user").value = "";
    loadUsers();
  } catch (e) { alert(e.message); }
};

async function loadUsers() {
  const d = await api("/api/users");
  $("user-rows").innerHTML = d.users.map((u) => `
    <div class="flex items-center gap-2 border-b border-slate-800/60 py-1">
      <span class="flex-1 ${u.role === "Owner" ? "text-[var(--gold-bright)]" : "text-slate-300"}">${esc(u.username)}
        <span class="text-slate-600">${esc(u.role)}${u.pending ? " · pending first login" : (u.has_mfa ? " · active" : "")}</span></span>
      ${u.role === "Owner" ? "" : `<button data-u="${esc(u.username)}" class="user-del text-red-500/70 hover:text-red-400">remove</button>`}
    </div>`).join("");
  document.querySelectorAll(".user-del").forEach((b) => (b.onclick = async () => {
    if (confirm(`Remove ${b.dataset.u}?`)) {
      await api(`/api/users/${encodeURIComponent(b.dataset.u)}`, "DELETE"); loadUsers();
    }
  }));
}

/* ---------------- biometrics / passkey (WebAuthn) ---------------- */

const b64uToBuf = (s) => {
  const b64 = s.replace(/-/g, "+").replace(/_/g, "/") + "=".repeat((4 - (s.length % 4)) % 4);
  return Uint8Array.from(atob(b64), (c) => c.charCodeAt(0)).buffer;
};
const bufToB64u = (buf) =>
  btoa(String.fromCharCode(...new Uint8Array(buf)))
    .replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");

$("lg-bio").onclick = async () => {
  $("lg-msg").textContent = "";
  const u = $("lg-user").value.trim();
  if (!u) { $("lg-msg").textContent = "Enter your username first, then tap the biometric button."; return; }
  if (!navigator.credentials) { $("lg-msg").textContent = "This browser doesn't support passkeys."; return; }
  try {
    const options = await api("/api/webauthn/login/begin", "POST", { username: u });
    options.challenge = b64uToBuf(options.challenge);
    (options.allowCredentials || []).forEach((c) => (c.id = b64uToBuf(c.id)));
    const cred = await navigator.credentials.get({ publicKey: options });
    const d = await api("/api/webauthn/login/complete", "POST", {
      username: u, id: cred.id, rawId: bufToB64u(cred.rawId), type: cred.type,
      response: {
        clientDataJSON: bufToB64u(cred.response.clientDataJSON),
        authenticatorData: bufToB64u(cred.response.authenticatorData),
        signature: bufToB64u(cred.response.signature),
        userHandle: cred.response.userHandle ? bufToB64u(cred.response.userHandle) : null,
      },
    });
    saveAuth(d); showMain();
  } catch (e) { $("lg-msg").textContent = "Biometric login failed: " + e.message; }
};

$("btn-passkey").onclick = async () => {
  const msg = $("passkey-msg");
  msg.textContent = "Waiting for your device…";
  try {
    const options = await api("/api/webauthn/register/begin", "POST", {});
    options.challenge = b64uToBuf(options.challenge);
    options.user.id = b64uToBuf(options.user.id);
    (options.excludeCredentials || []).forEach((c) => (c.id = b64uToBuf(c.id)));
    const cred = await navigator.credentials.create({ publicKey: options });
    const r = await api("/api/webauthn/register/complete", "POST", {
      id: cred.id, rawId: bufToB64u(cred.rawId), type: cred.type,
      response: {
        clientDataJSON: bufToB64u(cred.response.clientDataJSON),
        attestationObject: bufToB64u(cred.response.attestationObject),
      },
    });
    msg.textContent = "✓ " + (r.message || "Passkey added.");
    listPasskeys();
  } catch (e) { msg.textContent = "✗ " + e.message; }
};

// W12 — list + remove registered passkeys
async function listPasskeys() {
  const box = $("passkey-list");
  if (!box) return;
  try {
    const r = await api("/api/webauthn/credentials", "GET");
    if (!r.credentials.length) { box.innerHTML = ""; return; }
    box.innerHTML = r.credentials.map((c) =>
      `<div class="flex items-center justify-between text-[.65rem] text-slate-500">`
      + `<span>🔑 ${c.short}…</span>`
      + `<button data-cid="${c.id}" class="pk-rm text-red-400 hover:text-red-300">remove</button>`
      + `</div>`).join("");
    box.querySelectorAll(".pk-rm").forEach((b) => {
      b.onclick = async () => {
        try { await api("/api/webauthn/credentials/" + b.dataset.cid, "DELETE"); listPasskeys(); }
        catch (e) { $("passkey-msg").textContent = "✗ " + e.message; }
      };
    });
  } catch (_) { /* not logged in / no passkeys */ }
}

/* ---------------- sessions / repos ---------------- */

async function refreshSessions() {
  try {
    const d = await api("/api/sessions");
    $("session-list").innerHTML = d.sessions.map((s) =>
      `<div class="group flex items-center gap-1 rounded px-2 py-1 hover:bg-yellow-900/20 ${s.id === state.sid ? "bg-yellow-900/30" : ""}">
         <span data-sid="${s.id}" class="session-item flex-1 cursor-pointer truncate ${s.id === state.sid ? "text-[var(--gold-bright)]" : "text-slate-300"}">
           ${esc(s.title)} <span class="text-slate-600">$${s.spent_usd}</span></span>
         ${s.status === "interrupted"
           ? `<button data-resume="${s.id}" class="session-resume text-amber-400 hover:text-amber-300 text-[.65rem] px-1 opacity-0 group-hover:opacity-100" title="Resume interrupted session">resume</button>`
           : ""}
         <button data-del="${s.id}" class="session-del text-slate-600 hover:text-red-400 opacity-0 group-hover:opacity-100" title="Delete session">✕</button>
       </div>`).join("")
      || '<div class="text-slate-600">none yet</div>';
    document.querySelectorAll(".session-item").forEach((el) =>
      (el.onclick = () => openSession(el.dataset.sid)));
    // N6: resume button for interrupted sessions
    document.querySelectorAll(".session-resume").forEach((el) => (el.onclick = async (e) => {
      e.stopPropagation();
      el.disabled = true; el.textContent = "…";
      try {
        await api(`/api/sessions/${el.dataset.resume}/resume`, "POST");
        openSession(el.dataset.resume);
      } catch (err) { alert("Resume failed: " + err.message); }
      finally { el.disabled = false; el.textContent = "resume"; }
      refreshSessions();
    }));
    document.querySelectorAll(".session-del").forEach((el) => (el.onclick = async (e) => {
      e.stopPropagation();
      if (!confirm("Delete this session and its history?")) return;
      try { await api(`/api/sessions/${el.dataset.del}`, "DELETE"); }
      catch (err) { alert(err.message); return; }
      if (state.sid === el.dataset.del) { state.sid = null; stopPolling(); $("stream").innerHTML = ""; $("hdr-title").textContent = "no session"; }
      refreshSessions();
    }));
  } catch (e) { /* ignore */ }
}

/* ---------------- saved plans (N7) ---------------- */

async function refreshSpecs() {
  const box = $("spec-list");
  if (!box) return;
  try {
    const d = await api("/api/specs");
    const specs = d.specs || [];
    if (!specs.length) {
      box.innerHTML = '<div class="text-slate-600">none yet</div>';
      return;
    }
    box.innerHTML = specs.map((s) =>
      `<div class="group flex items-center gap-1 rounded px-2 py-1 hover:bg-yellow-900/20">
         <span class="flex-1 truncate text-slate-300" title="${esc(s.slug)}">
           ${esc(s.title || s.slug)}
           <span class="text-slate-600 text-[.65rem]">[${esc((s.artifacts || []).join(","))}]</span>
         </span>
         <button data-slug="${esc(s.slug)}" data-title="${esc(s.title || s.slug)}"
           class="spec-exec gold-btn rounded px-2 py-0.5 text-[.65rem] opacity-0 group-hover:opacity-100"
           title="Execute this plan in a new default-mode session">&#9654; run</button>
       </div>`).join("");
    box.querySelectorAll(".spec-exec").forEach((btn) => {
      btn.onclick = async () => {
        const slug = btn.dataset.slug;
        btn.disabled = true;
        btn.textContent = "…";
        try {
          const d = await api(`/api/specs/${encodeURIComponent(slug)}/execute`, "POST",
            { title: `exec:${slug}` });
          await refreshSessions();
          openSession(d.id);
        } catch (e) {
          alert("Execute failed: " + e.message);
        } finally {
          btn.disabled = false;
          btn.textContent = "▶ run";
        }
      };
    });
  } catch (e) { /* ignore — not critical */ }
}

$("btn-refresh-specs").onclick = refreshSpecs;

async function refreshRepos() {
  try {
    const d = await api("/api/repos");
    $("repo-list").innerHTML = d.repos.map((r) =>
      `<div class="text-slate-400">📁 ${esc(r.name)} <span class="text-slate-600">${esc(r.branch)}${r.dirty ? " ●" : ""}</span></div>`).join("")
      || '<div class="text-slate-600">no repos cloned</div>';
  } catch (e) { /* ignore */ }
}

$("btn-new-session").onclick = async () => {
  const title = prompt("Session title (optional):") || "";
  const d = await api("/api/sessions", "POST", { title });
  await refreshSessions(); openSession(d.id);
};

$("btn-clone").onclick = async () => {
  const url = $("repo-url").value.trim();
  if (!url) return;
  $("btn-clone").textContent = "…";
  try { await api("/api/repos", "POST", { url }); $("repo-url").value = ""; refreshRepos(); }
  catch (e) { alert(e.message); }
  $("btn-clone").textContent = "clone";
};

function openSession(sid) {
  state.sid = sid; state.after = -1;
  $("stream").innerHTML = "";
  refreshSessions();
  startPolling(true);
}

/* ---------------- event stream ---------------- */

function agentTag(e) {
  return e.agent ? `<span class="text-[var(--gold-dark)]">[${esc(e.agent)}]</span> ` : "";
}

function renderEvent(e) {
  const div = document.createElement("div");
  switch (e.type) {
    case "user":
      div.className = "ev-user rounded px-3 py-2 ml-12";
      div.innerHTML = esc(e.text); break;
    case "text":
      div.className = "ev-text rounded px-3 py-2 mr-12";
      div.innerHTML = agentTag(e) + esc(e.text)
        .replace(/```([\s\S]*?)```/g, '<code class="block bg-black/50 rounded p-2 my-1 overflow-x-auto">$1</code>')
        .replace(/`([^`]+)`/g, '<code class="bg-black/50 px-1 rounded">$1</code>');
      break;
    case "tool":
      div.className = "ev-tool px-3";
      div.innerHTML = `${agentTag(e)}⚙ ${esc(e.name)} <span class="detail">${esc(e.detail)}</span>`;
      div.onclick = () => div.classList.toggle("open"); break;
    case "tool_result": {
      div.className = "ev-tool px-3" + (e.ok ? "" : " text-red-400");
      let trHtml = `${agentTag(e)}↳ ${e.ok ? "ok" : "FAIL"} <span class="detail">${esc(e.detail)}</span>`;
      if (e.diff) {
        // Render diff lines with +/- coloring in a collapsed monospace block.
        const diffLines = e.diff.split("\n").map((ln) => {
          const cls = ln.startsWith("+") && !ln.startsWith("+++")
            ? "diff-add" : ln.startsWith("-") && !ln.startsWith("---")
            ? "diff-del" : ln.startsWith("@@")
            ? "diff-hunk" : "";
          return `<span class="${cls}">${esc(ln)}</span>`;
        }).join("\n");
        trHtml += `<pre class="diff-block">${diffLines}</pre>`;
      }
      div.innerHTML = trHtml;
      div.onclick = () => div.classList.toggle("open"); break;
    }
    case "agent_start":
      div.className = "ev-agent px-3 py-1";
      div.innerHTML = `🐒 deployed <b>${esc(e.agent)}</b> <span class="text-slate-500">[${esc(e.tier)} · ${esc(e.model)}]</span> — ${esc(e.task)}`;
      break;
    case "agent_end":
      div.className = "ev-agent px-3 py-1 text-slate-400";
      div.innerHTML = `🐒 <b>${esc(e.agent)}</b> reported back`; break;
    case "cost":
      div.className = "ev-cost px-3";
      div.textContent = `${e.model} · ${e.in_tokens}→${e.out_tokens} tok · $${(e.usd).toFixed(4)}`;
      break;
    case "approval":
      div.className = "ev-approval rounded px-3 py-2";
      div.innerHTML =
        `<div class="text-[var(--gold-bright)] font-bold mb-1">⚠ APPROVAL REQUIRED</div>
         <code class="block bg-black/60 rounded p-2 mb-2 text-xs">${esc(e.command)}</code>
         <button class="gold-btn rounded px-3 py-1 text-xs" data-aid="${e.approval_id}" data-ok="1">APPROVE</button>
         <button class="rounded px-3 py-1 text-xs bg-red-900/70 hover:bg-red-800 ml-2" data-aid="${e.approval_id}" data-ok="0">DENY</button>`;
      div.querySelectorAll("button").forEach((b) => (b.onclick = async () => {
        await api(`/api/sessions/${state.sid}/approve`, "POST",
          { approval_id: b.dataset.aid, approve: b.dataset.ok === "1" });
        div.querySelectorAll("button").forEach((x) => (x.disabled = true));
        div.style.opacity = 0.5;
      }));
      break;
    case "approval_result":
      div.className = "ev-tool px-3";
      div.textContent = e.approved ? "✓ approved" : "✗ denied"; break;
    case "error":
      div.className = "ev-err rounded px-3 py-2";
      div.innerHTML = agentTag(e) + esc(e.message); break;
    case "done":
      div.className = "ev-cost px-3"; div.textContent = "— done —"; break;
    default: return null;
  }
  return div;
}

let _pollInflight = false;
async function poll() {
  // In-flight guard: an overlapping tick would re-fetch the same `after`
  // cursor and render every returned event a second time.
  if (!state.sid || _pollInflight) return;
  _pollInflight = true;
  try {
    const d = await api(`/api/sessions/${state.sid}/events?after=${state.after}`);
    const stream = $("stream");
    const atBottom = stream.scrollHeight - stream.scrollTop - stream.clientHeight < 60;
    for (const e of d.events) {
      const el = renderEvent(e);
      if (el) stream.appendChild(el);
      state.after = e.i;
    }
    if (d.events.length && atBottom) stream.scrollTop = stream.scrollHeight;
    state.status = d.status;
    $("hdr-dot").className = "dot " + d.status;
    $("hdr-status").textContent = d.status;
    $("hdr-spend").textContent = `$${d.spent_usd} / session`;
    const sess = document.querySelector(`[data-sid="${state.sid}"]`);
    $("hdr-title").textContent = sess ? sess.textContent.split("$")[0].trim() : state.sid;
    $("btn-stop").classList.toggle("hidden", d.status === "idle");
    setPollSpeed(d.status !== "idle");   // cadence only — must NOT fork a poll
  } catch (e) { /* transient */
  } finally { _pollInflight = false; }
}

// THE DUPLICATE-SEND-DISPLAY BUG LIVED HERE: poll() used to end by calling
// startPolling, whose immediate poll() call made every chain
// self-perpetuating — and stopPolling() only clears the interval, never an
// in-flight chain. So each send()/openSession() forked one more immortal
// poller; after N sends, N concurrent pollers fetched the same `after`
// cursor and each rendered the new events → the Nth message (and its
// model/tool/cost events) appeared N times. Now there is exactly one
// interval, re-created only when the cadence changes, and poll() never
// schedules itself.
function setPollSpeed(fast) {
  const ms = fast ? 1500 : 6000;
  if (state.timer && state.pollMs === ms) return;
  stopPolling();
  state.pollMs = ms;
  state.timer = setInterval(poll, ms);
}
function startPolling(fast) { setPollSpeed(fast); poll(); }
function stopPolling() { if (state.timer) clearInterval(state.timer); state.timer = null; state.pollMs = 0; }

/* ---------------- composer ---------------- */

function renderChips() {
  $("file-chips").innerHTML = state.files.map((f, i) =>
    `<span class="gold-border rounded px-2 py-0.5 text-[.65rem] text-slate-300">${esc(f.name)}
       <button data-i="${i}" class="text-red-400 ml-1">✕</button></span>`).join("");
  document.querySelectorAll("#file-chips button").forEach((b) =>
    (b.onclick = () => { state.files.splice(+b.dataset.i, 1); renderChips(); }));
}

let _pasteSeq = 0;
function extFor(type) {
  return ({ "image/png": "png", "image/jpeg": "jpg", "image/gif": "gif",
            "image/webp": "webp", "image/svg+xml": "svg" })[type] || "bin";
}
// Add a File/Blob to the composer attachments (base64), reused by picker, paste, drop.
function addFile(f) {
  if (!f) return;
  const name = f.name || `pasted-${++_pasteSeq}.${extFor(f.type)}`;
  const reader = new FileReader();
  reader.onload = () => {
    state.files.push({ name, content_b64: reader.result.split(",", 2)[1] || "" });
    renderChips();
  };
  reader.readAsDataURL(f);
}

$("btn-attach").onclick = () => $("file-input").click();
$("file-input").onchange = () => {
  for (const f of $("file-input").files) addFile(f);
  $("file-input").value = "";
};

// Paste images/files straight from the clipboard into the prompt box.
$("msg").addEventListener("paste", (e) => {
  const items = (e.clipboardData || {}).items || [];
  let took = 0;
  for (const it of items) {
    if (it.kind === "file") { addFile(it.getAsFile()); took++; }
  }
  // text falls through to the default paste; only images are intercepted
  if (took) e.preventDefault();
});

// Drag-and-drop files anywhere on the composer.
const _composer = document.getElementById("composer") || $("msg");
["dragover", "dragenter"].forEach((ev) => _composer.addEventListener(ev, (e) => {
  e.preventDefault(); _composer.classList.add("drop-active");
}));
["dragleave", "drop"].forEach((ev) => _composer.addEventListener(ev, (e) => {
  e.preventDefault(); _composer.classList.remove("drop-active");
}));
_composer.addEventListener("drop", (e) => {
  for (const f of (e.dataTransfer || {}).files || []) addFile(f);
});

let _sendInflight = false;
async function send() {
  // In-flight submit guard (defense in depth): one submission at a time —
  // Enter mashing / double-clicks can't fire a second POST (= a second real
  // model call) while the first is on the wire.
  if (_sendInflight) return;
  const text = $("msg").value.trim();
  if (!text) return;
  _sendInflight = true;
  $("btn-send").disabled = true;
  try {
    if (!state.sid) {
      const d = await api("/api/sessions", "POST", { title: text.slice(0, 40) });
      state.sid = d.id; state.after = -1; $("stream").innerHTML = ""; refreshSessions();
    }
    await api(`/api/sessions/${state.sid}/message`, "POST",
      { text, files: state.files, mode: state.mode });
    $("msg").value = ""; state.files = []; renderChips();
    startPolling(true);
  } catch (e) { alert(e.message);
  } finally { _sendInflight = false; $("btn-send").disabled = false; }
}

/* ---------------- mode selector ---------------- */

function renderMode() {
  document.querySelectorAll(".mode-btn").forEach((b) => {
    const on = b.dataset.mode === state.mode;
    b.classList.toggle("gold-btn", on);
    b.classList.toggle("text-slate-400", !on);
  });
  $("mode-hint").textContent = MODE_HINTS[state.mode] || "";
}
document.querySelectorAll(".mode-btn").forEach((b) => (b.onclick = () => {
  state.mode = b.dataset.mode;
  localStorage.setItem("cm_mode", state.mode);
  renderMode();
}));
renderMode();

/* ---------------- settings dropdown ---------------- */
function setSettingsOpen(open) {
  $("settings-menu").classList.toggle("hidden", !open);
  $("settings-caret").textContent = open ? "▾" : "▸";
}
$("btn-settings").onclick = (e) => {
  e.stopPropagation();
  setSettingsOpen($("settings-menu").classList.contains("hidden"));
};
// Clicking a menu item that opens a modal (or the swarm link) collapses the menu;
// the passkey button keeps it open so its inline status message stays visible.
$("settings-menu").addEventListener("click", (e) => {
  const t = e.target.closest("a, button");
  if (t && t.id !== "btn-passkey") setSettingsOpen(false);
});
// Click outside the settings area closes it.
document.addEventListener("click", (e) => {
  if ($("settings-menu").classList.contains("hidden")) return;
  if (!e.target.closest("#btn-settings") && !e.target.closest("#settings-menu"))
    setSettingsOpen(false);
});

$("btn-send").onclick = send;
$("msg").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); }
});
$("btn-stop").onclick = () => api(`/api/sessions/${state.sid}/stop`, "POST", {});

/* ---------------- voice (free, Chrome Web Speech API) ---------------- */

const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
if (!SR) { $("btn-mic").style.display = "none"; }
else {
  let rec = null;
  $("btn-mic").onclick = () => {
    if (rec) { rec.stop(); return; }
    rec = new SR();
    rec.lang = "en-US"; rec.interimResults = true; rec.continuous = false;
    const base = $("msg").value;
    rec.onresult = (ev) => {
      let final = "", interim = "";
      for (const r of ev.results) (r.isFinal ? (final += r[0].transcript) : (interim += r[0].transcript));
      $("msg").value = (base + " " + final + interim).trim();
    };
    rec.onend = () => { rec = null; $("btn-mic").classList.remove("bg-yellow-900/40"); };
    rec.onerror = rec.onend;
    $("btn-mic").classList.add("bg-yellow-900/40");
    rec.start();
  };
}

/* ---------------- models modal ---------------- */

$("btn-models").onclick = () => {
  $("modal-models").classList.remove("hidden");
  // Restore persisted auto-add preference
  const chk = $("chk-auto-add-free");
  if (chk) {
    chk.checked = localStorage.getItem("cm_auto_add_free") === "1";
    chk.onchange = () => localStorage.setItem("cm_auto_add_free", chk.checked ? "1" : "0");
  }
  loadProviders();
};
$("modal-close").onclick = () => $("modal-models").classList.add("hidden");

// Track which provider rows are expanded (session-only; collapses reset on modal close)
const _pvExpanded = new Set();
// Current sort order for provider list: "keyed" | "cost" | "name" | "used"
let _pvSort = "keyed";
// Last-used timestamps per provider id (localStorage-backed)
const _pvLastUsed = JSON.parse(localStorage.getItem("cm_pv_last_used") || "{}");
const _pvSaveLastUsed = () => localStorage.setItem("cm_pv_last_used", JSON.stringify(_pvLastUsed));
// Favorite model IDs, stored as "{pid}:{mid}" strings (localStorage-backed)
const _pvFavorites = new Set(JSON.parse(localStorage.getItem("cm_pv_favorites") || "[]"));
const _pvSaveFavorites = () => localStorage.setItem("cm_pv_favorites", JSON.stringify([..._pvFavorites]));
// Active provider filter: "" | "free" | "keyed" | "auto"
let _pvFilter = "";

// Keyboard shortcuts for the models modal
document.addEventListener("keydown", (e) => {
  const modalOpen = !$("modal-models")?.classList.contains("hidden");
  if (e.key === "Escape" && modalOpen) {
    $("modal-models").classList.add("hidden");
    return;
  }
  if (!modalOpen) return;
  // Don't fire when user is typing in an input
  if (["INPUT","TEXTAREA","SELECT"].includes(e.target.tagName)) return;
  if (e.key === "r") $("btn-or-refresh")?.click();
  if (e.key === "a" && !$("btn-add-all-free")?.classList.contains("hidden")) $("btn-add-all-free")?.click();
});

async function loadProviders() {
  const d = await api("/api/models");
  $("auto-cheapest").checked = !!d.auto_cheapest;
  // Auto-expand the selected/main provider on first load; don't collapse manually-opened rows
  if (_pvExpanded.size === 0 && d.selected && d.selected !== "auto") {
    _pvExpanded.add(d.selected);
  } else if (_pvExpanded.size === 0) {
    // auto mode: expand the cheapest auto-flagged provider
    const autoP = d.providers.find((p) => p.auto && p.has_key);
    if (autoP) _pvExpanded.add(autoP.id);
  }
  // Compute client-side tier labels (mirrors provider_for_tier logic: sort by out cost)
  // callable = keyed+auto providers sorted by cost; cascadeOrder = 1-based call order
  const callable = d.providers.filter((p) => p.has_key).sort((a, b) => a.out - b.out);
  const cascadeOrder = {};
  callable.filter((p) => p.auto).forEach((p, i) => { cascadeOrder[p.id] = i + 1; });
  const n = callable.length;
  const _tierOf = (pid) => {
    const idx = callable.findIndex((p) => p.id === pid);
    if (idx < 0) return null;
    if (idx === 0) return "t0";
    if (idx === n - 1) return "t3";
    if (idx <= Math.floor(n / 3)) return "t1";
    return "t2";
  };

  // Apply active filter then sort
  const filteredProviders = _pvFilter === "free"
    // filter by active models list, not catalog — shows providers you can use free RIGHT NOW
    ? d.providers.filter((p) => (p.models || []).some((m) => { const c = (p.catalog || {})[m]; return c && c.in === 0 && c.out === 0; }))
    : _pvFilter === "keyed"
    ? d.providers.filter((p) => p.has_key)
    : _pvFilter === "auto"
    ? d.providers.filter((p) => p.auto)
    : d.providers;
  const sortedProviders = [...filteredProviders].sort((a, b) => {
    if (_pvSort === "cost") return a.out - b.out;
    if (_pvSort === "name") return a.label.localeCompare(b.label);
    if (_pvSort === "used") {
      const ta = _pvLastUsed[a.id] || 0, tb = _pvLastUsed[b.id] || 0;
      return tb - ta; // most-recently-used first
    }
    // "keyed": keyed first, then by cost
    if (a.has_key !== b.has_key) return a.has_key ? -1 : 1;
    return a.out - b.out;
  });

  $("provider-rows").innerHTML = sortedProviders.map((p) => {
    const allModels = p.models || [];
    const cat = p.catalog || {};
    const _costHint = (m) => {
      const c = cat[m]; if (!c) return "";
      if (c.in === 0 && c.out === 0) return " ⚡free";
      return ` $${c.in}/$${c.out}/M`;
    };
    const _isFree = (m) => { const c = cat[m]; return c && c.in === 0 && c.out === 0; };
    const _isFav = (m) => _pvFavorites.has(`${p.id}:${m}`);
    const sortedModels = [...allModels].sort((a, b) => {
      if (_isFav(a) !== _isFav(b)) return _isFav(a) ? -1 : 1;
      if (_isFree(a) !== _isFree(b)) return _isFree(a) ? -1 : 1;
      return a.localeCompare(b);
    });
    const activeModel = (d.auto_cheapest || d.selected === p.id) ? p.model : null;
    const opts = sortedModels.map((m) =>
      `<option value="${esc(m)}" ${m === p.model ? "selected" : ""}>${m === activeModel ? "★ " : ""}${esc(m)}${_costHint(m)}</option>`).join("");
    const isMain = p.id === d.selected && !d.auto_cheapest;
    const manyModels = allModels.length > 5;
    const expanded = _pvExpanded.has(p.id);
    const now = Math.floor(Date.now() / 1000);
    const errAge = p.last_error_at ? now - p.last_error_at : null;
    const dotColor = !p.last_error_at
      ? (p.has_key ? "text-green-400" : "text-slate-600")
      : (errAge < 3600 ? "text-red-400" : "text-yellow-500");
    const dotTitle = p.last_error
      ? `Error ${errAge < 60 ? "just now" : errAge < 3600 ? Math.round(errAge/60)+"m ago" : Math.round(errAge/3600)+"h ago"}: ${p.last_error}`
      : (p.has_key
          ? (p.id === "openrouter"
              ? `key set ${p.key_hint} — authenticated (higher rate limits)`
              : `key set ${p.key_hint}`)
          : (p.id === "openrouter" ? "no key — unauthenticated (rate-limited free tier)" : "no key"));
    const catAge = p.catalog_refreshed_at ? now - p.catalog_refreshed_at : null;
    const catAgeStr = catAge === null ? null
      : catAge < 60 ? "just now"
      : catAge < 3600 ? Math.round(catAge/60)+"m ago"
      : catAge < 86400 ? Math.round(catAge/3600)+"h ago"
      : Math.round(catAge/86400)+"d ago";
    return `
    <div class="border-b border-slate-800/60 py-2 ${isMain ? "bg-yellow-900/10 rounded" : ""} ${!p.has_key ? "opacity-50" : ""}">
      <div class="flex items-center gap-2">
        <button data-id="${esc(p.id)}" class="pv-toggle text-slate-500 hover:text-slate-300 text-xs w-4"
          title="${expanded ? "Collapse" : "Expand"}">${expanded ? "▼" : "▶"}</button>
        <button data-id="${esc(p.id)}" class="pv-main ${isMain ? "text-[var(--gold-bright)]" : "text-slate-600"} hover:text-[var(--gold)]" title="Use as main (when Auto is off)">★</button>
        <span class="${dotColor}" title="${esc(dotTitle)}">●</span>
        <b class="pv-label-edit ${isMain ? "text-[var(--gold-bright)]" : "text-slate-200"}" data-id="${esc(p.id)}"
          title="${p.notes ? esc(p.notes) : "Double-click to rename"}">${esc(p.label)}</b>
        ${allModels.length > 0 ? `<span class="text-slate-600 text-xs">(${allModels.length})</span>` : ""}
        <span class="flex-1"></span>
        ${(() => { const t = _tierOf(p.id); return t
          ? `<span class="text-[.6rem] px-1 rounded border ${
              t === "t0" ? "text-green-400 border-green-900/40" :
              t === "t1" ? "text-blue-400 border-blue-900/40" :
              t === "t2" ? "text-yellow-500 border-yellow-900/40" :
                           "text-red-400 border-red-900/40"
            }" title="Tier ${t} — position in cheapest-first routing">${t}</span>`
          : ""; })()}
        <span class="text-slate-600 text-xs">${p.model ? esc(p.model) : ""}</span>
        ${d.auto_cheapest && cascadeOrder[p.id]
          ? `<span class="text-[.6rem] text-slate-500 border border-slate-700 rounded px-1"
              title="Auto-cheapest call order">#${cascadeOrder[p.id]}</span>` : ""}
        <label class="flex items-center gap-1 text-slate-400" title="Include in cheapest-first cascade">
          <input type="checkbox" class="pv-auto accent-yellow-500" data-id="${esc(p.id)}" ${p.auto ? "checked" : ""}>✓auto</label>
        <button data-id="${esc(p.id)}" class="pv-del text-red-500/60 hover:text-red-400">remove</button>
      </div>
      ${p.last_error ? `<div class="pl-6 mt-0.5 text-red-400/80 text-xs truncate" title="${esc(p.last_error)}">⚠ ${esc(p.last_error.slice(0, 80))}${p.last_error.length > 80 ? "…" : ""}</div>` : ""}
      ${p.has_key && allModels.length === 0 ? `<div class="pl-6 mt-0.5 text-yellow-500/80 text-xs">⚠ No models configured — expand and add at least one model ID</div>` : ""}
      <div class="pv-detail flex items-center gap-2 mt-1 pl-6 ${expanded ? "" : "hidden"}">
        ${manyModels ? `<input type="text" class="pv-filter input rounded px-1 py-0.5 w-28 text-xs" data-id="${esc(p.id)}"
          data-models="${esc(JSON.stringify(sortedModels))}" data-current="${esc(p.model)}"
          placeholder="filter…" title="Filter models">` : ""}
        <select class="pv-model input rounded px-1 py-0.5 flex-1" data-id="${esc(p.id)}">${opts}</select>
        <input type="password" class="pv-key input rounded px-1 py-0.5 flex-1" data-id="${esc(p.id)}"
          placeholder="${p.has_key ? "key set ✓ (type to replace)" : "paste API key"}">
        <input type="text" class="pv-notes input rounded px-1 py-0.5 w-32 text-xs" data-id="${esc(p.id)}"
          placeholder="notes…" value="${esc(p.notes || "")}" title="Freeform notes (shown as label tooltip)">
        <button data-id="${esc(p.id)}" class="pv-savekey gold-btn rounded px-2 py-0.5">save</button>
        <span class="text-slate-600">$${p.out}/M</span>
        ${catAgeStr ? `<span class="text-slate-600 text-xs" title="Catalog last fetched">↻ ${esc(catAgeStr)}</span>` : ""}
      </div>
      <div class="pv-detail flex flex-wrap items-center gap-1 mt-1 pl-6 ${expanded ? "" : "hidden"}">
        ${allModels.length >= 2 ? allModels.map((m) => {
          const mc = cat[m];
          const pillTag = mc
            ? (mc.in === 0 && mc.out === 0
                ? `<span class="text-green-400 text-[.6rem]">⚡</span>`
                : `<span class="text-slate-500 text-[.6rem]">$${mc.out}/M</span>`)
            : "";
          const fav = _isFav(m);
          return `<span class="inline-flex items-center gap-0.5 bg-slate-800 rounded px-1 text-xs text-slate-400">${esc(m)}${pillTag}`
            + `<button class="pv-fav ${fav ? "text-yellow-400" : "text-slate-600/60"} hover:text-yellow-400 ml-0.5" data-pid="${esc(p.id)}" data-mid="${esc(m)}" title="${fav ? "Unpin" : "Pin to top"}">★</button>`
            + `<button class="pv-cpmodel text-slate-500/60 hover:text-slate-300 ml-0.5" data-mid="${esc(m)}" title="Copy model ID">⎘</button>`
            + `<button class="pv-rmmodel text-red-500/50 hover:text-red-400 ml-0.5" data-pid="${esc(p.id)}" data-mid="${esc(m)}" title="Remove model">×</button></span>`;
        }).join("") : ""}
        <input type="text" class="pv-addmodel input rounded px-1 py-0.5 text-xs w-44" data-id="${esc(p.id)}"
          placeholder="+ add model id…">
        <button class="pv-addmodel-btn text-slate-500 hover:text-[var(--gold)] text-xs border border-slate-700 rounded px-2 py-0.5" data-id="${esc(p.id)}">add</button>
        <span class="pv-addmodel-msg text-xs text-slate-600" data-id="${esc(p.id)}"></span>
        ${allModels.length >= 2
          ? `<button class="pv-cplist text-slate-500/60 hover:text-slate-300 text-xs ml-auto" data-pid="${esc(p.id)}" data-models="${esc(JSON.stringify(allModels))}" title="Copy all model IDs as newline-separated list">⎘ list</button>`
          : ""}
      </div>
    </div>`;
  }).join("");

  document.querySelectorAll(".pv-toggle").forEach((b) => (b.onclick = () => {
    const id = b.dataset.id;
    if (_pvExpanded.has(id)) _pvExpanded.delete(id); else _pvExpanded.add(id);
    const row = b.closest("div[class*='border-b']");
    row.querySelectorAll(".pv-detail").forEach((el) => el.classList.toggle("hidden"));
    b.textContent = _pvExpanded.has(id) ? "▼" : "▶";
    b.title = _pvExpanded.has(id) ? "Collapse" : "Expand";
  }));
  document.querySelectorAll(".pv-main").forEach((b) => (b.onclick = async () => {
    await api("/api/models/select", "POST", { id: b.dataset.id });
    await api("/api/models/settings", "POST", { auto_cheapest: false });
    // Record last-used timestamp for sort-by-used
    _pvLastUsed[b.dataset.id] = Math.floor(Date.now() / 1000);
    _pvSaveLastUsed();
    loadProviders();
  }));
  document.querySelectorAll(".pv-del").forEach((b) => (b.onclick = async () => {
    const pDel = d.providers.find((x) => x.id === b.dataset.id);
    const warn = pDel?.has_key ? `\n⚠ This provider has a key stored — it will be deleted too.` : "";
    if (confirm(`Remove provider ${b.dataset.id}?${warn}`)) {
      await api(`/api/models/${encodeURIComponent(b.dataset.id)}`, "DELETE"); loadProviders();
    }
  }));
  document.querySelectorAll(".pv-savekey").forEach((b) => (b.onclick = async () => {
    const id = b.dataset.id;
    const prov = d.providers.find((x) => x.id === id);
    const key = document.querySelector(`.pv-key[data-id="${id}"]`).value;
    const model = document.querySelector(`.pv-model[data-id="${id}"]`).value;
    const auto = document.querySelector(`.pv-auto[data-id="${id}"]`).checked;
    const notes = document.querySelector(`.pv-notes[data-id="${id}"]`)?.value || "";
    try {
      await api("/api/models", "POST", {
        id, label: prov.label, kind: prov.kind, base_url: prov.base_url,
        model, models: prov.models, key, notes,
        input_cost_per_m: prov.in, output_cost_per_m: prov.out, auto,
      });
      // auto-collapse the row after a successful key save; auto-refresh OR catalog
      if (key) {
        _pvExpanded.delete(id);
        if (id === "openrouter") setTimeout(() => $("btn-or-refresh")?.click(), 400);
      }
      loadProviders();
    } catch (e) { alert(e.message); }
  }));
<<<<<<< Updated upstream
=======
  // copy full model list to clipboard
  document.querySelectorAll(".pv-cplist").forEach((btn) => (btn.onclick = () => {
    const models = JSON.parse(btn.dataset.models);
    navigator.clipboard?.writeText(models.join("\n")).then(() => {
      const orig = btn.textContent;
      btn.textContent = "✓";
      setTimeout(() => { btn.textContent = orig; }, 1400);
    });
  }));
  // set model as active via pill click
  document.querySelectorAll(".pv-setmodel").forEach((btn) => (btn.onclick = async () => {
    const { pid, mid } = btn.dataset;
    const prov = d.providers.find((x) => x.id === pid);
    if (!prov) return;
    try {
      await api("/api/models", "POST", {
        id: prov.id, label: prov.label, kind: prov.kind, base_url: prov.base_url,
        model: mid, models: prov.models, key: "", notes: prov.notes || "",
        input_cost_per_m: prov.in, output_cost_per_m: prov.out, auto: prov.auto,
      });
      loadProviders();
    } catch (e) { alert(e.message); }
  }));
>>>>>>> Stashed changes
  // copy model ID to clipboard
  document.querySelectorAll(".pv-cpmodel").forEach((btn) => (btn.onclick = () => {
    navigator.clipboard?.writeText(btn.dataset.mid).then(() => {
      const orig = btn.textContent;
      btn.textContent = "✓";
      setTimeout(() => { btn.textContent = orig; }, 1200);
    });
  }));
  // inline remove-model handler
  document.querySelectorAll(".pv-rmmodel").forEach((btn) => (btn.onclick = async () => {
    const { pid, mid } = btn.dataset;
    if (!confirm(`Remove model ${mid} from ${pid}?`)) return;
    try {
      await api(`/api/models/${encodeURIComponent(pid)}/models/${encodeURIComponent(mid)}`, "DELETE");
      loadProviders();
    } catch (e) { alert(e.message); }
  }));
  // inline add-model handler
  document.querySelectorAll(".pv-addmodel-btn").forEach((btn) => (btn.onclick = async () => {
    const id = btn.dataset.id;
    const input = document.querySelector(`.pv-addmodel[data-id="${id}"]`);
    const msg = document.querySelector(`.pv-addmodel-msg[data-id="${id}"]`);
    const newModel = input.value.trim();
    if (!newModel) return;
    const prov = d.providers.find((x) => x.id === id);
    if (!prov) return;
    const updatedModels = [...new Set([...(prov.models || []), newModel])];
    try {
      await api("/api/models", "POST", {
        id, label: prov.label, kind: prov.kind, base_url: prov.base_url,
        model: prov.model, models: updatedModels,
        input_cost_per_m: prov.in, output_cost_per_m: prov.out, auto: prov.auto,
      });
      input.value = "";
      msg.textContent = "✓";
      setTimeout(() => { msg.textContent = ""; }, 2000);
      loadProviders();
    } catch (e) { msg.textContent = e.message; }
  }));
  document.querySelectorAll(".pv-addmodel").forEach((el) => (el.onkeydown = (e) => {
    if (e.key === "Enter") document.querySelector(`.pv-addmodel-btn[data-id="${el.dataset.id}"]`).click();
  }));
  // model dropdown / auto checkbox auto-save on change
  document.querySelectorAll(".pv-model, .pv-auto").forEach((el) => (el.onchange = () => {
    document.querySelector(`.pv-savekey[data-id="${el.dataset.id}"]`).click();
  }));
  // model filter: rebuilds dropdown options on each keystroke
  document.querySelectorAll(".pv-filter").forEach((input) => {
    input.oninput = () => {
      const q = input.value.toLowerCase();
      const allModels = JSON.parse(input.dataset.models);
      const current = input.dataset.current;
      const sel = document.querySelector(`.pv-model[data-id="${input.dataset.id}"]`);
      const filtered = q ? allModels.filter((m) => m.toLowerCase().includes(q)) : allModels;
      sel.innerHTML = filtered.map((m) =>
        `<option value="${esc(m)}" ${m === current ? "selected" : ""}>${esc(m)}</option>`
      ).join("");
    };
  });
  // Collapse-all / expand-all
  const _setAllExpanded = (expand) => {
    document.querySelectorAll(".pv-toggle").forEach((b) => {
      const id = b.dataset.id;
      if (expand) _pvExpanded.add(id); else _pvExpanded.delete(id);
      b.closest("div[class*='border-b']")?.querySelectorAll(".pv-detail")
        .forEach((el) => el.classList.toggle("hidden", !expand));
      b.textContent = expand ? "▼" : "▶";
      b.title = expand ? "Collapse" : "Expand";
    });
  };
  if ($("btn-collapse-all")) $("btn-collapse-all").onclick = () => _setAllExpanded(false);
  if ($("btn-expand-all")) $("btn-expand-all").onclick = () => _setAllExpanded(true);

  // Sort toggle buttons (keyed / cost / A-Z / used)
  ["keyed", "cost", "name", "used"].forEach((mode) => {
    const btn = $(`btn-sort-${mode}`);
    if (!btn) return;
    btn.className = `text-xs border rounded px-2 py-0.5 ${
      _pvSort === mode
        ? "border-[var(--gold)] text-[var(--gold-bright)]"
        : "border-slate-700 text-slate-500 hover:text-slate-300"
    }`;
    btn.onclick = () => { _pvSort = mode; loadProviders(); };
  });

  // Quick-filter buttons
  ["", "free", "keyed", "auto"].forEach((f) => {
    const btn = $(`btn-filter-${f || "all"}`);
    if (!btn) return;
    btn.className = `text-xs border rounded px-2 py-0.5 ${
      _pvFilter === f
        ? "border-cyan-600 text-cyan-300"
        : "border-slate-700 text-slate-500 hover:text-slate-300"
    }`;
    btn.onclick = () => { _pvFilter = f; loadProviders(); };
  });

  // Favorite model toggle
  document.querySelectorAll(".pv-fav").forEach((btn) => (btn.onclick = () => {
    const key = `${btn.dataset.pid}:${btn.dataset.mid}`;
    if (_pvFavorites.has(key)) _pvFavorites.delete(key); else _pvFavorites.add(key);
    _pvSaveFavorites();
    loadProviders();
  }));

  // Global model search: show only rows whose label or model IDs match
  const searchInput = $("provider-search");
  if (searchInput) {
    const applySearch = () => {
      const q = searchInput.value.toLowerCase();
      document.querySelectorAll("#provider-rows > div").forEach((row, i) => {
        if (!q) { row.style.display = ""; return; }
        const p = sortedProviders[i];
        if (!p) { row.style.display = ""; return; }
        const haystack = [p.label, p.id, ...(p.models || [])].join(" ").toLowerCase();
        row.style.display = haystack.includes(q) ? "" : "none";
      });
    };
    searchInput.oninput = applySearch;
    applySearch(); // apply on re-render if search text persists
  }

  // Provider label inline rename: double-click the <b> label to edit
  document.querySelectorAll(".pv-label-edit").forEach((b) => {
    b.ondblclick = async () => {
      const id = b.dataset.id;
      const newLabel = prompt("Rename provider:", b.textContent.trim());
      if (!newLabel || newLabel === b.textContent.trim()) return;
      const cfg = await api("/api/models");
      const p = cfg.providers.find((x) => x.id === id);
      if (!p) return;
      await api("/api/models", "POST", {
        id: p.id, label: newLabel.trim(), kind: p.kind,
        base_url: p.base_url, model: p.model,
        models: p.models, key: "", notes: p.notes || "",
        input_cost_per_m: p.in, output_cost_per_m: p.out, auto: p.auto,
      });
      loadProviders();
    };
  });

  // Duplicate model ID warning
  const _allModelIds = d.providers.flatMap((p) => (p.models || []).map((m) => ({ m, pid: p.id })));
  const _midCounts = {};
  _allModelIds.forEach(({ m }) => { _midCounts[m] = (_midCounts[m] || 0) + 1; });
  const _dupes = Object.keys(_midCounts).filter((m) => _midCounts[m] > 1);
  let _dupWarn = $("dup-model-warn");
  if (!_dupWarn) {
    _dupWarn = document.createElement("p");
    _dupWarn.id = "dup-model-warn";
    _dupWarn.className = "text-xs text-yellow-500 mb-2";
    $("provider-rows").after(_dupWarn);
  }
  _dupWarn.textContent = _dupes.length
    ? `⚠ Duplicate model IDs across providers: ${_dupes.slice(0, 3).join(", ")}${_dupes.length > 3 ? " …" : ""}`
    : "";

  // Populate bulk-add provider selector
  const bulkPid = $("bulk-add-pid");
  if (bulkPid) {
    const prev = bulkPid.value;
    bulkPid.innerHTML = d.providers.map((p) =>
      `<option value="${esc(p.id)}" ${p.id === prev ? "selected" : ""}>${esc(p.label)}</option>`
    ).join("");
  }

  // Pass OR catalog data as a hint to loadFreeModels to skip the extra API call
  const orProv = d.providers.find((p) => p.id === "openrouter");
  const freeCount = orProv
    ? Object.values(orProv.catalog || {}).filter((c) => c.in === 0 && c.out === 0).length
    : 0;
  // Update sidebar badge with pulse when free models are available
  const btnModels = $("btn-models");
  if (btnModels) {
    const freeSpan = freeCount > 0
      ? `<span class="text-green-400 text-[.65rem] free-pulse">⚡${freeCount}</span>`
      : "";
    btnModels.innerHTML = freeCount > 0
      ? `⚙ Models &amp; keys ${freeSpan}`
      : "⚙ Models &amp; keys";
  }
  if (orProv) {
    const catalogEntries = Object.entries(orProv.catalog || {});
    const freeHint = {
      free: catalogEntries.filter(([, c]) => c.in === 0 && c.out === 0).map(([id]) => ({ id })),
      refreshed_at: orProv.catalog_refreshed_at || null,
      totalInCatalog: catalogEntries.length,
    };
    loadFreeModels(freeHint);
  } else {
    loadFreeModels();
  }
}

$("auto-cheapest").onchange = async () => {
  await api("/api/models/settings", "POST", { auto_cheapest: $("auto-cheapest").checked });
  loadProviders();
};

/* ---------------- free-model auto-lister (Layer A) ---------------- */

function _catalogAge(refreshed_at) {
  if (!refreshed_at) return null;
  const secs = Math.floor(Date.now() / 1000) - refreshed_at;
  if (secs < 60) return `${secs}s ago`;
  if (secs < 3600) return `${Math.floor(secs / 60)}m ago`;
  if (secs < 86400) return `${Math.floor(secs / 3600)}h ago`;
  return `${Math.floor(secs / 86400)}d ago`;
}

async function loadFreeModels(hint) {
  // hint: optional {free, refreshed_at} pre-fetched from GET /api/models to save a round-trip
  try {
    const r = hint || await api("/api/models/openrouter/free");
    const free = r.free || [];
    const age = _catalogAge(r.refreshed_at);
    const stale = r.refreshed_at && (Date.now() / 1000 - r.refreshed_at) > 86400;
    if (age && !$("free-models-msg").textContent.startsWith("✓")) {
      const totalInCatalog = hint?.totalInCatalog ?? null;
      const countStr = totalInCatalog !== null ? ` · ${totalInCatalog} total` : "";
      $("free-models-msg").textContent = stale ? `⚠ catalog ${age}${countStr}` : `catalog ${age}${countStr}`;
      if (stale) $("free-models-msg").classList.add("text-yellow-500");
      else $("free-models-msg").classList.remove("text-yellow-500");
    }
    if (!free.length && !r.refreshed_at) {
      // No catalog yet — auto-trigger a background refresh on first open
      $("free-models-list").innerHTML = `<span class="not-italic">Fetching free models…</span>`;
      $("btn-or-refresh").click();
      return;
    }
    if (!free.length) {
      $("free-models-list").innerHTML = `<span class="not-italic">No free models cached — click ↻ Refresh.</span>`;
      $("btn-add-all-free").classList.add("hidden");
      return;
    }
    $("free-models-list").innerHTML = free.map((m) =>
      `<button class="free-pill inline-flex items-center gap-1 bg-green-900/20 text-green-400 border border-green-900/40 rounded px-1 mr-1 mb-1 hover:border-green-400/60" data-id="${esc(m.id)}" title="Click to copy model ID">`
      + `<span class="not-italic text-xs">${esc(m.id)}</span>`
      + `<span class="text-green-700 text-[.6rem]">⎘</span></button>`
    ).join("");
    $("free-models-list").querySelectorAll(".free-pill").forEach((btn) => (btn.onclick = () => {
      navigator.clipboard.writeText(btn.dataset.id).then(() => {
        const orig = btn.querySelector("span:last-child").textContent;
        btn.querySelector("span:last-child").textContent = "✓";
        setTimeout(() => { btn.querySelector("span:last-child").textContent = orig; }, 1200);
      });
    }));
    $("btn-add-all-free").classList.remove("hidden");
    // Show/hide "use cheapest" and "Remove :free" based on current OR config
    try {
      const cfg = await api("/api/models");
      const or = cfg.providers.find((p) => p.id === "openrouter");
      const hasFreeTagged = or && (or.models || []).some((m) => m.endsWith(":free"));
      if (hasFreeTagged) $("btn-remove-free").classList.remove("hidden");
      else $("btn-remove-free").classList.add("hidden");
      // "★ use cheapest" — show when OR has free models in its active list
      const hasFreeActive = or && (or.models || []).some((m) => {
        const c = (or.catalog || {})[m];
        return c && c.in === 0 && c.out === 0;
      });
      if (hasFreeActive) $("btn-use-cheapest-free")?.classList.remove("hidden");
      else $("btn-use-cheapest-free")?.classList.add("hidden");
    } catch (_) { /* non-critical */ }
  } catch (_) {
    $("free-models-list").textContent = "";
  }
}

$("btn-remove-free").onclick = async () => {
  if (!confirm("Remove all :free-tagged models from OpenRouter's list?")) return;
  $("btn-remove-free").disabled = true;
  try {
    const cfg = await api("/api/models");
    const or = cfg.providers.find((p) => p.id === "openrouter");
    const toRemove = (or?.models || []).filter((m) => m.endsWith(":free"));
    for (const mid of toRemove) {
      await api(`/api/models/openrouter/models/${encodeURIComponent(mid)}`, "DELETE");
    }
    $("free-models-msg").textContent = `✓ removed ${toRemove.length} :free models`;
    $("btn-remove-free").classList.add("hidden");
    loadProviders();
  } catch (e) {
    $("free-models-msg").textContent = e.message || "remove failed";
  } finally {
    $("btn-remove-free").disabled = false;
  }
};

$("btn-bulk-add").onclick = async () => {
  const pid = $("bulk-add-pid").value;
  const lines = ($("bulk-add-models").value || "").split("\n").map((s) => s.trim()).filter(Boolean);
  if (!pid || !lines.length) { $("bulk-add-msg").textContent = "pick provider + enter IDs"; return; }
  $("btn-bulk-add").disabled = true;
  $("bulk-add-msg").textContent = "adding…";
  try {
    const cfg = await api("/api/models");
    const prov = cfg.providers.find((p) => p.id === pid);
    if (!prov) throw new Error("Provider not found");
    const existing = new Set(prov.models || []);
    const toAdd = lines.filter((m) => !existing.has(m));
    const updatedModels = [...(prov.models || []), ...toAdd];
    await api("/api/models", "POST", {
      id: prov.id, label: prov.label, kind: prov.kind, base_url: prov.base_url,
      model: prov.model, models: updatedModels, key: "", notes: prov.notes || "",
      input_cost_per_m: prov.in, output_cost_per_m: prov.out, auto: prov.auto,
    });
    $("bulk-add-msg").textContent = `✓ +${toAdd.length} (${lines.length - toAdd.length} dupes skipped)`;
    $("bulk-add-models").value = "";
    loadProviders();
  } catch (e) {
    $("bulk-add-msg").textContent = e.message || "failed";
  } finally {
    $("btn-bulk-add").disabled = false;
  }
};

$("btn-use-cheapest-free").onclick = async () => {
  try {
    const cfg = await api("/api/models");
    const or = cfg.providers.find((p) => p.id === "openrouter");
    if (!or) return;
    // Find the free model with the shortest name (proxy for "official" / simplest) among active models
    const freeModels = (or.models || []).filter((m) => {
      const c = (or.catalog || {})[m]; return c && c.in === 0 && c.out === 0;
    });
    if (!freeModels.length) { $("free-models-msg").textContent = "no free models in OR list"; return; }
    freeModels.sort((a, b) => a.length - b.length);
    const chosen = freeModels[0];
    await api("/api/models", "POST", {
      id: or.id, label: or.label, kind: or.kind, base_url: or.base_url,
      model: chosen, models: or.models, key: "", notes: or.notes || "",
      input_cost_per_m: or.in, output_cost_per_m: or.out, auto: or.auto,
    });
    $("free-models-msg").textContent = `★ active: ${chosen}`;
    loadProviders();
  } catch (e) {
    $("free-models-msg").textContent = e.message || "failed";
  }
};

$("btn-or-refresh").onclick = async () => {
  $("free-models-msg").textContent = "refreshing…";
  $("btn-or-refresh").disabled = true;
  try {
    const r = await api("/api/models/openrouter/refresh", "POST", {});
    $("free-models-msg").textContent = `✓ ${r.total} models, ${r.free} free`;
    await loadFreeModels();
    // auto-add free if checkbox is ticked
    if ($("chk-auto-add-free")?.checked && r.free > 0) {
      await api("/api/models/free/add_all", "POST", {});
      $("free-models-msg").textContent = `✓ ${r.total} models, ${r.free} free (auto-added)`;
      loadProviders();
    }
  } catch (e) {
    const msg = e.message || "refresh failed";
    $("free-models-msg").textContent = msg;
    // live countdown in button label for cooldown errors
    const wait = msg.match(/wait (\d+)s/);
    if (wait) {
      let remaining = parseInt(wait[1]);
      const tick = setInterval(() => {
        remaining--;
        if (remaining <= 0) {
          clearInterval(tick);
          $("btn-or-refresh").textContent = "↻ Refresh";
          $("btn-or-refresh").disabled = false;
        } else {
          $("btn-or-refresh").textContent = `↻ ${remaining}s`;
        }
      }, 1000);
    }
  } finally {
    $("btn-or-refresh").disabled = false;
  }
};

$("btn-add-all-free").onclick = async () => {
  $("btn-add-all-free").disabled = true;
  try {
    const r = await api("/api/models/free/add_all", "POST", {});
    $("free-models-msg").textContent = `✓ added ${r.added} (${r.total} free total)`;
    loadProviders();
  } catch (e) {
    $("free-models-msg").textContent = e.message || "add failed";
  } finally {
    $("btn-add-all-free").disabled = false;
  }
};

<<<<<<< Updated upstream
=======
$("btn-toggle-free").onclick = () => {
  const body = document.getElementById("free-models-section").querySelectorAll(":scope > :not(:first-child)");
  const btn = $("btn-toggle-free");
  const collapsed = btn.textContent === "▶";
  body.forEach((el) => el.classList.toggle("hidden", collapsed));
  btn.textContent = collapsed ? "▼" : "▶";
  btn.title = collapsed ? "Collapse section" : "Expand section";
};

$("btn-clear-errors").onclick = async () => {
  try {
    const r = await api("/api/models/clear_errors", "POST", {});
    $("export-msg").textContent = `✓ cleared ${r.cleared} error${r.cleared !== 1 ? "s" : ""}`;
    setTimeout(() => { $("export-msg").textContent = ""; }, 2000);
    loadProviders();
  } catch (e) {
    $("export-msg").textContent = e.message || "clear failed";
  }
};

>>>>>>> Stashed changes
$("btn-import-config").onclick = async () => {
  const raw = prompt("Paste exported config JSON:");
  if (!raw) return;
  try {
    const payload = JSON.parse(raw);
    const r = await api("/api/models/import", "POST", payload);
    $("export-msg").textContent = `✓ imported ${r.imported} providers`;
    setTimeout(() => { $("export-msg").textContent = ""; }, 3000);
    loadProviders();
  } catch (e) {
    $("export-msg").textContent = e.message || "import failed";
  }
};

$("btn-export-config").onclick = async () => {
  try {
    const data = await api("/api/models/export");
    await navigator.clipboard?.writeText(JSON.stringify(data, null, 2));
    $("export-msg").textContent = "✓ copied";
    setTimeout(() => { $("export-msg").textContent = ""; }, 2000);
  } catch (e) {
    $("export-msg").textContent = e.message || "copy failed";
  }
};

// Inline base_url validation for custom provider form
const _validateBaseUrl = () => {
  const kind = $("pv-kind").value;
  const base = $("pv-base").value.trim();
  const msg = $("pv-msg");
  if (kind === "openai" && !base) {
    msg.textContent = "⚠ base_url is required for OpenAI-compatible providers";
    msg.className = "col-span-2 text-xs text-yellow-400";
  } else {
    if (msg.textContent.startsWith("⚠")) { msg.textContent = ""; msg.className = "col-span-2 text-xs text-slate-400"; }
  }
};
$("pv-kind").addEventListener("change", _validateBaseUrl);
$("pv-base").addEventListener("input", _validateBaseUrl);

$("pv-save").onclick = async () => {
  const id = $("pv-id").value.trim();
  if (!id) { $("pv-msg").textContent = "Give the provider an id."; return; }
  if ($("pv-kind").value === "openai" && !$("pv-base").value.trim()) {
    $("pv-msg").textContent = "⚠ base_url is required for OpenAI-compatible providers."; return;
  }
  try {
    await api("/api/models", "POST", {
      id, label: id, kind: $("pv-kind").value,
      base_url: $("pv-base").value.trim(), model: $("pv-model").value.trim(),
      models: $("pv-model").value.trim() ? [$("pv-model").value.trim()] : [],
      key: $("pv-key").value,
      input_cost_per_m: parseFloat($("pv-in").value) || 0,
      output_cost_per_m: parseFloat($("pv-out").value) || 0, auto: true,
    });
    $("pv-msg").textContent = "Added ✓";
    ["pv-id", "pv-base", "pv-model", "pv-key", "pv-in", "pv-out"].forEach((k) => ($(k).value = ""));
    loadProviders();
  } catch (e) { $("pv-msg").textContent = e.message; }
};

/* ---------------- free-provider presets (#12) ---------------- */

const _PROVIDER_PRESETS = [
  { id: "groq",     label: "Groq",          base_url: "https://api.groq.com/openai/v1",
    model: "llama-3.3-70b-versatile",
    models: ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "mixtral-8x7b-32768"],
    in: 0, out: 0 },
  { id: "cerebras", label: "Cerebras",       base_url: "https://api.cerebras.ai/v1",
    model: "llama3.1-8b",
    models: ["llama3.1-8b", "llama3.1-70b"],
    in: 0, out: 0 },
  { id: "mistral",  label: "Mistral (free)", base_url: "https://api.mistral.ai/v1",
    model: "mistral-small-latest",
    models: ["mistral-small-latest", "open-mistral-nemo"],
    in: 0, out: 0 },
  { id: "github",   label: "GitHub Models",  base_url: "https://models.inference.ai.azure.com",
    model: "gpt-4o-mini",
    models: ["gpt-4o-mini", "Phi-3.5-mini-instruct", "Meta-Llama-3.1-8B-Instruct"],
    in: 0, out: 0 },
];

(function () {
  const box = $("preset-btns");
  if (!box) return;
  _PROVIDER_PRESETS.forEach((p) => {
    const btn = document.createElement("button");
    btn.className = "border border-slate-700 text-slate-300 hover:border-[var(--gold)] hover:text-[var(--gold)] rounded px-2 py-0.5";
    btn.textContent = `+ ${p.label}`;
    btn.onclick = () => {
      $("pv-id").value = p.id;
      $("pv-base").value = p.base_url;
      $("pv-model").value = p.model;
      $("pv-in").value = p.in;
      $("pv-out").value = p.out;
      $("pv-key").focus();
      $("pv-msg").textContent = "Pre-filled — paste your API key and click Add provider.";
    };
    box.appendChild(btn);
  });
})();

/* ---------------- MCP modal ---------------- */

$("btn-mcp").onclick = () => { $("modal-mcp").classList.remove("hidden"); loadMcpServers(); loadConnectorCatalog(); };
$("mcp-close").onclick = () => $("modal-mcp").classList.add("hidden");

// Wave 4 #9 — connector marketplace: list catalog entries; click pre-fills the
// add-form. Defensive: never throws if a field/element is absent.
async function loadConnectorCatalog() {
  const box = $("mcp-catalog");
  if (!box) return;
  try {
    const r = await api("/api/connectors", "GET");
    box.innerHTML = (r.connectors || []).map((c, i) =>
      `<button data-i="${i}" class="mcp-cat text-left gold-border rounded px-2 py-1 hover:bg-yellow-900/10">`
      + `<span class="text-[var(--gold-bright)]">${esc(c.name)}</span> `
      + `<span class="text-slate-600">${esc(c.transport)}</span>`
      + `<div class="text-slate-500 text-[.6rem]">${esc(c.description || "")}</div></button>`).join("");
    box.querySelectorAll(".mcp-cat").forEach((b) => {
      b.onclick = () => prefillConnector(r.connectors[b.dataset.i]);
    });
  } catch (_) { /* not owner / offline */ }
}

function prefillConnector(c) {
  if (!c) return;
  const set = (id, v) => { const el = $(id); if (el != null && v != null) el.value = v; };
  set("mcp-name", c.name);
  const tsel = $("mcp-transport");
  if (tsel) { tsel.value = c.transport; tsel.dispatchEvent(new Event("change")); }
  if (c.transport === "http") set("mcp-url", c.url);
  else { set("mcp-command", c.command); set("mcp-args", (c.args || []).join(" ")); }
  if (c.needs) { const m = $("mcp-msg"); if (m) m.textContent = "ℹ " + c.needs; }
}

function mcpStatusDot(s) {
  if (s.enabled === false) return '<span class="dot" style="background:#475569" title="disabled"></span>';
  if (s.status === "connected") return '<span class="dot" style="background:#39d353" title="connected"></span>';
  return '<span class="dot" style="background:#ef4444" title="error"></span>';
}

function renderMcpRows(servers) {
  const container = $("mcp-server-rows");
  container.innerHTML = servers.length
    ? ""
    : '<div class="text-slate-600">no servers configured</div>';

  servers.forEach((s) => {
    const row = document.createElement("div");
    row.className = "border-b border-slate-800/60 py-2";
    row.dataset.mcpId = s.id;

    // Show host for http, command basename for stdio
    let hint = "";
    if (s.transport === "stdio") {
      hint = esc((s.command || "").split("/").pop());
    } else {
      try { hint = esc(new URL(s.url || "").host); } catch (_) { hint = esc(s.url || ""); }
    }
    const transportBadge = s.transport === "stdio"
      ? '<span class="gold-border rounded px-1 text-[.6rem] text-[var(--gold)] ml-1">stdio</span>'
      : "";

    const toolCount = (s.tools || []).length;
    // OAuth badge + connect button (shown only for oauth servers)
    const oauthBadge = s.auth === "oauth"
      ? (s.oauth_connected
          ? '<span class="rounded px-1 text-[.6rem] bg-green-900/60 text-green-300 ml-1">OAuth ✓</span>'
          : '<span class="rounded px-1 text-[.6rem] bg-red-900/60 text-red-300 ml-1">OAuth ✗</span>')
      : "";
    const oauthConnectBtn = (s.auth === "oauth" && !s.oauth_connected)
      ? `<button class="mcp-oauth-connect gold-border rounded px-2 py-0.5 text-[.65rem] text-[var(--gold-bright)] hover:bg-yellow-900/20" title="Start OAuth flow">Connect (OAuth)</button>`
      : "";
    row.innerHTML = `
      <div class="flex items-center gap-2 cursor-pointer mcp-row-header">
        ${mcpStatusDot(s)}
        <b class="flex-1 text-slate-200">${esc(s.name)}</b>${transportBadge}${oauthBadge}
        <span class="text-slate-500">${hint}</span>
        <span class="text-slate-400">${toolCount} tool${toolCount !== 1 ? "s" : ""}</span>
        ${oauthConnectBtn}
        <button class="mcp-toggle ${s.enabled ? "text-green-400" : "text-slate-600"} hover:text-green-300" title="${s.enabled ? "disable" : "enable"}">${s.enabled ? "on" : "off"}</button>
        <button class="mcp-refresh text-slate-400 hover:text-[var(--gold)]" title="reconnect &amp; refresh tools">↻</button>
        <button class="mcp-del text-red-500/60 hover:text-red-400" title="remove server">✕</button>
      </div>
      ${s.status === "error" && s.error ? `<div class="text-red-400 text-[.7rem] pl-4 mt-0.5">${esc(s.error)}</div>` : ""}
      <div class="mcp-tool-list hidden pl-4 pt-1 space-y-0.5">
        ${(s.tools || []).map((t) =>
          `<div class="text-slate-400"><span class="text-slate-200">${esc(t.name)}</span>
           ${t.read_only ? '<span class="gold-border rounded px-1 text-[.6rem] text-[var(--gold)] ml-1">ro</span>' : ""}
           <span class="text-slate-600 ml-1">${esc((t.description || "").slice(0, 80))}${(t.description || "").length > 80 ? "…" : ""}</span></div>`
        ).join("") || '<div class="text-slate-600">no tools</div>'}
      </div>`;

    row.querySelector(".mcp-row-header").onclick = (e) => {
      if (e.target.closest("button")) return;
      row.querySelector(".mcp-tool-list").classList.toggle("hidden");
    };

    const oauthConnectEl = row.querySelector(".mcp-oauth-connect");
    if (oauthConnectEl) {
      oauthConnectEl.onclick = async () => {
        try {
          const d = await api(`/api/mcp/${encodeURIComponent(s.id)}/oauth/start`, "POST", {});
          window.open(d.authorize_url, "_blank", "noopener,noreferrer,width=600,height=700");
          // Poll for completion after a short delay so the user has time to authorize
          $("mcp-msg").textContent = "OAuth window opened — authorize, then click ↻ to refresh.";
        } catch (err) { $("mcp-msg").textContent = err.message; }
      };
    }

    row.querySelector(".mcp-toggle").onclick = async () => {
      try {
        await api(`/api/mcp/${encodeURIComponent(s.id)}/toggle`, "POST", {});
        loadMcpServers();
      } catch (err) { $("mcp-msg").textContent = err.message; }
    };

    row.querySelector(".mcp-refresh").onclick = async () => {
      $("mcp-msg").textContent = "refreshing…";
      try {
        await api(`/api/mcp/${encodeURIComponent(s.id)}/refresh`, "POST", {});
        $("mcp-msg").textContent = "";
        loadMcpServers();
      } catch (err) { $("mcp-msg").textContent = err.message; }
    };

    row.querySelector(".mcp-del").onclick = async () => {
      if (!confirm(`Remove MCP server "${s.name}"?`)) return;
      try {
        await api(`/api/mcp/${encodeURIComponent(s.id)}`, "DELETE");
        loadMcpServers();
      } catch (err) { $("mcp-msg").textContent = err.message; }
    };

    container.appendChild(row);
  });
}

async function loadMcpServers() {
  try {
    const d = await api("/api/mcp");
    renderMcpRows(d.servers || []);
  } catch (e) { $("mcp-msg").textContent = e.message; }
}

// Transport select: toggle http vs stdio field groups
$("mcp-transport").onchange = () => {
  const isStdio = $("mcp-transport").value === "stdio";
  $("mcp-http-fields").classList.toggle("hidden", isStdio);
  $("mcp-stdio-fields").classList.toggle("hidden", !isStdio);
};

// Auth type: toggle bearer vs oauth fields (http transport only)
$("mcp-auth").onchange = () => {
  const isOAuth = $("mcp-auth").value === "oauth";
  $("mcp-bearer-fields").classList.toggle("hidden", isOAuth);
  $("mcp-oauth-fields").classList.toggle("hidden", !isOAuth);
};

$("mcp-preset-github").onclick = () => {
  $("mcp-transport").value = "http";
  $("mcp-transport").dispatchEvent(new Event("change"));
  $("mcp-auth").value = "bearer";
  $("mcp-auth").dispatchEvent(new Event("change"));
  $("mcp-name").value = "github";
  $("mcp-url").value = "https://api.githubcopilot.com/mcp/";
  $("mcp-token").placeholder = "Bearer token / PAT — stored server-side";
  $("mcp-token").focus();
};

// Google Drive official remote MCP — owner must register their own OAuth app at
// https://console.cloud.google.com and fill in their own client_id (and optionally
// client_secret for confidential clients). Scope is for Drive read-only; adjust as needed.
$("mcp-preset-gdrive").onclick = () => {
  $("mcp-transport").value = "http";
  $("mcp-transport").dispatchEvent(new Event("change"));
  $("mcp-auth").value = "oauth";
  $("mcp-auth").dispatchEvent(new Event("change"));
  $("mcp-name").value = "google-drive";
  $("mcp-url").value = "https://drive.googleapis.com/mcp/";
  $("mcp-oauth-az").value = "https://accounts.google.com/o/oauth2/v2/auth";
  $("mcp-oauth-tz").value = "https://oauth2.googleapis.com/token";
  $("mcp-oauth-scope").value = "https://www.googleapis.com/auth/drive.readonly";
  $("mcp-oauth-cid").value = "";
  $("mcp-oauth-cid").focus();
};

// Microsoft 365 official remote MCP — owner must register their own app at
// https://portal.azure.com (Entra ID) and fill in their own client_id.
// The tenant 'common' allows both personal and work accounts; replace with your tenant ID
// if needed. Scopes below cover basic Files read and Mail read.
$("mcp-preset-m365").onclick = () => {
  $("mcp-transport").value = "http";
  $("mcp-transport").dispatchEvent(new Event("change"));
  $("mcp-auth").value = "oauth";
  $("mcp-auth").dispatchEvent(new Event("change"));
  $("mcp-name").value = "microsoft-365";
  $("mcp-url").value = "https://graph.microsoft.com/mcp/";
  $("mcp-oauth-az").value = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize";
  $("mcp-oauth-tz").value = "https://login.microsoftonline.com/common/oauth2/v2.0/token";
  $("mcp-oauth-scope").value = "Files.Read Mail.Read offline_access";
  $("mcp-oauth-cid").value = "";
  $("mcp-oauth-cid").focus();
};

$("mcp-add").onclick = async () => {
  $("mcp-msg").textContent = "";
  const name = $("mcp-name").value.trim();
  const transport = $("mcp-transport").value;
  if (!name) { $("mcp-msg").textContent = "Name is required."; return; }

  let body;
  if (transport === "stdio") {
    const command = $("mcp-command").value.trim();
    if (!command) { $("mcp-msg").textContent = "Command is required for stdio."; return; }
    // args: space-separated string → array
    const argsRaw = $("mcp-args").value.trim();
    const args = argsRaw ? argsRaw.match(/(?:[^\s"']+|"[^"]*"|'[^']*')+/g) || [] : [];
    // env: KEY=VALUE pairs, space-separated → object
    const envRaw = $("mcp-env").value.trim();
    const env = {};
    if (envRaw) {
      envRaw.split(/\s+/).forEach((pair) => {
        const idx = pair.indexOf("=");
        if (idx > 0) env[pair.slice(0, idx)] = pair.slice(idx + 1);
      });
    }
    body = { name, transport: "stdio", command, args, env };
  } else {
    const url  = $("mcp-url").value.trim();
    if (!url) { $("mcp-msg").textContent = "URL is required for HTTP."; return; }
    const auth = $("mcp-auth").value;
    if (auth === "oauth") {
      const az = $("mcp-oauth-az").value.trim();
      const tz = $("mcp-oauth-tz").value.trim();
      const cid = $("mcp-oauth-cid").value.trim();
      if (!az || !tz || !cid) {
        $("mcp-msg").textContent = "OAuth requires authorize_url, token_url, and client_id.";
        return;
      }
      body = {
        name, transport: "http", url, auth: "oauth",
        oauth: {
          authorize_url: az,
          token_url: tz,
          client_id: cid,
          client_secret: $("mcp-oauth-csec").value,
          scope: $("mcp-oauth-scope").value.trim(),
        },
      };
    } else {
      body = { name, transport: "http", url, token: $("mcp-token").value, auth: "bearer" };
    }
  }

  try {
    await api("/api/mcp", "POST", body);
    ["mcp-name", "mcp-url", "mcp-token", "mcp-command", "mcp-args", "mcp-env",
     "mcp-oauth-az", "mcp-oauth-tz", "mcp-oauth-cid", "mcp-oauth-csec", "mcp-oauth-scope",
    ].forEach((k) => ($(k).value = ""));
    $("mcp-auth").value = "bearer";
    $("mcp-auth").dispatchEvent(new Event("change"));
    $("mcp-msg").textContent = "Added ✓";
    loadMcpServers();
  } catch (e) { $("mcp-msg").textContent = e.message; }
};

/* ---------------- boot ---------------- */

if (state.token) {
  api("/api/me").then((d) => {
    state.role = d.role;
    if (d.must_reset) showSetup(); else showMain();
  }).catch(() => showLogin());
} else showLogin();
