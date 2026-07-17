# CodeMonkeys — Security

## Threat model in one line

This app gives an LLM a shell. Treat the whole Fly app as the blast radius and
keep that radius away from everything else.

## Hard rules

1. **Own app, own volume.** Never co-locate CodeMonkeys with any other app's
   machine or data volume. It executes arbitrary code; the only data it should
   be able to reach is its own workspace.
2. **Scoped GitHub token.** Fine-grained PAT, only the repos agents may touch,
   Contents read/write only. Rotate it if anything looks off.
3. **Secrets in env/Fly secrets or /data — never in the repo.** `data/` is
   gitignored; model keys live in `/data/model_config.json` on the volume.
4. **Approval gates stay on.** Pushes, deploys, `rm -rf`, `git reset --hard`,
   `git clean`, `sudo` require a human click. Don't add bypasses.

## Auth design

- PIN hashed with PBKDF2-HMAC-SHA256, 200k iterations, per-user salt
- Mandatory per-user TOTP (RFC 6238); registration closes after first (Owner)
  account unless `OPEN_ENROLLMENT=true`. The enrollment QR is rendered locally
  (segno → SVG data URI) so the shared secret never leaves the machine.
- Session tokens: HMAC-SHA256-signed payloads, 7-day TTL, secret generated on
  first boot (`/data/session_secret.key`, mode 600)
- Every coding endpoint requires the Owner role; unauthenticated → 401, wrong
  role → 403 (fail closed)
- Login is brute-force throttled on **both** factors: the PIN/TOTP path
  (`/api/login`) and the passkey path (`/api/webauthn/login/*`) share the same
  counters, so a lock covers both. The throttle has **three dimensions**, any of
  which trips an HTTP 429 + `Retry-After`: per-account (`LOGIN_MAX_FAILS`), per
  source-IP (`LOGIN_IP_MAX_FAILS`, keyed on `Fly-Client-IP`) so one source is
  bounded across *all* usernames it tries, and a system-wide global ceiling
  (`LOGIN_GLOBAL_MAX_FAILS`) as a circuit-breaker for distributed guessing. The
  state is **persisted** (`data/login_throttle.json`, write-through) so locks and
  counters survive a restart. Invited (`must_reset`) accounts log in
  username-only (owner-ratified 2026-07-17, replacing the C-2 setup PIN; MFA
  not yet enrolled) — the throttle bounds username guessing and is deliberately
  not cleared until `/api/account/setup` completes. The token issued to a
  pending account is scope-limited: `verify_token` rejects `must_reset`
  accounts, so it only works for `/api/account/setup`. Residual (accepted):
  someone who learns a pending invite username before its owner first logs in
  can claim that account; auto-generated `dev-<hex>` names keep the window
  unguessable. See "Known limitations" for tunables and residuals.
