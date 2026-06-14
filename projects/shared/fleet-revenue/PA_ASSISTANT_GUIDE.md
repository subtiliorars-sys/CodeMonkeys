# Personal Assistant / Executive Assistant Guide — JimmyTheHat Revenue Launch

> **🌐 Send your EA this link (start here):**  
> **https://subtiliorars-sys.github.io/PixelSports---Preview/launch/pa-guide/**  
> **All pages:** https://subtiliorars-sys.github.io/PixelSports---Preview/launch/  
> **Email template:** `projects/shared/fleet-revenue/EA_HANDOFF.md`

**For:** Daniel’s personal assistant  
**From:** Dev team (copy is pre-written; you are clicking through platforms)  
**Goal:** Turn on tips/donations, publish missing itch pages, prep crowdfunding — without rewriting marketing copy.  
**Time estimate:** Phase 1 ≈ 45 min · Phase 2 ≈ 90 min · Phase 3 (crowdfunding prep) ≈ 2–3 hours spread over a week  

---

## Before you start

### What you need from Daniel (one-time)

Ask Daniel to provide **secure access** (password manager share or screen-share session — **never** paste passwords into email/Slack):

| Account | URL | Why |
|---------|-----|-----|
| **itch.io** | https://itch.io/dashboard | Create projects, paste copy, enable PWYW |
| **Ko-fi** | https://ko-fi.com/home/coffeeshop | Confirm payouts / memberships |
| **GitHub** (optional) | https://github.com/subtiliorars-sys | Only if asked to run deploy script on Daniel’s machine |
| **Kickstarter** (Phase 3) | https://www.kickstarter.com | Identity + bank — Daniel may need to be on camera for ID |

### What you do NOT need

- You do **not** write game descriptions — they are in markdown files (listed below).
- You do **not** need to understand code to complete Phases 1–2.
- You do **not** launch Kickstarter until Daniel approves the draft and footage.

### Security rules

1. Never commit or screenshot API keys, bank details, or government ID.
2. Use Daniel’s machine or a trusted logged-in browser session for deploy commands.
3. If Butler/deploy fails, save the error text and stop — don’t retry with new keys.
4. **Ilerioluwa GK Training** is a client site (Simon) — **do not** add donate funnels or change copy there without Daniel’s explicit OK.

### Reference files (on Daniel’s computer)

All paths are under the home workspace, e.g. `/home/subtiliorars/`:

| File | Purpose |
|------|---------|
| `projects/shared/fleet-revenue/FLEET_REVENUE_MANIFEST.json` | Master list of games + URLs |
| `projects/shared/fleet-revenue/KICKSTARTER_CAMPAIGN_DRAFT.md` | Paste into Kickstarter |
| `projects/shared/fleet-revenue/CROWDFUNDING_PLAYBOOK.md` | Strategy notes for Daniel |
| `projects/shared/fleet-revenue/OWNER_5_MIN_REVENUE.md` | Short owner checklist |

---

## Phase 1 — Turn on money today (~45 minutes)

### Task 1.1 — Ko-fi payouts

1. Log in to https://ko-fi.com/subtiliorars (or create page if missing).
2. Go to **Settings → Payment Setup** (or **Get Paid**).
3. Complete Stripe/PayPal connection if not already green.
4. Confirm public page loads: https://ko-fi.com/subtiliorars

**Done when:** Dashboard shows payouts **enabled** or **connected**.

---

### Task 1.2 — itch.io PWYW on live games

For **each** project below, open Dashboard → project → **Edit** → **Pricing**:

| Game | itch URL |
|------|----------|
| PixelSports Hub | https://subtiliorars.itch.io/jimmythehat-pixelsports |
| Yes Man | https://subtiliorars.itch.io/jimmythehat-yes-man |
| No Is a Complete Sentence | https://subtiliorars.itch.io/jimmythehat-no-complete-sentence |
| TradeGame | https://subtiliorars.itch.io/tradegame-trading-simulator |

**Settings for each:**

- Pricing: **No payment required** (free download/play)
- Check **Suggest a minimum contribution** → **$3 USD**
- Save

**Done when:** All four show PWYW / suggested tip on the public page.

---

### Task 1.3 — Create 3 missing itch projects

Butler (auto-upload) **cannot** push until these project pages exist.

For each row: Dashboard → **Create new project** → Kind: **HTML** → main file: `index.html` → URL slug **exactly** as shown:

