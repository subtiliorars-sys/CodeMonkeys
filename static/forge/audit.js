/* N11 — Audit log viewer (owner-only).
   Reads the Bearer token from sessionStorage (same key as app.js),
   calls GET /api/audit with filter params, renders a table. */

const TOKEN_KEY = "cm_token";

function getToken() {
  return sessionStorage.getItem(TOKEN_KEY) || "";
}

function fmtTs(ts) {
  if (!ts) return "—";
  const d = new Date(ts * 1000);
  return d.toISOString().replace("T", " ").slice(0, 19) + "Z";
}

function boolSpan(val) {
  if (val === true  || val === "true")  return `<span class="bool-t">yes</span>`;
  if (val === false || val === "false") return `<span class="bool-f">no</span>`;
  return String(val);
}

function renderDetail(evt) {
  const skip = new Set(["sid", "i", "ts", "type"]);
  const parts = [];
  for (const [k, v] of Object.entries(evt)) {
    if (skip.has(k)) continue;
    if (typeof v === "boolean") {
      parts.push(`${k}: ${boolSpan(v)}`);
    } else if (v !== null && v !== undefined && v !== "") {
      // Truncate very long strings in the cell (already capped server-side too)
      const s = String(v).length > 400 ? String(v).slice(0, 400) + "…" : String(v);
      parts.push(`<b>${k}</b>: ${escHtml(s)}`);
    }
  }
  return parts.join("\n") || "—";
}

function escHtml(s) {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

async function load() {
  const tok = getToken();
  const msgEl = document.getElementById("msg");
  msgEl.className = "";
  msgEl.textContent = "Loading…";

  const type    = document.getElementById("f-type").value;
  const session = document.getElementById("f-session").value.trim();
  const limit   = Math.min(1000, Math.max(1, parseInt(document.getElementById("f-limit").value) || 200));

  const params = new URLSearchParams({ limit });
  if (type)    params.set("type", type);
  if (session) params.set("session", session);

  let data;
  try {
    const resp = await fetch(`/api/audit?${params}`, {
      headers: tok ? { Authorization: "Bearer " + tok } : {},
    });
    if (resp.status === 401 || resp.status === 403) {
      msgEl.className = "err";
      msgEl.textContent = `Access denied (${resp.status}) — owner login required.`;
      return;
    }
    if (!resp.ok) {
      const txt = await resp.text();
      msgEl.className = "err";
      msgEl.textContent = `Error ${resp.status}: ${txt.slice(0, 200)}`;
      return;
    }
    data = await resp.json();
  } catch (e) {
    msgEl.className = "err";
    msgEl.textContent = `Fetch failed: ${e}`;
    return;
  }

  const events = data.events || [];
  msgEl.textContent = data.note || "";

  document.getElementById("hdr-count").textContent =
    `${events.length} event${events.length !== 1 ? "s" : ""}`;

  const tbody = document.getElementById("tbody");
  tbody.innerHTML = "";
  const empty = document.getElementById("empty");

  if (events.length === 0) {
    empty.style.display = "";
    return;
  }
  empty.style.display = "none";

  for (const evt of events) {
    const tr = document.createElement("tr");
    const typeClass = `type-${(evt.type || "").replace(/_/g, "_")}`;
    tr.innerHTML = `
      <td class="ts">${escHtml(fmtTs(evt.ts))}</td>
      <td class="${typeClass}">${escHtml(evt.type || "")}</td>
      <td class="sid">${escHtml((evt.sid || "").slice(0, 12))}</td>
      <td class="detail">${renderDetail(evt)}</td>`;
    tbody.appendChild(tr);
  }
}

/* S-3 (issue #68) — tamper-evidence check of the persisted audit hash chain.
   Calls GET /api/audit/verify (owner-only) and shows intact/tampered. */
async function verifyChain() {
  const el = document.getElementById("chain-status");
  el.style.color = "var(--dim)";
  el.textContent = "verifying…";
  try {
    const tok = getToken();
    const resp = await fetch("/api/audit/verify", {
      headers: tok ? { Authorization: "Bearer " + tok } : {},
    });
    if (resp.status === 401 || resp.status === 403) {
      el.style.color = "var(--red)";
      el.textContent = `access denied (${resp.status}) — owner login required`;
      return;
    }
    const data = await resp.json();
    if (data.ok) {
      el.style.color = "#39d353";
      el.textContent = `chain intact ✓ ${data.entries} entr${data.entries === 1 ? "y" : "ies"}` +
        (data.head ? `, head ${String(data.head).slice(0, 12)}…` : "");
    } else {
      el.style.color = "var(--red)";
      el.textContent = `TAMPERED ✗ ${data.error || "chain verification failed"}` +
        (data.line ? ` (line ${data.line})` : "");
    }
  } catch (e) {
    el.style.color = "var(--red)";
    el.textContent = `verify failed: ${e}`;
  }
}

document.getElementById("btn-refresh").addEventListener("click", load);
document.getElementById("btn-verify").addEventListener("click", verifyChain);

// Trigger load on Enter in filter inputs
["f-type", "f-session", "f-limit"].forEach(id => {
  document.getElementById(id).addEventListener("keydown", e => {
    if (e.key === "Enter") load();
  });
});

// Auto-load on page open
load();
