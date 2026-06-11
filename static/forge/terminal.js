/* CodeMonkeys web terminal — Claude Code-style REPL with interactive companion
   and integrated mode/model controllers. Vanilla JS, no dependencies. */
"use strict";

const state = {
  token: localStorage.getItem("cm_token") || "",
  username: localStorage.getItem("cm_username") || "",
  role: localStorage.getItem("cm_role") || "",
  sid: "", cursor: -1, timer: null, mode: "default",
  nextBudget: null, pendingApproval: null,
  lastActivity: Date.now(), hist: [], histIdx: -1,
  // N5 streaming: live div being appended to for the current assistant turn.
  streamDiv: null,
  typingTimeout: null,
  lastStatusText: ""
};

const IDLE_STOP_MS = 10 * 60 * 1000;   // stop polling after 10 min of inactivity
const ANSI_RE = /\x1b\[[0-9;]*[A-Za-z]|\x1b\][^\x07]*\x07/g;

const sb = document.getElementById("scrollback");
const input = document.getElementById("cmd");
const statusLeft = document.getElementById("status-left");
const statusRight = document.getElementById("status-right");
const modelSelect = document.getElementById("model-select");
const monkeyWrap = document.getElementById("monkey-box-wrap");
const monkeyBubble = document.getElementById("monkey-bubble");

// Mode Buttons
const modes = {
  default: document.getElementById("mode-default"),
  plan: document.getElementById("mode-plan"),
  auto: document.getElementById("mode-auto")
};

function line(text, cls) {
  const div = document.createElement("div");
  if (cls) div.className = cls;
  div.textContent = String(text).replace(ANSI_RE, "");   // F4: textContent only
  sb.appendChild(div);
  sb.scrollTop = sb.scrollHeight;
  return div;
}

function setStatus(t) {
  state.lastStatusText = t;
  statusLeft.textContent = t;
}

async function api(path, method = "GET", body) {
  const r = await fetch(path, {
    method,
    headers: {
      "Content-Type": "application/json",
      ...(state.token ? { Authorization: "Bearer " + state.token } : {})
    },
    ...(body ? { body: JSON.stringify(body) } : {}),
  });
  let d = {};
  try { d = await r.json(); } catch (_) { /* non-JSON error body */ }
  if (!r.ok) throw new Error(d.detail || `${r.status} ${r.statusText}`);
  return d;
}

/* ---------------- Monkey Companion States ---------------- */

function setMonkeyState(anim, msg) {
  // Clear any existing animation classes
  monkeyWrap.className = "monkey-box " + anim;
  if (msg) {
    monkeyBubble.textContent = msg;
  }
}

// Typing state triggers when typing and decays back to idle
function triggerMonkeyTyping() {
  if (monkeyWrap.classList.contains("working")) return; // Don't interrupt running agent animation
  setMonkeyState("typing", "Typing task...");
  if (state.typingTimeout) clearTimeout(state.typingTimeout);
  state.typingTimeout = setTimeout(() => {
    if (!monkeyWrap.classList.contains("working")) {
      setMonkeyState("idle", "Ooh ooh! Ready.");
    }
  }, 1200);
}

/* ---------------- Models loading ---------------- */

async function loadModels() {
  // Models select endpoint is owner-only, check role
  if (state.role !== "Owner") {
    modelSelect.disabled = true;
    modelSelect.innerHTML = `<option value="auto">Auto (Smart Routing)</option>`;
    return;
  }
  try {
    const d = await api("/api/models");
    let optionsHtml = `<option value="auto" ${d.selected === "auto" ? "selected" : ""}>Auto (Smart Routing)</option>`;
    (d.providers || []).forEach(p => {
      if (p.has_key) {
        optionsHtml += `<option value="${p.id}" ${d.selected === p.id ? "selected" : ""}>${p.label} (${p.model || p.kind})</option>`;
      }
    });
    modelSelect.innerHTML = optionsHtml;
  } catch (err) {
    console.error("Failed to load models settings:", err);
  }
}

modelSelect.addEventListener("change", async () => {
  const val = modelSelect.value;
  try {
    setMonkeyState("working", "Configuring model...");
    await api("/api/models/select", "POST", { id: val });
    if (val === "auto") {
      await api("/api/models/settings", "POST", { auto_cheapest: true });
    } else {
      await api("/api/models/settings", "POST", { auto_cheapest: false });
    }
    setMonkeyState("success", "Model updated!");
    setTimeout(() => setMonkeyState("idle", "Ooh ooh! Ready."), 1500);
  } catch (err) {
    setMonkeyState("error", `Err: ${err.message}`);
  }
});

