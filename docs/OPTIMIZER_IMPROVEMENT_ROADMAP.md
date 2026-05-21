# Lineup Optimizer Improvement Roadmap

Tracks the agreed improvements to the **Multi-Week Transfer Planner** (`runMultiWeekPlanner` in `web/public/app.js`). The single-round Transfer Advisor is in good shape and not part of this roadmap.

Order: implement, test, document, get user sign-off, then move to the next item.

## Status

| # | Proposal | Status |
|---|---|---|
| P1 | Propagate budget across rounds | **done** |
| P2 | Target-team feasibility pre-check | **done** |
| P3 | Continuous target-distance objective (replace last-round cliff) | pending |
| P4 | Render budget evolution in results UI | pending |
| P5 | Replace greedy Wildcard/Limitless with real optimizer | pending |
| P6 | Beam dedupe key includes chip/bank state | pending |
| P7 | Annotate penalty trade-offs in rendering | pending |
| P8 | Cadillac / cold-start handling in projections | pending |
| P9 | (future) ML predictions for future-round projections | parked |

## P1 — Propagate budget across rounds

**Problem:** beam search uses a frozen budget (`budget: state.budget` at line 3374). If your team appreciates $2.2M after a race, that purchasing power is invisible to next round's transfer search. Breaks reachability for any target team that depends on held-asset appreciation.

**Fix:** after each round's transfers, advance `state.budget` by `Σ predictPriceChange(pick).expectedChange` across the new team's held picks. Store appreciation in `roundActions` for later display.

**Implementation (app.js v53):** In the `runMultiWeekPlanner` beam loop, at each candidate's `nextBeam.push` site, sum `predictPriceChange(pick, projectedPts).expectedChange` across the post-transfer team (5 drivers + 2 constructors). New state.budget = state.budget + roundAppreciation. Per-round `roundActions` entries now carry `budgetBefore`, `appreciation`, `budgetAfter` for the upcoming P4 UI render. The budget value is the spending ceiling (held team value + bank), so the same `<= state.budget` constraint inside `generateTransferCandidates` continues to work correctly.

**Approximation note:** `predictPriceChange` derives PPM from `seasonSummary.rounds` actual results. As the planner projects further into the horizon, the rolling-3 window doesn't refresh with simulated results — so projected appreciation 2-3 rounds out gets noisier. Acceptable for the first iteration; could be improved later by feeding simulated round outcomes back into PPM.

## P2 — Target-team feasibility pre-check

**Problem:** if target team costs more than `currentBudget + projectedAppreciation`, planner silently returns whatever it could fit instead of saying "impossible".

**Fix:** compute ceiling = budget + horizon-summed appreciation on held picks. If `targetCost > ceiling`, render a feasibility card up-front showing shortfall and which target picks are too expensive. Continue plan as "best partial match" with the gap quantified.

**Implementation (app.js v54):** In `runMultiWeekPlanner` after `roundProjections` is built, build a `feasibilityInfo` object containing `targetCost`, `currentBudget`, `horizonAppreciation` (sum across all horizon rounds of expected price changes on currently-held picks), `projectedCeiling`, and classification flags `isReachableNow` / `isPossiblyReachable` / `isUnreachable`. Also identifies the 2 priciest target picks (so user can revise target) and counts target picks already held. New `renderFeasibilityCard(info)` function renders a color-coded card (green/orange/red) at the top of results. Card always renders the beam-search plans below as "best partial match" when unreachable.

**Ceiling estimation note:** horizonAppreciation assumes the user holds the CURRENT team throughout the horizon. This is an upper bound — they could swap to target picks earlier and let those appreciate, but that requires affording the target's transition cost up-front (chicken-and-egg). If even this upper bound falls short of `targetCost`, target is definitively unreachable.

## P3 — Continuous target-distance objective

**Problem:** target bonus (+100/match) only applied on last round. Intermediate rounds optimize purely for points, ignoring the target until the cliff.

**Fix:** add `targetDistance × weight × (roundsRemaining + 1)` cost to every state's score. Near-term still favors points; late rounds heavily penalize being off-target.

## P4 — Render budget evolution

**Problem:** budget changes (and now P1's appreciation) are invisible to the user.

**Fix:** per-round line in plan card: `Budget: $X → $Y (+$Z appreciation, -$W transfer spend)`.

## P5 — Replace greedy Wildcard/Limitless

**Problem:** chip-fired team is picked greedily (sort by score, take top-N within budget). Misses dominated lineups.

**Fix:** call into `searchCombosWithPruning` (the same optimizer the single-round advisor uses) to find the optimal chip-fired team.

## P6 — Beam dedupe key

**Problem:** dedup key is just team composition. Two states with same team but different remaining chips collapse — the worse one wins by being first-seen.

**Fix:** key = `team | chipsAvailable-sorted | bankedTransfers`.

## P7 — Penalty trade-off annotation

**Problem:** user can't audit "was the -10pt extra transfer worth it?"

**Fix:** in plan rendering, when penalty > 0, show `+X gross, -10 penalty, +Y net` per round.

## P8 — Cold-start handling

**Problem:** drivers with no history (Cadillac in 2026) silently get affinity = 1.0, projected = base. UI doesn't disclose this.

**Fix:** flag such picks in projection rendering ("naive form-only projection — no historical signal").

## P9 — ML for future rounds (parked)

**Goal:** replace `projectScoresForRound`'s track-similarity heuristic with actual ML predictions for future rounds (priors-only, since FP data doesn't exist yet). Requires running `06_run_predictions.py` for each upcoming round with `--phase pre_fp_predict` and consuming those outputs from the planner. Revisit after P1-P8 land.
