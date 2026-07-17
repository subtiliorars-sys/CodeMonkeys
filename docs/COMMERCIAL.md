# CodeMonkeys — Commercial product (ratified 2026-07-17)

Owner decision. Change price later without renaming the product.

## Brand vs seller

| Layer | Name | Role |
|-------|------|------|
| **Product brand / IP** | **CodeMonkeys** | What users see and play with — entertainment-framed coding-agent console |
| **Merchant of record** | **OmniTender Systems LLC** | Sells the subscription, Stripe, taxes, invoices, ToS |
| **Self-host / open** | CodeMonkeys (this repo) | Free to run yourself; commercial hosted seat is optional |

**Do not** require a second consumer brand (“Omni Code”). Optional later if marketing tests say so.

Footer / checkout copy: *CodeMonkeys — sold by OmniTender Systems LLC.*

## Offer

- **Price:** **$1 / month** (USD), Stripe subscription. Raise later via Stripe Price; no product rewrite.
- **What you get:** hosted CodeMonkeys seat + **free-model pack** wired for you (OpenRouter `:free` models + Auto routing) so you don’t babysit provider UIs.
- **BYOK (optional):** paste your own provider keys anytime for better models / higher limits.
- **What you do *not* get:** OmniTender/Owner Vertex GCP credits, shared `GITHUB_TOKEN`, or unlimited paid Claude/GPT on the house.

## Economics (non-negotiable)

The dollar buys the **workshop**, not the **tokens**. Model spend stays on:

1. Public / free-tier endpoints (rate-limited), or  
2. The subscriber’s own API keys.

Never put paying guests on shared paid credits by default.

## Access model

When billing is **enabled** (Stripe secrets set on the host):

1. Visitor starts **Subscribe — $1/mo** → Stripe Checkout.
2. Webhook marks / creates a Member with `subscription_status: active`.
3. First login → authenticator (+ optional passkey).
4. Free pack is seeded (OpenRouter free models + Auto). Play.

When billing is **disabled** (default for self-host / desktop): invite-only Owner flow unchanged. No Stripe required.

## Framing

Market as a playful coding console / agent workshop (entertainment product), not as OmniTender merchant tooling. Different audience, different tone. Legal line still names OmniTender as seller.

## Implementation status

| Piece | Status |
|-------|--------|
| This decision doc | ✅ |
| Stripe Checkout + webhook (fail-closed until secrets) | ✅ code; inert until `STRIPE_*` set |
| Login subscribe CTA + OmniTender seller line | ✅ |
| OpenRouter free callable without key + free-pack seed | ✅ |
| Per-user BYOK isolation (Members edit only their keys) | ⏳ next wave — see `docs/design/PER_USER_ISOLATION.md` |
| Public marketing page on omnitender.us | ⏳ optional follow-up |

## Ops (owner)

```text
fly secrets set -a codemonkeys \
  STRIPE_SECRET_KEY=sk_live_... \
  STRIPE_WEBHOOK_SECRET=whsec_... \
  STRIPE_PRICE_ID=price_... \
  BILLING_ENABLED=true
```

Create the $1/mo Price in Stripe Dashboard (OmniTender Systems LLC account).  
Webhook endpoint: `https://codemonkeys.fly.dev/api/billing/webhook`  
Events: `checkout.session.completed`, `customer.subscription.updated`, `customer.subscription.deleted`.

Self-hosters: leave unset — commercial surface stays OFF.
