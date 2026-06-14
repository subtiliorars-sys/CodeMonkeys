import type { BrowserContext, Page } from "playwright";
import type { GameEntry } from "../schema/game-data.js";
import type { ActionSummary } from "../security/approval-gate.js";
import { requireApproval } from "../security/approval-gate.js";

export interface PlatformRunOptions {
  context: BrowserContext;
  game: GameEntry;
  dryRun?: boolean;
}

export interface PlatformStrategy {
  readonly id: string;
  run(opts: PlatformRunOptions): Promise<void>;
}

export abstract class BasePlatform {
  abstract readonly id: string;
  abstract run(opts: PlatformRunOptions): Promise<void>;

  protected async gated(
    game: GameEntry,
    action: string,
    details: Record<string, string | number | boolean>,
    fn: (page: Page) => Promise<void>,
    context: BrowserContext,
    dryRun?: boolean
  ): Promise<void> {
    const summary: ActionSummary = {
      platform: this.id,
      gameId: game.id,
      action,
      details,
    };
    await requireApproval(summary);
    if (dryRun) {
      console.log(`[dry-run] Would execute: ${action}`);
      return;
    }
    const page = context.pages()[0] ?? (await context.newPage());
    await fn(page);
  }
}