/* ---------------- Mode Selection ---------------- */

function setMode(newMode) {
  if (!["default", "plan", "auto"].includes(newMode)) return;
  state.mode = newMode;
  
  // Update UI buttons
  Object.keys(modes).forEach(m => {
    if (modes[m]) {
      if (m === newMode) {
        modes[m].classList.add("active");
      } else {
        modes[m].classList.remove("active");
      }
    }
  });

  // Keep status bar in sync
  if (state.sid) {
    setStatus(state.lastStatusText.replace(/mode \w+/, `mode ${newMode}`));
  }
}

Object.keys(modes).forEach(m => {
  if (modes[m]) {
    modes[m].addEventListener("click", () => {
      setMode(m);
      setMonkeyState("success", `Mode -> ${m}`);
      setTimeout(() => setMonkeyState("idle", "Ooh ooh! Ready."), 1500);
    });
  }
});

/* ---------------- event rendering (poll loop) ---------------- */

function renderEvent(e) {
  switch (e.type) {
    case "user": break;                       // already echoed at the prompt
    case "text_delta": {
      setMonkeyState("working", "Assembling output...");
      const prefix = e.agent ? `[${e.agent}] ` : "";
      if (!state.streamDiv) {
        state.streamDiv = line(prefix, "t-out");
      }
      state.streamDiv.textContent += String(e.text || "").replace(ANSI_RE, "");
      sb.scrollTop = sb.scrollHeight;
      break;
    }
    case "text": {
      const prefix = e.agent ? `[${e.agent}] ` : "";
      if (state.streamDiv) {
        state.streamDiv.textContent = prefix + String(e.text || "").replace(ANSI_RE, "");
        state.streamDiv = null;
      } else {
        line(prefix + e.text, "t-out");
      }
      break;
    }
    case "tool": {
      state.streamDiv = null;
      line(`  ⚙ ${e.name} ${String(e.detail || "").slice(0, 160)}`, "t-dim");
      setMonkeyState("working", `Running ${e.name}...`);
      break;
    }
    case "tool_result": {
      line(`  ↳ ${e.ok ? "ok" : "FAIL"} ${String(e.detail || "").slice(0, 160)}`,
           e.ok ? "t-dim" : "t-err");
      break;
    }
    case "agent_start": {
      line(`  🐒 deployed ${e.agent} [${e.tier} · ${e.model}] — ${e.task}`, "t-agent");
      setMonkeyState("working", `Monkey ${e.agent} deployed!`);
      break;
    }
    case "agent_end": {
      line(`  🐒 ${e.agent} reported back`, "t-agent");
      break;
    }
    case "cost": {
      line(`  $ ${e.model} · ${e.in_tokens}→${e.out_tokens} tok · $${Number(e.usd).toFixed(4)}`, "t-dim");
      break;
    }
    case "approval": {
      state.pendingApproval = e.approval_id;
      line(`⚠ APPROVAL REQUIRED: ${e.command}`, "t-warn");
      line(`  type /approve to allow or /deny to refuse`, "t-warn");
      setMonkeyState("idle", "Waiting for approval...");
      break;
    }
    case "approval_result": {
      state.pendingApproval = null;
      line(e.approved ? "  ✓ approved" : "  ✗ denied", "t-dim");
      break;
    }
    case "debate_verify": {
      line(`  ⚖ debate-verify ${e.allowed ? "ALLOWED" : "BLOCKED"}: ${e.command}`, "t-dim");
      break;
    }
    case "terminal_exec": break;              // local echo already covers it
    case "terminal_exec_result": break;       // rendered from the POST response
    case "error": {
      state.streamDiv = null;
      line(`✗ ${e.message}`, "t-err");
      setMonkeyState("error", "Error encountered.");
      break;
    }
    case "done": {
      state.streamDiv = null;
      line("— done —", "t-dim");
      setMonkeyState("success", "Task finished!");
      setTimeout(() => setMonkeyState("idle", "Ooh ooh! Ready."), 3000);
      break;
    }
    default: break;
  }
}

