import { appendFileSync, mkdirSync } from "node:fs";
import { resolve } from "node:path";

/** Step 5 — radical transparency: append-only local audit trail. */
export function appendAudit(repoRoot: string, line: Record<string, unknown>): void {
  const dir = resolve(repoRoot, "user-data");
  mkdirSync(dir, { recursive: true, mode: 0o700 });
  const entry = { ts: new Date().toISOString(), ...line };
  appendFileSync(resolve(dir, "audit.log"), JSON.stringify(entry) + "\n", { mode: 0o600 });
}
