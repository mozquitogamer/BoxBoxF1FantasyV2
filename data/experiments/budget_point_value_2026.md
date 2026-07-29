# 2026 marginal budget-to-points analysis

## Headline metric

Primary fitted curve: **8.57 × (1 − exp(−races remaining / 1.80)) future projected points per $1M already secured before the deadline**.

The curve is anchored to the same +$1.0M perturbation at every historical deadline. Smaller and larger perturbations are retained for the lumpy frontier but do not set the smooth exchange rate.

Practical shorthand for the remaining 2026 horizon: **about 5.3 decision-grade points per $1M already secured, or about 4.6 points per forecast $1M rise with 11 races left**.

A price rise earned in the current race is available one race later. For a predicted rise, use the curve at **races left minus one**, then apply the price and points realisation discounts.

For decisions, discount that theoretical value by the observed marginal-points realisation multiplier of **0.625×**. This is a small-sample calibration, not a permanent game constant.

The Balanced-policy curve is retained in the JSON as a diagnostic only. It is excluded from the headline because that policy already assigns utility to price growth, which would make the valuation circular.

## Practical values

| Races left | Future races using a new rise | Secured $0.3M now | Forecast $0.3M decision value | Forecast $0.3M middle 50% | Secured $1M decision value |
|---:|---:|---:|---:|---:|---:|
| 1 | 0 | 1.09 pts | 0.00 pts | 0.00 to 0.00 pts | 2.28 pts |
| 3 | 2 | 2.08 pts | 0.93 pts | 0.81 to 1.28 pts | 4.34 pts |
| 5 | 4 | 2.41 pts | 1.24 pts | 1.18 to 1.30 pts | 5.02 pts |
| 8 | 7 | 2.54 pts | 1.36 pts | 1.31 to 1.39 pts | 5.29 pts |
| 11 | 10 | 2.56 pts | 1.39 pts | 1.31 to 1.46 pts | 5.34 pts |

## Affordability thresholds

- Across 8 genuine deadline states, an extra $0.3M changed the continuation lineup in 0.0% of states; $0.5M did so in 0.0%.
- An extra $1.0M unlocked a higher-projected continuation in 87.5% of states.
- The median minimum tested unlock among states with an unlock was $0.7M using a $0.1M grid.
- This is why the smooth curve should be treated as option value. The exact optimizer frontier overrides it whenever available.

## How the three season experiments fit in

- season_strategy_simulation_2026_v1: Balanced scored 255 more points and finished $11.1M higher (23.0 points per extra $1M).
- season_strategy_simulation_2026_v2: Balanced scored 171 more points and finished $9.9M higher (17.3 points per extra $1M).
- season_strategy_simulation_2026_v3_no_3x: Balanced scored 171 more points and finished $9.9M higher (17.3 points per extra $1M).
- Those ratios are directional rather than causal: the managers owned different assets and had different chip outcomes. The marginal curve instead holds the deadline state and policy fixed.

## How the risk-tolerance follow-up fits in

- The highest final budget was $124.3M. Two Budget Builder paths reached it.
- Those equal-budget paths finished 150 points apart.
- Budget Builder with medium tolerance scored 150 more points than minimal risk while finishing with the same budget.
- This supports treating budget as an option constraint, not as points already banked. Team selection quality still determines whether the spending power is converted into score.

## Price forecast calibration

- Predicted-rise observations: 146.
- Rise hit rate: 85.6%.
- Non-loss rate: 86.3%.
- Signed realised/predicted change ratio: 0.771.
- A forecast +$0.3M rise averaged an actual +$0.26M with a 96.0% hit rate.

## What happens after an actual rise

- Next move: 74.3% up, 12.6% flat, 13.2% down.
- 1 rounds later: 96.4% remain at or above the pre-rise price; 89.2% of the initial rise is retained on average after clipping further gains; median total retention ratio 2.00×.
- 2 rounds later: 89.1% remain at or above the pre-rise price; 86.6% of the initial rise is retained on average after clipping further gains; median total retention ratio 3.00×.
- 3 rounds later: 85.0% remain at or above the pre-rise price; 82.2% of the initial rise is retained on average after clipping further gains; median total retention ratio 3.00×.

## Why appreciation plateaus

- Any positive price bracket requires a rolling average of at least 0.9 × current price; the maximum positive bracket requires 1.2 × price.
- More precisely, the next score needed for any rise is max(0, 2.7 × current price − the previous two scores). The maximum-rise hurdle uses 3.6 × price instead.
- Every additional $0.1M of price therefore raises the next-race hurdle by 0.27 points for any rise and 0.36 points for the maximum rise.
- At $10M that is 9.0 / 12.0 average points; at $15M it is 13.5 / 18.0; at $20M it is 18.0 / 24.0.
- Once price exceeds $18.5M, positive bracket sizes also shrink from +$0.2M / +$0.6M to +$0.1M / +$0.3M.
- After a low-tier rise, 71.6% rose again next round. After a high-tier rise, 77.8% rose again.
- After the first rise in a streak, 56.5% rose again. After three or more consecutive rises, 86.1% rose again.
- The streak result reflects momentum and selection: only assets that kept outperforming survived into the three-rise group. It does not imply that appreciation can continue indefinitely.
- When the points required for another rise were at or below the asset's recent average, the next-rise rate was 89.8%. When the required score was above the recent average, it fell to 10.0%.
- These are the plateau controls: rising price increases the score required to keep appreciating, and the smaller high-tier brackets reduce the cash reward even when the asset keeps scoring.

## Decision rule

**Sacrifice points now only when:** points sacrificed < predicted budget rise × curve(races left − 1) × price-realisation discount × marginal-points realisation discount.

On the current sample, an isolated extra $0.3M unlocked no different continuation lineup in 100% of genuine deadline states. Treat the smoothed value as option value, not a guaranteed points gain.

**Example:** a certain 10 points is worth more than a forecast $0.3M rise at every observed horizon unless that $0.3M crosses a specific affordability threshold identified by the optimizer.
With 11 races left, the current decision-grade estimate values a forecast +$0.3M at about 1.39 points. Its bootstrap middle-50% range is 1.31 to 1.46 points. A forecast rise would need to be about $2.16M to justify sacrificing 10 points under the smooth model.

For an already secured rise, omit the forecast-reliability discount. If the extra budget does not cross a feasible-lineup price frontier, its immediate value can be zero; retain some option value for later transfers.

## Constraints

- The fitted headline curve uses genuine R6-R13 archives only.
- R1-R3 records remain in the JSON for sensitivity analysis but are excluded from the primary curve.
- Choices use archived forecasts, while future price paths use realised closing prices.
- The curve is fitted to one partial 2026 season and should be refreshed after every race.
- The fitted uncertainty band resamples only eight genuine deadline states and is descriptive.
- Values beyond eight usable races are extrapolated from the fitted saturation curve.
- Greedy round-by-round optimization is not a globally optimal season search.
- Budget value is lumpy because teams are discrete combinations, not divisible portfolios.
