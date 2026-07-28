---
title: We Simulated Two F1 Fantasy Strategies Across the 2026 Season
seo_title: F1 Fantasy Strategy Experiment: Points vs Budget
date: 2026-07-28
tags: analysis, strategy, budget, chips, optimizer, simulation
sources: /data/official_fantasy_points.json, /data/season_summary.json, /methodology/, /tools/lineup-optimizer/, /tools/transfer-planner/
---

What happens if one F1 Fantasy manager always chases the highest projected score, while another remains points-first but also builds team value?

We ran both strategies sequentially through every completed 2026 race, starting with a **$100.0M budget at the Australian Grand Prix**. Each manager selected five drivers and two constructors, carried the same team and bank balance into the next round, made transfers under the normal penalty rules, and earned the official fantasy points recorded after each race.

The final version of the experiment deliberately saved the 3x Boost for later in the season.

## The final result

- **Max Points:** 2,267 points and a final team value of **$107.8M**.
- **Balanced:** 2,438 points and a final team value of **$117.7M**.

The Balanced strategy finished **171 points ahead** and built **$9.9M more team value**.

That is the central finding. Treating budget growth as a secondary objective did not require abandoning points. The additional buying power compounded across the season and gave the Balanced manager stronger options later.

## How the two managers made decisions

The Max Points manager selected the legal lineup with the highest archived post-practice projection after transfer penalties.

The Balanced manager still prioritised projected points, but also gave value to forecast price appreciation. It was willing to accept a small immediate projection loss when the expected budget growth could improve future teams.

Every round used the forecast archive available for that phase of the weekend. Actual fantasy points were used only after the lineup had been selected, to score the result. Closing driver and constructor prices then determined the next round's budget.

## We also made the chip rules more realistic

The chip schedule followed familiar F1 Fantasy logic rather than simply choosing the round with the largest generic projected uplift.

- **Limitless:** Monaco, the most qualifying-dependent completed circuit and the hardest place to overtake.
- **No Negative:** Austria, which had the strongest combined forecast signal from DNF probability, weather risk and circuit incident risk.
- **Wild Card:** only when the manager's forecasted ideal lineup required at least four changes. That happened in Canada for Balanced and Belgium for Max Points.
- **Autopilot:** the strongest remaining captain-uncertainty round.
- **3x Boost:** saved for a future weekend.

The model had identified Miami as the best completed opportunity for 3x because both teams could afford two highly projected drivers. Playing it there would have added **56 points** to either season total, but this version of the experiment held the chip.

## The most interesting chip lesson

Monaco looked like the textbook Limitless round: overtaking difficulty was rated 10/10, so an unrestricted team packed with leading qualifiers should have a larger advantage over ordinary budget-constrained teams.

But the result depended heavily on the team entering the weekend. The same Limitless decision helped the Balanced season path while hurting the Max Points path once later transfers and budget changes were included.

That suggests a better rule than simply “play Limitless at Monaco.” A strong chip decision needs two conditions:

1. The circuit and weekend format should suit the chip.
2. The chip team must project materially better than the team the manager already owns, including the effect on the following rounds.

The same principle applies to Wild Card. A change in the competitive order matters only if it creates enough genuine lineup churn and multi-round value to justify rebuilding.

## An important limitation

This is an indicative strategy experiment, not a clean live-performance claim.

Rounds 1-3 use reconstructed post-practice prediction archives. Rounds 6-13 use genuine archived forecasts captured during the season. The official fantasy scores and prices are real throughout, but the early reconstructed forecasts mean the complete total should not be presented as a fully prospective backtest.

The experiment is still useful because the managers follow the same rules sequentially: no unlimited hindsight transfers, no retrospective selection using race results, and no resetting the budget to $100M every week.

## What we learned

The strongest result was not that budget should replace points. It was that a points-first strategy can improve when it gives some weight to team-value growth.

The Balanced manager ended with more points and substantially more buying power. Chip timing also proved inseparable from team state: the right traditional circuit is only the first filter, not the entire decision.

We will use these lessons to improve the [Lineup Optimizer](/tools/lineup-optimizer/), [Transfer Planner](/tools/transfer-planner/) and future chip recommendations. The next step is to require a multi-round advantage before recommending a permanent rebuild or a temporary Limitless team.