- Passkeys are self-service revocable: `GET /api/webauthn/credentials` lists the
  caller's own passkeys (handles only — no key material) and `DELETE
  /api/webauthn/credentials/{cred_id}` removes one. The filter only ever touches
  the **caller's own** credential list (no IDOR — a known foreign `cred_id` finds
  no match → 404). Removing every passkey is allowed: PIN+TOTP remain, so it can
  never lock the account out.
- Lockout recovery only via `fly ssh console` (`scripts/reset_access.py`)

## Sandboxing & limits

- File tools are path-jailed to the workspace (realpath prefix check)
- bash runs with cwd=workspace, 180 s timeout, output capped
- **Subprocess env scrub (defense-in-depth, NOT a boundary).** The `bash` tool,
  the owner terminal, and stdio MCP servers run with `_subprocess_env()` — host
  env vars whose name looks like a secret (`*TOKEN*`, `*SECRET*`, `*_KEY`,
  `PGPASSWORD`, `DATABASE_URL`, …) are stripped, so a command can't grab one
  with the naive `printenv X | base64` (a transform that evades the output
  redactor). PATH/HOME/SSH_AUTH_SOCK and other essentials are safelisted.
  **This does not close the conceded sandbox gap below** — it only removes the
  laziest vector.
- Baseline browser security headers on every response: `X-Frame-Options:
  SAMEORIGIN` + CSP `frame-ancestors 'self'` (anti-clickjacking — a cross-origin
  page can't frame-and-phish the PIN/TOTP login), `X-Content-Type-Options:
  nosniff`, `Referrer-Policy: no-referrer`. CSP is kept minimal (no `script-src`)
  so it doesn't break the Tailwind CDN; a stricter `script-src` pairs with
  vendoring Tailwind (see Known limitations).
- **Notify-on-done (outbound egress).** When a run finishes, the server can POST
  a completion ping to an owner-configured `NOTIFY_WEBHOOK_URL` (e.g. self-hosted
  ntfy). **OFF unless the URL is set.** Destination is env-only (no user/model
  influence on where it goes); payload is JSON **body** only (no CRLF/header
  injection), `allow_redirects=False`, 5 s timeout, best-effort in a daemon
  thread (a down notifier never affects the run). Payload is ops-metadata
  (`session/title/repo/status/outcome/spent_usd/ts`) with title/repo
  **best-effort** scrubbed — but they are user-supplied (and an issue title via
  the GitHub webhook is *external*), so treat the notify text as untrusted on the
  receiving end and set `NOTIFY_WEBHOOK_SECRET` (HMAC-SHA256, `X-CodeMonkeys-
  Signature`) so the receiver can authenticate it. Not a guarantee of zero
  secrets — `_scan_secrets` is a best-effort blocklist.
- **Secret-scan write guard.** `write_file`, `edit_file`, and `apply_patch`
  scan the content they persist (for `apply_patch`, only the added `+` lines)
  for obvious credential shapes — AWS access-key id, GitHub `ghp_`/`gho_`…,
  OpenAI `sk-`, Slack `xox*`, Google `AIza…`, PEM private-key blocks. A match
  appends a `⚠ SECRET WARNING` (naming the *kind*, never the value) to the tool
  result and into the audit log. **Non-blocking by design:** legit files
  (`.env.example`, fixtures) carry shaped tokens too, so the warning is a
  visible deterrent, not a hard stop — it surfaces a leak in the result + log
  instead of letting it commit silently. Conservative patterns to avoid crying
  wolf; not a DLP system.
- **Approval-gate matching is quote/escape-resistant.** Risky commands
  (`git push` incl. `--force`/`-f`, `fly`/`flyctl`, `rm -rf`, `git reset
  --hard`, `git clean`, `git branch -D`, `gh repo delete`, `sudo`, plus
  system-level/irreversible verbs `dd`, `mkfs`, recursive `chmod`/`chown` (any
  flag form — `-R`/`-fR`/`--recursive`), `truncate`, redirect-into-a-block-
  `/dev/` node, net-pipe-to-interpreter (`curl … | sh|bash|zsh|python|…`), and
  `shutdown`/`reboot`/`halt`/`poweroff`/`telinit`) are detected by `_is_risky`,
  which matches
  `RISKY_PATTERNS` against **both** the raw command and a shlex-normalized form.
  Normalizing first means shell quoting/escaping (`git "push"`, `g''it push`,
  `git\ push`, `"git" push`) can no longer hide a risky verb from the gate; a
  command that fails to tokenize (unbalanced quotes) fails **closed** (gated).
  Normalization errs toward gating: a risky phrase inside a string literal
  (`echo "...rm -rf..."`) also prompts — an extra click, never a missed action.
  **Residual:** runtime-only constructs resolved by bash at execution time —
  variable expansion (`g=git; $g push`), command substitution (`$(echo git) push`),
  and `eval` — are not visible to static matching and remain an accepted residual
  risk of gating a raw shell string (the kernel-sandbox gap below is the backstop).
- **Auto-mode risky _bash_ commands pass a debate-verify gate** (IDEATION #7).
  Auto mode has no human in the loop; before a `_is_risky` **bash** command
  executes there, three verifiers (intent / safety / security lenses, no tools —
  single judgment calls, not subagent loops) each try to refute it given recent
  session context. They run on **distinct providers when 3+ are keyed**
  (decorrelates the panel so one model's blind spot/jailbreak/injection can't
  sink all three); with fewer keyed providers the cheapest is reused, so the
  panel degrades to correlated lenses on one model — still useful, but weaker.
  Majority refute (≥2/3) = BLOCKED, reasons returned to the model. **Fail
  closed:** a verifier error, garbled verdict, or missing provider counts as a
  refutal. Verifier calls are metered into the session ledger and emit
  `debate_verify` events. default/plan keep the human approval gate unchanged.
  **Scope & residual:** the same panel gates risky `bash` **and** every
  auto-mode **MCP** tool call (W7 — an Owner-added connector is still a
  prompt-injection-reachable side effect with no human in the loop). The
  verifiers share `_is_risky`'s static-match residual above (for bash), and an
  LLM verdict is probabilistic. Treat this as **damage reduction for auto mode,
  never an authorization boundary** — the default-mode human gate is the only
  real boundary.
- Per-session USD budget halts the loop; subagent spawn cap 8; recursion depth 1
- **Plan mode is read-only, end to end.** Its toolset is read/list/glob/grep +
  `spawn_agent` + `save_spec`; it has no write_file/edit_file/bash. Subagents
  spawned from plan mode are intersected to the read-only set, so `spawn_agent`
  cannot be used to escalate to a write/bash-capable corps agent. The only thing
  plan mode may write is planning artifacts via `save_spec`, which is jailed to
  `<workspace>/.codemonkeys/specs/<slug>/<artifact>.md` (tighter than the general
  workspace jail; realpath-checked + `O_NOFOLLOW`, slug sanitized & length-capped).

## Cloud-egress consent (M-4, issue #67)

- Every outbound LLM call funnels through `call_model`; it is gated on the
  session owner's **recorded, revocable, per-user consent**
  (`data/egress_consent.json` — status, timestamp, bounded grant/revoke
  history). The gate raises **before any bytes leave the box** (fail closed);
  the debate-verify panel carries the same check. Erasing an account (M-7)
  cascades the consent record away.
- Self-service: `GET/POST /api/me/consent/egress` (any active account).
  Revocation takes effect on the **next** model call, including mid-run.
- `EGRESS_CONSENT_MODE` decides what an ABSENT record means:
  `explicit` (default, **Owner-ratified 2026-07-13** — affirmative grant
  required, absent → blocked) or `byok-implied` (owner BYO keys read as
  org-level consent, absent → allowed; explicit revocation still always
  blocks). An unrecognised value falls back to `explicit`, never open. See
  issue #67 "Owner-reserved" for the ratification.
- **Frontend** (`static/forge/`): a just-in-time modal (`#modal-egress-consent`
  in `index.html`, driven by `egress-consent.js`) checks `GET
  /api/me/consent/egress` before the one frontend call that can trigger
  `call_model` (`POST /api/sessions/{sid}/message` — the choke point shared by
  the main app, workbench, and Agents Hub via `window.api`) and blocks with a
  plain-language grant/decline prompt when consent isn't already granted. The
  standalone terminal page (`terminal.html`/`terminal.js`, which has no shared
  DOM with the main app) reuses the same `egress-consent.js` module but falls
  back to a blocking `confirm()` prompt plus a `/consent [grant|revoke]`
  command, since it has no modal markup of its own. Settings → Account has a
  toggle to revoke (or re-grant) consent at any time, calling the same
  `POST /api/me/consent/egress` endpoint. A mid-run `EgressConsentError` (e.g.
  consent revoked from another tab while a run is in flight) is detected by
  its fixed message prefix and rendered with its own "Grant cloud-egress
  access" action instead of a generic error. None of this changes the backend
  gate itself — it's UI in front of an already fail-closed `_require_egress_consent`.

