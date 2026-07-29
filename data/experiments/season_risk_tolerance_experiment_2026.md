# 2026 F1 Fantasy risk-tolerance season experiment

## Experimental design

Twelve virtual seasons were replayed: three manager philosophies crossed with four risk profiles. Every path started with $100.0M, used the same archived pre-deadline forecasts, carried its real lineup and prices forward, and scored against official results.

- No chips were played so risk tolerance is the isolated variable. The normal 2x captain remained active.
- Risk measure: Sum of max(-P5, 0) across the five drivers and two constructors in each archived pre-deadline Monte Carlo forecast.
- Rounds 1, 2, 3 use reconstructed archives; the remaining completed rounds use genuine lock-time archives.

## Results

| Manager | Risk profile | Full pts | Genuine pts | Final budget | Mean forecast downside | Realised negative pts | Worst round | Round SD |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Max Points | Total avoidance | 1940 | 1282 | $119.7M | 22.4 | -90 | 88 | 56.0 |
| Max Points | Minimal risk accepted | 2362 | 1590 | $119.2M | 30.4 | -101 | 86 | 73.5 |
| Max Points | Medium tolerance | 2358 | 1563 | $113.0M | 35.5 | -161 | 88 | 72.8 |
| Max Points | Maximum tolerance | 2380 | 1675 | $113.7M | 44.9 | -73 | 90 | 49.0 |
| Balanced | Total avoidance | 2032 | 1374 | $120.5M | 22.2 | -90 | 96 | 53.0 |
| Balanced | Minimal risk accepted | 2284 | 1512 | $122.6M | 24.9 | -85 | 86 | 60.7 |
| Balanced | Medium tolerance | 2433 | 1638 | $119.0M | 30.3 | -113 | 114 | 62.5 |
| Balanced | Maximum tolerance | 2495 | 1776 | $118.4M | 42.5 | -83 | 118 | 44.9 |
| Budget Builder | Total avoidance | 2032 | 1374 | $120.5M | 22.2 | -90 | 96 | 53.0 |
| Budget Builder | Minimal risk accepted | 2420 | 1680 | $124.0M | 25.4 | -62 | 113 | 44.2 |
| Budget Builder | Medium tolerance | 2464 | 1647 | $124.3M | 29.2 | -75 | 104 | 59.0 |
| Budget Builder | Maximum tolerance | 2363 | 1581 | $123.8M | 35.6 | -99 | 104 | 68.3 |

## Headline outcomes

- Highest score: Balanced / Maximum tolerance — 2495 points.
- Highest score on genuine lock-time archives: Balanced / Maximum tolerance — 1776 points.
- Highest final budget: Budget Builder / Medium tolerance — $124.3M.
- Lowest forecast downside: Balanced / Total avoidance — 22.2 mean negative-P5 exposure.

## Within-manager trade-offs

- Max Points: its strongest risk-managed version was Minimal risk accepted, scoring -85 genuine-archive points and finishing with $5.5M more versus maximum tolerance.
- Balanced: its strongest risk-managed version was Medium tolerance, scoring -138 genuine-archive points and finishing with $0.6M more versus maximum tolerance.
- Budget Builder: its strongest risk-managed version was Minimal risk accepted, scoring +99 genuine-archive points and finishing with $0.2M more versus maximum tolerance.
- The highest-budget path finished -31 full-season points, -129 genuine-archive points, and $5.9M more relative to the highest-scoring path.

## Did forecast risk predict realised damage?

- The descriptive correlation between mean forecast negative-P5 exposure and realised negative-point magnitude was 0.119, a weak relationship in this sample.
- Restricting to genuine archives, the forecast-risk versus realised-negative correlation was 0.026, also weak.
- Genuine-archive forecast downside and points had a 0.716 correlation, a strong relationship.
- Descriptive only: the 12 paths share rounds and many assets, so they are not independent observations.

## Interpretation guardrails

- Risk profiles use information available before the deadline. Official outcomes are used only after selection to score the paths.
- Total avoidance is intentionally extreme: even a tiny reduction in negative-P5 exposure outranks projected points and price growth.
- This is one partial season. The result shows how these policies behaved in 2026 so far, not a guarantee that the same risk setting will win future seasons.
