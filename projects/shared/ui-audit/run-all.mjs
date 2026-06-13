#!/usr/bin/env node
/**
 * Fleet UI audit — all web-facing systems.
 *   npm install && npx playwright install chromium
 *   node run-all.mjs
 *   node run-all.mjs --only codemonkeys,pixelsports-hub
 */
import { chromium } from "playwright";
import { spawn } from "node:child_process";
import { mkdirSync, writeFileSync, readFileSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { PROFILES } from "./lib/core.mjs";
import { runAdapter } from "./adapters/index.mjs";

const ROOT = dirname(fileURLToPath(import.meta.url));
const WORKSPACE = process.env.WORKSPACE || resolve(ROOT, "../../../..");
const manifest = JSON.parse(readFileSync(resolve(ROOT, "manifest.json"), "utf8"));

const args = process.argv.slice(2);
const only = args.includes("--only")
  ? new Set(args[args.indexOf("--only") + 1].split(","))
  : null;
const noStart = args.includes("--no-start");
const shotDir = args.includes("--shots")
  ? args[args.indexOf("--shots") + 1]
  : "/tmp/fleet-ui-audit";
mkdirSync(shotDir, { recursive: true });

const servers = new Map();
const allIssues = [];
let totalIterations = 0;

function projectPath(app) {
  return resolve(WORKSPACE, app.project);
}

function startServer(app) {
  if (app.reuseServer) return;
  const key = app.id;
  if (servers.has(key)) return;
  const cwd = projectPath(app);
  const cmd = app.start.replace(/\{port\}/g, String(app.port));
  console.log(`▶ ${app.id} : ${cmd}`);
  try {
    const child = spawn("bash", ["-c", cmd], { cwd, stdio: "ignore", detached: true });
    child.on("error", (e) => console.warn(`spawn warn ${app.id}: ${e.message}`));
    child.unref();
    servers.set(key, { child, base: `http://127.0.0.1:${app.port}` });
  } catch (e) {
    console.warn(`start failed ${app.id}: ${e.message}`);
  }
}

function baseUrl(app) {
  if (app.reuseServer) {
    const s = servers.get(app.reuseServer);
    return s?.base || `http://127.0.0.1:${app.port}`;
  }
  return servers.get(app.id)?.base || `http://127.0.0.1:${app.port}`;
}

async function waitUp(url, ms = 25000) {
  const start = Date.now();
  while (Date.now() - start < ms) {
    try {
      const res = await fetch(url, { signal: AbortSignal.timeout(2000) });
      if (res.ok || res.status < 500) return true;
    } catch (_) {}
    await new Promise((r) => setTimeout(r, 400));
  }
  return false;
}

async function seedApp(app) {
  if (!app.seed) return;
  const { execSync } = await import("node:child_process");
  const cwd = projectPath(app);
  try {
    execSync(app.seed.replace(/\{port\}/g, String(app.port)), { cwd, stdio: "pipe", timeout: 20000 });
  } catch (e) {
    console.warn(`Seed warn ${app.id}:`, e.stderr?.toString()?.slice(0, 120) || e.message);
  }
}

async function auditApp(browser, app) {
  const base = baseUrl(app);
  const up = await waitUp(base + (app.paths[0] || "/"));
  if (!up) {
    allIssues.push({ app: app.id, category: "server-down", detail: `Could not reach ${base}` });
    console.log(`[${app.id}] server-down: ${base}`);
    return;
  }

  let mfa;
  // MFA fetched fresh per profile inside codemonkeys adapter

  for (const path of app.paths) {
    for (const profile of PROFILES) {
      const ctx = await browser.newContext({
        viewport: { width: profile.width, height: profile.height },
        isMobile: profile.isMobile,
        hasTouch: profile.isMobile,
      });
      ctx.setDefaultTimeout(12000);
      const page = await ctx.newPage();
      const bucket = { appId: app.id, path, issues: [], iterations: 0 };
      try {
        await runAdapter(app.adapter, {
          page, profile, base, path, bucket, shotDir, mfa, app,
        });
      } catch (e) {
        bucket.issues.push({
          app: app.id, path, profile: profile.name,
          category: "audit-error", detail: String(e.message || e).slice(0, 120),
        });
        console.log(`[${app.id}/${profile.name}] audit-error: ${e.message}`);
      }
      totalIterations += bucket.iterations;
      allIssues.push(...bucket.issues);
      await ctx.close();
    }
  }
}

async function main() {
  const apps = manifest.apps.filter((a) => !only || only.has(a.id));
  console.log(`Fleet UI audit — ${apps.length} apps → ${shotDir}\n`);

  // Start unique servers
  const toStart = noStart ? [] : apps.filter((a) => !a.reuseServer);
  for (const app of toStart) {
    await seedApp(app);
    startServer(app);
  }
  await new Promise((r) => setTimeout(r, 2000));

  const browser = await chromium.launch({ headless: true });
  try {
    for (const app of apps) {
      console.log(`\n══ ${app.id} ══`);
      await auditApp(browser, app);
    }
  } finally {
    await browser.close();
  }

  const byApp = {};
  const byCat = {};
  for (const i of allIssues) {
    byApp[i.app] = (byApp[i.app] || 0) + 1;
    byCat[i.category] = (byCat[i.category] || 0) + 1;
  }

  const report = {
    when: new Date().toISOString(),
    shotDir,
    iterations: totalIterations,
    issueCount: allIssues.length,
    byApp,
    byCategory: byCat,
    issues: allIssues,
  };
  const reportPath = resolve(shotDir, "fleet-report.json");
  writeFileSync(reportPath, JSON.stringify(report, null, 2));

  console.log("\n══ Summary ══");
  console.log(`Iterations: ${totalIterations}`);
  console.log(`Issues: ${allIssues.length}`);
  if (Object.keys(byApp).length) console.log("By app:", byApp);
  if (Object.keys(byCat).length) console.log("By category:", byCat);
  console.log(`Report: ${reportPath}`);

  process.exit(allIssues.length ? 1 : 0);
}

main().catch((e) => { console.error(e); process.exit(2); });
