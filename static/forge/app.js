/* CodeMonkeys console — vanilla JS, no build step. */
"use strict";

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g,
  (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const state = {
  token: localStorage.getItem("cm_token") || "",
  username: localStorage.getItem("cm_username") || "",
  role: localStorage.getItem("cm_role") || "",
  sid: null, after: -1, status: "idle", timer: null, files: [], registering: false,
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

function showLogin() { $("view-login").classList.remove("hidden"); $("view-main").classList.add("hidden"); }
function showMain() {
  $("view-login").classList.add("hidden"); $("view-main").classList.remove("hidden");
  $("who").textContent = state.username;
  refreshSessions(); refreshRepos();
}
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
      $("lg-qr").src = "https://api.qrserver.com/v1/create-qr-code/?size=160x160&data="
        + encodeURIComponent(d.mfa_otpauth_uri);
      $("lg-mfa-setup").classList.remove("hidden");
    } else {
      const d = await api("/api/login", "POST", {
        username: $("lg-user").value, pin: $("lg-pin").value, mfa_code: $("lg-mfa").value,
      });
      saveAuth(d); showMain();
    }
  } catch (e) { $("lg-msg").textContent = e.message; }
};
$("lg-continue").onclick = () => showMain();
$("btn-logout").onclick = logout;

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
  } catch (e) { msg.textContent = "✗ " + e.message; }
};

/* ---------------- sessions / repos ---------------- */

