import { assertUrlAllowed } from "../security/url-allowlist.js";
import { BasePlatform, type PlatformRunOptions } from "./base.js";

const GAMEJOLT_DASHBOARD = "https://gamejolt.com/dashboard";

/** Stub — same security gates; implement when Game Jolt API/dashboard flow is defined. */
export class GameJoltPlatform extends BasePlatform {
  readonly id = "gamejolt";

  async run(opts: PlatformRunOptions): Promise<void> {
    const gj = opts.game.platforms.gamejolt;
    if (!gj?.enabled) {
      console.log(`  → Game Jolt disabled for "${opts.game.id}" — skipping.`);
      return;
    }

    await this.gated(
      opts.game,
      "navigate_gamejolt_dashboard",
      { url: GAMEJOLT_DASHBOARD },
      async (page) => {
        assertUrlAllowed(GAMEJOLT_DASHBOARD);
        await page.goto(GAMEJOLT_DASHBOARD, { waitUntil: "domcontentloaded", timeout: 60_000 });
        console.log("  → Game Jolt dashboard (stub). Implement form fill when ready.");
      },
      opts.context,
      opts.dryRun
    );
  }
}
