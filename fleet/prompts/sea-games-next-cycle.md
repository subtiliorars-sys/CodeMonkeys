# Sea Games — Next Work Cycle Prompt

**Status:** Ready to code  
**Duration:** Estimate 2–4 weeks per game (solo dev + design partner)

---

## What's Done

Three whale games fully designed and repo-initialized:
1. **WhiteWhale** — Hunted-leviathan action-adventure (8–10h)
2. **Cetacea** — Language-learning puzzle-adventure (4–6h)
3. **Tidesung** — Meditative whale-song experience (25–35 min)

Each has:
- Private HQ repo (full code/assets) + public Preview repo (teaser)
- Detailed GDD (private) / CONCEPT.md (public)
- Standardized Phaser 3 + TypeScript setup
- Proprietary licensing

Five additional sea game concepts locked (see `/fleet/sea-games-concepts.md`):
- Current, Tides, Abyss, Riptide, Windlass

---

## What to Do Next

**Pick one whale game to prototype:**

### Recommendation: Tidesung (Smallest Scope)
- 25–35 minute experience
- Core mechanic: whale song as interaction
- Single beautiful ocean location
- 2–3 week sprint to playable alpha

**Bootstrap the project:**
1. Clone `/tmp/game-repos/Tidesung` (or fresh clone from GitHub)
2. `npm init -y && npm install --save phaser`
3. Set up Vite config (build tool)
4. Create `/src/scenes/` folder structure
5. Initialize main game loop (camera, ocean canvas)

**Implement core loop:**
1. **Swimming mechanic** — free-form whale movement
2. **Song interaction** — Web Audio API for whale vocalizations
3. **Environmental response** — creatures/light respond to song
4. **Narrative arc** — birth → solo journey → reunion (minimal)
5. **Art proof-of-concept** — test visual direction

**Playtest & iterate:**
- Get a build running in the browser
- Test on real devices (Chromebook, desktop, mobile)
- Iterate on feel (speed, responsiveness, beauty)

---

## Key Docs

- **GDD:** `~/Tidesung/docs/GDD.md` (full design)
- **Concepts (Wave 2):** `~/fleet/sea-games-concepts.md`
- **Status:** `~/fleet/status/sea-games.md`

---

## Git Workflow

Standard per CLAUDE.md:
- Branch: `work/tidesung-core-loop`
- Stage only YOUR files: `git add src/ docs/`
- Commit early, push before end-of-session
- PR when core loop is playable

---

## Blockers to Resolve

- [ ] Which whale game to start with? (Tidesung recommended)
- [ ] Art direction locked? (Check GDD; recommend stylized 2D)
- [ ] Audio: whale phonemes (real data or synthesize?)
- [ ] Publishing: web-first vs. Steam/itch (affects architecture)

---

## Paste This to Start New Session

```
I'm picking up the Tidesung project (meditative whale-song game). 
The GDD is in ~/Tidesung/docs/GDD.md. 
I need to bootstrap Phaser 3 + TS, then implement:
1. Whale swimming mechanic
2. Song (Web Audio) interaction
3. Basic ocean scene
4. Get to playable alpha.

What's first?
```

---

**Prepared:** 2026-06-11  
**Ready:** Yes
