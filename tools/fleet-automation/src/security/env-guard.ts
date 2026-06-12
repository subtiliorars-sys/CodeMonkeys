import { execSync } from "node:child_process";
import { existsSync, statSync } from "node:fs";
import { resolve } from "node:path";

const SERVICE = "fleet-automation";

export function assertEnvNotTracked(repoRoot: string): void {
  const envPath = resolve(repoRoot, ".env");
  if (!existsSync(envPath)) return;

  try {
    const tracked = execSync("git ls-files --error-unmatch .env 2>/dev/null", {
      cwd: repoRoot,
      encoding: "utf8",
      stdio: ["pipe", "pipe", "ignore"],
    });
    if (tracked.trim()) {
      console.error("\n🚫 SECURITY: .env is tracked by git. Remove it immediately:");
      console.error("   git rm --cached .env && git commit -m 'untrack secrets'\n");
      process.exit(1);
    }
  } catch {
    // not tracked — good
  }

  if (process.platform !== "win32") {
    const mode = statSync(envPath).mode & 0o777;
    if (mode & 0o077) {
      console.warn(`⚠️  .env permissions are ${mode.toString(8)} — recommend chmod 600`);
    }
  }
}

export function assertUnsafeGatesNotDefault(): void {
  if (process.env.FLEET_AUTOMATION_UNSAFE_SKIP_GATES === "1") {
    console.warn("⚠️  Running with approval gates DISABLED — not recommended for production use.");
  }
}

export { SERVICE };
