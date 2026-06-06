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
  account unless `OPEN_ENROLLMENT=true`
- Session tokens: HMAC-SHA256-signed payloads, 7-day TTL, secret generated on
  first boot (`/data/session_secret.key`, mode 600)
- Every coding endpoint requires the Owner role; unauthenticated → 401, wrong
  role → 403 (fail closed)
- Lockout recovery only via `fly ssh console` (`scripts/reset_access.py`)

## Sandboxing & limits

- File tools are path-jailed to the workspace (realpath prefix check)
- bash runs with cwd=workspace, 180 s timeout, output capped
- Per-session USD budget halts the loop; subagent spawn cap 8; recursion depth 1

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

## Known limitations (v0.1)

- bash is jailed by cwd, **not** by kernel sandboxing — a hostile prompt could
  read app files or env vars on the machine. Mitigation: the machine holds
  nothing but CodeMonkeys itself; GITHUB_TOKEN is the most sensitive item.
- Single-machine trust boundary; no per-agent isolation yet (worktrees planned)
- No rate limiting on login (TOTP + PBKDF2 make brute force impractical, but
  add fail2ban-style lockout before opening enrollment)
- External CDN (Tailwind) and QR service used by the frontend — acceptable for
  a single-owner tool; vendor them before any multi-user use
