# Design: Per-user isolation (Standing list S6)

**Status:** PROPOSED — design only, no code. Needs an owner decision before any
build. Authored 2026-06-07 (overnight wave 13).

**Why this is design-first:** isolation is the single largest architectural gap
(`docs/STATE.md` "Known gaps"), it touches auth/session/workspace/secret
boundaries at once, and the right scope depends on a product decision the owner
owns: *is CodeMonkeys single-tenant-with-invites, or genuinely multi-tenant?*
Building the wrong scope is expensive to undo. This doc lays out the gap, the
options, and a recommended phased plan so the owner can pick.

---

## 1. Current state (what's shared today)

CodeMonkeys today is effectively **single-trust-domain**: every authenticated
member is as powerful as every other, and the Owner role only gates *config*
(models/keys/invites/MCP), not *data*.

| Resource | Today | File / symbol |
|----------|-------|---------------|
| Sessions | One global `SESSIONS` dict, **no creator/owner field**. Any member can list/read/message/stop/**delete** any session. | `server.py` `SESSIONS`, `session_list`/`session_*` are `verify_user` |
| Workspace | One shared `WORKSPACE_DIR` for all members + all sessions. | `WORKSPACE_DIR` |
| GitHub token | One shared `GITHUB_TOKEN`; every member's agent pushes/clones as it. | `_auth_url`, repos endpoints |
| Shell / bash | Shared, unjailed at the OS level (cwd-jail only — see SECURITY.md "conceded kernel-sandbox gap" + the #44 finding). | `t_bash` |
| Model keys | One key-per-provider config shared by all. | `model_config.json` |
| Blackboard / memory | Keyed by task slug, not user — shared namespace. | `.codemonkeys/blackboard-*.md` |

**Consequence:** invited members are fully trusted co-tenants. That is fine for
the current deployment (Owner + a few trusted devs) but blocks opening
enrollment to semi-trusted users, and it means one compromised/ malicious member
(or a prompt-injected agent in any session) reaches **everyone's** work and the
shared token.

## 2. Threat model

Actors, weakest-trust first:
- **A. Anonymous / unauthenticated** — already handled (fail-closed 401/403).
  Out of scope here.
- **B. Authenticated Member, honest-but-curious** — should not be able to read
  or mutate another member's sessions, files, or history. *Not enforced today.*
- **C. Authenticated Member, malicious** — actively tries to read others' data,
  steal the shared token, or use another member's session. *Not contained today.*
- **D. Prompt-injected agent** (a session whose task text / fetched content
  turns the model hostile) — runs bash/tools with the session's authority.
  Today that authority = the whole box (see #44). Isolation should shrink the
  blast radius to *that session's* sandbox.

**Non-goal:** defending the Owner against themselves, or defending against a Fly
host compromise. The machine remains the ultimate trust boundary.

## 3. Requirements (what "isolated" must mean)

1. **Session ownership.** Every session is bound to the member who created it;
   only that member (and the Owner, read-only for support) can list/read/
   message/stop/delete it.
2. **Workspace isolation.** A session's file tools + bash see only that
   session's (or that user's) files — not other users' repos/artifacts.
3. **Secret isolation.** A member's agent cannot read another member's secrets,
   and ideally cannot read the *shared* GitHub token / model keys via the shell
   (this is the #44 finding — isolation and the bash-sandbox decision overlap).
4. **Memory isolation.** Blackboard / fractal-memory / KB scoped per owner.
5. **No regression** to the single-Owner experience (the common case must stay
   one-click simple).

## 4. Hard constraints

- **One Fly machine, one Python process** today (scale-to-zero, own volume).
- **No local Docker on the dev host** (Chromebook) — anything requiring local
  container builds is painful to iterate.
- **bash is same-uid, cwd-jailed only.** True isolation of the *shell* needs OS
  sandboxing (separate uid / namespaces / seccomp), which is the same unsolved
  problem as the #44 exfil finding. **Filesystem-jail isolation is cheap;
  shell-level isolation is not.** The doc treats them as separate layers.

## 5. Options

### Layer 1 — Session→user binding (cheap, high value, do first)
Add `owner` (username) to each session dict + persisted index. Gate every
`/api/sessions/{sid}/*` on `session.owner == caller or caller is Owner`. Filter
`/api/sessions` to the caller's own (Owner sees all, flagged read-only for
others). Scope blackboard/memory/digest/pattern endpoints the same way.
- **Effort:** S–M. Pure app logic, no infra.
- **Closes:** threat B and most of C's *data* reach (one member can no longer
  read/delete another's sessions or memory).
- **Does NOT close:** filesystem or shell sharing (a malicious member's *agent*
  can still `cat` another user's files if they share `WORKSPACE_DIR`).

### Layer 2 — Per-user (or per-session) workspace subdir jail (cheap–medium)
Give each user a `WORKSPACE_DIR/u/<username>/` root (or per-session
`.../s/<sid>/`); the path-jail realpath check anchors to that subroot instead of
the shared root. Repos clone under it; file tools + bash `cwd` there.
- **Effort:** M. Touches `_jail`, repos endpoints, bash cwd, session creation.
- **Closes:** honest-but-curious file crossover (threat B at the FS layer).
- **Does NOT close:** a *malicious* agent — `bash` is cwd-jailed, not chrooted,
  so `cat ../<other-user>/...` still works (the #44 gap). Layer 2 is a privacy
  boundary, **not** a security boundary, until Layer 4.

### Layer 3 — Per-user secrets (medium)
Per-user GitHub token + per-user model keys (or per-user budgets on a shared
key). Requires UI + storage changes; pairs with the per-user-key billing the
P2 work deferred elsewhere in the fleet.
- **Effort:** M–L. **Closes:** shared-token blast radius (threat C/D can't act
  as everyone).
- Gated on a product decision (do members bring their own keys?).

### Layer 4 — Real shell sandbox (large, the only true security boundary)
Run the bash tool (and ideally each session's agent) under a separate uid
and/or a mount+pid namespace + seccomp, so `cat ../` and `/proc/<server>/environ`
stop working. This is the same fix the #44 finding needs.
- **Effort:** L, plus Fly infra (the app runs as one process; spawning
  namespaced children needs `unshare`/`bwrap`-style tooling in the image).
- **Closes:** threat C/D at the OS layer — the *only* option that makes Layers
  1–3 real against a malicious agent rather than just honest-but-curious.
- **Alternative:** per-user Fly machines (one micro-VM per tenant). Strongest
  isolation, highest ops cost; likely overkill unless going真 multi-tenant.

## 6. Recommended phased plan

1. **Phase 1 — Layer 1 (session→user binding).** Highest value/effort ratio;
   makes the product honestly multi-user for *trusted* members and is a clean,
   testable, reviewable PR. **Recommend doing this regardless** of the bigger
   decision — it's correct even single-tenant (audit clarity) and unblocks
   open-enrollment-to-trusted.
2. **Phase 2 — Layer 2 (workspace subdir jail)** + scope memory/KB per user.
   Privacy boundary for honest members.
3. **Decision gate.** Only pursue Layers 3–4 if the owner wants
   **semi-trusted** multi-tenancy. If CodeMonkeys stays "Owner + trusted devs,"
   Layers 1–2 are sufficient and Layer 4 can stay the documented residual
   (shared with #44).
4. **Phase 3 (if multi-tenant) — Layer 4 shell sandbox**, which simultaneously
   resolves the #44 exfil finding. Then Layer 3 secrets.

## 7. Open questions for the owner

1. **Tenancy intent:** single-tenant-with-trusted-invites (Layers 1–2 enough),
   or semi-trusted multi-tenant (needs Layer 4)? *This decides the whole scope.*
2. **Session visibility for the Owner:** should the Owner retain read-only
   visibility into all members' sessions (support/moderation), or be fully
   walled out? (Recommend read-only visibility, clearly labeled.)
3. **Per-user secrets (Layer 3):** members bring their own model/GitHub keys, or
   share the Owner's with per-user budgets?
4. **Sandbox appetite (Layer 4):** is per-session `bwrap`/namespace sandboxing
   on the single Fly machine acceptable, or is per-user Fly machines preferred
   (cost vs isolation)? This is the same call as the #44 bash-exfil decision —
   **resolve them together.**

## 8. Relationship to other work
- **#44 (bash env scrub) + questions.md bash-exfil note** — Layer 4 is the real
  fix for both; track as one decision.
- **Fleet P2 isolation** (MeniscusMaximus) solved a similar problem with
  per-user dirs — reuse that pattern for Layer 2.
- **Blackboard / fractal memory / two-layer KB** all currently share a namespace;
  Layer 1 scoping must extend to them.

---
*No code in this PR. If the owner approves Phase 1, it ships as its own
`work/session-ownership` PR with tests + a red-team pass (it's an auth boundary).*
