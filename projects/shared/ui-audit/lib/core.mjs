/** Shared overlap / viewport helpers for fleet UI audits */

export const PROFILES = [
  { name: "mobile-iphone14", width: 390, height: 844, isMobile: true },
  { name: "mobile-se", width: 375, height: 667, isMobile: true },
  { name: "desktop", width: 1280, height: 900, isMobile: false },
];

export function logIssue(bucket, profile, category, detail, extra = {}) {
  const row = { app: bucket.appId, path: bucket.path, profile, category, detail, ...extra };
  bucket.issues.push(row);
  console.log(`[${bucket.appId}/${profile}] ${category}: ${detail}`);
}

export async function rects(page, selectors) {
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
      };
    }
    return out;
  }, selectors);
}

export function overlap(a, b, minPx = 4) {
  if (!a || !b || a.hidden || b.hidden) return null;
  const x = Math.min(a.right, b.right) - Math.max(a.left, b.left);
  const y = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
  if (x < minPx || y < minPx) return null;
  return { x, y, area: x * y };
}

export function inViewport(r, vh) {
  if (!r || r.hidden || r.height < 4) return false;
  return r.bottom > 4 && r.top < vh - 4;
}

export async function shot(page, path) {
  try { await page.screenshot({ path, fullPage: false, timeout: 8000 }); }
  catch (_) {}
}

export async function safeClick(page, bucket, profile, sel, label) {
  bucket.iterations++;
  const el = page.locator(sel).first();
  if (!(await el.count())) return false;
  try {
    if (!(await el.isVisible())) return false;
    const box = await el.boundingBox();
    if (!box || box.width < 2 || box.height < 2) return false;
    await el.click({ timeout: 2500 });
    await page.waitForTimeout(80);
    return true;
  } catch (e) {
    logIssue(bucket, profile, "click-fail", `${label}: ${String(e.message || e).slice(0, 90)}`);
    return false;
  }
}

export async function auditClickables(page, bucket, profile, vh) {
  const bad = await page.evaluate((vhIn) => {
    const issues = [];
    const isFixed = (el) => {
      let n = el;
      while (n && n !== document.body) {
        const st = getComputedStyle(n);
        if (st.position === "fixed" || st.position === "sticky") return true;
        n = n.parentElement;
      }
      return false;
    };
    const nodes = [...document.querySelectorAll(
      "a[href], button:not([disabled]), [role=button], input:not([type=hidden]), textarea"
    )].filter((el) => {
      const st = getComputedStyle(el);
      if (st.display === "none" || st.visibility === "hidden") return false;
      const r = el.getBoundingClientRect();
      if (r.width < 8 || r.height < 8) return false;
      // Only flag fixed/sticky UI or controls that should be in the first screen
      return isFixed(el) || (r.top >= 0 && r.top < vhIn && r.bottom > 0);
    });
    for (const el of nodes) {
      const r = el.getBoundingClientRect();
      const fixed = isFixed(el);
      if (fixed && (r.bottom > vhIn + 2 || r.top < -2)) {
        issues.push({
          tag: el.tagName, id: el.id || "",
          text: (el.textContent || "").trim().slice(0, 40),
          bottom: Math.round(r.bottom), fixed: true,
        });
      } else if (!fixed && r.top < vhIn && r.bottom > vhIn + 24) {
        // Partially clipped in first viewport (hero CTAs etc.)
        issues.push({
          tag: el.tagName, id: el.id || "",
          text: (el.textContent || "").trim().slice(0, 40),
          bottom: Math.round(r.bottom), clipped: true,
        });
      }
    }
    return issues.slice(0, 6);
  }, vh);
  for (const b of bad) {
    const kind = b.fixed ? "fixed-offscreen" : "clipped-control";
    logIssue(bucket, profile, kind,
      `${b.tag}${b.id ? "#" + b.id : ""} "${b.text}" bottom=${b.bottom} (vh=${vh})`);
  }
}

export async function auditTinyTargets(page, bucket, profile) {
  const tiny = await page.evaluate(() => {
    return [...document.querySelectorAll("button, a[href], [role=button]")]
      .filter((el) => {
        const st = getComputedStyle(el);
        if (st.display === "none" || st.visibility === "hidden") return false;
        const r = el.getBoundingClientRect();
        return r.width > 0 && (r.width < 40 || r.height < 36);
      })
      .slice(0, 6)
      .map((el) => ({
        id: el.id || "",
        text: (el.textContent || "").trim().slice(0, 30),
        w: Math.round(el.getBoundingClientRect().width),
        h: Math.round(el.getBoundingClientRect().height),
      }));
  });
  for (const t of tiny) {
    logIssue(bucket, profile, "small-target",
      `${t.id || t.text || "control"} ${t.w}×${t.h}px (<44px touch guideline)`);
  }
}

export async function simulateKeyboard(page, open) {
  return page.evaluate((openKb) => {
    const full = window.innerHeight;
    const h = openKb ? full - Math.round(full * 0.42) : full;
    window.MobileKeyboard?.applyShellHeight?.(h);
    document.documentElement.style.setProperty("--cm-vvh", `${h}px`);
    document.documentElement.classList.toggle("cm-kb-active", openKb);
    return { h, openKb };
  }, open);
}

export function makeBucket(appId, path) {
  return { appId, path, issues: [], iterations: 0 };
}