## MCP connectors

- MCP server config (`/api/mcp` CRUD, `mcp_config.json`) is **Owner-only**, same
  fail-closed guard as `/api/models`. Bearer tokens are write-only — stored on
  `/data`, never returned by any GET nor emitted in events.
- **`readOnlyHint` is NOT trusted for gating.** It is a remote-controlled hint
  used only as a UI badge. Plan mode exposes **no** MCP tools; in default mode
  **every** MCP tool call passes through the human approval gate; auto skips (as
  with bash). A malicious server cannot mark itself read-only to bypass approval.
- MCP server URLs must be `https://` (or `http://` only for localhost/127.0.0.1/::1).
- Hostile-server blast radius is capped: per-request wall-clock deadline + 256 KB
  read cap on the JSON-RPC/SSE stream (no slowloris session hang); ≤128 merged
  tools/session and per-description cap (no context/cost amplification);
  namespaced `mcp_<slug>_<tool>` is first-writer-wins (no cross-server shadowing).
- **Accepted residual risk:** an Owner who adds a trusted server still grants that
  third party a prompt-injection channel into a model holding `bash`; the approval
  gate limits mutating MCP calls but not read-only data flow. The agent could also
  write `mcp_config.json` via unsandboxed `bash` (same kernel-sandbox gap below).

## MCP OAuth 2.1 (Google Drive, Microsoft 365, etc.)

### Token store
- Access tokens, refresh tokens, and expiry times are stored in a **separate file**
  `DATA_DIR/mcp_tokens.json`, written with mode **0600** (owner-readable only).
- This file is **never** returned by any API endpoint (`/api/mcp` GET surfaces only
  `oauth_connected: bool`), **never** logged, and **never** emitted in SSE events.
- `client_secret` (for confidential OAuth clients) lives in `mcp_config.json` on
  `/data` — consistent with the existing bearer token storage policy. This is
  plaintext-at-rest on the Fly volume. Mitigation: the volume is encrypted-at-rest
  by Fly; the machine holds no other tenants' data; the secrets are scoped to the
  specific OAuth app registered by the owner.

