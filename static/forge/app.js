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
  refreshSessions(); refreshRepos(); listPasskeys();
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