async function poll() {
  if (!state.sid) return;
  try {
    const d = await api(`/api/sessions/${state.sid}/events?after=${state.cursor}`);
    if (d.events.length) state.lastActivity = Date.now();
    d.events.forEach(renderEvent);
    state.cursor = d.next;
    setStatus(`session ${state.sid} · ${d.status} · $${d.spent_usd} spent · mode ${state.mode}`);
    if (d.status === "running") {
      if (!monkeyWrap.classList.contains("working")) {
        setMonkeyState("working", "Monkeys are hard at work!");
      }
    } else if (d.status === "idle" && monkeyWrap.classList.contains("working")) {
      setMonkeyState("idle", "Ooh ooh! Ready.");
    }
  } catch (err) {
    setStatus(`poll error: ${err.message}`);
  }
  if (Date.now() - state.lastActivity > IDLE_STOP_MS) {
    stopPolling();
    setStatus(`idle — polling paused (press Enter to resume) · session ${state.sid}`);
    setMonkeyState("idle", "Zzz... (press Enter to wake up)");
  }
}

function startPolling() {
  stopPolling();
  state.lastActivity = Date.now();
  state.timer = setInterval(poll, 1500);
  poll();
}

function stopPolling() {
  if (state.timer) {
    clearInterval(state.timer);
    state.timer = null;
  }
}

/* ---------------- commands ---------------- */

const HELP = `commands:
  <text>            send a task to the agent loop (creates a session if none)
  !<cmd>            run a one-shot shell command (Owner only; server-gated)
  /sessions         list sessions          /new [title]   start a fresh session
  /use <id>         attach to a session    /mode plan|default|auto
  /approve  /deny   answer a pending approval gate
  /stop             stop the current run   /status        session status
  /budget <usd>     budget for the NEXT /new
  /clear            clear scrollback       /logout        forget token, go to /`;

async function ensureSession() {
  if (state.sid) return;
  const d = await api("/api/sessions", "POST",
    { title: "", repo: "", ...(state.nextBudget ? { budget_usd: state.nextBudget } : {}) });
  state.sid = d.id; state.cursor = -1; state.nextBudget = null;
  line(`(new session ${d.id} · budget $${d.budget_usd})`, "t-dim");
  startPolling();
}

async function slash(text) {
  const [cmd, ...rest] = text.slice(1).split(/\s+/);
  const arg = rest.join(" ").trim();
  switch (cmd) {
    case "help": line(HELP, "t-dim"); break;
    case "sessions": {
      const d = await api("/api/sessions");
      if (!d.sessions.length) { line("(no sessions)", "t-dim"); break; }
      d.sessions.slice(0, 20).forEach((s) =>
        line(`${s.id === state.sid ? "*" : " "} ${s.id}  ${s.status.padEnd(16)} $${s.spent_usd}  ${s.title}`, "t-dim"));
      break;
    }
    case "new":
      stopPolling(); state.sid = ""; state.cursor = -1;
      if (arg) {
        const d = await api("/api/sessions", "POST",
          { title: arg, repo: "", ...(state.nextBudget ? { budget_usd: state.nextBudget } : {}) });
        state.sid = d.id; state.nextBudget = null;
        line(`(new session ${d.id} · budget $${d.budget_usd})`, "t-dim");
        startPolling();
      } else {
        line("(next message starts a fresh session)", "t-dim");
      }
      break;
    case "use":
      if (!arg) { line("usage: /use <session-id>", "t-err"); break; }
      stopPolling(); state.sid = arg; state.cursor = -1;
      line(`(attached to ${arg} — replaying recent events)`, "t-dim");
      startPolling(); break;
    case "mode":
      if (!["plan", "default", "auto"].includes(arg)) { line("usage: /mode plan|default|auto", "t-err"); break; }
      setMode(arg);
      line(`(mode -> ${arg})`, "t-dim"); break;
    case "approve": case "deny": {
      if (!state.sid || !state.pendingApproval) { line("(no pending approval)", "t-dim"); break; }
      await api(`/api/sessions/${state.sid}/approve`, "POST",
        { approval_id: state.pendingApproval, approve: cmd === "approve" });
      break;
    }
    case "stop":
      if (!state.sid) { line("(no session)", "t-dim"); break; }
      await api(`/api/sessions/${state.sid}/stop`, "POST", {}); line("(stop requested)", "t-dim"); break;
    case "status":
      if (!state.sid) { line("(no session — type a task or /new)", "t-dim"); break; }
      await poll(); break;
    case "budget": {
      const b = parseFloat(arg);
      if (!(b > 0)) { line("usage: /budget <usd>", "t-err"); break; }
      state.nextBudget = b; line(`(budget for next session: $${b})`, "t-dim"); break;
    }
    case "clear": sb.replaceChildren(); break;
    case "logout":
      ["cm_token", "cm_username", "cm_role"].forEach((k) => localStorage.removeItem(k));
      location.href = "/"; break;
    default: line(`unknown command: /${cmd} — try /help`, "t-err");
  }
}

