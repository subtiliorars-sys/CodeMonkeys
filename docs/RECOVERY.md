# CodeMonkeys — Recovery Runbook (read when something breaks)

**You do not need to code to use this.** Two ways to use any section below:
- **Easiest:** open the **Fly.io dashboard** in a browser (https://fly.io/dashboard
  → app **`codemonkeys`**) and click — most fixes are "set a secret" or "rollback,"
  both of which are buttons there.
- **Or hand it to an AI:** paste the error message **and the relevant section of
  this file** into Claude Code (or any AI assistant with terminal access) and say
  *"do this for me."* Every command here is exact and safe to run as written.

The app is **`codemonkeys`** on Fly. Its data (logins, keys, session secret) lives
on a Fly volume called **`cm_data`** mounted at **`/data`** — that volume survives
restarts and deploys. **Deploys are manual** — nothing you do goes live until a
deploy happens.

> CLI note: commands starting with `fly` need the Fly CLI installed and logged in
> (`fly auth login`). If you don't have it, use the **dashboard** equivalents called
> out in each section, or have the AI run the `fly` commands.

---

## ⭐ Prevention (do this once, avoid most emergencies)

1. **The master key is precious.** When you set `CM_MASTER_KEY` (see "First-time
   setup" below), **save it in your password manager** AND one other safe place.
   Losing it doesn't destroy your data, but it means a recovery step.
2. **Don't change `CM_MASTER_KEY` casually.** Changing ("rotating") it makes the
   app refuse to start until you either put the old value back or run the reset
   below. That's deliberate (it protects you from a silent breach) — just know the
   recovery (Scenario A).
3. The app is safe-by-default: every optional feature (`FLEET_TOKEN`,
   `NOTIFY_*`, `WEBHOOK_*`, `TERMINAL_*`) is **OFF unless you set its secret**.
   Turning one off = remove its secret + redeploy.

---

## Scenario A — App won't start after setting/changing the master key

**Symptom:** after a deploy, the app is down / restarting; logs show
**`cannot decrypt session_secret.key`** or **`session_secret.key is encrypted but
CM_MASTER_KEY is unset`**. (See logs: dashboard → app → **Monitoring**, or
`fly logs -a codemonkeys`.)

**Cause:** `CM_MASTER_KEY` is wrong, missing, or was changed. The app refuses to
boot rather than silently break your logins. **Your data is fine.**

### Fix 1 (best) — put the correct key back
You changed or lost the key; restore the original value.
- **Dashboard:** app `codemonkeys` → **Secrets** → set `CM_MASTER_KEY` to the
  original value (from your password manager) → it redeploys automatically.
- **CLI:** `fly secrets set CM_MASTER_KEY="<the-original-value>" -a codemonkeys`

The app boots and **all logins are preserved**.

### Fix 2 — original key is truly lost → one-step reset (everyone re-logs-in)
This makes the app boot again by generating a brand-new signing secret. It is
**safe** (it does not reuse any old/leaked value). The only cost: everyone has to
log in again (PINs/passkeys/2FA still work — only active sessions drop).

1. Pick a NEW master key — generate one:
   `python3 -c "import secrets; print(secrets.token_urlsafe(32))"`
   (or just use any 32+ character random string). **Save it in your password manager.**
2. Set **two** secrets and let it redeploy (**set both** — `CM_MASTER_KEY_RESET`
   alone, without a new `CM_MASTER_KEY`, will refuse to boot rather than quietly
   turn off at-rest encryption):
   - **Dashboard:** Secrets → set `CM_MASTER_KEY` = the new value, and add
     `CM_MASTER_KEY_RESET` = `true`.
   - **CLI:** `fly secrets set CM_MASTER_KEY="<new-value>" CM_MASTER_KEY_RESET=true -a codemonkeys`
3. Wait ~1 minute for it to restart. Confirm it's up (open the site / check logs —
   you'll see `GENERATED A FRESH session_secret.key`).
4. **Remove the reset flag** (important — don't leave it on):
   - **Dashboard:** Secrets → delete `CM_MASTER_KEY_RESET`.
   - **CLI:** `fly secrets unset CM_MASTER_KEY_RESET -a codemonkeys`
5. Log in again. Done.

---

## Scenario B — You're locked out of your account (lost 2FA, forgot PIN)

**Symptom:** can't pass login / lost your authenticator app.

**Fix:** run the recovery script on the server.
1. `fly ssh console -a codemonkeys`  (opens a shell inside the app)
2. List accounts:    `python scripts/reset_access.py list`
3. Reset your 2FA:   `python scripts/reset_access.py reset-mfa <your-username>`
   → it prints a new `otpauth://…` link; add it to your authenticator app
   (paste the link into any QR generator, or your app's "enter setup key").
4. Or reset your PIN: `python scripts/reset_access.py reset-pin <your-username> <new-pin>`
5. Type `exit` to leave the server, then log in.

*(No CLI? This one needs the server shell — have the AI run it, or use the Fly
dashboard's "SSH/Console" feature.)*

---

## Scenario C — A deploy broke the app / you want to undo the last change

**Symptom:** the app worked before the last deploy and now misbehaves.

**Fix — roll back to the previous working version (no code needed):**
- **Dashboard (easiest):** app `codemonkeys` → **Monitoring / Releases** → find the
  last good version → **Rollback**.
- **CLI:** `fly releases -a codemonkeys` (lists versions) → roll back with
  `fly deploy -a codemonkeys --image <the-previous-version's-image>` (the AI can
  read the image ref from the `fly releases` output).

Rollback is safe — your `/data` (logins/keys) is untouched by deploys.

---

## Scenario D — Turn a feature OFF fast (something's misbehaving)

Every optional feature is gated by a secret. To disable one, remove its secret and
redeploy (dashboard Secrets → delete, or CLI `fly secrets unset … -a codemonkeys`):
- **Webhook → PR runs:** unset `WEBHOOK_ENABLED` (and/or `WEBHOOK_SECRET`).
- **Notify-on-done pings:** unset `NOTIFY_WEBHOOK_URL`.
- **Fleet status feed:** unset `FLEET_TOKEN` (the endpoint then returns 404).
- **Web terminal:** unset `TERMINAL_ENABLED` / `TERMINAL_EXEC_ENABLED`.

To take the **whole app** offline temporarily: dashboard → scale machines to 0
(or `fly scale count 0 -a codemonkeys`); bring back with count 1.

---

## First-time setup of the master key (encrypt the session secret at rest)

Do this once, when you're ready to turn on at-rest encryption:
1. Generate a key: `python3 -c "import secrets; print(secrets.token_urlsafe(32))"`
2. **Save it in your password manager + one backup place.**
3. Set it: dashboard Secrets → add `CM_MASTER_KEY` = that value (or
   `fly secrets set CM_MASTER_KEY="<value>" -a codemonkeys`). It redeploys.
4. The app migrates the existing key to encrypted automatically — **logins are
   preserved.** From now on, keep that key (see Scenario A if it's ever lost).

**Until you do this, nothing changes** — the app runs exactly as today.

---

---

## Scenario E — Banner says "could not decrypt saved model API keys"

**Symptom:** a yellow warning banner appears at the top of the console after login
(Owner only). It says something like "Could not decrypt saved model API keys — re-enter
your keys in ⚙ Settings."

**Cause:** `CM_MASTER_KEY` was changed or removed since the model API keys were last
saved, so the app can't read the encrypted `model_config.json`.

**What's NOT broken:** your login, logins for invited developers, existing sessions,
and the app itself — everything still works; you just have to re-enter your API keys.
This is by design: model keys are re-enterable; the sign-in secret (Scenario A) is not.

**Best fix first — you might not need to re-enter anything:** if you still have the
old `CM_MASTER_KEY`, just put it back (Scenario A, Fix 1) and your saved keys come
right back. The app also auto-protects you: while it can't decrypt, the original
encrypted file is preserved as `model_config.json.undecryptable.bak` (and likewise
for `mcp_tokens.json`) before any save — so even an accidental Settings change can't
permanently lose your keys. Restore the old key and they're recoverable.

**Fix:**
1. Open the console → ⚙ Settings → **Models & keys**.
2. Re-enter each API key (Anthropic, OpenAI, etc.) and save.
3. The banner disappears automatically.

That's it. No redeploy needed. If you also set the correct `CM_MASTER_KEY` first, the
keys will be saved encrypted going forward — no more banner.

---

## Scenario F — Model API keys at rest (automatic)

**Default (2026-06+):** on first boot CodeMonkeys creates `data/master.key` on your
DATA volume and encrypts `model_config.json` / `mcp_tokens.json` automatically.
No env var required — the yellow "unencrypted keys" banner should not appear.

**Optional:** set `CM_MASTER_KEY` in Fly secrets if you want a pinned key across
volume restores or multi-machine deploys (see Scenario D above). Env wins over
`master.key`.

**Legacy symptom (old deploys):** banner said "Model API keys are stored unencrypted."
**Fix:** restart once after upgrading — bootstrap + warm migration encrypt in place.

> **Note:** `CM_MASTER_KEY` (env or `data/master.key`) protects the sign-in secret
> (Scenario A) AND model API keys / MCP tokens (Scenarios E/F).

---

## Where everything lives (for you or the AI)
- App: **`codemonkeys`** on Fly · dashboard: https://fly.io/apps/codemonkeys
- Data volume: **`cm_data`** → **`/data`** (survives deploys/restarts):
  - `/data/users.json` — accounts (PIN hashes, 2FA)
  - `/data/session_secret.key` — the login-token signing secret (encrypted if
    `CM_MASTER_KEY` is set); **FAIL-CLOSED** — wrong key = app won't start (Scenario A)
  - `/data/master.key` — auto-generated Fernet master (0600) when `CM_MASTER_KEY` env
    is unset; encrypts model/MCP config at rest
  - `/data/model_config.json` — your model API keys (encrypted when master key ready);
    **FAIL-SOFT** — wrong/missing key = empty config + banner (Scenario E), app keeps running
  - `/data/mcp_tokens.json` — MCP OAuth tokens (encrypted if `CM_MASTER_KEY` is set);
    same fail-soft behaviour as model_config
- Recovery script: `scripts/reset_access.py` (run via `fly ssh console`)
- Deeper context: `SECURITY.md`, `docs/STATE.md`

## When in doubt
Open Claude Code in this repo, paste the **error message** + the scenario you think
matches, and say *"walk me through fixing this."* It can read this file, check the
logs, and run the exact steps for you.
