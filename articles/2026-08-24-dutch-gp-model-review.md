---
title: Dutch GP 2026 Model Review: Pace, Predictions & the Race That Changed the Order
seo_title: Dutch GP 2026 F1 Fantasy Model Review: Pace & Prediction Accuracy
date: 2026-08-24
round: 14
tags: dutch gp, post-race analysis, prediction accuracy, race pace, f1 fantasy
sources: /data/actual_round14.json, /data/post_race_round14.json, /data/deep_dive_round14.json, /data/official_points.json, /accuracy/, /methodology/
---

The Dutch Grand Prix was a useful test of the difference between predicting **pace** and predicting the exact final classification.

The model's post-practice qualifying read was excellent. The final race result was much less tidy, shaped by five retirements, strong recovery drives and a close three-team fight at the front. Now that every Dutch GP driver and constructor score has been reconciled against the official F1 Fantasy totals, we can separate what the forecast got right from what race-day volatility changed.

## The headline: qualifying was a very strong read

The post-practice forecast recorded a **1.00-place qualifying MAE** across the 22-driver field, with eight exact calls.

- Norris was predicted on pole and took pole.
- Russell was predicted P2 and qualified P2.
- Antonelli was predicted P3 and qualified P3.
- Verstappen, Lawson, Colapinto, Alonso and Stroll were also called in their exact qualifying positions.

The model also identified the complete Q3 field. Every driver it placed in the qualifying top ten reached Q3, even where the final order shifted by a place or two.

That is important for F1 Fantasy because qualifying is both a direct scoring component and the most useful pre-race signal of track position. At a circuit where overtaking and strategy can still reshape the race, getting the front-running group right is often more actionable than claiming a perfect Sunday order.

## How the Q3 runners compared with the Friday race forecast

The race forecast below was saved after Sprint Qualifying, before Grand Prix qualifying and the race. The ten drivers are ordered by their eventual Grand Prix qualifying position.

1. **Norris:** qualified P1; forecast P2 in the race; finished P1.
2. **Russell:** qualified P2; forecast P5; finished P3.
3. **Antonelli:** qualified P3; forecast P4; finished P2.
4. **Piastri:** qualified P4; forecast P6; finished P6 exactly.
5. **Hamilton:** qualified P5; forecast P1; finished P4.
6. **Leclerc:** qualified P6; forecast P3; finished P5.
7. **Verstappen:** qualified P7; forecast P7; classified P22 after retirement.
8. **Lawson:** qualified P8; forecast P9; finished P7.
9. **Bortoleto:** qualified P9; forecast P11; finished P13.
10. **Lindblad:** qualified P10; forecast P8; finished P12.

Seven of the ten Q3 runners finished within two places of the forecast. Their average error was **3.3 places** including Verstappen's retirement, and **2.0 places** across the other nine drivers.

The broader front-of-field call was also strong. The model's predicted top six was Hamilton, Norris, Leclerc, Antonelli, Russell and Piastri. The actual top six was Norris, Antonelli, Russell, Hamilton, Leclerc and Piastri: the same six drivers, but in a different order.

## The Sprint backed up the front-running read

Across the 21 classified Sprint drivers, the model produced a **1.33-place MAE**. Five finishing positions were exact and 16 of 21 drivers finished within two places of the forecast.

That result matters because it gave an early indication that the leading group was being read correctly before Sunday. The Grand Prix did not invalidate that pace read; it demonstrated how much final order still depends on execution, track position, reliability and timing.

## The deep dive: there was no dominant team on raw race pace

The cleaned-lap race analysis shows just how close the front was. Mercedes, Ferrari and McLaren were separated by only **0.03 seconds per lap** on team-average pace:

- **Mercedes:** 75.10s average lap.
- **Ferrari:** 75.12s average lap.
- **McLaren:** 75.13s average lap.

The sector picture was similarly divided. McLaren held the slight edge in Sector 1, Ferrari was strongest in Sector 2, and Mercedes was quickest in Sector 3. In other words, there was no single team with a decisive advantage around the whole lap.

That is the context behind the final result. Norris won, but the underlying pace did not point to a simple McLaren walkover. The race was close enough that strategy, tyre phase and position on track could move the podium order.

## Antonelli started strongest; Leclerc finished strongest

Antonelli ranked first on cleaned-lap pace in both the opening and middle thirds of the race. He converted that pace into P2.

Leclerc produced the quickest closing-third pace of any driver, ahead of Norris and Piastri, even though he finished P5. His late hard- and soft-tyre phases were especially competitive once the race settled.

Norris was second-quickest in the closing third and completed a 19-lap final hard-tyre stint at a 74.69s average. That is a better description of the win than simply calling it outright pace dominance: McLaren executed a race-winning final phase in an exceptionally close contest.

## The midfield stories: Lawson, Hülkenberg and Alonso

Lawson's P7 was supported by the pace data. He ranked seventh in each third of the race and his final medium-tyre stint was his quickest sustained phase. That is a clean conversion of competitive midfield pace into a strong result.

Hülkenberg also had a solid underlying race. He ran around eighth to tenth in the three pace segments and finished P8 after gaining five places from the grid.

Alonso's P9 is different. He gained nine places, but his raw pace ranked around 14th early and 15th late. The result was a major recovery drive and a valuable Fantasy outcome, but the deep dive does not support treating it as evidence that Aston Martin suddenly had ninth-place race pace on merit alone.

## What the official Fantasy scores say

The Dutch GP official F1 Fantasy reconciliation is exact: **22 of 22 driver scores** and **11 of 11 constructor scores** match the official totals.

Against those official totals, the forecast's Fantasy-points MAE was **10.19 points per driver**. That is a deliberately demanding measure because it includes Sprint points, overtakes, positions gained or lost, bonuses and retirement penalties in addition to finishing position.

The average signed error was only **-0.51 points per driver**, so the model was not materially biased high or low across the field. Its 90% simulation ranges contained 19 of the 22 official driver scores.

The largest Fantasy deviations were exactly the type of events that are difficult to settle before lights out: Verstappen's retirement, Alonso's recovery to P9, Norris's 57-point weekend and Hamilton finishing lower than the P1 projection.

## What this means for the next decision

The Dutch GP should not be copied directly into a Monza lineup. The circuits reward different things, and Monza's forecast will change once practice data arrives.

But the weekend reinforces three useful principles:

- Treat a strong qualifying read and a correct front-running group as meaningful evidence, even if race events shuffle the exact positions.
- Use the Monte Carlo range as part of the decision, not as decoration. Retirements and recovery drives are not rare edge cases in Fantasy scoring.
- Separate raw pace from final result. A recovery can be brilliant and valuable without proving that the car was the ninth-fastest package on a clean lap-by-lap basis.

The [live Italian GP forecast](/picks/italian-gp-2026/) is now refreshed with updated prices. It is still a pre-practice forecast, so the most informative next update will come after representative Monza running.

## Method and sources

Qualifying and race-position comparisons use the archived post-Sprint Qualifying Dutch GP forecast and the final Grand Prix classification. Pace findings use cleaned race laps from the Dutch GP deep dive; pit-in, pit-out, safety-car and invalid laps are excluded where appropriate.

Official Fantasy totals, not provisional calculated scores, are used for the points-accuracy results in this article. Explore the underlying [Dutch GP results](/data/actual_round14.json), [post-race analysis](/data/post_race_round14.json), [race deep dive](/data/deep_dive_round14.json), [Accuracy dashboard](/accuracy/) and [methodology](/methodology/) for the supporting data and model context.
