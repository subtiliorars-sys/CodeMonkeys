import { chromium, type BrowserContext } from "playwright";
import { mkdirSync } from "node:fs";
import { resolve } from "node:path";

export interface BrowserSessionOptions {
  repoRoot: string;
  platform: string;
  headless?: boolean;
}

/**
 * Isolated persistent context per platform — cookies/session stay on disk under user-data/
 * with OS-level permissions (chmod 700 on Unix). Never transmitted by application code.
 */
export async function openPersistentContext(opts: BrowserSessionOptions): Promise<BrowserContext> {
  const base = process.env.FLEET_AUTOMATION_USER_DATA_DIR ?? resolve(opts.repoRoot, "user-data");
  const userDataDir = resolve(base, opts.platform);

  mkdirSync(userDataDir, { recursive: true, mode: 0o700 });

  const context = await chromium.launchPersistentContext(userDataDir, {
    headless: opts.headless ?? false,
    viewport: { width: 1280, height: 900 },
    acceptDownloads: false,
    bypassCSP: false,
    ignoreHTTPSErrors: false,
    locale: "en-US",
  });

  return context;
}

export async function closeContext(context: BrowserContext): Promise<void> {
  await context.close();
}
