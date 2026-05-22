# Lineup Optimizer Improvement Roadmap

Tracks the agreed improvements to the **Multi-Week Transfer Planner** (`runMultiWeekPlanner` in `web/public/app.js`). The single-round Transfer Advisor is in good shape and not part of this roadmap.

Order: implement, test, document, get user sign-off, then move to the next item.

## Status

| # | Proposal | Status |
|---|---|---|
| P1 | Propagate budget across rounds | **done** |
| P2 | Target-team feasibility pre-check | **done** |
| P3 | Continuous target-distance objective (replace last-round cliff) | **done** |
| P4 | Render budget evolution in results UI | **done** |
| P5 | Replace greedy Wildcard with real optimizer (Limitless already optimal) | **done** |
| P6 | Beam dedupe key includes chip/bank state | pending |
| P7 | Annotate penalty trade-offs in rendering | **done** |
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

**Implementation (app.js v55):** Replaced the last-round-only `+100/match` bonus block with a per-round distance penalty applied to every candidate's score: `distance × TARGET_WEIGHT × (ri+1)/horizon` where `distance` is the count of target picks NOT in the candidate (0..7) and `TARGET_WEIGHT = 30`. For a 3-round horizon this gives round-by-round weights of (10, 20, 30) per off-target pick — the final round still dominates (matching original behavior) but intermediate rounds now actively path-find toward target. Calibrated so 30 pts/off-target on the final round is meaningful relative to a typical ~25 pts/round driver projection (planner won't trade target match for <30 raw pts on last round) but doesn't force wildly suboptimal swaps when full convergence is impossible.

## P4 — Render budget evolution

