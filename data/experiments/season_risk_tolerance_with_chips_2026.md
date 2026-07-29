# 2026 F1 Fantasy risk-tolerance season experiment with chips

## Experimental design

Twelve virtual seasons were replayed: three manager philosophies crossed with four risk profiles. Every path started with $100.0M, used the same archived pre-deadline forecasts, carried its real lineup and prices forward, and scored against official results.

- Domain-informed V2 chip timing was applied using genuine pre-deadline archives only. The 3x Boost was saved. The normal 2x captain remained active.
- Risk measure: Sum of max(-P5, 0) across the five drivers and two constructors in each archived pre-deadline Monte Carlo forecast.
- Rounds 1, 2, 3 use reconstructed archives; the remaining completed rounds use genuine lock-time archives.

## Results

| Manager | Risk profile | Full pts | Genuine pts | Final budget | Mean forecast downside | Realised negative pts | Worst round | Round SD |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Max Points | Total avoidance | 2245 | 1587 | $123.3M | 20.7 | -65 | 117 | 54.4 |
| Max Points | Minimal risk accepted | 2431 | 1659 | $120.6M | 25.6 | -82 | 151 | 48.4 |
| Max Points | Medium tolerance | 2493 | 1698 | $116.6M | 32.1 | -101 | 99 | 62.0 |
| Max Points | Maximum tolerance | 2267 | 1562 | $107.8M | 48.8 | -185 | 65 | 57.7 |
| Balanced | Total avoidance | 2245 | 1587 | $123.3M | 20.7 | -65 | 117 | 54.4 |
| Balanced | Minimal risk accepted | 2443 | 1671 | $121.0M | 25.7 | -82 | 151 | 49.0 |
| Balanced | Medium tolerance | 2502 | 1707 | $118.9M | 29.8 | -113 | 101 | 62.0 |
| Balanced | Maximum tolerance | 2438 | 1719 | $117.7M | 38.6 | -120 | 108 | 58.6 |
| Budget Builder | Total avoidance | 2245 | 1587 | $123.3M | 20.7 | -65 | 117 | 54.4 |
| Budget Builder | Minimal risk accepted | 2387 | 1647 | $124.3M | 24.1 | -88 | 156 | 42.0 |
| Budget Builder | Medium tolerance | 2537 | 1720 | $124.3M | 27.0 | -75 | 156 | 50.4 |
| Budget Builder | Maximum tolerance | 2449 | 1667 | $120.3M | 38.1 | -132 | 118 | 64.8 |

## Chip impact versus the matching no-chip path

| Manager | Risk profile | Full-points Δ | Genuine-points Δ | Budget Δ |
|---|---|---:|---:|---:|
| Max Points | Total avoidance | +305 | +305 | +3.6M |
| Max Points | Minimal risk accepted | +69 | +69 | +1.4M |
| Max Points | Medium tolerance | +135 | +135 | +3.6M |
| Max Points | Maximum tolerance | -113 | -113 | -5.9M |
| Balanced | Total avoidance | +213 | +213 | +2.8M |
| Balanced | Minimal risk accepted | +159 | +159 | -1.6M |
| Balanced | Medium tolerance | +69 | +69 | -0.1M |
| Balanced | Maximum tolerance | -57 | -57 | -0.7M |
| Budget Builder | Total avoidance | +213 | +213 | +2.8M |
| Budget Builder | Minimal risk accepted | -33 | -33 | +0.3M |
| Budget Builder | Medium tolerance | +73 | +73 | +0.0M |
| Budget Builder | Maximum tolerance | +86 | +86 | -3.5M |

## Chip schedules

| Manager | Risk profile | Limitless | Wild Card | No Negative | Autopilot | 3x Boost |
|---|---|---:|---:|---:|---:|---:|
| Max Points | Total avoidance | 8 | 7 | 10 | 11 | Saved |
| Max Points | Minimal risk accepted | 8 | 12 | 10 | 11 | Saved |
| Max Points | Medium tolerance | 8 | Saved | 10 | 12 | Saved |
| Max Points | Maximum tolerance | 8 | 12 | 10 | 11 | Saved |
| Balanced | Total avoidance | 8 | 7 | 10 | 11 | Saved |
| Balanced | Minimal risk accepted | 8 | 12 | 10 | 11 | Saved |
| Balanced | Medium tolerance | 8 | 12 | 10 | 11 | Saved |
| Balanced | Maximum tolerance | 8 | 7 | 10 | 12 | Saved |
| Budget Builder | Total avoidance | 8 | 7 | 10 | 11 | Saved |
| Budget Builder | Minimal risk accepted | 8 | 6 | 10 | 12 | Saved |
| Budget Builder | Medium tolerance | 8 | 6 | 10 | 12 | Saved |
| Budget Builder | Maximum tolerance | 8 | 6 | 10 | 12 | Saved |

## Conditional chip contribution

Each value removes one chip while holding the other scheduled chips fixed, then replays the remaining season path.
These conditional effects are not additive because removing a chip can alter later transfers, budgets, and Wild Card state.

| Chip | Paths played | Positive return | Mean points | Median points | Range | Mean budget |
|---|---:|---:|---:|---:|---:|---:|
| Limitless | 12 | 92% | +81.0 | +71.0 | -164 to +218 | +0.1M |
| Wild Card | 11 | 100% | +43.5 | +40.0 | +15 to +156 | -0.2M |
| No Negative | 12 | 8% | +1.4 | +0.0 | +0 to +17 | +0.0M |
| Autopilot | 12 | 50% | +7.5 | +2.0 | +0 to +30 | +0.0M |

## Headline outcomes

- Highest score: Budget Builder / Medium tolerance — 2537 points.
- Highest score on genuine lock-time archives: Budget Builder / Medium tolerance — 1720 points.
- Highest final budget: Budget Builder / Minimal risk accepted — $124.3M.
- Lowest forecast downside: Max Points / Total avoidance — 20.7 mean negative-P5 exposure.

## Within-manager trade-offs

- Max Points: its strongest risk-managed version was Medium tolerance, scoring +136 genuine-archive points and finishing with $8.8M more versus maximum tolerance.
- Balanced: its strongest risk-managed version was Medium tolerance, scoring -12 genuine-archive points and finishing with $1.2M more versus maximum tolerance.
- Budget Builder: its strongest risk-managed version was Medium tolerance, scoring +53 genuine-archive points and finishing with $4.0M more versus maximum tolerance.
- The highest-budget path finished -150 full-season points, -73 genuine-archive points, and $0.0M more relative to the highest-scoring path.

## Did forecast risk predict realised damage?

- The descriptive correlation between mean forecast negative-P5 exposure and realised negative-point magnitude was 0.968, a strong relationship in this sample.
- Restricting to genuine archives, the forecast-risk versus realised-negative correlation was 0.960, also strong.
- Genuine-archive forecast downside and points had a 0.100 correlation, a weak relationship.
- Descriptive only: the 12 paths share rounds and many assets, so they are not independent observations.

## Interpretation guardrails

- Risk profiles use information available before the deadline. Official outcomes are used only after selection to score the paths.
- Total avoidance is intentionally extreme: even a tiny reduction in negative-P5 exposure outranks projected points and price growth.
- This is one partial season. The result shows how these policies behaved in 2026 so far, not a guarantee that the same risk setting will win future seasons.
