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
| P7 | Annotate penalty trade-offs in rendering | **done** |
| P8a | Confidence-weighted affinity (rookies/cold-start) | **done** |
| P8 | UI flag for low-confidence projections | **done** |
| P6 | Beam dedupe key includes chip/bank state | **done** |
| P9 | ML predictions for future-round projections | **done** |
| P10 | Hoist magic numbers into `MW_TUNABLES` | **done** |
| P11 | PPM-aware 2-swap candidate pool (raw score ∪ PPM) | **done** |
| P12 | Constructor+constructor 2-swap candidate | **done** |
| P13 | Target intensity dropdown (Loose / Balanced / Strict) | **done** |
| P14 | Clarify strategy score is internal-only ranking signal | **done** |

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

## P8a — Confidence-weighted affinity (app.js v60)

**Problem:** the old affinity code used a hard cliff: drivers had to have ≥2 total races AND cumulative similar-track weight ≥0.5 (sim>0.7 threshold) to escape affinity=1.0. Rookies and drivers without races at specialist circuits (Monaco, etc.) were silently locked at 1.0 even when partial signal existed — making veterans with strong track-specific history look disproportionately better at those tracks. Real example: Antonelli (strong current form, no Monaco history) vs Hamilton (weaker form, strong Monaco history) → Hamilton's affinity 1.4 vs Antonelli's silent 1.0 made the planner prefer Hamilton at Monaco even when Antonelli's base points were higher.

**Fix:** extracted the affinity calc into `computeAffinityWithConfidence(hist, targetVec, basePts)`. Three changes:
1. **Threshold relaxation:** `hist.length >= 1` (was 2), `weightSum > 0.1` (was 0.5). Any race-history driver now gets a chance to contribute signal.
2. **Softened similarity cliff:** `w = max(0, sim - 0.5) * 2.0` (was `(sim - 0.7) * 3.33`). Moderately-similar tracks contribute with lower weight instead of being ignored.
3. **Confidence-weighted blend:** `affinity = 1.0 + confidence * (rawAffinity - 1.0)` where `confidence = min(1, weightSum / 1.0)`. Low-data drivers get a dampened signal (closer to 1.0 baseline); high-data drivers get the full affinity. Smooth gradient instead of binary on/off.

`projectScoresForRound` now also returns `driverConfidence` and `constructorConfidence` dictionaries (per-pick confidence values in [0, 1]) for the UI to consume.

## P8 — UI flag for low-confidence projections (app.js v60)

**Problem:** even with P8a's smooth affinity blending, the user can't tell which heatmap cells are confident projections vs naive form-only estimates.

**Fix:** in `renderProjectionHeatmap`, each cell now reads `driverConfidence`/`constructorConfidence` from the round projection and applies one of three visual treatments:
- **Confidence > 0.5:** plain cell (full signal — historical data validates the projection).
- **Confidence 0.01-0.5:** dotted bottom border + slight opacity reduction + hover tooltip ("Limited historical signal (X% confidence)").
- **Confidence ≤ 0.01:** italic text + dotted border + stronger opacity reduction + tooltip ("No historical signal at similar tracks — naive form-only projection").

Current round (ML predictions) is hard-coded to confidence = 1.0 so it never shows the indicator. Legend below the heatmap explains the cell decorations.

## P6 — Beam dedupe key (app.js v61)

**Problem:** dedup key was just team composition. Two states with the same team but different remaining chips or different banked-FT counts collapsed — the first-seen one won even when the other represented a strictly better future.

**Fix:** key = `team-sorted | constructors-sorted | chipsAvailable-sorted | bankedTransfers`. Strictly-better paths now survive dedup.

## P9 — ML for future rounds (app.js v62, pipeline)

**Goal:** replace `projectScoresForRound`'s track-similarity heuristic with actual ML predictions for upcoming rounds.

**Implementation:**