### PKCE + state CSRF protection
- Every OAuth flow uses **PKCE S256** (RFC 7636): a 64-char random `code_verifier`
  is generated with `secrets.token_urlsafe`, and `code_challenge = BASE64URL(SHA256(verifier))`
  is sent to the authorization endpoint. The verifier is stored only in server-side
  memory and sent to the token endpoint — never to the browser.
- A **cryptographically random `state`** (32-byte base64url from `secrets.token_urlsafe`)
  is stored in an in-memory dict with a 600-second TTL.  The CSRF protection is
  **state-secrecy + PKCE** (single-use, TTL-bounded): callbacks with an unknown,
  expired, or already-consumed state are rejected (`_oauth_state_pop`).  The
  `username` field in the state entry identifies who initiated the flow as audit
  context but is **not enforced at callback time** — the callback endpoint carries
  no auth header (it is a browser redirect) and therefore cannot verify the
  initiating session identity.  The `error_description` from the provider is never
  echoed to the callback page (avoids reflected provider-controlled text).

### Redirect URI derivation
- The redirect URI is derived from `request.base_url` at call time — never hardcoded.
  It resolves to `<scheme>://<host>/api/mcp/oauth/callback`. This means:
  - On localhost it is `http://127.0.0.1:8080/api/mcp/oauth/callback`.
  - On Fly it is the `https://…fly.dev/api/mcp/oauth/callback` (or custom domain).
- **Owner action required:** register this exact URI in the OAuth app at the provider
  (Google Cloud Console or Azure Entra ID) before initiating the flow. A mismatch
  causes the provider to reject the authorization request.

### Refresh handling
- Before every MCP request on an OAuth server, `_mcp_oauth_access_token` checks
  `expires_at`. If the token expires within 60 seconds, it uses the stored
  `refresh_token` to obtain a fresh pair (RFC 6749 §6) and writes the result back
  to the token store (0600). Fail-closed: if refresh fails, the MCP call returns an
  error to the agent rather than proceeding with a stale or absent token.

### Accepted residual risk (OAuth-specific)
- The owner must register the OAuth app at the provider (Google Cloud Console /
  Azure Entra ID) and supply the correct `client_id` (and optionally `client_secret`
  for confidential clients). CodeMonkeys does not automate app registration.
- `client_secret` at rest in `mcp_config.json` is plaintext on `/data` — same risk
  posture as bearer tokens. If a higher security bar is required, store the secret
  externally and inject it as a Fly secret / environment variable instead of in the
  config UI. This is a known gap; addressing it requires a secrets-envelope layer.
- The OAuth callback endpoint (`/api/mcp/oauth/callback`) is publicly reachable
  (no auth header — the browser redirect cannot carry one). The state+PKCE
  mechanism is the sole CSRF guard; it is correct per RFC 7636 but depends on
  server-side state not being leaked. The in-memory dict is process-local; a
  restart during the 10-minute flow window will lose pending states.
- **Gate before production:** this code requires A5 red-team review and a live
  Google/Azure app registration test before the feature is opened to use.

## Known limitations (v0.1)