async function refreshSessions() {
  try {
    const d = await api("/api/sessions");
    $("session-list").innerHTML = d.sessions.map((s) =>
      `<div class="group flex items-center gap-1 rounded px-2 py-1 hover:bg-yellow-900/20 ${s.id === state.sid ? "bg-yellow-900/30" : ""}">
         <span data-sid="${s.id}" class="session-item flex-1 cursor-pointer truncate ${s.id === state.sid ? "text-[var(--gold-bright)]" : "text-slate-300"}">
           ${esc(s.title)} <span class="text-slate-600">$${s.spent_usd}</span></span>
         <button data-del="${s.id}" class="session-del text-slate-600 hover:text-red-400 opacity-0 group-hover:opacity-100" title="Delete session">✕</button>
       </div>`).join("")
      || '<div class="text-slate-600">none yet</div>';
    document.querySelectorAll(".session-item").forEach((el) =>
      (el.onclick = () => openSession(el.dataset.sid)));
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
    case "tool_result":
      div.className = "ev-tool px-3" + (e.ok ? "" : " text-red-400");
      div.innerHTML = `${agentTag(e)}↳ ${e.ok ? "ok" : "FAIL"} <span class="detail">${esc(e.detail)}</span>`;
      div.onclick = () => div.classList.toggle("open"); break;
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

async function poll() {
  if (!state.sid) return;
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
    startPolling(d.status !== "idle");
  } catch (e) { /* transient */ }
}

function startPolling(fast) {
  stopPolling();
  state.timer = setInterval(poll, fast ? 1500 : 6000);
  poll();
}
function stopPolling() { if (state.timer) clearInterval(state.timer); state.timer = null; }

/* ---------------- composer ---------------- */

function renderChips() {
  $("file-chips").innerHTML = state.files.map((f, i) =>
    `<span class="gold-border rounded px-2 py-0.5 text-[.65rem] text-slate-300">${esc(f.name)}
       <button data-i="${i}" class="text-red-400 ml-1">✕</button></span>`).join("");
  document.querySelectorAll("#file-chips button").forEach((b) =>
    (b.onclick = () => { state.files.splice(+b.dataset.i, 1); renderChips(); }));
}

$("btn-attach").onclick = () => $("file-input").click();
$("file-input").onchange = () => {
  for (const f of $("file-input").files) {
    const reader = new FileReader();
    reader.onload = () => {
      state.files.push({ name: f.name, content_b64: reader.result.split(",", 2)[1] || "" });
      renderChips();
    };
    reader.readAsDataURL(f);
  }
  $("file-input").value = "";
};

async function send() {
  const text = $("msg").value.trim();
  if (!text) return;
  if (!state.sid) {
    const d = await api("/api/sessions", "POST", { title: text.slice(0, 40) });
    state.sid = d.id; state.after = -1; $("stream").innerHTML = ""; refreshSessions();
  }
  try {
    await api(`/api/sessions/${state.sid}/message`, "POST",
      { text, files: state.files, mode: state.mode });
    $("msg").value = ""; state.files = []; renderChips();
    startPolling(true);
  } catch (e) { alert(e.message); }
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

$("btn-models").onclick = () => { $("modal-models").classList.remove("hidden"); loadProviders(); };
$("modal-close").onclick = () => $("modal-models").classList.add("hidden");

async function loadProviders() {
  const d = await api("/api/models");
  $("auto-cheapest").checked = !!d.auto_cheapest;
  $("provider-rows").innerHTML = d.providers.map((p) => {
    const opts = (p.models || []).map((m) =>
      `<option value="${esc(m)}" ${m === p.model ? "selected" : ""}>${esc(m)}</option>`).join("");
    const isMain = p.id === d.selected && !d.auto_cheapest;
    return `
    <div class="border-b border-slate-800/60 py-2 ${isMain ? "bg-yellow-900/10 rounded" : ""}">
      <div class="flex items-center gap-2">
        <button data-id="${esc(p.id)}" class="pv-main ${isMain ? "text-[var(--gold-bright)]" : "text-slate-600"} hover:text-[var(--gold)]" title="Use as main (when Auto is off)">★</button>
        <span class="${p.has_key ? "text-green-400" : "text-slate-600"}">●</span>
        <b class="flex-1 ${isMain ? "text-[var(--gold-bright)]" : "text-slate-200"}">${esc(p.label)}</b>
        <label class="flex items-center gap-1 text-slate-400" title="Include in cheapest-first cascade">
          <input type="checkbox" class="pv-auto accent-yellow-500" data-id="${esc(p.id)}" ${p.auto ? "checked" : ""}>✓auto</label>
        <button data-id="${esc(p.id)}" class="pv-del text-red-500/60 hover:text-red-400">remove</button>
      </div>
      <div class="flex items-center gap-2 mt-1 pl-6">
        <select class="pv-model input rounded px-1 py-0.5 flex-1" data-id="${esc(p.id)}">${opts}</select>
        <input type="password" class="pv-key input rounded px-1 py-0.5 flex-1" data-id="${esc(p.id)}"
          placeholder="${p.has_key ? "key set ✓ (type to replace)" : "paste API key"}">
        <button data-id="${esc(p.id)}" class="pv-savekey gold-btn rounded px-2 py-0.5">save</button>
        <span class="text-slate-600">$${p.out}/M</span>
      </div>
    </div>`;
  }).join("");

  document.querySelectorAll(".pv-main").forEach((b) => (b.onclick = async () => {
    await api("/api/models/select", "POST", { id: b.dataset.id });
    await api("/api/models/settings", "POST", { auto_cheapest: false });
    loadProviders();
  }));
  document.querySelectorAll(".pv-del").forEach((b) => (b.onclick = async () => {
    if (confirm(`Remove provider ${b.dataset.id}?`)) {
      await api(`/api/models/${encodeURIComponent(b.dataset.id)}`, "DELETE"); loadProviders();
    }
  }));
  document.querySelectorAll(".pv-savekey").forEach((b) => (b.onclick = async () => {
    const id = b.dataset.id;
    const prov = d.providers.find((x) => x.id === id);
    const key = document.querySelector(`.pv-key[data-id="${id}"]`).value;
    const model = document.querySelector(`.pv-model[data-id="${id}"]`).value;
    const auto = document.querySelector(`.pv-auto[data-id="${id}"]`).checked;
    try {
      await api("/api/models", "POST", {
        id, label: prov.label, kind: prov.kind, base_url: prov.base_url,
        model, models: prov.models, key,
        input_cost_per_m: prov.in, output_cost_per_m: prov.out, auto,
      });
      loadProviders();
    } catch (e) { alert(e.message); }
  }));
  // model dropdown / auto checkbox auto-save on change
  document.querySelectorAll(".pv-model, .pv-auto").forEach((el) => (el.onchange = () => {
    document.querySelector(`.pv-savekey[data-id="${el.dataset.id}"]`).click();
  }));
}

$("auto-cheapest").onchange = async () => {
  await api("/api/models/settings", "POST", { auto_cheapest: $("auto-cheapest").checked });
  loadProviders();
};

$("pv-save").onclick = async () => {
  const id = $("pv-id").value.trim();
  if (!id) { $("pv-msg").textContent = "Give the provider an id."; return; }
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

/* ---------------- boot ---------------- */

if (state.token) {
  api("/api/me").then(() => showMain()).catch(() => showLogin());
} else showLogin();
