---
title: We Simulated Three F1 Fantasy Strategies Across the 2026 Season
seo_title: F1 Fantasy Strategy Experiment: Three Season Simulations
date: 2026-07-28
tags: analysis, strategy, budget, chips, optimizer, simulation
sources: /data/official_fantasy_points.json, /data/season_summary.json, /methodology/, /tools/lineup-optimizer/, /tools/transfer-planner/
---

Would an F1 Fantasy manager score more by chasing the maximum projected points every weekend, or by accepting a small short-term compromise to build a more valuable team?

We built a sequential season simulator to find out. It replayed every completed 2026 race with two virtual managers, then repeated the season under three different chip policies.

The first manager always pursued **Max Points**. The second used a **Balanced** strategy: points remained the priority, but expected price growth also had value because a larger budget can unlock stronger teams later.

Across all three experiments, the Balanced manager finished with more points and substantially more team value. But the chip results were less straightforward. A chip choice that helped one strategy could hurt the other because the managers entered the same race with different teams, budgets and transfer needs.

This article explains all three experiments, their constraints, the results and what we learned.

## The common rules used in all three experiments

Both managers started Round 1 with **$100.0M** and selected the standard five drivers and two constructors.

The simulation then moved through the 11 completed races: internal Rounds 1, 2, 3 and 6-13. Bahrain and Saudi Arabia retained their original internal numbers but were cancelled, so they were not treated as completed fantasy rounds.

Each round followed the same sequence:

1. Load that weekend's archived post-practice forecast.
2. Evaluate every legal five-driver and two-constructor combination.
3. Select the best team under the manager's strategy and available budget.
4. Apply transfers and any transfer penalties.
5. Score the selected assets using the official fantasy result.
6. Revalue the persistent team using the official closing prices.
7. Carry the team, bank balance, team value and transfers into the next race.

The simulator did not reset either manager to $100M between races.

## Team-selection and transfer constraints

The normal 2x boost went to the highest projected driver in the selected team.

After Round 1, the managers received two free transfers. Unused transfers could roll forward, with the available total capped at five. The normal transfer strategy was allowed at most one paid transfer in a round, charged at **-10 points**.

The Max Points manager maximised archived projected fantasy points after transfer penalties.

The Balanced manager maximised projected points after penalties, then added eight units of decision value for every projected **$1M of price appreciation**. That did not mean budget replaced points. It meant the manager could accept a small forecast sacrifice when a likely price rise offered useful future buying power.

Price-growth forecasts mirrored the website's rolling-three points-per-million brackets. They used only earlier official scores plus the current forecast. Actual closing prices, rather than predicted prices, determined the next round's real budget.

Temporary scoring chips did not change the normal persistent-team decision. A 3x Boost, No Negative or Autopilot sat on top of the lineup the manager would otherwise choose. Limitless and Wild Card were different because their rules directly affect team selection.

## How official points and chip scoring were handled

All realised driver and constructor scores came from the official fantasy totals stored after each race.

The chip mechanics were:

- **3x Boost:** the highest projected selected driver scored 3x and the second-highest projected driver scored 2x.
- **Limitless:** the manager could choose an unlimited-budget team for one round, after which the persistent team reverted.
- **Wild Card:** transfers were unlimited and free, and the rebuilt team remained for future rounds.
- **No Negative:** negative driver and constructor asset scores were floored at zero for that round.
- **Autopilot:** the highest actual-scoring driver in the selected team received the 2x boost.

Constructor and driver ownership were both scored in the normal way. Owning a driver and that driver's constructor is legitimate in F1 Fantasy and therefore was not treated as duplicate scoring.

## Experiment 1: generic forecast-opportunity chip timing

The first experiment used a relatively simple forecast-based chip policy.

Limitless and 3x Boost were assigned to the strongest projected opportunities among genuine sprint-round archives. No Negative targeted the largest forecast P5 downside exposure, while Autopilot targeted the greatest captain uncertainty.

Wild Card was saved. We had no archived multi-round horizon forecast that could justify making a permanent rebuild based only on a one-round uplift.

### Experiment 1 chip schedule

For Max Points:

- 3x Boost: R6 Miami.
- Limitless: R7 Canada.
- No Negative: R12 Belgium.
- Autopilot: R13 Hungary.
- Wild Card: saved.

For Balanced:

- 3x Boost: R6 Miami.
- Limitless: R7 Canada.
- Autopilot: R8 Monaco.
- No Negative: R12 Belgium.
- Wild Card: saved.

### Experiment 1 results

Max Points finished with **2,286 points** and a **$105.7M** team value.

