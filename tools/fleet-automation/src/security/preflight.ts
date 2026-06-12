#!/usr/bin/env node
/**
 * Run before any automation: npm run preflight
 */
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { assertEnvNotTracked, assertUnsafeGatesNotDefault } from "./env-guard.js";

const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), "../..");

assertEnvNotTracked(repoRoot);
assertUnsafeGatesNotDefault();

console.log("✓ Preflight OK — .env not tracked, security checks passed.");
