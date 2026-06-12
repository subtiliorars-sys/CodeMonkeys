import { z } from "zod";

const itchPlatformSchema = z.object({
  slug: z.string().min(1).max(80).regex(/^[a-z0-9-]+$/, "itch slug: lowercase, numbers, hyphens only"),
  price: z.number().min(0).max(9999),
  kind: z.enum(["html", "downloadable"]),
  play_in_browser: z.boolean().optional(),
});

const steamPlatformSchema = z.object({
  app_id: z.union([z.number().int().positive(), z.null()]),
  coming_soon: z.boolean().optional(),
});

const gameJoltPlatformSchema = z.object({
  slug: z.union([z.string().max(80).regex(/^[a-z0-9-]*$/), z.null()]),
  enabled: z.boolean(),
});

export const gameEntrySchema = z.object({
  id: z.string().min(1).max(64).regex(/^[a-z0-9-]+$/),
  title: z.string().min(1).max(120),
  short_description: z.string().min(1).max(300),
  description: z.string().min(1).max(10_000),
  tags: z.array(z.string().min(1).max(40).regex(/^[a-z0-9 -]+$/i)).max(20),
  platforms: z.object({
    itch: itchPlatformSchema.optional(),
    steam: steamPlatformSchema.optional(),
    gamejolt: gameJoltPlatformSchema.optional(),
  }),
});

export const gameDataFileSchema = z.object({
  games: z.array(gameEntrySchema).min(1).max(50),
});

export type GameEntry = z.infer<typeof gameEntrySchema>;
export type GameDataFile = z.infer<typeof gameDataFileSchema>;
