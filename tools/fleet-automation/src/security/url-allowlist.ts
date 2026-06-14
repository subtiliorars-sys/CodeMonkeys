/**
 * Tradition 6 (no entanglement) — navigation limited to known store platforms.
 */

const ALLOWED_HOSTS = new Set([
  "itch.io",
  "www.itch.io",
  "partner.steamgames.com",
  "store.steampowered.com",
  "gamejolt.com",
  "www.gamejolt.com",
]);

export function assertUrlAllowed(url: string): void {
  let parsed: URL;
  try {
    parsed = new URL(url);
  } catch {
    throw new Error(`Rejected URL (parse failed): ${url}`);
  }
  if (parsed.protocol !== "https:") {
    throw new Error(`Rejected URL (HTTPS only): ${url}`);
  }
  if (!ALLOWED_HOSTS.has(parsed.hostname)) {
    throw new Error(
      `Rejected URL (not on allowlist): ${parsed.hostname}. ` +
        `Allowed: ${[...ALLOWED_HOSTS].join(", ")}`
    );
  }
}
