# Fleet UI audit

Playwright-based mobile + desktop layout audits for all web-facing fleet apps.

## Quick start

```bash
cd projects/shared/ui-audit
npm install
npx playwright install chromium
python3 seed-dev-accounts.py   # create ui-audit dev users (local only)
node run-all.mjs
```

## Test accounts (local dev only)

| App | User | Credential | File |
|-----|------|------------|------|
| CodeMonkeys | `ui-audit` | PIN `9999` + MFA from seed | `data/audit/users.json` |
| MeniscusMaximus | `ui-audit` | PIN `1234` + MFA / dev-login | `dev_users.json` |
| omni-herald | `ui-audit` | `audit-bootstrap-12` | `data/audit/users.json` |

Never point these at production `users.json` or `/data` volumes.

`data/audit/` and `dev_users.json` are gitignored in each project — safe to delete locally when done.

## One app

```bash
node run-all.mjs --only codemonkeys,pixelsports-hub
```

## Reports

JSON report + per-app screenshots under `/tmp/fleet-ui-audit/` (override with `--shots`).