async function exec(raw) {
  const command = raw.slice(1).trim();
  if (!command) { line("usage: !<shell command>", "t-err"); return; }
  await ensureSession();
  let d = await api("/api/terminal/exec", "POST", { sid: state.sid, command });
  if (d.needs_confirm) {
    line(`⚠ risky command — run anyway? type /yes to confirm`, "t-warn");
    state.confirmExec = command;
    return;
  }
  line(d.output, d.exit_code === 0 ? "t-out" : "t-err");
}

async function handle(text) {
  state.lastActivity = Date.now();
  if (state.sid && !state.timer) startPolling();          // resume after idle pause
  if (text === "/yes" && state.confirmExec) {
    const command = state.confirmExec; state.confirmExec = null;
    const d = await api("/api/terminal/exec", "POST", { sid: state.sid, command, confirm: true });
    line(d.output, d.exit_code === 0 ? "t-out" : "t-err");
    return;
  }
  state.confirmExec = null;
  if (text.startsWith("/")) return slash(text);
  if (text.startsWith("!")) return exec(text);
  await ensureSession();
  await api(`/api/sessions/${state.sid}/message`, "POST",
    { text, files: [], mode: state.mode });
}

/* ---------------- input ---------------- */

input.addEventListener("input", triggerMonkeyTyping);

input.addEventListener("keydown", async (ev) => {
  if (ev.key === "ArrowUp") {
    if (state.histIdx < state.hist.length - 1) state.histIdx += 1;
    input.value = state.hist[state.hist.length - 1 - state.histIdx] || "";
    ev.preventDefault(); return;
  }
  if (ev.key === "ArrowDown") {
    if (state.histIdx > -1) state.histIdx -= 1;
    input.value = state.histIdx === -1 ? "" : state.hist[state.hist.length - 1 - state.histIdx];
    ev.preventDefault(); return;
  }
  if (ev.key !== "Enter") return;
  const text = input.value.trim();
  input.value = ""; state.histIdx = -1;
  if (!text) return;
  state.hist.push(text);
  line("> " + text, "t-in");
  try {
    setMonkeyState("working", "Sending request...");
    await handle(text);
  }
  catch (err) {
    line(`✗ ${err.message}`, "t-err");
    setMonkeyState("error", `Error: ${err.message}`);
  }
});

document.body.addEventListener("click", (e) => {
  if (!window.getSelection().toString() && e.target.tagName !== "A" && e.target.tagName !== "SELECT" && e.target.tagName !== "BUTTON") input.focus();
});

/* ---------------- boot ---------------- */

(async function boot() {
  line("CodeMonkeys terminal — the same agent loop as the console, CLI-style.", "t-banner");
  setMonkeyState("idle", "Ooh ooh! Ready.");
  
  if (!state.token) {
    line("no login token found — sign in at the main console first:", "t-err");
    const d = document.createElement("div");
    const a = document.createElement("a"); a.href = "/"; a.textContent = "→ open the console to log in";
    d.appendChild(a); sb.appendChild(d);
    setStatus("not logged in"); input.disabled = true; return;
  }
  try {
    const me = await api("/api/me");
    state.role = me.role || state.role;
    statusRight.textContent = `${me.username} (${state.role})`;
    line(`logged in as ${me.username} (${state.role})`, "t-dim");
    line(state.role === "Owner"
      ? "type a task, !cmd for a one-shot shell command, /help for commands"
      : "type a task to drive the agent, /help for commands", "t-dim");
    setStatus("ready — no session yet");
    
    // Load model selectors
    await loadModels();
  } catch (err) {
    line(`✗ session invalid (${err.message}) — log in again at /`, "t-err");
    setStatus("not logged in"); input.disabled = true;
  }
})();
