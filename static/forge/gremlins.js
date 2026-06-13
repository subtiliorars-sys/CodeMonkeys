/* Code Gremlins — concept surface + one-click deploy prompt */
"use strict";

const CodeGremlins = {
  DEPLOY_PROMPT:
    "Deploy spawn_agent code-gremlins on the code from this session (and any files we changed). " +
    "Roast every flaw: correctness gaps, wasted work, simpler paths, and load/stress risks. " +
    "Run local stress checks where safe. Insult the code with file:line evidence — not vibes. " +
    "Escalate to red-team if you find auth, secrets, or cross-user data issues.",

  init() {
    this._wireModal();
    this._wireLanding();
    this._wireComposer();
  },

  open() {
    document.getElementById("modal-gremlins")?.classList.remove("hidden");
  },

  close() {
    document.getElementById("modal-gremlins")?.classList.add("hidden");
  },

  unleash(target) {
    const msg = document.getElementById("msg");
    if (!msg) return;
    let prompt = this.DEPLOY_PROMPT;
    if (target === "workspace") {
      prompt =
        "Deploy spawn_agent code-gremlins on the workspace repos. " +
        "Prioritize recently modified files. " + this.DEPLOY_PROMPT.split(". ").slice(1).join(". ");
    }
    msg.value = prompt;
    msg.focus();
    this.close();
    const hint = document.getElementById("gremlins-toast");
    if (hint) {
      hint.textContent = "Gremlin raid queued in composer — hit Send when ready.";
      hint.classList.remove("hidden");
      setTimeout(() => hint.classList.add("hidden"), 4000);
    }
  },

  _wireModal() {
    document.getElementById("btn-gremlins")?.addEventListener("click", () => this.open());
    document.getElementById("gremlins-close")?.addEventListener("click", () => this.close());
    document.getElementById("gremlins-unleash-session")?.addEventListener("click", () => this.unleash("session"));
    document.getElementById("gremlins-unleash-workspace")?.addEventListener("click", () => this.unleash("workspace"));
    document.getElementById("modal-gremlins")?.addEventListener("click", (e) => {
      if (e.target?.id === "modal-gremlins") this.close();
    });
  },

  _wireLanding() {
    document.getElementById("landing-gremlins")?.addEventListener("click", () => this.open());
  },

  _wireComposer() {
    document.getElementById("btn-gremlin-raid")?.addEventListener("click", () => this.unleash("session"));
  },
};

window.CodeGremlins = CodeGremlins;
document.addEventListener("DOMContentLoaded", () => CodeGremlins.init());