Balanced finished with **2,541 points** and a **$116.8M** team value.

Balanced won by **255 points** and ended with **$11.1M more team value**.

There was also an important warning. The Max Points no-chip baseline scored 2,380, meaning this chip schedule finished 94 points behind simply playing no chips. Balanced's no-chip baseline scored 2,495, so its chip schedule added 46 points.

The same generic policy did not suit both managers equally.

## Experiment 2: domain-informed chip timing

The second experiment replaced the generic chip timing with more familiar F1 Fantasy strategy rules.

### Limitless constraint

Limitless targeted the completed circuit with the highest overtaking difficulty. The reasoning was that a low-overtaking track makes qualifying and grid position more valuable, while the unlimited budget allows the manager to load up on the strongest premium qualifiers.

Monaco, rated **10/10 for overtaking difficulty**, was therefore selected.

### 3x Boost constraint

The 3x Boost targeted the strongest two-driver pairing the manager could afford in a normal legal lineup.

Miami was selected because both teams could afford Antonelli at 50.7 projected points and Ocon at 28.5. Their combined forecast was the strongest eligible pair.

### Wild Card constraint

Wild Card required at least four forecast-supported lineup changes and a meaningful utility improvement of at least 10.

We did not have a complete, timestamped upgrade log for every team and race. Instead, the simulator used forecasted optimal-lineup churn as the competitive-order or upgrade proxy. If the new model order suddenly required several changes, that was treated as evidence that a rebuild might be justified.

The Wild Card was evaluated against the team the manager would actually own after earlier chip decisions, not against a separate no-chip baseline.

### No Negative constraint

No Negative used a combined pre-race attrition score:

- Mean projected field DNF probability.
- The archived weather DNF multiplier.
- Forecast rain-risk category.
- Turn 1 incident risk.
- Safety-car probability.

Austria was selected. Its archive carried an 18.5% mean projected DNF probability, a 1.10x weather DNF multiplier and LOW rain risk, alongside a high incident-risk rating.

### Autopilot constraint

Autopilot went to the strongest remaining captain-uncertainty round after the other chips had been allocated.

### Experiment 2 chip schedule

For Max Points:

- 3x Boost: R6 Miami.
- Limitless: R8 Monaco.
- No Negative: R10 Austria.
- Autopilot: R11 Britain.
- Wild Card: R12 Belgium, making four changes.

For Balanced:

- 3x Boost: R6 Miami.
- Wild Card: R7 Canada, making four changes.
- Limitless: R8 Monaco.
- No Negative: R10 Austria.
- Autopilot: R12 Belgium.

### Experiment 2 results

Max Points scored **2,323 points** and finished with **$107.8M**.

Balanced scored **2,494 points** and finished with **$117.7M**.

Balanced won by **171 points** and built **$9.9M more team value**.

Compared with Experiment 1, the domain-informed policy improved Max Points by 37 points and $2.1M. Balanced scored 47 fewer points than in Experiment 1 but gained another $0.9M in team value.

Compared with playing no chips, Experiment 2 Max Points was 57 points behind, while Balanced was only one point behind and $0.7M lower in team value.

The domain rules made the strategies more explainable, but they did not guarantee that every chip produced a positive realised return.

## Experiment 3: save the 3x Boost

The third experiment repeated Experiment 2 with one change: **the 3x Boost was not played**.

It was explicitly saved for a future race, and no replacement chip was allowed to take its Miami slot. This matters because allowing another chip to move into R6 would have changed more than one variable and made the comparison less useful.

Every persistent team, transfer and budget decision remained the same as Experiment 2 because 3x Boost is a temporary scoring overlay. Only the points changed.

### Experiment 3 chip schedule

For Max Points:

- Limitless: R8 Monaco.
- No Negative: R10 Austria.
- Autopilot: R11 Britain.
- Wild Card: R12 Belgium.
- 3x Boost: saved.

For Balanced:

- Wild Card: R7 Canada.
- Limitless: R8 Monaco.
- No Negative: R10 Austria.
- Autopilot: R12 Belgium.
- 3x Boost: saved.

### Experiment 3 results

Max Points scored **2,267 points** and retained its **$107.8M** final team value.

Balanced scored **2,438 points** and retained its **$117.7M** final team value.

Both managers scored exactly 56 fewer points than in Experiment 2. In other words, playing the 3x Boost at Miami would have added 56 points to either team's completed-season total.

Saving it may still be rational if a later weekend offers a higher expected return. The experiment simply establishes the opportunity cost: the future use must beat the 56 points already available in the Miami result to improve on the completed-season counterfactual.

