# Web Terminal — design + red-team (Wave: owner request, branch `work/terminal`)

Owner ask: *"duplicate this exact workflow setup [the Claude Code CLI workflow]…
as a fallback in case people are struggling with the interface."*

This document is Phase A: an honest threat model, a scope decision, and an
adversarial red-team of the chosen design. Phase B (implementation) only happens
on a GO / GO-WITH-FIXES verdict with the fixes applied.

---

## 1. What is actually being asked for

Claude Code is **not a shell**. It is a chat REPL that *runs in* a terminal:
you type a task, an agent loop streams back text, tool calls, and approval
prompts; `!cmd` runs a one-off shell command; `/slash` commands manage sessions.
"Duplicate this exact workflow" therefore means: **a terminal-style REPL over
CodeMonkeys' existing session/agent loop** — not SSH-into-the-container.

Two candidate modes:

| | Mode 1 — "agent terminal" | Mode 2 — raw PTY |
|---|---|---|
| What | CLI-skin REPL driving the existing `/api/sessions/*` loop, plus an owner-only `!cmd` one-shot exec | Interactive `bash` on the Fly container (xterm.js + PTY) |
| New attack surface | One new endpoint (`!cmd` exec); REPL itself reuses existing, already-gated APIs | An unaudited interactive shell on a public app |
| Secrets exposure | Same as today's agent `bash` tool: child env inherits the container env (the conceded kernel-sandbox gap, SECURITY.md); output redaction scrubs known secret values | `env` prints every Fly secret raw; streamed output can't be reliably redacted mid-PTY (escape sequences split values across frames) |
| Receipts | Every command + output lands in the session JSONL like agent bash | Keystroke-level audit is impractical; no per-command receipt boundary |
| Risky-command gate | `_is_risky` + confirm step preserved | Bypassed entirely by design |
| Matches the ask | Yes — it *is* the Claude Code workflow | No — it's a different (admin) tool |

**Scope decision: Mode 1 only. Mode 2 (raw PTY) is NO-GO** — on a public Fly
app it is an always-armed RCE console whose env contains `GITHUB_TOKEN`, model
API keys, and the session-signing secret, with no workable mid-stream redaction
and no per-command receipts. Nothing in the owner's ask requires it. If a raw
PTY is ever revisited it needs its own design + red-team, and at minimum:
owner-only, separate env gate, scrubbed child env, localhost/WireGuard-only.

## 2. Threat model (Mode 1)

The app is reachable by the whole internet on Fly. The terminal feature adds:

1. **A static page** `GET /terminal` (HTML/JS, no secrets, no state).
2. **The REPL**, which calls only *existing* endpoints: `POST /api/sessions`,
   `POST /api/sessions/{sid}/message`, `GET /api/sessions/{sid}/events`,
   `POST /api/sessions/{sid}/approve`, `/stop`. All already require
   `verify_user` (valid HMAC token, active account). The REPL adds **zero new
   server-side capability** — anything it can do, the existing UI can do.
