/** Auth helpers for server-backed apps (dev/audit accounts only). */

export async function loginCodeMonkeys(page, base, { user = "ui-audit", pin = "9999", mfa = "" }) {
  const res = await page.request.post(`${base}/api/login`, {
    data: { username: user, pin, mfa_code: mfa },
  });
  if (!res.ok()) throw new Error(`CodeMonkeys login ${res.status()}: ${await res.text()}`);
  const data = await res.json();
  await page.goto(base + "/", { waitUntil: "domcontentloaded" });
  await page.evaluate(({ token, username, role }) => {
    localStorage.setItem("cm_token", token);
    localStorage.setItem("cm_username", username);
    localStorage.setItem("cm_role", role);
    if (typeof showMain === "function") showMain();
  }, { token: data.token, username: data.username, role: data.role });
}

export async function loginMeniscusDev(page, base) {
  const res = await page.request.post(`${base}/api/dev-login`, { data: {} });
  if (!res.ok()) throw new Error(`Meniscus dev-login ${res.status()}: ${await res.text()}`);
  const data = await res.json();
  await page.goto(base + "/static/console/index.html", { waitUntil: "domcontentloaded" });
  await page.evaluate(({ token, username, role }) => {
    localStorage.setItem("brain_token", token);
    localStorage.setItem("brain_username", username);
    localStorage.setItem("brain_role", role || "Owner");
  }, { token: data.token, username: data.username, role: data.role });
  await page.reload({ waitUntil: "domcontentloaded" });
  await page.waitForSelector("#app-screen:not(.hidden)", { timeout: 8000 }).catch(() => {});
}

export async function loginOmniHerald(page, base, { user = "ui-audit", password = "audit-bootstrap-12" }) {
  const res = await page.request.post(`${base}/api/login`, {
    data: { username: user, password },
  });
  if (!res.ok()) throw new Error(`omni-herald login ${res.status()}: ${await res.text()}`);
  await page.goto(base + "/", { waitUntil: "domcontentloaded" });
}

export async function fetchMfaCode(projectPath, usersFile, user) {
  const { spawnSync } = await import("node:child_process");
  const script = usersFile.includes("dev_users") ? "dev_seed.py" : "scripts/dev_seed.py";
  const out = spawnSync("python3", [script, "--code"], {
    cwd: projectPath,
    env: { ...process.env, USERS_FILE: usersFile, DEV_USER: user },
    encoding: "utf8",
    timeout: 15000,
  });
  const text = (out.stdout || "") + (out.stderr || "");
  if (out.error) throw new Error(out.error.message);
  if (out.status !== 0) throw new Error(text.slice(0, 120) || `exit ${out.status}`);
  const m = text.match(/MFA(?: code)?:\s*(\d{6})/i);
  if (!m) throw new Error(`Could not parse MFA: ${text.slice(0, 120)}`);
  return m[1];
}
