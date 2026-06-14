#!/usr/bin/env node
import { readFileSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import dotenv from "dotenv";
import { openPersistentContext, closeContext } from "./browser/context.js";
import { getPlatform, listPlatforms, type PlatformId } from "./platforms/index.js";
import { gameDataFileSchema } from "./schema/game-data.js";
import { assertEnvNotTracked, assertUnsafeGatesNotDefault } from "./security/env-guard.js";
import { setSecret, deleteSecret, type CredentialKind } from "./security/credentials.js";
import { requireMedallionStartup } from "./security/approval-gate.js";
import { appendAudit } from "./security/audit-log.js";

const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");

dotenv.config({ path: resolve(repoRoot, ".env") });

interface CliArgs {
  platform?: PlatformId;
  game?: string;
  dryRun?: boolean;
  credentials?: { cmd: "set" | "delete"; account: CredentialKind };
  list?: boolean;
}

function parseArgs(argv: string[]): CliArgs {
  const out: CliArgs = {};
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--platform" && argv[i + 1]) {
      out.platform = argv[++i] as PlatformId;
    } else if (a === "--game" && argv[i + 1]) {
      out.game = argv[++i];
    } else if (a === "--dry-run") {
      out.dryRun = true;
    } else if (a === "--list") {
      out.list = true;
    } else if (a === "credentials" && argv[i + 1] === "set" && argv[i + 2]) {
      out.credentials = {
        cmd: "set",
        account: normalizeCredAccount(argv[i + 2]),
      };
      i += 2;
    } else if (a === "credentials" && argv[i + 1] === "delete" && argv[i + 2]) {
      out.credentials = { cmd: "delete", account: normalizeCredAccount(argv[i + 2]) };
      i += 2;
    }
  }
  return out;
}

function normalizeCredAccount(raw: string): CredentialKind {
  const map: Record<string, CredentialKind> = {
    itch_butler_key: "itch-butler-key",
    "itch-butler-key": "itch-butler-key",
    steam_password_hint: "steam-password-hint",
    "steam-password-hint": "steam-password-hint",
  };
  const k = map[raw];
  if (!k) throw new Error(`Unknown credential account: ${raw}`);
  return k;
}

function loadGameData(): ReturnType<typeof gameDataFileSchema.parse> {
  const rel = process.env.FLEET_AUTOMATION_DATA_FILE ?? "game_data.json";
  const dataPath = resolve(repoRoot, rel);
  if (!dataPath.startsWith(repoRoot + "/")) {
    throw new Error("game_data.json must live inside the fleet-automation directory (path guard)");
  }
  const raw = JSON.parse(readFileSync(dataPath, "utf8"));
  return gameDataFileSchema.parse(raw);
}

async function readSecretFromStdin(prompt: string): Promise<string> {
  const readline = await import("node:readline/promises");
  const { stdin, stdout } = await import("node:process");
  if (!stdin.isTTY) throw new Error("Credential entry requires interactive terminal");
  console.log(prompt);
  console.log("(input hidden from shell history — type value and press Enter)");
  const rl = readline.createInterface({ input: stdin, output: stdout });
  try {
    // Node has no built-in hide echo; value still visible while typing — operator should clear history
    const v = (await rl.question("Secret: ")).trim();
    if (!v) throw new Error("Empty secret refused");
    return v;
  } finally {
    rl.close();
  }
}

async function main(): Promise<void> {
  const args = parseArgs(process.argv.slice(2));

  if (args.credentials) {
    if (args.credentials.cmd === "set") {
      const value = await readSecretFromStdin(`Store credential: ${args.credentials.account}`);
      await setSecret(args.credentials.account, value);
      console.log(`✓ Stored ${args.credentials.account} in OS credential store.`);
      return;
    }
    if (args.credentials.cmd === "delete") {
      await deleteSecret(args.credentials.account);
      console.log(`✓ Deleted ${args.credentials.account} from OS credential store.`);
      return;
    }
  }

  assertEnvNotTracked(repoRoot);
  assertUnsafeGatesNotDefault();

  const data = loadGameData();

  if (args.list) {
    console.log("Platforms:", listPlatforms().join(", "));
    console.log(
      "Games:",
      data.games.map((g) => g.id).join(", ")
    );
    return;
  }

  if (!args.platform) {
    console.error("Usage: npm run dev -- --platform itch --game jimmythehat-pixelsports");
    console.error("       npm run dev -- --list");
    console.error("       npm run dev -- credentials set itch_butler_key");
    process.exit(1);
  }

  if (!listPlatforms().includes(args.platform)) {
    throw new Error(`Unknown platform "${args.platform}". Valid: ${listPlatforms().join(", ")}`);
  }

  const gameId = args.game;
  if (!gameId) {
    throw new Error("--game <id> is required (see game_data.json ids)");
  }

  const game = data.games.find((g) => g.id === gameId);
  if (!game) {
    throw new Error(`Game id "${gameId}" not found in game_data.json`);
  }

  console.log(`\nFleet Automation — platform=${args.platform} game=${game.id}${args.dryRun ? " [DRY-RUN]" : ""}\n`);

  await requireMedallionStartup();
  appendAudit(repoRoot, { event: "session_start", platform: args.platform, game: game.id, dryRun: !!args.dryRun });

  const context = await openPersistentContext({
    repoRoot,
    platform: args.platform,
    headless: false,
  });

  try {
    const strategy = getPlatform(args.platform);
    await strategy.run({ context, game, dryRun: args.dryRun });
    console.log("\n✓ Platform run finished.");
  } catch (err) {
    console.error("\n✗ Run aborted:", err instanceof Error ? err.message : err);
    process.exit(1);
  } finally {
    await closeContext(context);
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
