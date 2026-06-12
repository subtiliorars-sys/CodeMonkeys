# Fleet Automation — Secure Multi-Platform Store Framework

Modular Playwright automation for **Itch.io**, **Steamworks**, and **Game Jolt** with a **zero-trust** security model. Designed so background AI agents or hijacked scripts **cannot** save store changes without your physical `Y` keystroke in an interactive terminal.

## Medallion governance (12 Steps + 12 Traditions)

**Hard-coded** in `src/governance/medallion-loop.ts` and enforced at:

1. **Session startup** — acknowledge Steps/Traditions before browser opens  
2. **Every action** — checkpoints printed before `[Y/N]`  
3. **Save/publish** — extra irreversible checkpoints (Steps 8–9, Traditions 1–2–6)

See `GOVERNANCE.md` and `docs/RED_TEAM.md`. Canonical paraphrases match
`MeniscusMaximus/brain/steps.py` and `CodeMonkeys/corps/agent-governance.md`.

## Security model (read this first)

| Layer | What it does |
|-------|----------------|
| **No hardcoded secrets** | API keys go in OS keychain via `keytar` (`credentials set`), never in git |
| **`.env` git guard** | Script **exits** if `.env` is tracked by git |
| **Zod + sanitization** | `game_data.json` is schema-validated; strings stripped of control chars and script patterns |
| **Approval gates** | Every navigation/fill/save prints a SHA-256 action digest and waits for `[Y/N]` |
| **TTY-only gates** | Non-interactive stdin (background agents) **cannot** proceed |
| **Persistent browser contexts** | Per-platform `user-data/<platform>/` — cookies stay local, chmod 700 |
| **Steam Guard halt** | Detects 2FA prompts and stops until you press ENTER after approving on your phone |

### Anti-AI guardrail

If something tries to run this script unattended, it blocks at:

1. Missing TTY → immediate error  
2. Each action → requires you to type `Y`  

Setting `FLEET_AUTOMATION_UNSAFE_SKIP_GATES=1` disables gates (logged loudly) — **do not use** for real store edits.

## Folder structure

```
fleet-automation/
├── game_data.json          # Central game manifest (validated)
├── .env.example            # Non-secret options only
├── src/
│   ├── main.ts             # Orchestrator CLI
│   ├── browser/context.ts  # Playwright persistent contexts
│   ├── schema/             # Zod schemas
│   ├── security/           # Gates, sanitize, credentials, preflight
│   └── platforms/          # Strategy modules (itch, steam, gamejolt)
└── user-data/              # Browser profiles (gitignored, chmod 700)
```

## Setup (one time)

```bash
cd projects/claude/fleet-automation
npm install
npx playwright install chromium
cp .env.example .env
chmod 600 .env    # Unix only
npm run preflight
```

### Store Butler API key (optional — for future upload automation)

```bash
npm run dev -- credentials set itch_butler_key YOUR_KEY_HERE
```

Key is stored in **Windows Credential Manager** / **macOS Keychain** / **Linux Secret Service** — not in files.

## Usage

List games and platforms:

```bash
npm run dev -- --list
```

**Dry-run** (approval gates still apply; no browser mutations after approval in dry-run mode):

```bash
npm run dev -- --platform itch --game jimmythehat-pixelsports --dry-run
```

**Itch.io** — opens dashboard, editor, fills fields, pauses before each step:

```bash
npm run dev -- --platform itch --game jimmythehat-pixelsports
```

**Steamworks** — opens partner portal; halts on Steam Guard:

```bash
npm run dev -- --platform steam --game jimmythehat-pixelsports
```

You must already be logged in via the persistent browser profile, or log in manually on first run.

## game_data.json

Edit titles/descriptions here — **never** paste untrusted AI output without reviewing. The schema rejects:

- Invalid slugs  
- Overlong strings  
- Script-like patterns (`<script`, `javascript:`, event handlers)

## Adding a platform

1. Create `src/platforms/myplatform.ts` extending `BasePlatform`  
2. Register in `src/platforms/index.ts`  
3. Extend Zod schema in `src/schema/game-data.ts`  

## What this does NOT do

- Bypass itch.io or Steam Terms of Service — use at your own risk  
- Replace identity verification or payment setup (human-only)  
- Run headless unattended store publishes (by design)

## Related fleet docs

- `PixelSports/docs/DEPLOY_STATUS.md` — current live URLs  
- `PixelSports/scripts/push-itch.sh` — Butler zip push (separate from this UI automation)
