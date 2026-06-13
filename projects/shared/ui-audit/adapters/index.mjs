import {
  makeBucket, logIssue, rects, overlap, inViewport, safeClick,
  auditClickables, auditTinyTargets, simulateKeyboard, shot,
} from "../lib/core.mjs";
import { loginCodeMonkeys, loginMeniscusDev, loginOmniHerald } from "../lib/auth.mjs";

export async function runAdapter(adapter, ctx) {
  const fn = ADAPTERS[adapter];
  if (!fn) throw new Error(`Unknown adapter: ${adapter}`);
  return fn(ctx);
}

const ADAPTERS = {
  async codemonkeys({ page, profile, base, path, bucket, shotDir, mfa, app }) {
    const p = profile.name;
    const vh = profile.height;
    const url = base + path;
    let code = mfa;
    if (!code && app) {
      try {
        const { fetchMfaCode } = await import("../lib/auth.mjs");
        const { resolve, dirname } = await import("node:path");
        const { fileURLToPath } = await import("node:url");
        const root = dirname(fileURLToPath(import.meta.url));
        const workspace = process.env.WORKSPACE || resolve(root, "../../../..");
        const { readFileSync } = await import("node:fs");
        const manifest = JSON.parse(readFileSync(resolve(root, "../manifest.json"), "utf8"));
        const cfg = manifest.apps.find((a) => a.id === app.id);
        code = await fetchMfaCode(resolve(workspace, cfg.project), "./data/audit/users.json", "ui-audit");
      } catch (e) {
        logIssue(bucket, p, "auth-fail", `MFA fetch: ${e.message}`);
        return;
      }
    }
    await page.goto(url, { waitUntil: "domcontentloaded" });
    await page.evaluate(() => localStorage.clear());
    await loginCodeMonkeys(page, base, { mfa: code });
    await page.goto(url, { waitUntil: "domcontentloaded" });
    await page.waitForSelector("#view-main:not(.hidden)", { timeout: 5000 }).catch(() => {});

    await checkCmRegions(page, bucket, p, vh, "idle");
    if (profile.isMobile) {
      await page.locator("#msg").focus().catch(() => {});
      const kb = await simulateKeyboard(page, true);
      await checkCmRegions(page, bucket, p, kb.h, "keyboard");
      await simulateKeyboard(page, false);
    }

    const targets = [
      "#btn-mobile-menu", "#landing-new-session", "[data-mode=plan]",
      "#btn-attach", "#btn-settings", "#fb-fab",
    ];
    for (const sel of targets) {
      await safeClick(page, bucket, p, sel, sel);
      await page.keyboard.press("Escape").catch(() => {});
      await page.evaluate(() => window.MobileDrawer?.close?.());
    }
    await shot(page, `${shotDir}/${bucket.appId}-${p}.png`);
  },

  async "meniscus-console"({ page, profile, base, path, bucket, shotDir }) {
    const p = profile.name;
    const vh = profile.height;
    await loginMeniscusDev(page, base);

    const r = await rects(page, {
      sidebar: "#app-sidebar",
      main: "#app-main",
      hamburger: "#sidebar-hamburger",
      fab: "#fb-fab",
    });
    if (profile.isMobile && r.hamburger && !inViewport(r.hamburger, vh)) {
      logIssue(bucket, p, "offscreen", "hamburger menu not in viewport");
    }
    if (r.fab && r.main) {
      const o = overlap(r.fab, r.main);
      if (o && o.area > 200) logIssue(bucket, p, "overlap", `FAB ∩ main (${Math.round(o.area)}px²)`);
    }

    const clicks = ["#sidebar-hamburger", "#newcomer-home-btn", "#btn-settings", "#fb-fab"];
    for (const sel of clicks) {
      await safeClick(page, bucket, p, sel, sel);
      await page.keyboard.press("Escape").catch(() => {});
    }
    if (profile.isMobile) {
      const input = page.locator("textarea, input[type=text]").first();
      if (await input.count()) {
        await input.focus().catch(() => {});
        await auditClickables(page, bucket, p, Math.round(vh * 0.58));
      }
    }
    await auditClickables(page, bucket, p, vh);
    await auditTinyTargets(page, bucket, p);
    await shot(page, `${shotDir}/${bucket.appId}-${p}.png`);
  },

  async "meniscus-cairn"(ctx) {
    await ADAPTERS["meniscus-console"](ctx);
  },

  async "static-site"({ page, profile, base, path, bucket, shotDir }) {
    const p = profile.name;
    const vh = profile.height;
    await page.goto(base + path, { waitUntil: "domcontentloaded" });
    await auditClickables(page, bucket, p, vh);
    await auditTinyTargets(page, bucket, p);

    const headerFooter = await rects(page, {
      header: "header, .site-header, .nav-bar",
      main: "main, #main, .wrap",
      footer: "footer, .site-footer",
    });
    if (headerFooter.footer && headerFooter.main) {
      const fixedFooter = await page.evaluate(() => {
        const f = document.querySelector("footer, .site-footer");
        if (!f) return false;
        const st = getComputedStyle(f);
        return st.position === "fixed" || st.position === "sticky";
      });
      if (fixedFooter) {
        const o = overlap(headerFooter.footer, headerFooter.main);
        if (o && o.area > 300) logIssue(bucket, p, "overlap", `footer ∩ main (${Math.round(o.area)}px²)`);
      }
    }

    const links = page.locator("nav a[href], header a[href], .topnav a[href]");
    const n = Math.min(await links.count(), 3);
    for (let i = 0; i < n; i++) {
      bucket.iterations++;
      try {
        const href = await links.nth(i).getAttribute("href");
        if (!href || href.startsWith("#") || href.startsWith("mailto:") || href.startsWith("http")) continue;
        await links.nth(i).click({ timeout: 2000 });
        await page.waitForTimeout(80);
        await auditClickables(page, bucket, p, vh);
      } catch (_) {}
    }

    const form = page.locator("input, textarea").first();
    if (profile.isMobile && await form.count()) {
      await form.focus().catch(() => {});
      await auditClickables(page, bucket, p, Math.round(vh * 0.58));
    }
    await shot(page, `${shotDir}/${bucket.appId}-${p}-${path.replace(/\W+/g, "_")}.png`);
  },

  async "canvas-game"({ page, profile, base, path, bucket, shotDir }) {
    const p = profile.name;
    const vh = profile.height;
    await page.goto(base + path, { waitUntil: "networkidle", timeout: 20000 }).catch(() =>
      page.goto(base + path, { waitUntil: "domcontentloaded" }),
    );
    await page.waitForTimeout(1500);

    const canvas = await page.evaluate((vhIn) => {
      const c = document.querySelector("canvas");
      if (!c) return { missing: true };
      const r = c.getBoundingClientRect();
      return {
        w: Math.round(r.width), h: Math.round(r.height),
        bottom: Math.round(r.bottom), vh: vhIn,
        overflowX: r.width > window.innerWidth + 4,
        overflowY: r.bottom > vhIn + 4,
      };
    }, vh);

    if (canvas.missing) logIssue(bucket, p, "missing-canvas", "no <canvas> found after load");
    else {
      if (canvas.overflowX) logIssue(bucket, p, "canvas-overflow", `canvas wider than viewport (${canvas.w}px)`);
      if (canvas.overflowY) logIssue(bucket, p, "canvas-overflow", `canvas extends below viewport (${canvas.bottom} > ${vh})`);
    }
    bucket.iterations += 5;
    await shot(page, `${shotDir}/${bucket.appId}-${p}.png`);
  },

  async "omni-herald"({ page, profile, base, path, bucket, shotDir }) {
    const p = profile.name;
    const vh = profile.height;
    await page.goto(base + path, { waitUntil: "domcontentloaded" });
    await loginOmniHerald(page, base);
    await auditClickables(page, bucket, p, vh);
    await auditTinyTargets(page, bucket, p);
    const clicks = ["button", "a[href]"];
    for (const sel of clicks) {
      const loc = page.locator(sel);
      if (await loc.count()) await safeClick(page, bucket, p, sel, sel);
    }
    await shot(page, `${shotDir}/${bucket.appId}-${p}.png`);
  },
};

async function checkCmRegions(page, bucket, profile, vh, label) {
  const r = await rects(page, { composer: "#composer", msg: "#msg", fab: "#fb-fab" });
  if (r.composer && !inViewport(r.composer, vh)) {
    logIssue(bucket, profile, "offscreen", `${label}: composer outside viewport (bottom=${Math.round(r.composer.bottom)}, vh=${vh})`);
  }
  if (r.msg && !inViewport(r.msg, vh)) {
    logIssue(bucket, profile, "offscreen", `${label}: #msg outside viewport`);
  }
  if (r.fab && r.composer) {
    const o = overlap(r.fab, r.composer);
    if (o && o.area > 100) logIssue(bucket, profile, "overlap", `${label}: FAB ∩ composer`);
  }
}
