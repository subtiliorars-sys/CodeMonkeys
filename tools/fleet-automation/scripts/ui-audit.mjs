#!/usr/bin/env node
/**
 * CodeMonkeys UI audit — mobile + desktop overlap & click smoke.
 * Run from tools/fleet-automation: node scripts/ui-audit.mjs
 */
import { chromium } from "playwright";
import { mkdirSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";

const args = process.argv.slice(2);
const base = args.includes("--base") ? args[args.indexOf("--base") + 1] : "http://127.0.0.1:8081";
const shotDir = args.includes("--shots") ? args[args.indexOf("--shots") + 1] : "/tmp/cm-ui-audit";
mkdirSync(shotDir, { recursive: true });

const PROFILES = [
  { name: "mobile-iphone14", width: 390, height: 844, isMobile: true },
  { name: "mobile-se", width: 375, height: 667, isMobile: true },
  { name: "desktop", width: 1280, height: 900, isMobile: false },
];

const issues = [];
let iteration = 0;

function logIssue(profile, category, detail, extra = {}) {
  issues.push({ profile, category, detail, ...extra, iteration });
  console.log(`[${profile}] ${category}: ${detail}`);
}

async function rects(page, selectors) {
  return page.evaluate((sels) => {
    const out = {};
    for (const [key, sel] of Object.entries(sels)) {
      const el = document.querySelector(sel);
      if (!el) { out[key] = null; continue; }
      const r = el.getBoundingClientRect();
      const st = getComputedStyle(el);
      const hidden = el.closest(".hidden") !== null
        || st.display === "none" || st.visibility === "hidden" || parseFloat(st.opacity) === 0;
      out[key] = {
        top: r.top, left: r.left, right: r.right, bottom: r.bottom,
        width: r.width, height: r.height, hidden,
        display: st.display, visibility: st.visibility,
      };
    }
    return out;
  }, selectors);
}

function overlap(a, b, minPx = 4) {
  if (!a || !b || a.hidden || b.hidden) return null;
  const x = Math.min(a.right, b.right) - Math.max(a.left, b.left);
  const y = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
  if (x < minPx || y < minPx) return null;
  return { x, y, area: x * y };
}

function inViewport(r, vh) {
  if (!r || r.hidden || r.height < 8) return false;
  return r.bottom > 4 && r.top < vh - 4;
}

async function checkMainRegions(page, profile, vh, label) {
  const visible = await page.evaluate(() => !document.getElementById("view-main")?.classList.contains("hidden"));
  if (!visible) return null;

  const r = await rects(page, {
    header: "#view-main header",
    stream: "#stream",
    composer: "#composer",
    msg: "#msg",
    fab: "#fb-fab",
    drawer: "#sidebar.drawer-open",
    overlay: "#sidebar-overlay.visible",
    send: "#btn-send",
  });

  const badOverlaps = [
    ["header", "composer", 400],
    ["stream", "composer", 800],
    ["composer", "fab", 120],
  ];
  for (const [a, b, minArea] of badOverlaps) {
    const o = overlap(r[a], r[b]);
    if (o && o.area > minArea) {
      logIssue(profile, "overlap", `${label}: ${a} ∩ ${b} (${Math.round(o.area)}px²)`);
    }
  }

  if (r.composer && !inViewport(r.composer, vh)) {
    logIssue(profile, "offscreen", `${label}: composer outside viewport (top=${Math.round(r.composer.top)}, bottom=${Math.round(r.composer.bottom)}, h=${Math.round(r.composer.height)}, vh=${vh})`);
  }
  if (r.msg && !inViewport(r.msg, vh)) {
    logIssue(profile, "offscreen", `${label}: #msg outside viewport (bottom=${Math.round(r.msg.bottom)}, vh=${vh})`);
  }
  if (r.fab && r.composer && !r.fab.hidden && !r.composer.hidden) {
    const o = overlap(r.fab, r.composer);
    if (o && o.area > 80) {
      logIssue(profile, "fab-overlap", `${label}: feedback FAB overlaps composer (${Math.round(o.area)}px²)`);
    }
  }
  return r;
}

async function simulateKeyboard(page, open) {
  return page.evaluate((openKb) => {
    const full = window.innerHeight;
    const h = openKb ? full - Math.round(full * 0.42) : full;
    window.MobileKeyboard?.applyShellHeight?.(h);
    document.documentElement.classList.toggle("cm-kb-active", openKb);
    return { full, h, openKb };
  }, open);
}

async function enterMainShell(page) {
  await page.evaluate(() => {
    localStorage.removeItem("cm_token");
    ["view-login", "view-setup"].forEach((id) => document.getElementById(id)?.classList.add("hidden"));
    const main = document.getElementById("view-main");
    main?.classList.remove("hidden");
    window.state = {
      token: "", username: "auditor", role: "Owner", sid: null, after: -1,
      files: [], mode: "default", timer: null, pollMs: 0,
    };
    window.MobileDrawer?.init?.();
    window.MobileKeyboard?.init?.();
    const landing = document.getElementById("landing-welcome");
    landing?.classList.remove("hidden");
    document.querySelectorAll(".owner-only").forEach((el) => el.classList.remove("hidden"));
    document.getElementById("enc-banner")?.classList.add("hidden");
    document.getElementById("budget-alert")?.classList.add("hidden");
  });
  await page.waitForSelector("#view-main", { timeout: 3000, state: "attached" });
}

async function shot(page, path) {
  try { await page.screenshot({ path, fullPage: false, timeout: 8000 }); }
  catch (e) { console.warn(`screenshot skip ${path}: ${e.message?.slice(0, 60)}`); }
}

async function safeClick(page, profile, sel, label) {
  iteration++;
  const el = page.locator(sel).first();
  if (!(await el.count())) return { skipped: true };
  try {
    if (!(await el.isVisible())) return { skipped: true };
    const box = await el.boundingBox();
    if (!box || box.width < 2 || box.height < 2) return { skipped: true };
    await el.click({ timeout: 2500 });
    await page.waitForTimeout(100);
    return { ok: true };
  } catch (e) {
    logIssue(profile, "click-fail", `${label}: ${String(e.message || e).slice(0, 100)}`);
    return { ok: false };
  }
}

async function closeOverlays(page) {
  await page.keyboard.press("Escape");
  await page.evaluate(() => {
    window.MobileDrawer?.close?.();
    document.querySelectorAll("#modal-models,#modal-mcp,#modal-cost,#modal-corps,#modal-gremlins,#modal-feedback,#modal-invite")
      .forEach((m) => m.classList.add("hidden"));
  });
}

async function auditProfile(browser, profile) {
  const ctx = await browser.newContext({
    viewport: { width: profile.width, height: profile.height },
    isMobile: profile.isMobile,
    hasTouch: profile.isMobile,
    deviceScaleFactor: profile.isMobile ? 2 : 1,
  });
  const page = await ctx.newPage();
  const p = profile.name;
  const vh = profile.height;

  await page.goto(`${base}/`, { waitUntil: "domcontentloaded" });
  await page.evaluate(() => localStorage.clear());
  await page.reload({ waitUntil: "domcontentloaded" });

  // Login layout
  iteration++;
  const login = await rects(page, { panel: "#view-login .panel", user: "#lg-user" });
  if (login.user && login.user.bottom > vh - 20) {
    logIssue(p, "login-fold", `username field near bottom (${Math.round(login.user.bottom)}/${vh})`);
  }
  await shot(page, resolve(shotDir, `${p}-login.png`));

  await enterMainShell(page);
  await checkMainRegions(page, p, vh, "main-idle");
  await shot(page, resolve(shotDir, `${p}-main-idle.png`));

  // Composer + simulated keyboard (mobile only — desktop unaffected in prod)
  if (profile.isMobile) {
    await page.locator("#msg").focus();
    await page.waitForTimeout(120);
    await checkMainRegions(page, p, vh, "composer-focus");

    const kb = await simulateKeyboard(page, true);
    await page.locator("#msg").focus();
    await page.waitForTimeout(150);
    const withKb = await checkMainRegions(page, p, kb.h, "keyboard-open");
    if (withKb?.composer && withKb.composer.bottom > kb.h + 4) {
      logIssue(p, "keyboard-cover", `composer extends past keyboard viewport (${Math.round(withKb.composer.bottom)} > ${kb.h})`);
    }
    if (withKb?.msg && withKb.msg.bottom > kb.h + 4) {
      logIssue(p, "keyboard-cover", `#msg extends past keyboard viewport (${Math.round(withKb.msg.bottom)} > ${kb.h})`);
    }
    await shot(page, resolve(shotDir, `${p}-keyboard-open.png`));
    await simulateKeyboard(page, false);
  }

  // Mobile-lite route
  if (profile.isMobile) {
    await page.goto(`${base}/m`, { waitUntil: "domcontentloaded" });
    await enterMainShell(page);
    await checkMainRegions(page, p, vh, "route-/m");
    await safeClick(page, p, "#btn-mobile-menu", "drawer");
    await checkMainRegions(page, p, vh, "drawer-open");
    await shot(page, resolve(shotDir, `${p}-drawer.png`));
    await closeOverlays(page);
  }

  // Button sweep
  await page.goto(`${base}/`, { waitUntil: "domcontentloaded" });
  await enterMainShell(page);

  const targets = [
    "#btn-mobile-menu", "#landing-new-session", "#landing-models", "#landing-gremlins",
    "[data-mode=plan]", "[data-mode=default]", "[data-mode=auto]",
    "#btn-attach", "#btn-gremlin-raid", "#btn-settings", "#btn-sidebar-advanced",
    "#btn-new-session", "#wb-toggle-fleet", "#wb-toggle-term", "#fb-fab",
  ];
  for (const sel of targets) {
    await safeClick(page, p, sel, sel);
    await checkMainRegions(page, p, vh, `click-${sel}`);
    await closeOverlays(page);
  }

  // Owner modals (direct open — no API)
  const modals = [
    ["#modal-models", "#modal-close"],
    ["#modal-gremlins", "#gremlins-close"],
    ["#modal-corps", "#corps-close"],
  ];
  for (const [modal, close] of modals) {
    iteration++;
    await page.evaluate((m) => document.querySelector(m)?.classList.remove("hidden"), modal);
    await page.waitForTimeout(80);
    const m = await rects(page, { modal, close });
    if (m.modal && m.modal.height > vh + 2) {
      logIssue(p, "modal-overflow", `${modal} taller than viewport (${Math.round(m.modal.height)} > ${vh})`);
    }
    await shot(page, resolve(shotDir, `${p}-${modal.replace("#", "")}.png`));
    await page.locator(close).click().catch(() => {});
  }

  // Stress focus cycles (~150 iterations)
  const stress = ["#msg", "#session-filter", "#btn-mobile-menu", "#btn-send", "#btn-settings", "#landing-new-session"];
  for (let i = 0; i < 50; i++) {
    iteration++;
    const sel = stress[i % stress.length];
    const loc = page.locator(sel).first();
    if (await loc.isVisible().catch(() => false)) {
      if (sel === "#msg") {
        await loc.focus();
        await simulateKeyboard(page, i % 2 === 0);
      } else {
        await loc.click().catch(() => loc.focus().catch(() => {}));
      }
      await page.waitForTimeout(35);
      if (i % 7 === 0) await checkMainRegions(page, p, sel === "#msg" && i % 2 === 0 ? Math.round(vh * 0.58) : vh, `stress-${i}`);
    }
  }

  await shot(page, resolve(shotDir, `${p}-final.png`));
  await ctx.close();
}

async function main() {
  console.log(`UI audit → ${base}\nShots: ${shotDir}`);
  const browser = await chromium.launch({ headless: true });
  try {
    for (const profile of PROFILES) {
      console.log(`\n=== ${profile.name} ${profile.width}×${profile.height} ===`);
      await auditProfile(browser, profile);
    }
  } finally {
    await browser.close();
  }

  const report = { base, shotDir, iterations: iteration, issueCount: issues.length, issues };
  const reportPath = resolve(shotDir, "report.json");
  writeFileSync(reportPath, JSON.stringify(report, null, 2));

  const byCat = {};
  for (const i of issues) byCat[i.category] = (byCat[i.category] || 0) + 1;

  console.log(`\n=== Summary ===`);
  console.log(`Iterations: ${iteration}`);
  console.log(`Issues: ${issues.length}`);
  if (Object.keys(byCat).length) console.log("By category:", byCat);
  console.log(`Report: ${reportPath}`);
  process.exit(issues.length ? 1 : 0);
}

main().catch((e) => { console.error(e); process.exit(2); });
