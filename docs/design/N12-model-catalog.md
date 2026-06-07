# Design: N12 — model catalog / pricing refresh

**Status:** PROPOSED (design only, no code). Build after #58 (S4-B) merges — it
touches `load_models`/`model_config` / `DEFAULT_PROVIDERS`, the same region #58
reworked. Rebase on fresh main, then implement.

## Problem
Today the per-provider model lists **and** their costs (`in`/`out` USD per 1M) are
hardcoded in `DEFAULT_PROVIDERS` (server.py). A new model (a new Claude / GPT /
Gemini / OpenRouter free model) requires a **code edit + redeploy** to appear in
the picker, and the cost numbers drift out of date — which matters because the
cost governor + daily cap (N2) price runs off them.

## Goal
Let the owner keep the model catalog current **without code edits** — add/update
models and costs from the UI, and optionally auto-refresh from provider APIs that
expose model lists/pricing. Persist to `/data` (already where `model_config.json`
lives) so it survives restarts.

## What already exists (don't rebuild)
- `POST /api/models` upsert already accepts a provider's `models` list + `in`/`out`
  costs and persists them. So manual editing is *partly* possible already.
- `load_models()` seeds built-ins via `DEFAULT_PROVIDERS.setdefault` (new presets
  appear without wiping keys).

## Approach (two layers)
### Layer A — manual catalog editing (small, do first)
- ⚙ Models UI: per provider, an **"+ add model"** row (model id + in/out cost) and
  inline edit/remove of existing models; "set as selected". Wire to the existing
  upsert. Validate costs are finite ≥ 0 (reuse the N2 finite-guard pattern).
- Result: owner adds any new model in 10 seconds, no deploy.

### Layer B — auto-refresh from provider APIs (medium, optional)
`POST /api/models/{pid}/refresh` (owner-only) pulls the provider's current models:
- **OpenRouter** — `GET https://openrouter.ai/api/v1/models` returns models **with
  pricing** (`pricing.prompt`/`completion` per token). Best case: auto-populate
  list **and** costs (convert per-token → per-1M). This is the highest-value
  refresh (free-model list churns constantly — core to the value prop).
- **OpenAI** — `GET /v1/models` returns ids only (no pricing) → refresh the list,
  leave costs to manual/curated defaults.
- **Anthropic / others** — no public list endpoint → keep curated defaults; manual.
- Merge policy: add new models; do NOT overwrite a cost the owner manually set
  (track a `manual_cost` flag or only fill missing); never drop a model the owner
  pinned. Owner-triggered only (no background polling → controls API calls/cost).

## Risks / notes
- **Pricing units:** OpenRouter is USD/token; we store USD/1M — convert (×1e6) and
  round; guard against null/“variable” pricing.
- **Don't let refresh wipe keys or selection** — refresh touches `models`/costs
  only, never `key`/`selected`.
- **Cost-governor coupling:** N2's daily cap + tier routing read these costs;
  a bad refresh (e.g. 0 cost) could disable cost protection → validate finite > 0
  or fall back to the prior value; log anomalies.
- **Auth:** refresh uses the provider's stored key; owner-only endpoint; never log
  the key; https-only (reuse existing patterns).
- **Interaction with #58 (S4-B):** model_config is now encrypted-at-rest; refresh
  writes go through the same `save_models` (encryption-aware) path — fine, just
  build on top of #58.

## Tests (when built)
- Manual add/edit/remove model persists + survives reload; cost validation rejects
  non-finite/negative; OpenRouter refresh maps pricing per-token→per-1M correctly
  (stub the HTTP); refresh adds new models without overwriting manual costs or
  dropping pinned/selected; refresh never alters `key`/`selected`; owner-only.

## Owner decisions (none blocking now)
- Auto-refresh on OpenRouter only to start (highest value), or wire OpenAI list too?
- Overwrite-vs-preserve policy for costs on refresh (default: preserve manual,
  fill missing).
