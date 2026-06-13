# Code Gremlins

**Code Gremlins** are CodeMonkeys' feral red team — deployable agents whose job is to **insult your code until the flaws are obvious**, stress-test hot paths, and suggest simpler routes you missed.

They complement (not replace) formal **red-team** review:

| | **Code Gremlins** | **Red Team** |
|---|-------------------|--------------|
| **Tone** | Savage, specific, meme-adjacent | Cold, formal, security register |
| **Focus** | Waste, complexity, load, "why did you write it like that?" | Auth, data isolation, irreversible actions, money |
| **Model tier** | T2 (Sonnet) | T3 (Opus) |
| **Output** | Roast board + stress notes | SHIP / DO-NOT-SHIP verdict |

## When to unleash them

- After a feature lands and you want a **pre-merge roast**.
- Before optimizing — gremlins find **accidental complexity** first.
- When tests pass but something "feels heavy" — gremlins **stress paths** (local benchmarks, scaled fixtures).
- When the monkeys got cocky.

## When *not* to use gremlins alone

- Auth, secrets, multi-tenant isolation, payments → spawn **red-team** (T3), not just gremlins.
- Gremlins may **escalate** to red-team if they find something that stops being funny.

## How to deploy (in console)

1. Open **👹 Code Gremlins** from Settings (or the landing card).
2. Click **Unleash on session** — prefills a spawn prompt for the lead agent.
3. Or tell the session directly: *"Spawn code-gremlins on everything we touched this session."*

Agent definition: `corps/agents/code-gremlins.md` (loaded automatically into Daystrom corps).

## Example roast line (real findings only)

> **"This function is a participation trophy."**  
> `server.py:4206` — cooldown check re-scans the full provider list on every ping; under load that's O(providers × requests). Cache the bench set or you're paying rent on a closet.

Gremlins **report only** — field-engineer fixes, provost-qa verifies, red-team gates high-risk deltas.