- bash is jailed by cwd, **not** by kernel sandboxing — a hostile prompt could
  read app files or env vars on the machine. The `_subprocess_env()` scrub
  (above) removes secret-named host env vars from the shell, but this is
  defense-in-depth, **not a boundary**. A determined command still reaches:
  - the server's own **`/proc/<pid>/environ`** (same-uid child) — every secret
    Fly injected at startup, regardless of the child's scrubbed env;
  - **`/data` files** via `cat ../<file>` (bash is cwd-jailed, not chroot'd):
    `session_secret.key` (HMAC signing key → session forgery / auth bypass),
    `model_config.json` (model API keys), `mcp_tokens.json` (OAuth tokens),
    `users.json` (PBKDF2 hashes).
  Transforms (`| base64`, `| rev`) evade the output redactor, and `/data`
  secrets aren't in the redactor's value set at all. **Real fix = sandbox bash**
  (separate uid / mount+pid namespace / seccomp) and/or evict startup secrets
  from the server environ + encrypt `/data` secrets at rest. Tracked as an
  owner decision (see questions.md). Mitigation today: the machine holds nothing
  but CodeMonkeys itself, and risky bash is approval-gated (default) /
  debate-verified (auto).
- Single-machine trust boundary; no per-agent isolation yet (worktrees planned)
- Login brute-force throttle is in place (fail2ban-style) with three sliding-
  window dimensions, all sharing `LOGIN_WINDOW_SEC` (default 300 s) and
  window dimensions, all sharing `LOGIN_WINDOW_SEC` (default 300 s) and
  `LOGIN_LOCKOUT_SEC` (default 900 s), each returning HTTP 429 + `Retry-After`:
  `LOGIN_LOCKOUT_SEC` (default 900 s), each returning HTTP 429 + `Retry-After`:
  - **per-account** — `LOGIN_MAX_FAILS` (default 10) failures locks that username;
  - **per-account** — `LOGIN_MAX_FAILS` (default 10) failures locks that username;
  - **per source-IP** — `LOGIN_IP_MAX_FAILS` (default 30, `<=0` disables) locks one
  - **per source-IP** — `LOGIN_IP_MAX_FAILS` (default 30, `<=0` disables) locks one
    `Fly-Client-IP` across *all* usernames it attempts;
    `Fly-Client-IP` across *all* usernames it attempts;
  - **global** — `LOGIN_GLOBAL_MAX_FAILS` (default 200, `<=0` disables) is a
  - **global** — `LOGIN_GLOBAL_MAX_FAILS` (default 200, `<=0` disables) is a
    system-wide circuit-breaker for guessing distributed across many IPs/usernames.
    system-wide circuit-breaker for guessing distributed across many IPs/usernames.


  The throttle runs **before** any PBKDF2 work and applies to unknown usernames
  The throttle runs **before** any PBKDF2 work and applies to unknown usernames
  too (no account-existence oracle). State is written through to
  too (no account-existence oracle). State is written through to
  `data/login_throttle.json` and reloaded at startup, so locks **survive a
  `data/login_throttle.json` and reloaded at startup, so locks **survive a
  restart** (no longer fail-open on reboot). Both tracking dicts are bounded
  restart** (no longer fail-open on reboot). Both tracking dicts are bounded
  (`LOGIN_TRACK_CAP`) with locked/near-threshold entries protected from eviction,
  (`LOGIN_TRACK_CAP`) with locked/near-threshold entries protected from eviction,
  so IP-spoofing or username-spam floods can't grow memory or reset a victim.
  so IP-spoofing or username-spam floods can't grow memory or reset a victim.
  **Residuals:** (a) a global lock is a deliberate availability trade — a
  **Residuals:** (a) a global lock is a deliberate availability trade — a
  sufficiently large distributed flood can freeze *all* logins for the cooldown;
  sufficiently large distributed flood can freeze *all* logins for the cooldown;
  the ceiling is set high to make this a genuine emergency brake, and the owner
  the ceiling is set high to make this a genuine emergency brake, and the owner
  can recover via `fly ssh console` (`scripts/reset_access.py`) or by deleting
  can recover via `fly ssh console` (`scripts/reset_access.py`) or by deleting
  `data/login_throttle.json` and restarting; (b) an attacker who knows a username
  `data/login_throttle.json` and restarting; (b) an attacker who knows a username
  can still deliberately lock that one account for the cooldown; (c) the lock
  can still deliberately lock that one account for the cooldown; (c) the lock
  check and the failure-record are separate critical sections, so up to ~(server
  check and the failure-record are separate critical sections, so up to ~(server
  concurrency) extra in-flight guesses can land before a lock arms each cycle —
  concurrency) extra in-flight guesses can land before a lock arms each cycle —
  bounded by CPU-bound PBKDF2, never an unbounded bypass; (d) off-Fly, the
  bounded by CPU-bound PBKDF2, never an unbounded bypass; (d) off-Fly, the
  `Fly-Client-IP` header is client-supplied and could be spoofed to dodge the
  `Fly-Client-IP` header is client-supplied and could be spoofed to dodge the
  per-IP lock — on Fly the proxy sets it authoritatively, and the global ceiling
  per-IP lock — on Fly the proxy sets it authoritatively, and the global ceiling
  (keyed on nothing the client controls) backstops spoofing either way.
  (keyed on nothing the client controls) backstops spoofing either way.
- The TOTP enrollment QR is now generated **locally** server-side (segno, SVG
  data URI) — the otpauth secret is never sent to an external QR service. If
  data URI) — the otpauth secret is never sent to an external QR service. If
  segno is not installed the UI shows the secret for manual entry (it never
  segno is not installed the UI shows the secret for manual entry (it never
  falls back to an external CDN). **Still external:** Tailwind is loaded from a
  falls back to an external CDN). **Still external:** Tailwind is loaded from a
  CDN (`cdn.tailwindcss.com`) — cosmetic, no secret, but vendor it before any
  CDN (`cdn.tailwindcss.com`) — cosmetic, no secret, but vendor it before any
  multi-user/offline use.
  multi-user/offline use.
