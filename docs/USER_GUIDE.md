# BoxBoxF1Fantasy — User Guide

A complete guide to using all the tools on [boxboxf1fantasy.com](https://boxboxf1fantasy.com).

---

## Drivers Tab

Your starting point. Shows predicted fantasy points for every driver this round.

**Driver Cards** show:
- **Predicted points** — the ML model's best estimate for this driver's total fantasy points
- **MC 90% CI** — the range covering 90% of simulated outcomes (e.g., "8 — 53 pts" means there's a 5% chance of scoring below 8 and a 5% chance above 53)
- **Predicted positions** — qualifying and race finish predictions
- **Scoring breakdown** — where the points come from: qualifying, race position, overtakes, fastest lap probability, DOTD probability, and DNF risk
- **Confidence** — how much data supports the prediction (higher when FP telemetry is available)
- **DNF probability** — risk of not finishing, color-coded green/yellow/red
- **Price change bracket** — shows how many points the driver needs this round to see a price increase or decrease

**Tips:**
- Sort by predicted points, price, or value (points per $M)
- Toggle between card view and compact table view
- The confidence percentage tells you how much to trust the prediction — predictions with 90%+ confidence use both historical data AND current weekend practice telemetry

---

## Constructors Tab

Same layout as Drivers, but for the 11 constructors.

**Constructor scoring includes:**
- Sum of both drivers' qualifying + race points (excluding DOTD)
- Qualifying teamwork bonus (+10 if both reach Q3, down to -1 if neither reaches Q2)
- Expected pit stop points (based on team's historical pit stop speed)
- DNF impact (expected points lost from drivers' DNF probabilities)

**Tips:**
- Constructor pit stop points can be 7-15+ points — don't overlook them
- Check the scoring breakdown to see how much comes from pit stops vs driver performance

---

## Optimizer Tab

Three powerful tools in one tab. Switch between them using the mode buttons at the top.

### 1. Lineup Optimizer

**What it does:** Finds the absolute best team from scratch within your budget.

**How to use it:**
1. Set your budget (default $100M)
2. Choose a strategy:
   - **Max Expected Points** — highest predicted score this round
   - **Max Value** — best points per dollar spent
   - **Budget Builder** — prioritizes drivers likely to increase in price
   - **Balanced** — mix of points and value
3. Optionally select a chip (Limitless, 3x Boost, etc.)
4. Click "Find Best Lineups"

**Lock & Exclude:**
- **Left-click** a driver or constructor card (in the Drivers/Constructors tab) to **lock** them — they'll always be included in optimizer results
- **Right-click** to **exclude** — they'll never appear in results
- Locked picks show a green border; excluded show red with strikethrough

---

### 2. Transfer Advisor

**What it does:** Given your current team, finds the best 1-2 player swaps to improve your score.

**How to use it:**
1. **Select your current team** — click slots to add your 5 drivers + 2 constructors
2. Set your **available budget** (your current remaining budget in F1 Fantasy)
3. Set **free transfers** (how many free transfers you have this round)
4. Set **max extra transfers** (how many paid transfers you're willing to make — each costs -10 pts)
5. Choose a strategy and chip
6. Click "Find Best Transfers"

**Understanding results:**
- Results show swap-by-swap changes: who goes OUT and who comes IN
- **Net points** = predicted points minus any transfer penalty
- **NEW** labels highlight incoming players
- Each swap shows the expected price change for incoming players (green ↑ or red ↓)
- "Keep Current Team" appears when no transfer improves your score

**Lock/Exclude in Transfer Advisor:**
- Lock a driver to prevent the advisor from swapping them out
- Exclude a driver to prevent the advisor from swapping them in
- Use this to protect core picks while optimizing the rest

**When to use extra transfers:**
- 0 extra: Only swap within your free transfers (no penalty)
- 1 extra (-10 pts): Worth it if the new pick gains 10+ more points
- 2 extra (-20 pts): Only for dramatic improvements or end-of-season pushes
- 3+ extra: Use Wild Card chip instead!

---

### 3. Multi-Week Transfer Planner

**What it does:** Plans your transfer strategy across 2-5 upcoming rounds, finding the optimal timing for swaps, chip deployment, and transfer banking.

**How to use it:**
1. **Select your current team** (same as Transfer Advisor)
2. Set budget, free transfers, and planning horizon (2-5 rounds)
3. Choose a strategy:
   - **Max Expected Points** — pure performance
   - **Balanced** — mix of points and value efficiency
   - **Budget Builder** — prioritizes asset appreciation
4. **Check available chips** — select the chips you still have. The planner will suggest when to deploy them.
5. **Optional: Target Team** — check "Plan toward a target team" and select the 5 drivers + 2 constructors you want to end up with. The planner will steer transfers toward that team while still optimizing intermediate rounds.
6. Click "Plan My Transfers"

**Understanding results:**

The **Projection Heatmap** shows projected scores for the top drivers and constructors across upcoming rounds. Color coding:
- Dark green = well above average
- Green = above average
- Yellow = below average
- Red = well below average

**Plan Cards** show the top 5 strategies:
- Each round shows: hold (keep team), swap (who in/out), or chip deployment
- Total projected points across the planning horizon
- Transfer banking (unused transfers carry over, max 5)

**How score projections work:**
- **Current round:** Uses actual ML predictions from the model
- **Future rounds:** Uses `recent form × track similarity` — if a driver has been scoring well and the upcoming circuit is similar to tracks where they excel, their projected score is higher
- Track similarity uses 9 circuit characteristics (downforce level, overtaking difficulty, corner speed, etc.)

**Tips:**
- Check "Wild Card" if you have it — the planner will find the optimal round to deploy it
- Sprint rounds (marked with a sprint badge) have higher projected points due to extra scoring opportunities
- Bank transfers when the upcoming round doesn't benefit from a swap — use them later when a big upgrade is available
- Plans that hold (make no changes) for a round mean your current team is already well-suited for that circuit
- Use "Target Team" mode when you know which team you want but need help planning the transfer path to get there
- Click "View Team Evolution" on any plan to see your full roster at each round, with new additions highlighted in green

---

## Season Tab

Track championship progress and price trends.

**Features:**
- **Championship standings** — cumulative fantasy points across all completed rounds
- **Driver price tracker** — shows starting price, current price, change, and trend for every driver
- **Constructor price tracker** — same for constructors

---

## H2H Tab (Head-to-Head)

Compare any two drivers or constructors side-by-side.

**Shows:**
- Win probability (which player is more likely to outscore the other)
- Predicted points comparison
- Monte Carlo distribution overlap
- Statistical comparison (qualifying position, race position, overtakes, etc.)
- Recommendation: which one to pick and why

---

## Accuracy Tab

See how well our predictions performed against actual results.

**Metrics shown:**
- **Per-round MAE** — average position prediction error for each completed round
- **90% CI coverage** — what percentage of actual outcomes fell within our predicted confidence intervals (target: 90%)
- **50% CI coverage** — narrower band check (target: 50%)
- **Per-driver scatter** — predicted vs actual points for each driver across all rounds

---

## Deep Dive Tab

Post-race analysis for completed rounds.

**Shows:**
- Predicted vs actual positions
- Where the model was right and wrong
- Pace analysis from race data
- Stint-by-stint breakdown

---

## General Tips

1. **Run the pipeline after FP3** — predictions are most accurate when practice telemetry is included (confidence jumps from ~65% to ~90%)
2. **Don't ignore constructors** — pit stop points and qualifying bonuses add up significantly
3. **Use the Multi-Week Planner** when you have 3+ free transfers banked — it's most valuable when you have flexibility
4. **Lock your best performers** in the Transfer Advisor to prevent them from being swapped out
5. **Budget Builder strategy** is best early in the season when compounding price growth matters most
6. **Watch the price change brackets** — sometimes holding a "poor" performer one more round pushes them into a price drop