**Problem:** budget changes (and now P1's appreciation) are invisible to the user.

**Fix:** per-round line in plan card: `Budget: $X → $Y (+$Z appreciation, -$W transfer spend)`.

**Implementation (app.js v56):** Two additions to `displayMultiWeekResults`:
1. **Plan header** gets a horizon budget summary: `Budget: $110.0M → $115.4M (+$5.4M)`, color-coded by sign.
2. **Each round column in the timeline** gets a dashed-bordered budget block below the existing pts/meta lines: `$110.0M → $112.2M` (before/after) with `+$2.2M apprec` underneath. Color-coded green/red. Renders only when `budgetBefore/After/appreciation` are present on the action (graceful fallback for legacy plans).

**Transfer spend deliberately omitted:** in this model, `state.budget` is the spending ceiling (held team value + bank). Transfers preserve the ceiling — you sell at price X, buy at price Y, so ceiling shifts only via appreciation between rounds. The actual bank value would require tracking per-round bank explicitly, which adds complexity for a number that's already implicit in the team-cost-vs-ceiling delta. May revisit if users want it.

## P5b — Limitless revert + chips respect target (app.js v59)

**Two bugs caught after P5 deploy:**

1. **Limitless was being treated as a permanent team change.** F1 Fantasy rule: Limitless is a one-round dream team; your real team is untouched. Pre-fix, firing Limitless consumed banked free transfers, applied a -10pt penalty per "extra swap" in the dream team, propagated the dream team to subsequent rounds, and compounded the dream team's projected appreciation into next round's budget. All wrong.

2. **Chips ignored the target team.** Wildcard's `findOptimalWildcardTeam` picked the max-points team within budget regardless of target. The P3 distance penalty was applied later in the score loop, but there was no alternative wildcard team to fall back to — the search had already locked in the highest-points team. Same architectural issue applied (less severely) to Limitless's distance penalty being measured against the dream team rather than the persistent team.

**Implementation:**
- `findOptimalWildcardTeam(budget, proj, targetInfo)` now takes optional `targetInfo = { driverSet, conSet, distanceWeight }` and incorporates the distance penalty directly into its objective. Driver pool is augmented with any target picks not already in the top-15 by score so they're considered. When target is set, the search natively picks the best balance of points and target-alignment.
- New per-round `roundTargetInfo` in the beam loop carries the per-round distance weight (`TARGET_WEIGHT * (ri+1) / horizon`, matching P3's main-loop calculation).
- New `isLimitless` flag drives a clean split between **dream team** (used for this round's `pts` calculation) and **persistent team** (used for state propagation, appreciation calc, distance penalty, strategy weighting, and carry-forward into next round).
- Limitless: `penalty = 0`, `remainingTransfers = transfersThisRound` (no consumption), `state.drivers/constructors` stay as pre-limitless.
- New `persistedTeam` field on `roundActions[]` records the team that carries into the next round. Used by team-evolution and P7 trade-off rendering so the round AFTER a limitless doesn't paint reverted-back picks as "NEW".
- Display: chip label gets `(reverts after round)` suffix for limitless.

**Limitless target distance:** intentionally measured against persistent team, not dream team. The dream team is temporary so its target match doesn't contribute to actual target convergence across the horizon. Limitless contributes only this round's score boost — it doesn't affect target progress in either direction.

## P5 — Replace greedy Wildcard with real optimizer

**Problem:** Wildcard-fired team is picked greedily (sort constructors by score → take top 2 regardless of price → fill drivers by score within remaining budget). Misses dominated lineups where a cheaper constructor would free budget for a much better driver.

**Fix:** call into `searchCombosWithPruning` (the same optimizer the single-round advisor uses) to find the optimal chip-fired team. Limitless is unchanged — with unlimited budget, top-5 + top-2 by score IS already optimal.

**Implementation (app.js v58):** New top-level `findOptimalWildcardTeam(budget, proj)` helper next to `searchCombosWithPruning`. Builds top-15 driver pool by projected score, sorts ascending by price for branch-and-bound pruning, enumerates all C(11,2)=55 constructor pairs, and runs `searchCombosWithPruning` for each pair to find best 5-driver combo within remaining budget. Returns `{drivers, constructors, cost, score}` or null.

**Performance:** the brute-force search is ~10-50× more work than the old greedy. To keep beam search responsive, `runMultiWeekPlanner` memoizes results in a `wildcardCache` map keyed by `(roundIndex, budget_bucket_0.1M)`. Wildcard's optimal team depends only on those two inputs (it ignores current team), so 60 beam states with similar budgets share one search. Without the cache, a 3-round 60-state beam would run 180 brute-force searches; with it, typically 3-10.

## P6 — Beam dedupe key

**Problem:** dedup key is just team composition. Two states with same team but different remaining chips collapse — the worse one wins by being first-seen.

**Fix:** key = `team | chipsAvailable-sorted | bankedTransfers`.

## P7 — Penalty trade-off annotation

**Problem:** user can't audit "was the -10pt extra transfer worth it?"

**Fix:** in plan rendering, when penalty > 0, show `+X gross, -10 penalty, +Y net` per round.

**Implementation (app.js v57):** Two additions to the per-round timeline block in `displayMultiWeekResults`:
1. **When penalty > 0** the points block expands to show gross + penalty + net explicitly (`14.3 net` / `24.3 gross · -10 pen · 2 FT`) so the user sees the whole math, not just the post-penalty number.
2. **Each round with swaps** gets a new "vs hold" trade-off line: compares the candidate's gross score against scoring the previous round's team against this round's projections. When penalty > 0, includes a verdict (`worth it` / `lost vs hold` / `break-even`). When no penalty, just shows the swap's gross delta. `prevTeamForTradeoff` is tracked across the timeline iteration so each round compares against the previous chosen team.

**Chip caveat:** hold-alternative uses raw `scoreTeam` without chip multipliers, so when the round fires a chip the comparison is directional rather than exact. Flagged with `*` and a `title` tooltip on the trade-off line.

## P8 — Cold-start handling

**Problem:** drivers with no history (Cadillac in 2026) silently get affinity = 1.0, projected = base. UI doesn't disclose this.

**Fix:** flag such picks in projection rendering ("naive form-only projection — no historical signal").

## P9 — ML for future rounds (parked)

**Goal:** replace `projectScoresForRound`'s track-similarity heuristic with actual ML predictions for future rounds (priors-only, since FP data doesn't exist yet). Requires running `06_run_predictions.py` for each upcoming round with `--phase pre_fp_predict` and consuming those outputs from the planner. Revisit after P1-P8 land.
