---
title: What If Our F1 Fantasy Managers Had Different Risk Tolerances?
seo_title: F1 Fantasy Risk Tolerance: A Follow-Up Experiment
date: 2026-07-29
tags: analysis, strategy, risk, budget, chips, optimizer, simulation
sources: https://docs.google.com/spreadsheets/d/17WRZq0Y0LKrtkay4DzjllAHYA0DCDEppG-9Q9tlVceQ/edit?usp=sharing, /data/official_fantasy_points.json, /data/season_summary.json, /methodology/, /tools/lineup-optimizer/, /tools/transfer-planner/
---

After I published my first season experiment comparing Max Points with a Balanced approach, one of the comments raised an interesting follow-up question: what would happen if the virtual managers also had different levels of risk tolerance?

The original experiment asked whether it was better to chase the highest immediate projection or sacrifice a little short-term score for expected budget growth. The Balanced manager won all three versions, which suggested that points and future buying power should not be treated as completely separate objectives.

But that experiment left another part of team selection fixed.

It did not ask whether the managers should avoid drivers and constructors with ugly lower-end outcomes, accept some downside when the reward was worthwhile, or ignore forecast risk and chase upside.

So I treated the suggestion as a secondary experiment and expanded the original idea.

This time I replayed the 2026 season so far with twelve virtual managers. The simulation crossed three team-building approaches (Max Points, Balanced and a more aggressive Budget Builder) with four levels of risk tolerance.

Every manager started with $100.0M, made transfers from one race to the next, used the same archived pre-deadline forecasts, scored against the official F1 Fantasy results and carried their real team value forward.

This is not a replacement for the first experiment. It is another angle on the same underlying question: once a manager has decided how much to value points and budget, how much forecast downside should they accept?

The headline result was surprisingly clear.

The best combination was **Budget Builder with medium risk tolerance**. It scored 2,537 points, led the genuine lock-time comparison with 1,720 points and finished with a $124.3M budget.

That was not the safest strategy and it was not the most aggressive. It sat in the middle.

