/**
 * Treat all game_data strings as untrusted — strip control chars and HTML-like payloads
 * before they reach Playwright fill() calls.
 */

const CONTROL_CHARS = /[\u0000-\u001F\u007F]/g;
const SCRIPT_LIKE = /<script|javascript:|on\w+\s*=/gi;

export function sanitizePlainText(input: string, maxLen: number): string {
  let s = input.normalize("NFKC").replace(CONTROL_CHARS, "").trim();
  if (SCRIPT_LIKE.test(s)) {
    throw new Error("Rejected input: possible script/injection pattern detected");
  }
  if (s.length > maxLen) {
    s = s.slice(0, maxLen);
  }
  return s;
}

export function sanitizeSlug(input: string): string {
  const s = sanitizePlainText(input, 80).toLowerCase();
  if (!/^[a-z0-9-]+$/.test(s)) {
    throw new Error(`Rejected slug: "${s}"`);
  }
  return s;
}

export function sanitizeGameEntryForPlatform<T extends Record<string, unknown>>(entry: T): T {
  const out = { ...entry };
  for (const [k, v] of Object.entries(out)) {
    if (typeof v === "string") {
      (out as Record<string, unknown>)[k] = sanitizePlainText(v, 10_000);
    }
  }
  return out;
}
