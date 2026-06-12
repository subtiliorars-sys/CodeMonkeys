import type { Page } from "playwright";
import type { GameEntry } from "../schema/game-data.js";
import { sanitizePlainText } from "../security/sanitize.js";
import { assertUrlAllowed } from "../security/url-allowlist.js";
import { BasePlatform, type PlatformRunOptions } from "./base.js";
import * as readline from "node:readline/promises";
import { stdin as input, stdout as output } from "node:process";

const STEAM_PARTNER = "https://partner.steamgames.com/";

export class SteamPlatform extends BasePlatform {
  readonly id = "steam";

  async run(opts: PlatformRunOptions): Promise<void> {
    const steam = opts.game.platforms.steam;
    if (!steam) {
      throw new Error(`Game "${opts.game.id}" has no steam platform config in game_data.json`);
    }

    await this.gated(
      opts.game,
      "navigate_steamworks",
      { url: STEAM_PARTNER },
      async (page) => {
        assertUrlAllowed(STEAM_PARTNER);
        await page.goto(STEAM_PARTNER, { waitUntil: "domcontentloaded", timeout: 90_000 });
        await waitForSteamGuardIfNeeded(page);
      },
      opts.context,
      opts.dryRun
    );

    if (steam.app_id) {
      const title = sanitizePlainText(opts.game.title, 120);
      await this.gated(
        opts.game,
        "open_steam_app_admin",
        { app_id: steam.app_id },
        async (page) => {
          const url = `https://partner.steamgames.com/apps/landing/${steam.app_id}`;
          assertUrlAllowed(url);
          await page.goto(url, { waitUntil: "domcontentloaded", timeout: 90_000 });
          await waitForSteamGuardIfNeeded(page);
          console.log(`  → Steamworks app ${steam.app_id} landing. Title stub: ${title}`);
        },
        opts.context,
        opts.dryRun
      );
    } else {
      console.log("  → No app_id configured — Steam module stops at dashboard (stub).");
    }

    await this.gated(
      opts.game,
      "steam_manual_confirm_complete",
      { note: "Confirm store changes manually in Steamworks UI" },
      async () => {
        console.log("  → Steamworks requires manual review of all store edits.");
      },
      opts.context,
      opts.dryRun
    );
  }
}

/**
 * Detect Steam Guard / 2FA — halt automation until operator confirms on phone or enters code.
 */
export async function waitForSteamGuardIfNeeded(page: Page): Promise<void> {
  const guardSelectors = [
    "text=Steam Guard",
    "text=Enter the code",
    "text=Use the Steam Mobile App",
    "#twofactorcode_entry",
    'input[name="twofactorcode"]',
  ];

  for (const sel of guardSelectors) {
    const loc = page.locator(sel).first();
    if (await loc.count()) {
      console.log("\n🔐 STEAM GUARD DETECTED — automation halted.");
      console.log("   Approve on your phone or enter the code in the browser window.\n");

      if (!process.stdin.isTTY) {
        throw new Error("Steam Guard requires interactive terminal to continue");
      }

      const rl = readline.createInterface({ input, output });
      try {
        await rl.question("Press ENTER after you have completed Steam Guard approval: ");
      } finally {
        rl.close();
      }
      await page.waitForTimeout(1500);
      return;
    }
  }
}
