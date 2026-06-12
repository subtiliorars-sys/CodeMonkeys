# Red Team Report — fleet-automation v0.1

*Date: 2026-06-12 · Reviewer: Command (adversarial pass before fleet push)*

## Scope

Adversarial review of secure store automation: credential handling, approval gates,
Medallion loop, URL navigation, data injection, and unattended execution.

## Findings

| ID | Severity | Finding | Status |
|----|----------|---------|--------|
| RT-1 | **HIGH** | `FLEET_AUTOMATION_UNSAFE_SKIP_GATES=1` disables all human gates | **MITIGATED** — loud warning; documented never-use in README |
| RT-2 | **HIGH** | Credentials on CLI argv leak to shell history | **FIXED** — stdin prompt only |
| RT-3 | **MED** | No URL allowlist — open redirect / exfil via malicious game_data | **FIXED** — HTTPS allowlist for itch/steam/gamejolt |
| RT-4 | **MED** | `game_data.json` path env could point outside repo | **FIXED** — path must stay under repo root |
| RT-5 | **MED** | `user-data/` cookies not encrypted at rest (chmod 700 only) | **ACCEPTED** — document OS disk encryption recommendation |
| RT-6 | **MED** | Background agent with TTY hijack could auto-answer Y | **ACCEPTED** — physical terminal trust boundary; use dedicated user session |
| RT-7 | **LOW** | Itch/Steam CSS selectors brittle — wrong field mutation | **ACCEPTED** — dry-run + per-step gates limit blast radius |
| RT-8 | **LOW** | keytar unavailable on some Linux headless hosts | **ACCEPTED** — fail with clear message; Butler optional |
| RT-9 | **PASS** | Non-TTY stdin blocks execution | Verified |
| RT-10 | **PASS** | `.env` tracked in git crashes preflight | Verified |
| RT-11 | **PASS** | Zod + sanitize blocks script injection in JSON | Verified |
| RT-12 | **PASS** | Medallion loop hard-coded at startup + pre-action + pre-irreversible | Implemented |

## Residual risk

- Operator must not export `FLEET_AUTOMATION_UNSAFE_SKIP_GATES=1` in shell profile.
- First live run should use `--dry-run` until itch form selectors are validated on your account layout.
- Steam Guard still requires human phone approval (by design).

## Sign-off

Safe to ship to MeniscusMaximus + CodeMonkeys with Medallion loop enforced.
Not safe for unattended CI — **intentionally blocked**.