1. **`pipeline/06_run_predictions.py`** gains an `output_suffix` parameter. When non-empty, predictions land in `data/predictions/round{N}/predictions_{suffix}.parquet` and `prediction_metadata_{suffix}.json` instead of the canonical files. The race-completed guard is also bypassed for suffixed runs (since they don't touch the accuracy archive). This lets us run priors-only predictions for future rounds without clobbering the canonical current-round files.

2. **`pipeline/predict_horizon.py`** is a new orchestrator. It calls `run_predictions(round, skip_fp=True, force=True, output_suffix="horizon")` for each round in `[current_round+1, current_round+horizon]` (skipping cancelled rounds), then converts the predicted positions into simplified expected fantasy points using the same scoring formulas as `07_calculate_fantasy.py` (minus the per-driver risk-rating lookup — uses a fixed 8% league-average DNF probability for projection purposes). Constructors aggregate as `sum(driver_pts excl DOTD)`. Output: `web/public/data/horizon_projections.json`.

3. **`web/public/app.js`** gains a `horizonProjections` global. `loadMultiWeekData()` fetches the file (optional — falls back silently if missing or stale). `projectScoresForRound()` prefers the ML projection for any driver/constructor present in the horizon JSON; falls back to the affinity heuristic only when ML data is missing. ML-projected cells get `confidence = 0.95` so they render as full-signal in the heatmap.

**Usage:**
```
python pipeline/predict_horizon.py --current-round 7 --horizon 5
```

Should be run after `06_run_predictions.py` (for the current round) in the weekly pipeline. Cadence: each `post_fp` / `post_quali` cycle should re-run it so the planner sees fresh ML projections for future rounds whenever current-round data changes.

**Trade-offs of the simplified scoring in `predict_horizon.py`:**
- Uses fixed DNF probability (8% league avg) instead of per-driver risk ratings (which require loading recent results + price data — too heavy for the projection script).
- Doesn't apply pitstop bonuses or quali-tier bonuses to constructors (too noisy to project two weekends ahead).
- Caps the "positions gained" overtake estimate to keep extreme-jump scenarios from inflating projections.
- These approximations are intentional: future-round projections are inherently noisy, and the goal is "much better than the affinity heuristic" not "as exact as the current-round fantasy calc."

## P10 — Hoist magic numbers into MW_TUNABLES

**Problem:** Beam width (60), transfer penalty (10), target weight (30), pool sizes, similarity thresholds, strategy weights — scattered across 200+ lines. No central spot to tweak or sensitivity-test.

**Fix:** Single `MW_TUNABLES = { ... }` block at the top of the Multi-Week Planner section in `app.js`. Every magic number now references it. Comments explain role + sensible range per constant.

**Implementation (app.js v63):** Added `MW_TUNABLES` covering beam search (beamWidth, transferPenalty, maxBankedTransfers), target team (targetWeight + intensity map), candidate pool sizes (driverPoolByScore/Ppm, conPoolByScore/Ppm), wildcard pool, strategy weights (budgetGainWeight, balancedPointsWeight, balancedPpmWeight), PPM bracket thresholds, and affinity heuristic params (sim floor, full-confidence weight, clamp range). Existing constants in `runMultiWeekPlanner`, `findOptimalWildcardTeam`, `computeAffinityWithConfidence`, `generateTransferCandidates` now read from this block. No behaviour change at default values.

## P11 — PPM-aware 2-swap candidate pool

**Problem:** `generateTransferCandidates` 2-swap pool was top-8 drivers / top-4 cons by raw projected score. Missed cheap high-PPM picks that enable budget-relief swaps (down-trade an expensive driver + up-trade a cheap high-value one).

**Fix:** Build two pools — top-N by raw score + top-N by PPM (proj / current_price) — then dedupe via Set. Raw-score pool covers high-ceiling absolute picks; PPM pool covers bang-for-the-buck.

**Implementation (app.js v63):** `topAvailDrivers` and `topAvailCons` constructed as the union of `driverPoolByScore` and `driverPoolByPpm` (likewise for cons). Defaults: 8+8 drivers, 4+3 cons; typical union ~10-12 drivers, ~5-6 cons (sets overlap substantially at the top). Cost impact: ~50% more 2-swap combos generated but still bounded — multi-week planner stays sub-second.

## P12 — Constructor+constructor 2-swap candidate

**Problem:** `generateTransferCandidates` only had driver+driver and driver+constructor 2-swaps. Asymmetric coverage — the planner could never swap both constructors at once, even when doing so was strictly better.

**Fix:** Add a constructor+constructor 2-swap branch. Only one unique pair (the 2 constructor slots), so it's a single `[i=0, j=1]` loop over `topAvailCons` × `topAvailCons`.

**Implementation (app.js v63):** ~15-line addition at the end of `generateTransferCandidates`. Uses the same `topAvailCons` pool from P11 (so it picks up the PPM-aware ranking). Skips when either constructor slot is empty.

## P13 — Target intensity dropdown

**Problem:** `TARGET_WEIGHT = 30` was hardcoded. Users had no way to say "get me close to this team but optimize freely" (loose) vs "force convergence even at point cost" (strict).

**Fix:** Add a Loose/Balanced/Strict dropdown next to the target team checkbox, wired to `MW_TUNABLES.targetIntensity` (10 / 30 / 80).

**Implementation (app.js v63 + index.html):** New `<select id="mwTargetIntensity">` in the target team panel (HTML lines ~352-358). `runMultiWeekPlanner` reads the value and resolves `targetWeight` from the lookup before the beam loop. `TARGET_WEIGHT` inside the loop now references the resolved value instead of a literal. Backward compatible: missing dropdown defaults to balanced (30).

## P14 — Strategy score is internal-only ranking signal

**Problem:** The strategy dropdown (Max Points / Balanced / Budget Builder) re-ranks plans via a weighted internal score, but the displayed plan total is the raw net projected points. Users wondered why "Budget Builder" showed fewer points than "Max Points" even though it was "their pick".

**Fix:** Add a hint above the plans grid clarifying that totals are raw projected net points and the Strategy dropdown only affects ordering.

**Implementation (app.js v63):** One-line hint added under the "Recommended Plans" heading in `displayMultiWeekResults`. No score-calculation change — `plan.totalPoints` was already the raw value; only the explanation was missing.
