# Sea Games Wave — Summary & Handoff

**Date:** 2026-06-11  
**Status:** CONCEPTS LOCKED, REPOS INITIALIZED  
**Next Phase:** Development (Wave 2 TBD)

---

## Wave 1: Whale Games (COMPLETE)

Three whale-focused indie games, fully documented and repo-initialized.

### Repos Created (6 total)

1. **WhiteWhale** (private) + **WhiteWhale---Preview** (public)
   - Hunted-leviathan action-adventure, 8–10 hours
   - Inspired by Moby Dick + Subnautica
   - Theme: predator-prey inversion, mythic fate vs. agency

2. **Cetacea** (private) + **Cetacea---Preview** (public)
   - Narrative puzzle-adventure, 4–6 hours
   - Core mechanic: learn whale dialects to solve puzzles
   - Theme: communication as bridge between loneliness and belonging

3. **Tidesung** (private) + **Tidesung---Preview** (public)
   - Meditative experience, 25–35 minutes
   - Core mechanic: whale song as only interaction
   - Theme: one perfect moment of discovery and reunion

### Documentation per Repo
- **Private HQ:** Full README, proprietary LICENSE, comprehensive .gitignore, detailed GDD
- **Public Preview:** Teaser README, proprietary LICENSE, preview .gitignore, CONCEPT.md

### Tech Stack (All)
- **Engine:** Phaser 3 + TypeScript
- **Build:** Vite
- **Audio:** Web Audio API + Howler.js (whale vocalizations)
- **Testing:** Jest

---

## Wave 2: Additional Sea Games (CONCEPTS LOCKED)

Five additional ocean/sea game concepts documented in `/fleet/sea-games-concepts.md`:

1. **Current** — Fish/ecosystem simulator (ambient, educational)
2. **Tides** — Nautical exploration/piracy (6–10h action-adventure)
3. **Abyss** — Abyssal horror/discovery (4–6h mystery)
4. **Riptide** — Tide/current physics puzzles (3–5h puzzle-platformer)
5. **Windlass** — Sailboat racing/exploration (2–6h sailing-sim)

**Status:** Concept documents written, no repos created yet.

---

## Decisions Made

✅ **Naming:** Locked in (WhiteWhale, Cetacea, Tidesung + 5 more)  
✅ **Repo Pattern:** Private HQ + Public Preview (proprietary, no confidential)  
✅ **License:** Proprietary/all-rights-reserved across all  
✅ **Game Design:** Full GDD for whale games, CONCEPT docs for teaser repos  
✅ **Tech Stack:** Phaser 3 + TS standardized  

---

## Outstanding Decisions

- [ ] Prototype priority (which game first?)
- [ ] Art direction (pixel vs. stylized 3D vs. painterly?)
- [ ] Audio outsourcing (whale vocalizations, sound design)
- [ ] Publishing strategy (itch.io, Steam, web-first?)
- [ ] Team/collaboration model (solo dev + design partner scaling?)

---

## Files Created

- `/fleet/sea-games-concepts.md` — all 5 Wave 2 concepts
- `/fleet/sea-games-wave-summary.md` — this document
- 6 GitHub repos fully initialized with docs and config

---

## Next Work Cycle

When ready to proceed:

1. **Phase 1:** Pick one whale game to prototype (likely Tidesung — smallest scope)
2. **Phase 2:** Bootstrap dev environment (npm init, Phaser setup, git workflow)
3. **Phase 3:** Core loop implementation (swimming + interaction mechanic)
4. **Phase 4:** Visual proof-of-concept (art direction test)

For Wave 2 games: repeat repo initialization when ready to begin.

---

**Prepared by:** Claude Code  
**For:** New Fleet + Wave work cycle
