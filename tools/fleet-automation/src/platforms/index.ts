import type { PlatformStrategy } from "./base.js";
import { ItchPlatform } from "./itch.js";
import { SteamPlatform } from "./steam.js";
import { GameJoltPlatform } from "./gamejolt.js";

export type PlatformId = "itch" | "steam" | "gamejolt";

const registry: Record<PlatformId, () => PlatformStrategy> = {
  itch: () => new ItchPlatform(),
  steam: () => new SteamPlatform(),
  gamejolt: () => new GameJoltPlatform(),
};

export function getPlatform(id: PlatformId): PlatformStrategy {
  const factory = registry[id];
  if (!factory) throw new Error(`Unknown platform: ${id}`);
  return factory();
}

export function listPlatforms(): PlatformId[] {
  return Object.keys(registry) as PlatformId[];
}
