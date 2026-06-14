import { createHash } from "node:crypto";
import * as readline from "node:readline/promises";
import { stdin as input, stdout as output } from "node:process";
import {
  checkpointsForPhase,
  formatMedallionBanner,
  isIrreversibleAction,
  type LoopPhase,
} from "../governance/medallion-loop.js";

export interface ActionSummary {
  platform: string;
  gameId: string;
  action: string;
  details: Record<string, string | number | boolean>;
}

export function hashAction(summary: ActionSummary): string {
  const payload = JSON.stringify(summary, Object.keys(summary).sort());
  return createHash("sha256").update(payload).digest("hex").slice(0, 16);
}

/**
 * Hard execution gate — requires physical Y/N in an interactive TTY.
 * Cannot be bypassed by env unless FLEET_AUTOMATION_UNSAFE_SKIP_GATES=1 (logged loudly).
 */
function phaseForAction(action: string): LoopPhase {
  return isIrreversibleAction(action) ? "pre_irreversible" : "pre_action";
}

/** Startup medallion loop — runs once before any browser session opens. */
export async function requireMedallionStartup(): Promise<void> {
  if (process.env.FLEET_AUTOMATION_UNSAFE_SKIP_GATES === "1") return;
  assertInteractiveTty();
  console.log(formatMedallionBanner("startup", "fleet-automation session start"));
  await promptYesNo("Acknowledge Medallion startup checkpoints and continue");
}

export async function requireApproval(summary: ActionSummary): Promise<void> {
  if (process.env.FLEET_AUTOMATION_UNSAFE_SKIP_GATES === "1") {
    console.warn("\n⚠️  UNSAFE: approval gates disabled via FLEET_AUTOMATION_UNSAFE_SKIP_GATES=1\n");
    return;
  }

  assertInteractiveTty();

  const phase = phaseForAction(summary.action);
  console.log(formatMedallionBanner(phase, summary.action));

  const digest = hashAction(summary);
  console.log("\n╔══════════════════════════════════════════════════════════════╗");
  console.log("║  APPROVAL REQUIRED — review before any browser mutation      ║");
  console.log("╚══════════════════════════════════════════════════════════════╝");
  console.log(`  Platform : ${summary.platform}`);
  console.log(`  Game     : ${summary.gameId}`);
  console.log(`  Action   : ${summary.action}`);
  console.log(`  Details  : ${JSON.stringify(summary.details)}`);
  console.log(`  SHA-256  : ${digest} (truncated)`);
  console.log("");

  await promptYesNo("Proceed? [Y/N]");
}

function assertInteractiveTty(): void {
  if (!process.stdin.isTTY || !process.stdout.isTTY) {
    throw new Error(
      "Approval gate blocked: stdin/stdout must be an interactive terminal (TTY). " +
        "Background agents cannot bypass this gate (Step 1 / Tradition 2)."
    );
  }
}

async function promptYesNo(label: string): Promise<void> {
  const rl = readline.createInterface({ input, output });
  try {
    for (;;) {
      const answer = (await rl.question(`${label}: `)).trim().toUpperCase();
      if (answer === "Y" || answer === "YES") return;
      if (answer === "N" || answer === "NO") {
        throw new Error("Action denied by operator at approval gate (human veto)");
      }
      console.log("  Please type Y or N.");
    }
  } finally {
    rl.close();
  }
}

/** Expose for tests / audit exports */
export function medallionCheckpointsFor(action: string) {
  return checkpointsForPhase(phaseForAction(action));
}
