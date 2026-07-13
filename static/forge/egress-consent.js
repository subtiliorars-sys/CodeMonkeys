/* M-4 cloud-egress just-in-time consent (issue #67).
 *
 * Every trigger that can start a model call funnels through this module
 * before the actual POST /api/sessions/{sid}/message fires:
 *   - app.js / workbench.js / agents-hub.js share window.api (app.js:31) — one
 *     patch there covers all three.
 *   - terminal.js is a standalone page with its own local api(); it has no
 *     modal DOM, so it falls back to a blocking confirm() prompt below.
 *
 * Backend contract (server.py "M-4 cloud-egress consent"):
 *   GET  /api/me/consent/egress  -> {status, updated_at, mode, effective_allowed, reason}
 *   POST /api/me/consent/egress {"granted": true|false}
 * The gate itself lives server-side and fails closed; this file only adds the
 * UI in front of it — it never changes what the server allows.
 */
"use strict";

const EgressConsent = (() => {
  let pending = null; // in-flight ensure() promise so concurrent triggers share one prompt

  function modalEls() {
    return {
      backdrop: document.getElementById("modal-egress-consent"),
      grant: document.getElementById("egress-consent-grant"),
      decline: document.getElementById("egress-consent-decline"),
      declinedMsg: document.getElementById("egress-consent-declined-msg"),
    };
  }

  function showDomModal(apiFn, el) {
    return new Promise((resolve) => {
      el.declinedMsg?.classList.add("hidden");
      el.backdrop.classList.remove("hidden");
      const cleanup = () => { el.grant.onclick = null; el.decline.onclick = null; };
      el.grant.onclick = async () => {
        el.grant.disabled = true;
        try {
          await apiFn("/api/me/consent/egress", "POST", { granted: true });
          cleanup();
          el.backdrop.classList.add("hidden");
          resolve(true);
        } catch (e) {
          alert("Couldn't record consent: " + e.message);
          el.grant.disabled = false;
        }
      };
      el.decline.onclick = async () => {
        try {
          await apiFn("/api/me/consent/egress", "POST", { granted: false });
        } catch (e) { /* still block locally even if the write failed */ }
        cleanup();
        el.declinedMsg?.classList.remove("hidden");
        resolve(false);
      };
    });
  }

  async function showConfirmFallback(apiFn) {
    const granted = confirm(
      "Cloud-egress consent required\n\n" +
      "Sending a task to the agent sends your prompt and code to a third-party " +
      "AI model provider. CodeMonkeys needs your explicit consent before that happens.\n\n" +
      "OK = grant consent and continue.\n" +
      "Cancel = decline — model calls stay blocked until you run /consent grant."
    );
    try {
      await apiFn("/api/me/consent/egress", "POST", { granted });
    } catch (e) { /* best-effort; the local choice still governs this page */ }
    return granted;
  }

  function showPrompt(apiFn) {
    const el = modalEls();
    return el.backdrop ? showDomModal(apiFn, el) : showConfirmFallback(apiFn);
  }

  async function ensure(apiFn) {
    if (pending) return pending;
    pending = (async () => {
      let status;
      try {
        status = await apiFn("/api/me/consent/egress");
      } catch (e) {
        return false; // can't confirm consent -> fail closed in the UI too
      }
      if (status.effective_allowed) return true;
      return showPrompt(apiFn);
    })();
    try {
      return await pending;
    } finally {
      pending = null;
    }
  }

  // Re-opens the same prompt on demand (e.g. a "grant access" button on a
  // mid-run consent error, or the settings toggle turning back on).
  function reopen(apiFn) {
    return ensure(apiFn);
  }

  // The exact prefix is fixed server-side (server.py _require_egress_consent).
  function isConsentError(message) {
    return /^Cloud egress blocked \(M-4\)/i.test(message || "");
  }

  return { ensure, reopen, isConsentError };
})();
window.EgressConsent = EgressConsent;

/* ---- Settings > Account tab toggle (main app only — absent on terminal.html) ---- */
document.addEventListener("DOMContentLoaded", () => {
  const toggle = document.getElementById("stn-egress-consent-toggle");
  const label = document.getElementById("stn-egress-consent-label");
  const msg = document.getElementById("stn-egress-consent-msg");
  if (!toggle) return;

  async function refresh() {
    if (typeof window.api !== "function") return;
    try {
      const d = await window.api("/api/me/consent/egress");
      toggle.checked = !!d.effective_allowed;
      label.textContent = d.effective_allowed ? "Cloud model calls allowed" : "Cloud model calls blocked";
      msg.textContent = d.status
        ? `Consent ${d.status}${d.updated_at ? " · " + new Date(d.updated_at * 1000).toLocaleString() : ""}`
        : "No consent decision on record yet — you'll be asked the next time you send a message.";
    } catch (e) {
      msg.textContent = "Couldn't load consent status: " + e.message;
    }
  }

  toggle.addEventListener("change", async () => {
    toggle.disabled = true;
    try {
      await window.api("/api/me/consent/egress", "POST", { granted: toggle.checked });
    } catch (e) {
      alert("Couldn't update consent: " + e.message);
    } finally {
      toggle.disabled = false;
      refresh();
    }
  });

  refresh();
  // Re-sync whenever Settings is (re)opened, so a grant/decline made via the
  // JIT modal (or another tab) since the panel last loaded is reflected here.
  const settingsModal = document.getElementById("modal-settings");
  if (settingsModal) {
    new MutationObserver(() => {
      if (!settingsModal.classList.contains("hidden")) refresh();
    }).observe(settingsModal, { attributes: true, attributeFilter: ["class"] });
  }
});
