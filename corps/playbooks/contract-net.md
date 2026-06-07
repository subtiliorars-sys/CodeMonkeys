# Playbook: Contract-Net (self-bid assignment)

*Exotic pattern. Loaded only when triggered from `CORPS_PLAYBOOKS.md`. **Usually overkill —
default top-down assignment (Command picks the cheapest capable unit) is right almost
always.** Documented here for completeness; reach for it rarely.*

## Use when
A **batch of heterogeneous tasks** where unit fit/cost varies enough that top-down
assignment is visibly suboptimal — and the batch is big enough that a bidding round pays
for itself.

## Don't use when
Single tasks, small batches, or anytime cost-locked. The bidding round is pure overhead
(it needs a central aggregation step — a bottleneck), and at small scale it never recoups.
This is the classic contract-net tradeoff: better matching, but announce-bid-award costs.

## How to run (real primitives)
1. **Announce** the task list to the candidate units (one cheap prompt): "rate your fit
   (0–5) and estimated cost/tier for each task you could take."
2. **Bid:** each unit returns its self-rated fit + cost (one structured response).
3. **Award:** Command assigns each task to the **highest fit ÷ cost** bidder, no duplicates,
   respecting the spawn cap and reserve.
4. Then run the awarded tasks as a normal parallel wave.

## Payoff vs cost
Payoff: better task↔unit matching under heterogeneity. Cost: an extra announce+bid round
(latency + tokens) and a central award step. The bar to justify it is high.

## Exit
An assignment map, then normal execution. AAR line: `PLAYBOOK: contract-net · helped? yes/no/partial`.