3. **One new endpoint**: `POST /api/terminal/exec` — the `!cmd` one-shot.
   This is deliberate RCE-for-the-owner, so it carries the layered, fail-closed
   gate stack copied from the webhook pattern (PR #36):

   - **Gate 0 — env gate, default OFF, 404.** `TERMINAL_ENABLED` must be
     explicitly true or both `/terminal` and `/api/terminal/*` return 404
     (don't advertise the feature exists). Exec needs a **second** gate,
     `TERMINAL_EXEC_ENABLED` — page+REPL can be on while `!cmd` stays dark.
     Unset/typo'd env = closed.
   - **Gate 1 — authn/authz: `verify_owner`.** Members never get exec; they get
     403 even with both env gates on. (The REPL itself is available to any
     active account, because it grants nothing the main UI doesn't.)
   - **Gate 2 — session binding.** Exec must name an existing session that is
     `idle`; the command and its output are emitted into that session's
     event log (the same redacted, append-only JSONL as agent bash) — **every
     command leaves a receipt**, including refused ones.
   - **Gate 3 — risky-command speed bump.** `_is_risky(cmd)` (push / deploy /
     rm -rf / secrets etc.) returns `needs_confirm`; the client must re-send
     with `confirm: true`. This is an anti-footgun, **not** a security boundary
     (an API caller can set `confirm` directly — but that caller already holds
     an Owner token; see red-team §5.3).
   - **Gate 4 — bounded execution.** Same harness as the agent's `t_bash`:
     `cwd=WORKSPACE_DIR`, `BASH_TIMEOUT`, `OUTPUT_CAP`, command length cap
     (`TERMINAL_CMD_MAX_CHARS`), and a global concurrency cap
     (`TERMINAL_MAX_CONCURRENT`, default 1 → 429 beyond).
   - **Gate 5 — output redaction both ways.** The receipt goes through `emit()`
     (already `_redact`s known secret values); the HTTP response body is
     **also** passed through `_redact()` before returning.

### What environment does exec expose?

Exactly what the agent's `bash` tool already exposes: full container env,
because `git push` needs `GITHUB_TOKEN` and that parity is the point of a
fallback. This is the **conceded kernel-sandbox gap** documented in
SECURITY.md; the mitigations are unchanged: secret *values* are scrubbed from
everything echoed/persisted, and the only principal who can reach exec is the
Owner — who can already run any command today by asking the agent and clicking
Approve. **Exec adds convenience, not privilege.** A scrubbed child env was
considered and rejected for v1: it breaks `git push`/`fly` (the main fallback
use cases) while the secret a scrub would protect is still readable from
`/proc/self/environ` of the server process's children — i.e. it's theater
against the holder of an Owner token.

### Kill switch / timeouts / concurrency

- **Kill switch:** `fly secrets unset TERMINAL_ENABLED` (or `…_EXEC_ENABLED`)
  restarts the app with the feature 404-dark. In-flight execs die with the
  process; agent runs are stoppable per-session via the existing `/stop`.
- **Idle timeout:** there is **no persistent server-side connection or PTY to
  time out** — the transport is polling and exec is a bounded synchronous
  subprocess. The client stops polling after 10 min without input (cosmetic,
  resource-friendly), and the session token already expires (`SESSION_TTL`).
- **Concurrency:** one exec at a time globally (default); the agent loop's own
  caps (budget, MAX_TURNS, MAX_SUBAGENTS) are untouched.

## 3. Transport (stdlib/pinned-deps constraint — no websocket lib)

uvicorn is pinned without `websockets`/`wsproto`, so WebSockets are out.
Options considered:

| | SSE (StreamingResponse) + POST input | Long-poll | Short-poll cursor (existing) |
|---|---|---|---|
| New code surface | New streaming endpoint, per-client generator threads, heartbeats, Fly proxy idle-timeout handling, reconnect/cursor resync logic | New blocking endpoint holding worker threads | **None — `GET /api/sessions/{sid}/events?after=N` already exists, is auth-gated, tested, and survives restarts** |
| Failure modes | Half-open streams, missed events on reconnect | Thread starvation under uvicorn's default worker model | 1.5 s worst-case latency |
| Receipts/redaction | Must re-implement on the stream | same | Already done (`emit` path) |

**Decision: reuse the existing short-poll cursor endpoint** (1.5 s interval
while active, matching `app.js`). A terminal is latency-tolerant at 1.5 s; the
built UI already proves the pattern end-to-end through the Fly proxy; and the
security review surface for transport is **zero new lines**. SSE is the upgrade
path if sub-second streaming is ever wanted — it slots in behind the same
cursor semantics without changing the client's render model.

## 4. Frontend

Constraint honored: **no CDN, ever** (repo is mid-exit from CDNs, PR #34).
Evaluated:

- **xterm.js, vendored** (~280 KB min + CSS + fit addon, MIT). Buys: real
  ANSI/VT rendering, a cursor, scroll regions. Needed **only when there is a
  PTY** — which is NO-GO'd above. For a line-based REPL it adds a vendored
  third-party supply-chain import (fetched from npm, must be hash-pinned and
  re-audited on every bump), poor mobile keyboard behavior, and zero functional
  gain over a styled `<pre>`. **Rejected for v1.** It becomes the mandatory
  choice if Mode 2 is ever approved — and then vendored, hash-recorded, never
  CDN'd.
- **DIY terminal pane** (chosen): vanilla JS + the existing Tailwind pipeline,
  monospace scrollback `<div>`, readline-style input with history
  (↑/↓), `textContent`-only rendering (no `innerHTML` for any server/model
  text — terminal output is hostile input to the DOM), ANSI escapes stripped.
  Matches the repo's "vanilla JS, no build step" layout contract and adds no
  third-party code.

UX (the Claude Code muscle-memory set):

```
codemonkeys v1 — type a task, /help for commands
> fix the failing test in tests/test_uploads.py        ← message to agent loop
  ⏺ reading tests/test_uploads.py …                    ← tool events as dim lines
  ⏺ approval needed: git push origin work/fix  → /approve or /deny
> /approve
> !git status                                          ← owner-only one-shot exec
/help /sessions /new [title] /use <id> /mode plan|default|auto
/approve /deny /stop /status /budget <usd> /clear /logout
```

Auth: the page reuses the existing login token (`localStorage cm_token`, same
origin). No token → "log in at / first" with a link; no login form is
duplicated. The page calls `/api/me` to learn the role and hides `!` for
non-owners (server still enforces — hiding is UX, not security).

## 5. RED-TEAM (adversarial pass on the above)

**R1. Unauthenticated internet scanner hits `/terminal` and `/api/terminal/exec`.**
Default deploy: both 404 (env gates unset). Enabled deploy: page is static and
secret-free; exec returns 401 without a token, 403 for non-Owner. Fail-closed
chain holds. **Verdict: OK.**

**R2. Invited Member opens the terminal.**
They can drive the REPL — i.e., exactly the session APIs they already use via
the main UI (`verify_user`), with the same approval gates and budget caps.
`!cmd` → 403 server-side regardless of client hiding. No escalation found.
**Verdict: OK.**

**R3. Stolen Owner token (XSS elsewhere, leaked localStorage, shoulder-surf).**
With exec enabled this is immediate RCE. But it is **not a new outcome**: an
Owner token today already yields RCE-equivalence (add a model key → run an
auto-mode session → debate-verify is the only brake; or approve your own risky
commands in default mode). Terminal exec shortens time-to-impact, doesn't
change the impact class. Mitigations that actually matter are upstream and
already tracked: CSP phase-2 (script-src 'self', PR #34 follow-up), token TTL,
TOTP+passkey login. Residual risk accepted **for the Owner role only** — this
is why exec is not `verify_user`. **Verdict: ACCEPTED RISK (owner-only), with
fix F1 (second env gate) to keep exec dark unless deliberately armed.**

**R4. CSRF: attacker page POSTs to `/api/terminal/exec`.**
Auth is a Bearer header, not a cookie; browsers don't attach it cross-site, and
there is no cookie session to ride. JSON body + Authorization required.
**Verdict: OK.**

**R5. Confirm-flag bypass: API caller sends `confirm: true` on first call.**
True — and out of scope as a *security* control: the caller holds an Owner
token (see R3). The confirm step exists to stop the *legitimate* owner from
fat-fingering `git push --force` in a terminal that feels casual. Documented
honestly as an anti-footgun. **Verdict: OK (documented), fix F2: refused and
unconfirmed attempts still emit receipts, so even a bypassing caller leaves a
trail in the JSONL.**

**R6. Secret exfil via exec output (`env`, `cat /data/model_config.json`).**
`emit()` already `_redact`s known secret values in the receipt; **found a gap:**
the HTTP *response* would have returned raw output. **Fix F3 (applied): response
body passes through `_redact()` too.** Residual: secrets whose env names don't
match `_SECRET_NAME_RE` and aren't model keys — same conceded gap as agent
bash, unchanged exposure, owner-only audience. **Verdict: GO with F3.**

**R7. Resource exhaustion: 10 MB command body, fork bombs, infinite output,
parallel execs.**
Command capped at `TERMINAL_CMD_MAX_CHARS` (8 000) → 413; output truncated at
`OUTPUT_CAP`; wall-clock bounded by `BASH_TIMEOUT`; global semaphore
`TERMINAL_MAX_CONCURRENT=1` → 429. Fork bombs / detached children (`nohup &`)
survive the timeout — **identical to the agent's bash tool today** (no kernel
sandbox; conceded in SECURITY.md). No regression introduced. **Verdict: OK.**

**R8. Receipt forgery / log injection: command containing `\n{"type":"done"}`.**
Receipts are emitted as JSON fields (`json.dumps` escapes newlines), not by
string concatenation into the JSONL. Rendering is `textContent`-only, so no
DOM injection either. **Verdict: OK (fix F4: terminal page renders all event
text via textContent, ANSI stripped — enforced in code review + test).**

**R9. Busy-session interleave: exec into a session mid-agent-run could
interleave receipts and confuse the approval state machine.**
**Fix F5 (applied): exec requires the bound session to be `idle`, else 409** —
mirrors the existing `/message` guard.

**R10. Misconfiguration drift: owner sets `TERMINAL_ENABLED` but forgets what
it exposes.**
`TERMINAL_ENABLED` alone = REPL page only (no new capability).
`TERMINAL_EXEC_ENABLED` alone = nothing (page is 404, and exec checks both).
Every combination short of deliberately setting **both** keeps `!cmd` dark.
**Verdict: OK.**

**R11. The static page itself as an oracle (fingerprinting, cached JS).**
Page is served with the repo-standard no-cache headers and contains only UI
strings. 404-when-off prevents feature fingerprinting on default deploys.
**Verdict: OK.**

**R12. Raw PTY pressure ("can we just add a real shell later?").**
Restated NO-GO with reasons (env dump, no receipts, no redaction, no risky
gate). Any future attempt must re-run this red-team. **Verdict: NO-GO for
Mode 2, recorded.**

### Fixes ledger (all applied in v1)

| # | Fix | Status |
|---|-----|--------|
| F1 | Separate `TERMINAL_EXEC_ENABLED` gate on top of `TERMINAL_ENABLED`; both default OFF; 404 when off | applied |
| F2 | Receipts for refused/unconfirmed/denied exec attempts, not just successful ones | applied |
| F3 | `_redact()` on the exec HTTP response, not only the JSONL receipt | applied |
| F4 | `textContent`-only rendering, ANSI stripped, no `innerHTML` for any event text | applied |
| F5 | Exec 409s unless the bound session is `idle` | applied |

## 6. VERDICT

**GO-WITH-FIXES (fixes F1–F5 applied in the v1 implementation).**

Scope shipped in v1: Mode 1 agent terminal (`/terminal` page + REPL over the
existing session loop) + owner-only `!cmd` exec behind the double env gate.
Mode 2 raw PTY: **NO-GO**, do not implement without a fresh red-team.

Activation (all default OFF — the feature does not exist until the owner does
this deliberately):

```
fly secrets set TERMINAL_ENABLED=true            # page + REPL
fly secrets set TERMINAL_EXEC_ENABLED=true       # !cmd one-shot exec (owner-only)
```
