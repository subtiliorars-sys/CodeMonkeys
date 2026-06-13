# Revenue launch — your 5 minutes (agent did the rest)

Everything below is **built and copy-paste ready**. You are not writing store pages from scratch.

## Fastest money path (today)

1. **Ko-fi** — already linked everywhere as `https://ko-fi.com/subtiliorars`. Confirm payouts: Ko-fi → Settings → Payment Setup.
2. **itch PWYW** — for each live game: Dashboard → project → Pricing → **No payment required** → check **Suggest a minimum contribution** → `$3` (or $0 for pure tips).
3. **Create 3 empty itch projects** (Kind: HTML, main file `index.html`) — Butler cannot push until these exist:
   - `jimmythehat-driving-me-nuts`
   - `jimmythehat-broadside`
   - `jimmythehat-sortie`
4. **Deploy zips** (Butler key on disk):
   ```bash
   cd projects/claude/PixelSports
   export BUTLER_API_KEY="$(tr -d ' \n\r' < ~/.config/itch/api_key)"
   bash scripts/deploy-fleet.sh
   ```
5. **Paste store copy** — open each project's `docs/ITCH_PASTE_READY*.md` (paths in `FLEET_REVENUE_MANIFEST.json`) into itch description fields. Or run fleet-automation metadata pass (batch approve ~5 clicks per page).

## Public support hub (live after deploy)

- **URL:** `/support/` on PixelSports hub (itch + GitHub Pages)
- **File:** `projects/claude/PixelSports/public/support/index.html`
- Links every game + donate buttons → Ko-fi

## Crowdfunding (Kickstarter / Indiegogo)

**Agent cannot click "Launch" for you** — requires your identity, bank, and platform approval (~1–2 weeks review).

**Agent built:** `projects/shared/fleet-revenue/KICKSTARTER_CAMPAIGN_DRAFT.md` — paste into Kickstarter project editor.

**Realistic recommendation:** Run **itch PWYW + Ko-fi for 30 days** first. Use tip volume as proof for a $3k–8k "PixelSports Season 1" campaign later.

## Optional bundle (week 2)

itch Dashboard → Bundles → **JimmyTheHat Free Play Pack** — hub + Yes Man + No + TradeGame. Suggested bundle tip: $5 PWYW.