| Title | URL slug (must match) | Future URL |
|-------|----------------------|------------|
| Driving Me Nuts | `jimmythehat-driving-me-nuts` | https://subtiliorars.itch.io/jimmythehat-driving-me-nuts |
| Broadside | `jimmythehat-broadside` | https://subtiliorars.itch.io/jimmythehat-broadside |
| Sortie | `jimmythehat-sortie` | https://subtiliorars.itch.io/jimmythehat-sortie |

**Minimum to create:** title + slug + Kind HTML. You can leave description blank for Phase 2.

Apply same PWYW settings ($3 suggested) as Task 1.2.

**Done when:** All three URLs open (even if empty/placeholder).

---

### Task 1.4 — Verify support hub

Open: https://subtiliorars.itch.io/jimmythehat-pixelsports/support/

Confirm:

- [ ] Page loads
- [ ] Game links work
- [ ] Ko-fi button goes to https://ko-fi.com/subtiliorars

If `/support/` 404s, tell Daniel — deploy may need re-run (Phase 2.3).

---

## Phase 2 — Paste store copy & deploy (~90 minutes)

### Task 2.1 — Copy-paste itch descriptions

Open each markdown file in a text editor, copy sections into itch **Edit → Description** (and short description if the file has one).

| Game | Copy from this file |
|------|---------------------|
| PixelSports Hub | `projects/claude/PixelSports/docs/ITCH_PASTE_READY.md` |
| Yes Man | `projects/claude/yes-man/docs/ITCH_PASTE_READY.md` |
| No Is a Complete Sentence | `projects/claude/yes-man/docs/ITCH_PASTE_READY_NO.md` |
| TradeGame | `projects/claude/TradeGame/docs/assets/ITCH_IO_PAGE.md` |
| Driving Me Nuts | `projects/claude/DrivingMeNuts/docs/ITCH_PASTE_READY.md` |
| Broadside | `projects/claude/PixelSports/docs/ITCH_PASTE_READY_BROADSIDE.md` |
| Sortie | `projects/claude/PixelSports/docs/ITCH_PASTE_READY_SORTIE.md` |

**itch formatting tips:**

- itch uses Markdown — paste as-is.
- Add **screenshots** if the file mentions them: use in-game shots or ask Daniel for a folder.
- Tag suggestions (if empty): `browser`, `free`, `pixel-art`, `indie`.

**Done when:** All seven pages have full descriptions saved.

---

### Task 2.2 — Screenshots (if missing)

Minimum per flagship page (Daniel or you with Daniel’s games open in browser):

| Page | Screenshot |
|------|------------|
| PixelSports Hub | Hub + one game (volleyball) |
| Broadside | Combat/map screen |
| Sortie | Dogfight wireframe |
| Driving Me Nuts | Food truck / district screen |
| Yes Man / No | Main gameplay panel |

Size: itch accepts most PNG/JPG; aim 1280×720 or similar landscape.

---

### Task 2.3 — Run fleet deploy (Daniel’s machine or with his OK)

**Who:** Prefer Daniel or someone with his itch API key on disk.  
**Where:** Terminal on Daniel’s Linux machine.

```bash
cd projects/claude/PixelSports
export BUTLER_API_KEY="$(tr -d ' \n\r' < ~/.config/itch/api_key)"
bash scripts/deploy-fleet.sh
```

**Success looks like:** Log ends without `invalid game` errors; itch pages show updated builds.

**If `invalid game`:** Phase 1.3 slugs were not created — go back and fix.

**If no API key file:** Ask Daniel to generate one: itch → **User menu → API keys** → save to `~/.config/itch/api_key` (chmod 600).

---

### Task 2.4 — Optional itch bundle (week 2)

itch Dashboard → **Bundles** → Create:

- **Name:** JimmyTheHat Free Play Pack  
- **Include:** Hub, Yes Man, No, TradeGame  
- **Pricing:** PWYW, suggest **$5**

Skip unless Daniel asks.

---

## Phase 3 — Crowdfunding prep (spread over ~1 week)

**Do not submit Kickstarter until Daniel approves** text + video.

### Task 3.1 — Kickstarter account (Daniel may need to be present)

1. Go to https://www.kickstarter.com/start
2. Sign in as Daniel (or create account in his name with his email).
3. Complete **identity verification** and **bank account** linking — Kickstarter requires the project owner.
4. Create a **draft project** (do not publish yet).

---

### Task 3.2 — Paste campaign copy

Open `projects/shared/fleet-revenue/KICKSTARTER_CAMPAIGN_DRAFT.md` and copy into the Kickstarter draft:

| KS field | Copy from draft section |
|----------|-------------------------|
| Title | Campaign title |
| Subtitle | Subtitle |
| Goal | $6,500 |
| Duration | 21 days (or Daniel’s choice) |
| Story | “Story” / Project Description |
| Rewards | “Reward tiers” table |
| Risks | Risks section |

---

### Task 3.3 — Campaign video (60–90 seconds)

Script is in the draft under **Video script**.

**PA can:**

- Record screen gameplay (Broadside, Yes Man, volleyball, DMN) using OBS or QuickTime
- Cut a simple montage (no fancy editing required)
- Upload to Kickstarter as project video

**Daniel must:** Approve final video before submit.

---

### Task 3.4 — Campaign images (3 minimum)

| Image | Content |
|-------|---------|
| Hero | PixelSports logo + “Play free in browser” |
| Tiers | Simple graphic of $3 / $8 / $12 / $25 rewards |
| Games collage | 4–6 screenshots in one image |

Canva template is fine. Save as JPG/PNG, upload to Kickstarter.

---

### Task 3.5 — Before submit checklist (Daniel signs off)

- [ ] Video uploaded
- [ ] 3+ images uploaded
- [ ] Reward tiers match draft (Steam keys only for listed games)
- [ ] **10 people** lined up to back on day 1 (friends/family list)
- [ ] Daniel read Risks + Transparency sections
- [ ] Submit for Kickstarter review (3–14 days wait)

**Alternative:** If Kickstarter delays, duplicate copy to **Indiegogo** (same draft file).

---

### Task 3.6 — Parallel: itch Creator Page + Ko-fi memberships

Low effort, no review gate:

| Platform | Steps |
|----------|-------|
| **itch** | Profile → enable **Creator’s Page** → link support hub |
| **Ko-fi** | Optional **Memberships** tier ($3/mo “Fleet Supporter”) — copy tier name from Daniel |

---

## Phase 4 — Report back to Daniel

When finished (or blocked), send Daniel this filled-in template:

```
REVENUE LAUNCH STATUS — [date]

Phase 1
- Ko-fi payouts: [enabled / blocked — reason]
- itch PWYW on 4 live games: [done / which missing]
- 3 new itch slugs created: [yes / which missing]
- Support hub loads: [yes / no]

Phase 2
- Descriptions pasted: [list games done]
- Screenshots added: [yes / partial / need Daniel]
- deploy-fleet.sh: [success / not run / error: …]

Phase 3
- Kickstarter draft: [created / not started]
- Video: [uploaded / in progress / need Daniel]
- Images: [uploaded / in progress]
- Submitted for KS review: [yes / waiting on Daniel]

Blockers:
- [list anything needing Daniel]

Links to verify:
- https://subtiliorars.itch.io/jimmythehat-pixelsports/support/
- https://ko-fi.com/subtiliorars
- [new itch pages]
- [Kickstarter draft URL if created]
```

---

## Quick escalation guide

| Situation | Action |
|-----------|--------|
| Can’t log into itch/Ko-fi | Daniel must reset password or share session |
| `invalid game` on deploy | Slug typo — compare to Phase 1.3 table |
| Kickstarter wants business entity | Pause; Daniel decides sole prop vs LLC |
| TradeGame legal wording questions | Do not edit; flag Daniel (education sim disclaimer) |
| Ilerioluwa / Meniscus / Cairn pages | **Do not change** unless Daniel explicitly asks |
| Missing paste-ready file | Tell Daniel — dev can generate in ~10 min |

---

## Live URLs cheat sheet

| What | URL |
|------|-----|
| itch profile | https://subtiliorars.itch.io |
| Support hub | https://subtiliorars.itch.io/jimmythehat-pixelsports/support/ |
| Ko-fi | https://ko-fi.com/subtiliorars |
| Buy Me a Coffee | https://buymeacoffee.com/subtilior.ars |
| PayPal | https://paypal.me/DanielRead413 |

---

## Suggested schedule for the PA

| Day | Tasks |
|-----|-------|
| **Day 1** | Phase 1 entirely (Ko-fi, PWYW, create 3 slugs, verify support hub) |
| **Day 2** | Phase 2.1–2.2 (paste all descriptions + screenshots) |
| **Day 3** | Phase 2.3 deploy with Daniel; fix any errors |
| **Week 2** | Phase 3.1–3.4 draft Kickstarter + video + images |
| **When Daniel approves** | Phase 3.5 submit KS; enable itch Creator Page |

---

*Questions the dev/agent can answer: paste file locations, deploy errors, missing copy. Questions only Daniel can answer: bank/tax, legal entity, Ilerioluwa client boundaries, final Kickstarter go-live.*