## Why Monaco Limitless produced a complicated answer

Monaco looked like the textbook Limitless round. Overtaking difficulty was 10/10, so an unrestricted premium team should, in theory, gain more from strong qualifying than a normal budget-constrained lineup.

But chip value depends on the team being replaced.

When we removed Monaco Limitless from the Experiment 2 schedule while keeping the other chip timings fixed, the downstream effect differed sharply:

- Max Points was 164 season points and $4.0M worse with Limitless than without it.
- Balanced was 209 season points and $3.0M better with Limitless than without it.

Those figures include later transfers and budget effects, not only Monaco's immediate score.

The lesson is not that Monaco is a bad Limitless track. It is that circuit suitability is only the first condition. The unlimited team must also project materially better than the manager's existing lineup, and the cost of reverting afterward must be considered.

## Constraints and limitations

These simulations are designed to be transparent, but they are not a perfect live-manager backtest.

### Reconstructed early archives

Rounds 1-3 use reconstructed post-practice forecasts created later. Rounds 6-13 use genuine archives captured during the season.

The official points and price changes are real throughout, but reconstructed forecasts can benefit from later model development or training data. Full-season totals must therefore be described as indicative rather than prospective performance.

### Retrospective comparison of forecast opportunities

Chip rounds were selected without using the eventual race result, but the policy compared the archived pre-race opportunities across the completed season.

That means the selection process knew which later forecast opportunities eventually appeared. A live manager at R6 would know the calendar and circuit types, but not the exact weather, DNF forecast or model confidence that would exist at R10 or R12.

This is forecast-only hindsight rather than result hindsight. It is cleaner than choosing chips from actual scores, but it is not the same as making every decision online with only information available that day.

### No complete upgrade timeline

The Wild Card policy used optimal-lineup churn as a proxy for upgrades or a changing competitive order. This is useful, but it cannot distinguish a genuine car upgrade from a track-specific matchup, changing reliability outlook, price movement or model noise.

A better future version would use a timestamped upgrade log alongside multi-round forecasts.

### The experiment tests the full decision system

The results combine model quality, optimizer decisions, transfer constraints, price forecasts, chip timing and actual race variance.

They do not isolate the pure accuracy of the qualifying or race-position models. A poor result can come from a prediction miss, a correct forecast with unlucky race events, an overly aggressive transfer, or a chip that was theoretically suitable but unnecessary for the team already owned.

### No claim of globally optimal chip use

The simulator evaluates defined policies. It does not search every possible season-long chip schedule with hindsight.

Doing that would find the mathematically highest realised total, but it would answer a less useful question: what would have worked if the results were already known?

## What the three experiments taught us

First, the Balanced strategy was consistently stronger. It won all three experiments and ended with between $9.9M and $11.1M more team value than Max Points.

Second, budget growth worked best as a secondary objective. The Balanced manager remained points-first; it did not select cheap assets merely because they might rise.

Third, a traditional chip rule is not enough on its own. “Limitless at a low-overtaking circuit” and “No Negative in risky weather” are useful filters, but the recommendation must also be compared with the manager's existing team.

Fourth, Wild Card should be driven by multi-round change. Requiring four or more forecast-supported transfers was a better starting point than responding to a single attractive asset.

Finally, saving a chip has a measurable opportunity cost. Holding 3x Boost preserved the future option, but it left 56 completed-season points unused. That gives us a benchmark for evaluating later 3x opportunities.

## What we will improve next

The next version should evaluate chips using a multi-round expected-value calculation.

Limitless should require both a suitable circuit and a clear projected advantage over the current team after accounting for the reversion. Wild Card should use upgrade evidence and several future rounds, not only current-week lineup churn. No Negative should compare its protection value with the probability and size of negative scores in the exact selected team. The 3x model should measure the projected incremental multiplier value rather than relying only on two strong names.

Those changes can feed directly into the [Lineup Optimizer](/tools/lineup-optimizer/) and [Transfer Planner](/tools/transfer-planner/).

## Bottom line

Across three sequential season simulations, the points-first Balanced strategy produced the strongest combination of scoring and budget growth.

Experiment 1 delivered the highest Balanced total at 2,541 points. Experiment 2 used the most realistic chip philosophy and finished on 2,494. Experiment 3 saved the 3x Boost and finished on 2,438, leaving a known 56-point opportunity unused.

The most valuable lesson was not a single chip round. It was that fantasy strategy is path-dependent. The right move depends on the circuit, the forecast, the price market, the transfers available and, above all, the team already owned.
