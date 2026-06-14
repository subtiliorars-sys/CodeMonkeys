import keytar from "keytar";
import { SERVICE } from "./env-guard.js";

export type CredentialKind = "itch-butler-key" | "steam-password-hint";

/**
 * OS-level credential store (Windows Credential Manager / macOS Keychain / Linux Secret Service).
 * Passwords and API keys never live in source or committed files.
 */
export async function getSecret(account: CredentialKind): Promise<string | null> {
  return keytar.getPassword(SERVICE, account);
}

export async function setSecret(account: CredentialKind, value: string): Promise<void> {
  if (!value || value.length < 4) {
    throw new Error("Refusing to store empty or trivial secret");
  }
  await keytar.setPassword(SERVICE, account, value);
}

export async function deleteSecret(account: CredentialKind): Promise<boolean> {
  return keytar.deletePassword(SERVICE, account);
}

export async function requireSecret(account: CredentialKind): Promise<string> {
  const v = await getSecret(account);
  if (!v) {
    throw new Error(
      `Missing credential "${account}". Store via:\n` +
        `  npm run dev -- credentials set ${account.replace(/-/g, "_")} <value>`
    );
  }
  return v;
}
