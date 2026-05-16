# BoxBoxF1Fantasy — User Guide

A guide to every feature on [boxboxf1fantasy.com](https://boxboxf1fantasy.com).

For technical architecture, see [TECHNICAL_DEEP_DIVE.md](TECHNICAL_DEEP_DIVE.md). For pipeline operation, see [OPERATIONS_GUIDE.md](OPERATIONS_GUIDE.md).

---

## Tab Overview

The site has 11 tabs. Tabs lazy-load — only the active tab fetches its data, so navigation is fast.

- **Drivers** — all 22 drivers ranked by predicted points (the page you land on)
- **Constructors** — all 11 teams with constructor-specific scoring
- **Optimizer** — three lineup tools: Lineup Optimizer, Transfer Advisor, Multi-Week Planner
- **Season** — championship standings + price trackers
- **H2H** — head-to-head matchup predictions between any two drivers or constructors
- **Accuracy** — predicted vs actual analysis (toggle Drivers / Constructors)
- **Race Deep Dive** — post-race analysis: pace, tyre strategy, stints, fuel-corrected pace
- **Videos** — curated F1 video content for the current weekend
- **Articles** — generated data-driven race previews and post-race reviews
- **About** — methodology, data sources, credits

---

## Drivers Tab

Your starting point. Predicted fantasy points for every driver this round.

### Driver Cards

- **Predicted points** — the ML model's best estimate for total fantasy points this round
- **MC 90% CI** — the range covering 90% of simulated outcomes (e.g., "8 — 53 pts" means 5% chance below 8, 5% above 53)
- **Predicted positions** — qualifying and race finish predictions; sprint positions on sprint weekends
- **Scoring breakdown** — qualifying, race, overtakes, fastest lap, DOTD, DNF risk, and sprint (if sprint weekend)
- **Confidence** — how much data backs the prediction (higher when FP telemetry is available)
- **DNF probability** — color-coded green/yellow/red; based on rolling 5-race DNF rate
- **Price change bracket** — points needed this round to trigger an A/B-tier price increase or decrease

### Tips

- Sort by predicted points, price, or value (points per $M)
- Toggle between card view and compact table view
- Confidence ≥ 90% means we have FP telemetry. Confidence ~65-70% is priors-only.
- **Left-click a driver card** to lock them into the optimizer (green border)
- **Right-click** to exclude (red border, strikethrough)

---

## Constructors Tab

Same layout as Drivers, for the 11 constructors.

### Constructor scoring

- Sum of both drivers' qualifying + race points (excludes DOTD per official rules)
- Qualifying teamwork bonus (Both Q3 = +10, ..., Neither = -1)
- Expected pit stop points — analytical EV from team's historical pit stop time distribution; includes fastest-stop bonus and world-record (<1.80s) bonus
- DNF impact — expected points lost from both drivers' DNF probabilities

### Tips

- Constructor pit stop points can be 7-15+ points — don't overlook them
- Check the scoring breakdown to see how much comes from pit stops vs driver performance
- Like drivers: left-click to lock, right-click to exclude

---

## Optimizer Tab

Three tools, switchable from the mode buttons at the top.

### 1. Lineup Optimizer

**What it does:** Brute-force best 5+2 lineup within budget.

1. Set budget (default $100M)
2. Choose strategy:
   - **Max Expected Points** — highest score this round
   - **Max Value** — best points per dollar
   - **Budget Builder** — prioritizes drivers likely to gain price
   - **Balanced** — mix of points and value
3. Optionally select a chip (see [Chips](#the-6-chips) below)
4. Click "Find Best Lineups"

The brute-force evaluates ~1.4M combinations with budget pruning, returns top 200 lineups in ~1-2 seconds.

### 2. Transfer Advisor

**What it does:** Given your current team, finds the best 1-2 swaps to improve your score.

1. **Set your current team** — click slots to pick your 5 drivers + 2 constructors
2. Set **available budget** (your remaining F1 Fantasy budget)
3. Set **free transfers** (how many you have this round)
4. Set **max extra transfers** (0-2; each costs -10 pts)
5. Choose strategy + optional chip
6. Click "Find Best Transfers"

**Results:**
- Each row shows OUT → IN with predicted point delta
- **Net points** = predicted points minus transfer penalty
- "NEW" badges highlight incoming players
- Each swap shows expected price change for the incoming player (green ↑ or red ↓)
- "Keep Current Team" appears when no transfer beats holding

**Lock & Exclude in Transfer Advisor:**
- Lock a driver to prevent the advisor from swapping them out
- Exclude a driver to prevent the advisor from swapping them in
- Use this to protect core picks while optimizing the rest

**When to spend extra transfers:**
- 0 extra: Free transfers only, no penalty
- 1 extra (-10 pts): Worth it if the new pick gains 10+ more points
- 2 extra (-20 pts): Only for dramatic improvements
- 3+: Use Wild Card chip instead

### 3. Multi-Week Transfer Planner

**What it does:** Plans your transfer strategy across 2-5 upcoming rounds with optimal chip deployment.

1. **Set current team** (same picker as Transfer Advisor)
2. Set budget, free transfers, planning horizon (2-5 rounds)
3. Choose strategy:
   - **Max Expected Points** — pure performance
   - **Balanced** — mix of points and value
   - **Budget Builder** — prioritizes asset appreciation
4. **Check available chips** — the planner suggests when to deploy them
5. **Optional: Target Team** — check "Plan toward a target team" to lock in your dream 5+2; the planner steers transfers toward it while still optimizing each round
6. Click "Plan My Transfers"

**Results:**
- **Projection Heatmap** — top drivers/constructors × upcoming rounds, color-coded
- **Plan Cards** — top 5 transfer sequences with hold/swap/chip per round
- **Team Evolution** — expandable view showing your full roster at each round with NEW badges and projected points

**How future-round projections work:**
- Current round: actual ML predictions
- Future rounds: `recent form × track similarity × sprint multiplier`
- Track similarity uses 9 circuit characteristics (downforce, overtaking difficulty, corner speed, etc.)

**Tips:**
- Check "Wild Card" if available — the planner finds the optimal round to deploy it
- Sprint rounds have +15% projected points (extra scoring opportunity)
- Bank transfers when the upcoming round doesn't benefit from a swap (max 5 banked)
- "Hold" entries mean your current team is already well-suited for that circuit
- Use "Target Team" mode when you have a roster you want to end up with but need help planning the path

---

## The 6 Chips

| Chip | Effect |
|------|--------|
| **Limitless** | No budget cap |
| **3x Boost** | Best driver scores 3x; second-best scores 2x |
| **Wild Card** | Unlimited free transfers (no -10 pts penalties) |
| **No Negative** | Negative driver scores become 0 |
| **Autopilot** | Auto 2x on best driver |
| **Final Fix** | Allows a roster change after qualifying |

The optimizer fully understands all 6 — its scoring function applies the correct boosts when ranking lineups.

---

## Season Tab

Track championship progress and price trends.

- **Championship standings** — cumulative fantasy points across all completed rounds
- **Driver price tracker** — starting price, current price, change, trend per driver
- **Constructor price tracker** — same for constructors

---

## H2H Tab (Head-to-Head)

Compare any two drivers or constructors side-by-side.

- **Win probability** — which player is more likely to outscore the other (computed from MC distribution overlap)
- **Predicted points comparison**
- **Statistical comparison** — qualifying position, race position, overtakes, etc.
- **Recommendation** — pick suggestion with rationale

---

## Accuracy Tab

Predicted vs actual analysis for completed rounds.

- **Drivers / Constructors toggle** at the top — switch view between driver-level and constructor-level accuracy
- **Phase toggle** — Latest / Pre-FP / Post-FP / Post-Quali. Switches which snapshot of the prediction is being measured:
  - **Latest** — the canonical prediction (usually the most-informed forecast we made before the race)
  - **Pre-FP** — what the model predicted *before* any free practice ran (priors only, no telemetry)
  - **Post-FP** — what the model predicted *after* free practice but *before* qualifying
  - **Post-Quali** — what the model predicted *after* qualifying, using the actual grid
  - Phases without archives for any round are greyed out. Each button shows a count of how many rounds have that phase available.
- **Per-round MAE** — average prediction error for each completed round
- **90% CI coverage** — what % of actual outcomes fell within our 90% CI (target: 90%)
- **50% CI coverage** — narrower band check (target: 50%)
- **Per-driver / per-constructor scatter** — predicted vs actual points
- **Race filter** — toggle individual rounds in/out of the stats

When you see a purple banner mentioning **"reconstructed"** archives, that means the original predictions for those rounds were lost (the early pipeline allowed re-predictions after the race, which polluted the archive). We walk-forward retrained the model with those rounds *excluded* and re-predicted on raw pre-race data to produce an honest reconstruction. These are flagged transparently so you know what you're looking at.

When constructor official points haven't been entered for a round, an amber note appears: "Official constructor points not entered yet — using pipeline-calculated actuals."

---

## Race Deep Dive Tab

Post-race analysis for completed rounds.

- **Predicted vs actual positions** — see where the model was right and wrong
- **Fuel-corrected pace** — applies ~0.035s/lap correction so early-stint laps with full fuel are comparable to late-stint laps
- **Stint-by-stint breakdown** — per-driver stints with compound, lap count, average pace, degradation
- **Sector pace** — best and average per sector
- **Compound-specific analysis** — soft/medium/hard pace
- **Tyre strategy** — actual stint compounds and lengths
- **Pit stop times** — stationary times for the constructor pit stop scoring

---

## Videos Tab

Curated F1 video content relevant to the current race weekend or season — race highlights, analysis clips, technical breakdowns.

---

## Articles Tab

Generated data-driven articles. Race previews, post-race reviews, season trends. Sourced from `web/public/articles/*.md`.

---

## About Tab

Background on how BoxBoxF1Fantasy works — the ML pipeline, data sources, scoring methodology, project credits.

---

## General Tips

1. **Run after FP3 for best predictions** — confidence jumps from ~65% to ~90% when FP telemetry is included
2. **Don't ignore constructors** — pit stop points + qualifying bonus are easy points
3. **Use the Multi-Week Planner when you have 3+ free transfers** — the value of planning ahead is highest when you have flexibility
4. **Lock your best performers** in the Transfer Advisor to protect them from being swapped
5. **Budget Builder strategy is best early-season** — compounding price growth matters most in the first 6-8 rounds
6. **Watch the price brackets** — sometimes holding a "poor" performer one more round pushes them past the threshold for a price drop, letting you sell at a better price
7. **The Accuracy tab is your reality check** — see how close the model has been on past rounds before betting big on this round's predictions
