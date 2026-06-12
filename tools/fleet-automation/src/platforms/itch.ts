import type { Page } from "playwright";
import type { GameEntry } from "../schema/game-data.js";
import { sanitizePlainText } from "../security/sanitize.js";
import { assertUrlAllowed } from "../security/url-allowlist.js";
import { BasePlatform, type PlatformRunOptions } from "./base.js";

const ITCH_DASHBOARD = "https://itch.io/dashboard";

export class ItchPlatform extends BasePlatform {
  readonly id = "itch";

  async run(opts: PlatformRunOptions): Promise<void> {
    const itch = opts.game.platforms.itch;
    if (!itch) {
      throw new Error(`Game "${opts.game.id}" has no itch platform config in game_data.json`);
    }

    const title = sanitizePlainText(opts.game.title, 120);
    const shortDesc = sanitizePlainText(opts.game.short_description, 300);
    const slug = itch.slug;

    await this.gated(
      opts.game,
      "navigate_itch_dashboard",
      { url: ITCH_DASHBOARD },
      async (page) => {
        assertUrlAllowed(ITCH_DASHBOARD);
        await page.goto(ITCH_DASHBOARD, { waitUntil: "domcontentloaded", timeout: 60_000 });
        console.log("  → Itch dashboard loaded. Ensure you are logged in.");
      },
      opts.context,
      opts.dryRun
    );

    await this.gated(
      opts.game,
      "open_project_editor",
      { slug },
      async (page) => {
        const editUrl = `https://itch.io/dashboard/game/${slug}/edit`;
        assertUrlAllowed(editUrl);
        await page.goto(editUrl, { waitUntil: "domcontentloaded", timeout: 60_000 });
        console.log(`  → Opened editor for slug: ${slug}`);
      },
      opts.context,
      opts.dryRun
    );

    await this.gated(
      opts.game,
      "fill_store_fields",
      { title, shortDesc, play_in_browser: itch.play_in_browser ?? false },
      async (page) => {
        await fillIfPresent(page, 'input[name="title"], #game_title', title);
        await fillIfPresent(page, 'textarea[name="short_text"], #game_short_text', shortDesc);
        if (itch.play_in_browser) {
          await toggleIfPresent(page, 'input[name="play_in_browser"], #play_in_browser', true);
        }
        console.log("  → Form fields filled (not saved yet).");
      },
      opts.context,
      opts.dryRun
    );

    await this.gated(
      opts.game,
      "SAVE_ITCH_PROJECT",
      { slug, warning: "This will persist changes on itch.io" },
      async (page) => {
        const saveBtn = page.locator('button:has-text("Save"), input[type="submit"][value*="Save"]').first();
        if (await saveBtn.count()) {
          await saveBtn.click();
          await page.waitForTimeout(2000);
          console.log("  → Save clicked.");
        } else {
          console.log("  → Save button not found — complete manually on this screen.");
        }
      },
      opts.context,
      opts.dryRun
    );
  }
}

async function fillIfPresent(page: Page, selector: string, value: string): Promise<void> {
  const el = page.locator(selector).first();
  if (await el.count()) {
    await el.fill(value);
  }
}

async function toggleIfPresent(page: Page, selector: string, checked: boolean): Promise<void> {
  const el = page.locator(selector).first();
  if (await el.count()) {
    if (checked) await el.check();
    else await el.uncheck();
  }
}