You can inspect every team, weekend, transfer, reason, chip and budget movement in the [full experiment spreadsheet](https://docs.google.com/spreadsheets/d/17WRZq0Y0LKrtkay4DzjllAHYA0DCDEppG-9Q9tlVceQ/edit?usp=sharing).

## The suggestion behind this follow-up

The first experiment already gave us two established virtual managers.

Max Points pursued the highest archived projection. Balanced remained points-first but gave some value to expected price appreciation, allowing it to make a small short-term sacrifice when that could create useful buying power later.

The commenter's suggestion added a second dimension: those managers might make very different choices depending on how strongly they reacted to the bad end of the Monte Carlo forecast.

A manager who hates risk might avoid a driver whose expected score is strong but whose P5 outcome is negative. Another manager might accept that downside because the ceiling is worth it. A third might ignore the lower tail entirely.

That led to two linked questions:

1. Does the conclusion from the first experiment still hold once risk tolerance changes?
2. Is there a useful middle ground between avoiding negative outcomes at all costs and accepting maximum risk?

To explore that properly, I retained Max Points and Balanced, added a more aggressive Budget Builder as an outer comparison, and tested all three under four risk profiles.

That produced a three-by-four grid: three manager philosophies, each replayed at four levels of downside tolerance.

The aim was not to rewrite the first experiment or find a magic setting that will win every season. It was to stress-test its lesson from a new direction.

## The three virtual manager approaches

The first two approaches came directly from the original experiment. Budget Builder was added to show what happened when the price-growth preference was pushed further.

### Max Points

The Max Points manager selected the legal team with the highest archived projected score after transfer penalties.

Price growth could still affect the manager's future spending power because actual price changes were carried forward, but expected appreciation had no value in the team-selection objective. If one lineup projected one point more than another, Max Points preferred it even if the alternative was expected to gain more budget.

### Balanced

The Balanced manager kept projected points as the main objective but added eight units of decision value for every forecast $1M of appreciation.

This was not a budget-first approach. It was allowed to accept a small projected-points sacrifice when the expected price rise could create useful buying power for later races.

### Budget Builder

The Budget Builder used the same mechanism more aggressively, adding twenty units of decision value for every forecast $1M of appreciation.

It still cared about points. It did not blindly buy the cheapest drivers. But when two teams were reasonably close on projected score, it was much more willing to prefer the lineup expected to appreciate.

## The four levels of risk tolerance

The risk measure came from the archived pre-deadline Monte Carlo forecast.

For each possible lineup, the simulator looked at the P5 result for all five drivers and both constructors. Any negative P5 value represented a genuinely bad lower-tail outcome. The lineup's downside exposure was the sum of those negative values.

In plain English: if the forecast said several selected assets had a meaningful chance of producing negative fantasy scores, the team carried more downside risk.

The four profiles treated that exposure differently.

### Total avoidance

Total avoidance minimised negative-P5 exposure before considering the manager's normal philosophy.

This was intentionally extreme. Even a very small improvement in forecast downside could outrank a large difference in projected points or expected price growth.

It answers the question: what happens if we avoid forecast negative scores at almost any cost?

### Minimal risk accepted

This profile subtracted 2.00 utility points for every point of negative-P5 exposure.

It still allowed risk, but only when the expected points or price-growth benefit was strong enough to compensate for it.

### Medium tolerance

Medium tolerance applied a smaller penalty of 0.75 utility points for every point of negative-P5 exposure.

Risk mattered, but it was one input rather than the first priority. A lineup could carry a worse lower tail if the projected reward justified it.

### Maximum tolerance

Maximum tolerance applied no downside penalty.

The manager selected solely according to the Max Points, Balanced or Budget Builder philosophy. Forecast P5 risk was displayed and measured, but it did not affect the choice.

## Common rules and season simulation

To keep the comparison meaningful, the follow-up reused the core structure of the first experiment.

All twelve managers followed the same basic game process.

Each path:

1. Started Round 1 with $100.0M.
2. Selected five drivers and two constructors.
3. Loaded the archived forecast available before that race's team deadline.
4. Evaluated legal teams under the manager's available budget.
5. Applied transfers and any transfer penalties.
6. Scored the chosen assets using official F1 Fantasy points.
7. Revalued the persistent team at the official closing prices.
8. Carried the lineup, cash, transfers and team value into the next completed race.

The replay covered the eleven completed rounds: Australia, China, Japan, Miami, Canada, Monaco, Spain, Austria, Britain, Belgium and Hungary. The cancelled Bahrain and Saudi Arabian rounds were naturally skipped.

The normal 2x captain remained active throughout. The 3x Boost was deliberately saved, matching the final version of the previous experiment.

## Transfer constraints

After Round 1, managers received the normal free-transfer allowance. Unused transfers could roll forward, and the simulator could take a paid transfer when the improvement justified the ten-point hit.

Wild Card could rebuild the persistent team without transfer penalties. Limitless created a temporary unlimited-budget team for one round, after which the owned team returned.

This distinction matters because the experiment was path-dependent. A transfer made in Canada could change the available budget, Wild Card need and optimal team several races later.

Across the twelve paths, the simulator analysed **214 persistent asset changes**. The spreadsheet includes the outgoing and incoming asset, prices, projected-point change, forecast price movement, P5 exposure, transfer penalty and a written explanation for every move.

When several assets changed together, the report paired outgoing and incoming assets by price proximity so the ledger would be readable. The optimizer itself selected the full seven-asset lineup jointly, so the lineup-level decision is more important than treating each displayed pair as an isolated one-for-one swap.

## Chip policy

The chips were not the main variable in this follow-up. I kept the domain-informed policy from the previous experiment so the new comparison could concentrate on risk tolerance.

The experiment used the domain-informed chip rules developed in the previous simulation, and chip timing was based only on genuine pre-deadline archives.

### Limitless

Limitless was played at Monaco, Round 8, for all twelve managers.

The theory was the same as before: a low-overtaking circuit increases the value of qualifying and track position, while the unlimited budget lets a manager afford the strongest premium qualifiers.

### Wild Card

Wild Card required a forecast-supported permanent rebuild, generally involving at least four lineup changes and a meaningful utility improvement.

Depending on the team path, it was played in Miami, Canada or Belgium. One Max Points path saved it because the rebuild threshold was not reached.

### No Negative

No Negative was played in Austria for every path. The selection used pre-race DNF probability, weather adjustment, rain category, Turn 1 incident risk and safety-car probability.

### Autopilot

Autopilot went to the strongest remaining captain-uncertainty opportunity. Depending on the path, that was Britain or Belgium.

### 3x Boost

The 3x Boost was not played. It remained available for the rest of the season.

## Complete results: Max Points

The four Max Points paths produced:

- **Total avoidance:** 2,245 total points, 1,587 genuine-archive points and a $123.3M final budget.
- **Minimal risk accepted:** 2,431 total points, 1,659 genuine-archive points and a $120.6M final budget.
- **Medium tolerance:** 2,493 total points, 1,698 genuine-archive points and a $116.6M final budget.
- **Maximum tolerance:** 2,267 total points, 1,562 genuine-archive points and a $107.8M final budget.

Medium tolerance was comfortably the best Max Points version.

Compared with maximum tolerance, it scored 226 more total points and 136 more genuine-archive points while finishing with $8.8M more budget.

That is an important result. Adding a sensible risk penalty did not merely reduce volatility. It improved both the realised score and the final team value.

Total avoidance built a much larger budget than maximum tolerance, but its refusal to accept downside left 248 points on the table compared with the medium setting.

## Complete results: Balanced

The four Balanced paths produced:

- **Total avoidance:** 2,245 total points, 1,587 genuine-archive points and a $123.3M final budget.
- **Minimal risk accepted:** 2,443 total points, 1,671 genuine-archive points and a $121.0M final budget.
- **Medium tolerance:** 2,502 total points, 1,707 genuine-archive points and a $118.9M final budget.
- **Maximum tolerance:** 2,438 total points, 1,719 genuine-archive points and a $117.7M final budget.

Medium tolerance won the full completed-season comparison, while maximum tolerance scored twelve more points over the genuine lock-time rounds.

That is a much closer trade-off than in Max Points. Medium tolerance finished with $1.2M more budget and reduced realised negative points from -120 to -113, but the difference in genuine-archive scoring was small.

The Balanced philosophy was already applying some discipline by valuing future price growth. As a result, maximum tolerance was less damaging here than it was for pure Max Points.

## Complete results: Budget Builder

The four Budget Builder paths produced:

- **Total avoidance:** 2,245 total points, 1,587 genuine-archive points and a $123.3M final budget.
- **Minimal risk accepted:** 2,387 total points, 1,647 genuine-archive points and a $124.3M final budget.
- **Medium tolerance:** 2,537 total points, 1,720 genuine-archive points and a $124.3M final budget.
- **Maximum tolerance:** 2,449 total points, 1,667 genuine-archive points and a $120.3M final budget.

This was the strongest group in the experiment, and medium tolerance was the overall winner.

The most striking comparison is against the minimal-risk Budget Builder. Both finished on the same displayed $124.3M budget, but medium tolerance scored 150 more total points and 73 more genuine-archive points.

In other words, once the manager was already placing strong value on price growth, accepting a moderate amount of forecast downside created far more points without sacrificing the final budget.

Maximum tolerance also performed well, but medium tolerance beat it by 88 total points, 53 genuine-archive points and $4.0M in final team value.

## Why all three total-avoidance managers became the same team

Every total-avoidance path finished with exactly 2,245 points, 1,587 genuine-archive points and $123.3M.

That is not an error.

The total-avoidance rule was lexicographic: minimise downside first, then use the manager philosophy as a tie-breaker. Because risk dominated the decision, the Max Points, Balanced and Budget Builder objectives rarely had room to change the selected lineup.

This shows the cost of an absolute rule. If avoiding a slightly worse P5 outcome always takes priority, the distinction between a points manager and a budget manager almost disappears.

The result was excellent capital preservation and low realised negative scoring, but not the best season score.

## Did the forecast risk measure actually identify danger?

Yes, at least descriptively in this sample.

Across the twelve paths, the correlation between mean forecast negative-P5 exposure and the magnitude of realised negative points was **0.968**.

When the analysis was restricted to genuine lock-time archives, the correlation was still **0.960**.

That is a strong relationship. The lower-tail forecast was doing what it was designed to do: lineups flagged with greater downside exposure generally suffered more negative points in the official results.

But there is a second result that matters just as much.

The correlation between genuine-archive forecast downside and genuine-archive points was only **0.100**.

Avoiding negative scores and maximising total points are not the same objective. The safest lineup can protect the floor while missing a great deal of upside.

That is exactly why medium tolerance worked so well. It used the risk signal without allowing it to control every decision.

## What happened with the chips?

Chip value was measured conditionally: remove one chip, keep the other scheduled chips fixed, and replay the remaining path.

These effects are not additive. Removing a chip can change transfers, budget and the state of a later Wild Card, so the contribution of one chip depends on the rest of the season path.

### Limitless

Limitless produced a positive conditional return in eleven of the twelve paths.

Its mean contribution was +81 points, with a median of +71. But the range was enormous: from -164 to +218.

That makes Limitless the clearest example of why a correct circuit rule is not enough. Monaco may be the theoretically attractive track, but the chip still has to beat the exact budget-limited team the manager already owns.

### Wild Card

Wild Card was the most consistently successful chip.

It was played in eleven paths and produced a positive return in all eleven. Its mean contribution was +43.5 points, its median was +40 and the range ran from +15 to +156.

Its mean budget effect was -$0.2M, which is a useful reminder that Wild Card should not be judged only by immediate price growth. A permanent rebuild can improve the scoring path even if the closing budget is slightly lower.

### No Negative

No Negative produced a positive return in only one of the twelve paths.

Its mean contribution was +1.4 points and its median was zero. The best result was +17.

The Austria risk signal may have been reasonable before the deadline, but the negative outcomes largely did not materialise inside the selected teams. This is the nature of insurance: a sensible protection decision can have little realised payoff when the bad event does not happen.

### Autopilot

Autopilot produced a positive return in half the paths.

Its mean contribution was +7.5 points, with a median of +2 and a maximum of +30.

It was useful, but its value depended heavily on whether the normal projected captain was beaten by another driver already owned.

## Chips helped some paths and hurt others

The complete chip schedule did not automatically improve every strategy.

Relative to the matching no-chip simulation:

- Max Points with medium tolerance gained 135 points.
- Balanced with medium tolerance gained 69 points.
- Budget Builder with medium tolerance gained 73 points.
- Max Points with maximum tolerance lost 113 points.
- Balanced with maximum tolerance lost 57 points.
- Budget Builder with minimal risk accepted lost 33 points.

This does not mean the chips themselves awarded negative points. It means their temporary teams or permanent downstream changes produced a worse completed-season path than the matching no-chip counterfactual.

The manager's starting team, budget and later transfer needs changed the value of the same nominal chip policy.

## The biggest lessons from the experiment

The result does not overturn the first experiment. It refines it.

### Medium risk tolerance produced the best overall balance

The overall winner used neither total safety nor maximum aggression.

Budget Builder with medium tolerance converted forecast price growth into future buying power, while still applying enough downside penalty to avoid the worst fragile lineups.

### Budget growth and points did not have to conflict

The winning path also tied for the highest final budget.

Budget Builder with minimal risk accepted reached the same $124.3M, but scored 150 fewer points. The lesson is not simply “chase budget”. It is to value budget without overpaying for safety or giving up too much forecast score.

That strengthens the original experiment's central finding. Future buying power can be valuable, but only when it remains connected to the points objective.

### Total avoidance was too blunt

The safest paths had the lowest mean downside exposure and only -65 realised negative points. They also finished 292 points behind the overall winner.

Absolute downside avoidance protected the floor, but it erased too much of the manager's intended strategy.

### Maximum tolerance was usually unnecessary

Maximum tolerance did not win any of the three manager groups.

The forecast risk measure had real information. Ignoring it completely generally produced more realised negative points, a lower final budget or both.

### Wild Card needs a real rebuild signal

The Wild Card policy was the most consistently valuable part of the chip schedule because it required meaningful lineup churn rather than merely targeting a famous circuit or a single high projection.

That supports using the [Transfer Planner](/tools/transfer-planner/) across several races before committing the chip.

### Risk is a team-level question

A driver's DNF probability alone is not enough. Constructors combine two cars, several risky assets can accumulate in one lineup, and a cheap high-risk choice may unlock a premium driver elsewhere.

The useful quantity is the downside of the full seven-asset team relative to its expected points and future budget, not a red or green label on one driver.

## Important limitations

This is a detailed backtest, but it is not a controlled experiment or a promise about future performance.

### Rounds 1–3 used reconstructed forecasts

Australia, China and Japan did not have the same genuine lock-time prediction archives as the later races, so their forecasts were reconstructed.

That is why the article reports both total points and genuine-archive points. The genuine figure covers Miami through Hungary and should carry more weight when judging the current prediction and optimizer system.

### The twelve paths are not independent samples

The managers replayed the same races, shared many assets and often selected similar lineups.

The correlation figures are descriptive. Twelve overlapping paths are not enough to claim a universal statistical law.

### Official results contain race variance

The optimizer made selections from pre-deadline forecasts, but the paths were scored using the actual outcomes.

A theoretically strong choice can lose through contact, weather, strategy errors or a mechanical retirement. Equally, a risky choice can survive and score extremely well.

### The experiment tests the whole decision system

The totals combine prediction accuracy, Monte Carlo risk estimates, price forecasts, transfer rules, optimizer choices, chip timing and actual race outcomes.

They do not isolate the accuracy of the qualifying or race-position model by itself.

### Chip selection still contains forecast-only hindsight

The chip policy did not use eventual race scores to select its rounds, but it compared the archived forecast opportunities that appeared across the completed part of the season.

A live manager knows the calendar, but does not know the exact future weather and forecast confidence that will exist several races later.

## What I would change next

The next useful version should make risk tolerance dynamic rather than fixed for an entire season.

Early in the year, when many races remain, expected budget growth may justify accepting more short-term uncertainty. Later in the season, points become harder to recover and the value of another $1M naturally falls.

The risk setting should also respond to:

- The number of races remaining.
- Whether a manager is defending a lead or chasing.
- The amount of budget already accumulated.
- The selected team's exact negative-P5 exposure.
- Weather and track-specific DNF risk.
- Whether Wild Card or No Negative remains available.
- The projected points gained per extra unit of downside.

That would turn the optimizer from a fixed personality into a race-by-race decision system.

## Bottom line

The first experiment suggested that a points-first Balanced approach could beat blindly chasing the highest immediate projection.

This reader-suggested follow-up adds an important qualification: the amount of downside a manager is willing to accept can matter just as much as the weight placed on budget growth.

The best result came from **Budget Builder with medium risk tolerance**: 2,537 total points, 1,720 genuine-archive points and a $124.3M final budget.

Total avoidance built a strong budget and successfully reduced negative outcomes, but it sacrificed too many points. Maximum tolerance ignored a useful risk signal and failed to win under any manager philosophy.

The best answer was in the middle: remain points-aware, value future budget, and accept downside only when the projected reward is large enough.

That is probably the most practical combined conclusion from both experiments. Do not chase the highest projection blindly, but do not turn safety or budget growth into absolute rules either. Risk should influence the team, but it should not be allowed to choose the team by itself.

The [full Google Sheet](https://docs.google.com/spreadsheets/d/17WRZq0Y0LKrtkay4DzjllAHYA0DCDEppG-9Q9tlVceQ/edit?usp=sharing) contains all twelve approaches, every weekend lineup, the complete transfer ledger, chip analysis and methodology.
