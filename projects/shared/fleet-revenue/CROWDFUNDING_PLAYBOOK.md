# Crowdfunding playbook — what you do vs what the agent builds

**Short answer:** Yes — create accounts on the platforms below. The agent can build **all copy, tiers, images specs, landing pages, and itch/Ko-fi funnels** in the repo. Only **identity verification, bank linking, and clicking "Submit for review"** require you (5–30 minutes per platform, then 3–14 days wait).

---

## Platform matrix

| Platform | You create account | Agent can build | You must click submit | Best for |
|----------|-------------------|-----------------|----------------------|----------|
| **Ko-fi** | [ko-fi.com](https://ko-fi.com) — free | Donate links, support hub, tier copy | Enable payouts in Settings | Ongoing tips, zero review |
| **itch Creator** | Already on itch | PWYW copy, bundles, `/support/` hub | Enable Creator Page + minimum tip | Parallel to Kickstarter |
| **Kickstarter** | [kickstarter.com](https://kickstarter.com) — verify ID + bank | Full campaign in `KICKSTARTER_CAMPAIGN_DRAFT.md` | Create project → paste → submit | Season 1 bundle, Steam keys |
| **Indiegogo** | [indiegogo.com](https://indiegogo.com) | Same draft, retitled | Create campaign → paste | Backup if KS delays |
| **Patreon** | [patreon.com](https://patreon.com) | Tier doc + thank-you posts | Launch page | Monthly fleet devlog |
| **GoFundMe** | gofundme.com | Story + goal copy | Publish | One-off hardware/medical — **not ideal for games** |

**Not automatable by agent:** government ID upload, Stripe Connect, tax form (W-9 / sole prop), campaign video upload (you record or approve AI VO), day-1 backer coordination.

---

## Recommended sequence (lowest risk)

### Phase 0 — live now (no crowdfunding account needed)

1. Ko-fi payouts on → already linked fleet-wide.
2. itch PWYW $3 on live games.
3. Create 3 itch slugs (Broadside, Sortie, DMN) — see `OWNER_5_MIN_REVENUE.md`.
4. Support hub: https://subtiliorars.itch.io/jimmythehat-pixelsports/support/

**Goal:** 30 days of tip data = social proof for Kickstarter.

### Phase 1 — parallel "always on" (you: ~15 min)

| Step | Owner time | Agent already built |
|------|------------|---------------------|
| Ko-fi **Memberships** or **Shop** | 10 min | Tier names in manifest |
| itch **Creator's Page** | 5 min | Hub + fleet links |
| Optional Patreon | 15 min | Can draft `PATREON_TIERS.md` on request |

### Phase 2 — Kickstarter / Indiegogo (you: ~2 hours spread over a week)

| Day | You | Agent (on request) |
|-----|-----|-------------------|
| 1 | Create KS account, verify identity, link bank | Paste from `KICKSTARTER_CAMPAIGN_DRAFT.md` into a local preview HTML |
| 2–3 | Record 60–90s gameplay montage (script in draft) | Shot list + caption file |
| 4 | Upload 3 images (hero, tiers, fleet collage) | Image briefs + itch screenshots as source |
| 5 | Submit for review | Update `FLEET_REVENUE_MANIFEST.json` status |
| 7–14 | Wait for approval | Prep launch Discord/email copy |
| Launch | Back your own project day 1 + 10 friends | Monitor comments template |

**Funding goal in draft:** $6,500 · 21 days · PixelSports Season 1 (audio + 2 Steam boxes + DMN Office Quarter).

---

## What to tell the agent after you create accounts

Send handles only (no passwords):

```
Kickstarter: created, draft project URL is …
Ko-fi: subtiliorars — memberships enabled
itch Creator: enabled
Goal: launch KS in 2 weeks / or Indiegogo backup
```

Then ask for any of:

- `PATREON_TIERS.md` — monthly devlog structure
- `KICKSTARTER_PREVIEW.html` — local campaign preview page
- `LAUNCH_EMAIL.md` — day-0 backer blast
- `REWARD_FULFILLMENT.md` — Steam key + Discord onboarding
- Per-game mini-campaigns (e.g. TradeGame edu stretch goal only)

---

## Legal / honest limits

- **Solo dev + AI-assisted** — say so in Risks (already in KS draft).
- **Steam keys** — only promise titles with realistic ship windows.
- **TradeGame** — education sim, not financial advice (keep in campaign FAQ).
- **Meniscus / recovery apps** — keep out of JimmyTheHat game Kickstarter; separate brand if ever crowdfunded.

---

## Files already in repo

| File | Purpose |
|------|---------|
| `KICKSTARTER_CAMPAIGN_DRAFT.md` | Paste-ready KS story + tiers + video script |
| `FLEET_REVENUE_MANIFEST.json` | All donate URLs + game status |
| `OWNER_5_MIN_REVENUE.md` | itch + Ko-fi fast path |
| `PixelSports/public/support/index.html` | Fleet support landing |
| `CROWDFUNDING_PLAYBOOK.md` | This doc |

---

## Bottom line

**Yes, start the accounts.** Ko-fi + itch Creator today (minutes). Kickstarter when you have 30s of footage and 10 day-1 backers lined up. The agent cannot log in as you, but everything **before** the submit button can live in git — copy, tiers, landing pages, fulfillment checklists — and ship as you verify each platform.
