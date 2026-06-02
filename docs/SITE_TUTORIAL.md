# BoxBoxF1Fantasy — Complete Site Tutorial & Video Script

**A full walkthrough of [boxboxf1fantasy.com](https://boxboxf1fantasy.com): every tab, every feature, the quirks, and — most importantly — how to actually use it to win at F1 Fantasy.**

This document is written so it can be read two ways:

1. **As a tutorial** — a plain-English guide to the whole site, top to bottom.
2. **As a YouTube video script** — each section has `[SHOW]` screen-direction cues, `[SAY]` narration you can read aloud (or adapt), and `💡 PRO TIP` call-outs that make the best "pause and rewind" moments.

If you just want the bullet-point cheat sheet, jump to [The One-Page Cheat Sheet](#the-one-page-cheat-sheet) at the bottom.

> **For the companion docs:** the reference-style [USER_GUIDE.md](USER_GUIDE.md) documents each feature without the narration; [TECHNICAL_DEEP_DIVE.md](TECHNICAL_DEEP_DIVE.md) explains how the model works; [OPERATIONS_GUIDE.md](OPERATIONS_GUIDE.md) is for running the pipeline.

> **A note on examples:** numbers in this script (driver names, points, prices) are taken from **Round 8, the Monaco Grand Prix, 2026** — whatever is live when you record will differ. Treat them as illustrations of *how to read* the numbers, not as fixed values.

---

## Video at a glance

| | |
|---|---|
| **Working title** | "The F1 Fantasy Tool I Built (And How to Use It to Win)" |
| **Alt titles** | "Stop Guessing Your F1 Fantasy Team — Use Data" / "A Full Tour of BoxBoxF1Fantasy" |
| **Target length** | 15–22 minutes |
| **Audience** | F1 Fantasy players who want an edge — beginners to intermediate |
| **The promise (your hook)** | By the end, you'll know exactly how to pick a team, plan transfers weeks ahead, and read the model honestly — for free. |
| **Chapters** | Intro → How it works (30s) → Drivers → Constructors → Weather → Optimizer (the big one) → Chips → H2H → Accuracy → Season → Analysis & Deep Dive → Quirks → My weekly routine → Outro |

---

## 0. Cold open / The hook (0:00–0:40)

`[SHOW]` Site homepage loading, Drivers tab populated with cards. Maybe a fast montage of the Optimizer running and the Multi-Week Planner heatmap.

`[SAY]`
> "F1 Fantasy looks simple — pick five drivers, two constructors, stay under budget. But the people at the top of your mini-league aren't guessing. They're thinking about price changes, transfer timing, which chip to fire and when, and which driver is about to have a great weekend on a track that suits their car.
>
> I got tired of paying for tools that were honestly worse than my own gut, so I built my own — a machine-learning pipeline that predicts every session of every weekend, runs ten thousand race simulations, and turns it into picks. It's completely free. This is BoxBoxF1Fantasy, and in the next fifteen minutes I'm going to show you how to use every part of it to actually climb your league."

`[SHOW]` Title card / logo.

💡 **PRO TIP (for the creator):** Open on the *result* people want (a winning team / a sharp transfer), not on a menu. Show the payoff, then teach.

---

## 1. The 30-second mental model (0:40–1:30)

Before clicking anything, give viewers the one thing that makes everything else make sense: **where do the numbers come from?**

`[SHOW]` The About tab's "How It Works" cards (Data → Features → ML → Monte Carlo → Fantasy Points → Post-Race), scrolling slowly.

`[SAY]`
> "Quick — here's the whole thing in thirty seconds, because it'll make every number on this site make sense.
>
> One: we pull real F1 data — timing, results, telemetry — going back to 2020. Two: every driver and team gets turned into a profile: recent form, how they go at this *type* of track, reliability, free-practice pace when we have it. Three: machine-learning models predict where everyone qualifies and finishes. Four — and this is the important one — we run the race **ten thousand times** in simulation, with crashes, safety cars, overtakes, fastest laps all happening at realistic rates. Five: every one of those simulated outcomes gets scored with the **official** 2026 F1 Fantasy rules. What you see on a card is the *average* of ten thousand simulated races, plus the range.
>
> That's why this isn't one guy's opinion — it's a distribution. Keep that word in your head: **distribution**. It's the key to reading everything here honestly."

💡 **PRO TIP:** The phrase "we run the race 10,000 times" is your single best soundbite. It's concrete, it's surprising, and it justifies the confidence intervals you'll explain later.

---

## 2. The Drivers tab — reading a card (1:30–4:30)

This is the page everyone lands on. Spend real time here; if viewers can read one card, they can read the whole site.

`[SHOW]` Drivers tab. Hover/zoom on the **top driver card** (e.g. Antonelli, 31.7 pts at Monaco).

`[SAY]`
> "This is where you land, and it's the heart of the site: all twenty-two drivers, ranked by predicted fantasy points for *this* weekend. Let's read the top card together, because once you can read one, you can read everything."

Walk through each field on the card, in order:

| Field | What to say |
|---|---|
| **Predicted points** (the big number) | "This is the headline: the model's best single estimate of total fantasy points this weekend. It already includes qualifying, race, overtakes, fastest-lap and Driver-of-the-Day chances, minus DNF risk." |
| **MC 90% confidence interval** (e.g. "8 — 53 pts") | "This range is the gold. It means: in 90% of our ten-thousand simulations, this driver scored between these two numbers. A *narrow* band is a safe, predictable pick. A *wide* band is a gamble — big upside, big downside. **A wide band is not a bug. It's the model being honest that this driver's weekend could go a lot of ways.**" |
| **Predicted qualifying & race positions** | "Where we think they'll start and finish. On sprint weekends you'll also see sprint positions." |
| **Confidence %** | "How much data backs this. Around 65% means we're working off history only — it's early in the weekend. Around 90%+ means free-practice telemetry has landed and the picture is sharp. If you see 65%, treat it as directional." |
| **DNF risk** (green/yellow/red) | "Reliability and crash risk, colour-coded. This is baked into the points already, but it's worth a glance — a red DNF risk on an expensive driver is a real downside." |
| **Price + price-change bracket** | "Their current price, and how many points they need this weekend to trigger a price rise or drop. This matters more than beginners think — I'll come back to it." |
| **Scoring breakdown** | "Click to expand and you'll see exactly where the points come from — quali, race, overtakes, the bonuses. If a number surprises you, this is where you check the model's reasoning." |

`[SHOW]` Expand a scoring breakdown. Then demonstrate the sort dropdown.

`[SAY]`
> "Up top you can re-sort the whole field. **Expected Points** is the default. But flip it to **PPM** — points per million — and the board completely changes. PPM is your *value* ranking: who gives you the most points per dollar. That's how you find the cheap driver who lets you afford a star somewhere else."

`[SHOW]` Sort by PPM, point out a cheap high-PPM driver. Then toggle card/table view. Then the team filter and search box.

💡 **PRO TIP (say this one slowly):** "Expected Points tells you who scores the most. **PPM tells you who's *underpriced*.** Championship-winning fantasy teams are built on PPM, not big names — because every million you save on a value pick is a million you can spend on a difference-maker."

### The lock / exclude trick (record this — people miss it)

`[SHOW]` Left-click a driver card → green border. Right-click another → red border + strikethrough.

`[SAY]`
> "Two clicks most people never discover. **Left-click** any card to *lock* that driver — a green border. **Right-click** to *exclude* them — red, struck through. These carry straight into the optimizer. So if you're certain you want Verstappen and you'd never touch a particular backmarker, lock one, exclude the other, and every tool on the site respects it."

### The ± What-If slider (your secret weapon)

`[SHOW]` Click the small **±** button top-left of a card. Drag the slider to +2. Watch the points update.

`[SAY]`
> "See this little plus-minus button? This is for when *you* know something the model doesn't. Say you've watched practice and you're convinced a driver is two places faster than we're giving them credit for. Click here, drag to +2 — meaning 'two positions better' — and the card instantly recomputes their points with your view applied, right next to the model's baseline.
>
> The model's prediction never changes — your bump is an overlay, just for you. There's a purple pill at the top that tracks all your active bumps; hit **Manage** and you can set team-wide sliders, reset everything, or even share your scenario as a link so your mate can see the exact same what-if."

💡 **PRO TIP:** What-If bumps are stored in *your browser only* and **reset when the round changes** — so a Monaco bump won't haunt you in Spain. Use them freely.

### Weather badges

`[SHOW]` A card with a 🌧 or 🥶 badge (if the forecast is triggering one).

`[SAY]`
> "If you see a little rain cloud or a snowflake on a card, the race forecast is wet or cold and the simulation has reacted: it widens the uncertainty bands, raises DNF risk, and nudges historically wet-strong drivers — your Verstappens, Hamiltons, Alonsos — slightly up. Cold weekends quietly favour Mercedes and Williams. It's deliberately *conservative* — it under-promises on chaos weekends rather than over-promising."

---

## 3. The Constructors tab — the points beginners leave on the table (4:30–6:00)

`[SHOW]` Constructors tab. Open the **Pit Stop Performance** panel at the top.

`[SAY]`
> "Same layout, eleven teams. But constructors score differently, and this is where casual players lose ground — because two big sources of constructor points have nothing to do with where the cars finish.
>
> **One: pit stops.** Look at this panel — these are real wheels-up stationary times. A team that consistently bangs out sub-2-second stops is banking double-digit fantasy points every weekend, automatically. The model projects this from each team's pit-stop history, and it can be worth seven, ten, fifteen points. Most people never look at it.
>
> **Two: the qualifying teamwork bonus.** If *both* drivers reach Q3, the constructor gets plus ten. If neither escapes Q1, minus one. So a team with two cars reliably in the top ten is worth more than the headline finishing positions suggest."

`[SHOW]` Expand a constructor's scoring breakdown showing pit-stop EV + quali bonus.

`[SAY]`
> "Open any constructor's breakdown and you can see the split — how much is coming from the drivers versus pit stops versus that teamwork bonus. One rule worth knowing: constructor scores **never** include driver boost multipliers. Your 2x and 3x chips only ever apply to drivers. So don't pick a constructor expecting your boost to carry over — it won't, by the official rules."

💡 **PRO TIP:** When two constructors are close on predicted points, **let pit-stop performance break the tie.** It's the most reliable, least-random points source on the grid — it doesn't care about safety cars.

---

## 4. The weather widget (6:00–6:45)

`[SHOW]` The weather forecast widget on the Drivers tab — per-session rain risk, temp, wind. Expand the explainer.

`[SAY]`
> "Back on the Drivers tab there's a per-session weather forecast — practice, qualifying, sprint, race — with rain risk, temperature and wind, refreshed through the weekend. When rain risk is high, expand it and the widget tells you in plain English exactly what the simulation did: how much it widened the bands, how much it bumped DNF risk, who it favoured.
>
> Two ways to play weather. One: trust the model — it's already reacting. Two: if you have a strong personal read — say you think a particular wet specialist is going to *thrive* — go back to the cards and dial it in yourself with the plus-minus slider. The site gives you both the automated take and the manual override."

---

## 5. The Optimizer — the tab that wins leagues (6:45–12:00)

This is the longest, most valuable section. It has **three modes**. Slow down here.

`[SHOW]` Optimizer tab. Point at the three mode buttons: **Build Fresh Lineup**, **Transfer Advisor**, **Multi-Week Planner**.

`[SAY]`
> "This is the tab that actually wins leagues, and it has three tools. Which one you want depends on where you are in the season. Let me show you all three."

### 5a. Build Fresh Lineup — start of season, or a Wild Card (6:50–8:00)

`[SHOW]` Set budget to 100, pick "Max Expected Points", click **Find Best Lineups**. Results appear.

`[SAY]`
> "Building from scratch — new season, or you're about to fire a Wild Card. Set your budget, pick a strategy, hit go. Behind the scenes it's checking **all 1.4 million** legal combinations of five drivers and two constructors and ranking them. Takes about a second.
>
> Four strategies, and they matter:
> - **Max Expected Points** — the highest-scoring team this weekend, full stop.
> - **Max Value** — the best points-per-dollar team, leaving money in the bank.
> - **Budget Builder** — favours picks likely to *rise* in price, so your team value grows.
> - **Balanced** — a sensible blend.
>
> Early in the season I lean **Budget Builder**, and here's the non-obvious reason why."

`[SHOW]` Switch to Budget Builder, run it, show a slightly different team.

💡 **PRO TIP:** "Early-season, **team value compounds.** Every price rise you bank in the first 6–8 rounds is extra budget for the *rest of the year*. A team that's slightly worse on points but rising in value can be worth more by mid-season than a team that scored a few more points but stagnated. Build budget while it's cheap to."

`[SHOW]` Remind viewers: the lock/exclude from the Drivers tab applies here. Show the chip dropdown.

`[SAY]`
> "Remember the locks and excludes from earlier? They apply here. Want to force Leclerc in and never see a Haas? Lock and exclude, then optimize around that. And up here you can tell it which chip you're playing so the team it builds is the *right* team for that chip."

### 5b. Transfer Advisor — the one you'll use every week (8:00–9:45)

`[SHOW]` Switch to Transfer Advisor. Fill in current 5 drivers + 2 constructors via the slot picker. Set budget, free transfers, max extra transfers. Click **Find Best Transfers**.

`[SAY]`
> "This is the one you'll use most. You already *have* a team — what's the best one or two changes to make this week? Punch in your current five drivers and two constructors, your bank balance, and how many free transfers you've got. Then the key setting: **max extra transfers.** Each transfer beyond your free ones costs minus ten points, so tell it how aggressive you're willing to be."

`[SHOW]` Results list. Zoom on a single swap row showing `OUT → IN`, the points delta, and the new `+4.2pts −$1.5M` style swap line + the efficiency line.

`[SAY]`
> "Now look at what each suggestion tells you. Every swap shows who comes **out**, who comes **in**, and two numbers I added specifically because they're the two you actually weigh: what it does to your **points**, and what it does to your **wallet**. Plus-four-point-two points, minus one-and-a-half million — green when a swap frees up cash, red when it costs you.
>
> And this line here — the **efficiency** line — tells you the gain *versus simply keeping your team*, and the gain *per transfer used*. That's the honest test of whether taking a minus-ten hit is worth it. If an extra transfer only nets you six points after the penalty, the tool will tell you, and you keep your team."

`[SHOW]` Point out a "Keep Current Team" result, and the smarter pool surfacing a cheap enabler.

`[SAY]`
> "Two things people love here. First, if no move beats holding, it just says **keep your team** — it won't invent a transfer to look busy. Second, the search now deliberately considers cheap 'enabler' picks — a budget driver you bring in *purely* to afford a star somewhere else. Those used to be invisible if you sorted by raw points; now the tool finds them."

`[SHOW]` Lock a core driver, re-run.

💡 **PRO TIP:** "Lock your keepers before you run it. If there's a driver you're *not* selling no matter what, lock them — now the advisor spends its budget optimizing the other six slots instead of suggesting you trade your best asset for a marginal gain."

### 5c. Multi-Week Planner — think three races ahead (9:45–11:30)

`[SHOW]` Switch to Multi-Week Planner. Set horizon to 3 rounds. Run it. Show the heatmap + plan cards.

`[SAY]`
> "Here's where you separate from the pack. Most people transfer one week at a time. This plans **two to five rounds ahead** at once, because the best move this week sometimes depends on what's coming. You don't want to sell a driver who's perfect for the next three tracks just to grab five points today.
>
> Run it and you get two things. This **heatmap** shows the top drivers and constructors across your upcoming rounds, colour-coded — green is a good matchup, red is a poor one. You can literally see which races suit which drivers. And these **plan cards** are full transfer *sequences*: hold here, swap there, fire this chip on that round — with the points and your budget evolving across the whole stretch."

`[SHOW]` Point at a plan card's per-round budget line and the "vs hold" trade-off line.

`[SAY]`
> "Each plan shows your budget growing or shrinking round by round, and on any swap round, a 'versus hold' line telling you whether that extra-transfer hit actually paid off over the horizon. Where do the future scores come from? The current round is full model predictions; future rounds use a lighter ML projection, or — for tracks we don't have a clean read on yet — how similar each upcoming circuit is to ones where each driver has gone well. Treat the far-out rounds as *directional*, not gospel."

`[SHOW]` Tick "Plan toward a target team", build a dream team, set intensity to Balanced. Show the feasibility card.

`[SAY]`
> "And the power feature: **Target Team mode.** Tell it the dream team you want to end up with, and it finds the optimal *path* to get there — which transfers, in which order, over which rounds. The intensity dial controls how hard it chases: **Loose** only converges if it's nearly free, **Strict** forces it even at a points cost, **Balanced** is the sweet spot. Before it even searches, this **feasibility card** tells you straight up — green, your target is affordable now; orange, maybe, if prices move your way; red, not happening, and here's exactly how much you're short and which picks are too expensive."

💡 **PRO TIP:** "Use the Multi-Week Planner most when you have **three or more free transfers banked.** Flexibility is exactly when planning ahead pays — and it'll often tell you to *bank* a transfer this week so you can make a double move when a sprint round or a favourable track cluster arrives."

### 5d. The six chips — what they do and when to fire them (11:30–12:00)

`[SHOW]` The chip dropdown, listing all six.

`[SAY]`
> "Quick run through your six chips, because timing them is half the game:"

| Chip | What it does | When to fire it |
|---|---|---|
| **Limitless** | No budget cap for one round | A round where the absolute best team is way over budget — load up on every star at once. |
| **3x Boost** | Best driver scores 3×, second-best 2× | A weekend you're very confident in a specific driver having a *big* score (pole + win + overtakes). |
| **Wild Card** | Unlimited free transfers, no penalties | When your team needs a *total* rebuild — pair it with the Lineup Optimizer's fresh build. |
| **No Negative** | Negative driver scores become zero | A chaos/wet weekend with high DNF risk across your team — caps your downside. |
| **Autopilot** | Auto-2× on your best driver | A safe insurance chip when you're not sure who'll pop — let it pick the boost for you. |
| **Final Fix** | One roster change *after* qualifying | Save it for a weekend where qualifying surprises are likely — react to the actual grid. |

`[SAY]`
> "The optimizer and the planner both understand all six — pick the chip in the dropdown and they'll build the team that makes the most of it, and even tell you the best round to deploy it across your horizon."

---

## 6. H2H — settle a single decision (12:00–12:45)

`[SHOW]` H2H tab. Pick two drivers (e.g. your captain candidates). Show the win probability + comparison.

`[SAY]`
> "Stuck between two picks for one slot — or deciding who to captain? Head-to-Head puts any two drivers or constructors side by side and gives you a straight **win probability**: how often one outscores the other across the simulations. Plus the supporting stats — quali, race, overtakes — and a recommendation. This is the fastest way to settle a single 'who do I pick?' argument with yourself."

💡 **PRO TIP:** "The win probability comes from the *overlap of the two distributions*, not just comparing two averages. So if one driver has a slightly lower average but a much safer range, H2H can — correctly — still favour them for a must-not-blank slot."

---

## 7. Accuracy — why you can trust any of this (12:45–14:00)

This section builds credibility. Don't skip it — it's what separates your tool from "some guy's predictions."

`[SHOW]` Accuracy tab. Show per-round MAE, the scatter plot, the CI-coverage numbers. Toggle Drivers/Constructors. Toggle the phase buttons.

`[SAY]`
> "Now the tab that proves I'm not just making numbers up: **Accuracy.** After every race, we score our own predictions against what actually happened, and publish it — warts and all.
>
> This is the average error per round. This scatter is predicted versus actual. And this is the one I care about most: **confidence-interval coverage.** Remember those 90% bands on the driver cards? This checks whether reality actually lands inside them about 90% of the time. If it does, the uncertainty is *honest* — when the site says it's unsure, it's genuinely unsure, and when it's confident, you can lean in.
>
> This **phase toggle** is a neat trick: it shows what we predicted *before* practice, versus *after* practice, versus *after* qualifying — so you can literally see the forecast sharpen as the weekend unfolds."

`[SHOW]` Point at the model-version note about R7→R8.

`[SAY]`
> "And if you ever see a sudden jump in accuracy between two rounds, that's usually a model upgrade landing — the note here and the Changelog tab will tell you exactly what changed. I publish the misses too, because a tool that only shows its wins is a tool you shouldn't trust."

💡 **PRO TIP (credibility soundbite):** "Most prediction tools never show you how wrong they were. This one has a whole tab for it. *That's* the reason to trust the other tabs."

---

## 8. Season — manage your budget like an asset (14:00–14:45)

`[SHOW]` Season tab. Scroll through championship standings, fantasy standings, the driver and constructor price trackers.

`[SAY]`
> "The Season tab is your big-picture view: the real championship standings, the cumulative fantasy standings, and — the part that actually affects your strategy — the **price trackers.** Every driver and constructor, starting price versus current price, who's trending up, who's bleeding value.
>
> Treat your team like a portfolio. If a driver you own is sliding in price every week, you're losing budget whether they score or not. The price tracker plus the Budget Builder strategy in the optimizer is how you stay ahead of that — buy risers early, sell faders before the drop."

💡 **PRO TIP:** "Sometimes the smart move is to hold a *poor* performer one extra round — if they're about to cross a price-drop threshold, holding lets you sell at the better price instead of crystallising the loss. The price brackets on the driver cards tell you when you're near a line."

---

## 9. Analysis & Race Deep Dive — for the data nerds (14:45–15:45)

`[SHOW]` Analysis tab → Free Practice panel, then Post-Race panel. Then the Race Deep Dive tab with a round selected.

`[SAY]`
> "Two tabs for people who like to look under the hood. **Analysis** has free-practice pace breakdowns — useful on a Friday or Saturday to see who's actually quick before you commit — and a post-race panel.
>
> **Race Deep Dive** is the full post-race telemetry treatment: fuel-corrected pace so you can compare a heavy car early in a stint to a light one late, stint-by-stint tyre analysis, sector pace, and the real pit-stop times that feed the constructor scoring. If you want to *understand* why a driver scored what they did — not just trust the number — this is where you go."

💡 **PRO TIP:** "Check FP pace in the Analysis tab before locking your team on a Saturday. If a driver the model still rates is suddenly dead last in long-run pace, that's your cue to use the plus-minus slider — or just fade them."

---

## 10. The quick tabs — Changelog, Videos, Articles, About (15:45–16:30)

`[SHOW]` Click quickly through Changelog, Videos, Articles, About.

`[SAY]`
> "Four more, quickly:
> - **Changelog** — every meaningful change to the model or the site, in plain English. If a prediction shifts and you want to know why, it's documented here. I even document the changes I *reverted* — there's an entry this week about a bug I shipped and then pulled.
> - **Videos** — curated F1 content for the weekend. (Subscribe button's right there, hint hint.)
> - **Articles** — data-driven previews and reviews for each round.
> - **About** — how it all works, the data sources, the known limitations, and — if the site's saved you from a bad transfer — a coffee button. It's free and it stays free; tips just cover the hosting and the 2 a.m. model retrains."

---

## 11. Quirks & gotchas — "that's working as intended" (16:30–18:00)

This section is gold for retention — it pre-empts the exact things that make new users think the site is broken. Frame every one as "this looks weird, here's why it's right."

`[SHOW]` The About tab's "Known Limitations & Quirks" list. Hit the big ones on screen.

`[SAY]`
> "Let me save you some confusion — a few things look like bugs and aren't:
>
> **The calendar skips Round 4 and Round 5.** Bahrain and Saudi were cancelled in 2026, but I kept their round numbers so nothing shifts. So Miami is Round 6, Canada is 7, Monaco is 8 — Rounds 4 and 5 just aren't there. Not a glitch.
>
> **Wide confidence intervals are honest, not noisy.** A range of '8 to 53 points' reflects real F1 chaos — a midfielder genuinely *could* score either. The model says so instead of faking precision.
>
> **Predictions shift across the weekend.** Pre-practice it's running on history — about 65% confidence. Once practice data lands it sharpens to ~90%. After qualifying the grid is locked and it tightens again. If a driver moves between Friday and Sunday, that's the model learning, not flip-flopping.
>
> **Monaco scores look low — that's real.** Almost no overtakes means almost no overtake points for the whole field. A low-scoring weekend on this site usually means a genuinely low-scoring track.
>
> **New teams play it safe.** Cadillac has no history to learn from, so their numbers sit near grid-average until 2026 results pile up. Same for rookies. Lower confidence early is correct, not lazy.
>
> **Sprint weekends are slightly fuzzier.** One practice session instead of three means less data and wider bands. Expected."

💡 **PRO TIP:** "If something on the site surprises you, check the **Changelog** and the **About → Quirks** list before assuming it's wrong. Nine times out of ten it's documented and intentional — and the tenth time, there's a contact link, so tell me."

---

## 12. My weekly routine — put it all together (18:00–20:00)

**This is the most valuable section in the whole video.** Everything above was "what the buttons do." This is "here's exactly how I use it to win." Make it concrete and repeatable.

`[SHOW]` Walk the actual flow on screen as you narrate each step.

`[SAY]`
> "Okay — let me show you exactly how I use this every weekend, start to finish. Steal this routine.
>
> **Early in the week — Monday to Thursday.** Predictions are up early, on history alone. I open the **Multi-Week Planner**, set it to three rounds, and look at the heatmap. I'm not transferring yet — I'm spotting which races are coming and whether I should *bank* this week's transfer for a bigger move later. If I have a dream team in mind, I switch on Target mode and check the feasibility card.
>
> **Friday or Saturday, after practice.** This is the big one. Confidence jumps to ~90% once practice data lands. I check the **Analysis** tab for free-practice pace — anyone surprisingly fast or slow? Then I go to the **Transfer Advisor**, lock the drivers I'm keeping, and find my best one or two moves. I read the efficiency line religiously — if an extra transfer doesn't clear the minus-ten hit, I don't take it.
>
> **The deadline is the start of qualifying — don't miss it.** There's a lock-deadline countdown right in the header. Get your team in before it hits zero.
>
> **Before I finalise, two sanity checks.** I open **H2H** for any 50-50 slot or captain call. And I glance at the **weather** widget — if it's wet, I lean on safer picks or cap my downside with a chip.
>
> **After the race.** I check the **Accuracy** tab to see how the model — and honestly, *I* — did, and the **Race Deep Dive** if I want to understand a result. Then I look at the **price trackers** on the Season tab to plan next week's budget.
>
> That's it. Maybe fifteen minutes across the week, and you're making every decision with data instead of vibes."

💡 **PRO TIP (the thesis of the whole video):** "You don't have to use every feature every week. The winning habit is just this: **check practice pace, run the Transfer Advisor, respect the efficiency line, and don't chase points that don't beat the penalty.** Everything else is upside."

---

## 13. Outro / CTA (20:00–20:45)

`[SHOW]` Back to the homepage. Logo. Social/support links.

`[SAY]`
> "So that's the whole site. To recap the winning habits: build on **value**, not just big names. Plan **transfers ahead**, don't react week to week. **Time your chips** for the weekends that suit them. Trust the **wide bands** — they're honest. And always check whether an extra transfer actually beats the minus-ten.
>
> It's all free, there's no login, no paywall — I built it because I wanted it to exist. If it helps you climb your league, the best thanks is to **subscribe** so I can keep making these, drop your toughest fantasy decision in the comments and I'll run it on the site, and if you're feeling generous there's a coffee link in the description.
>
> Good luck this weekend — go win your league. See you at the next race."

`[SHOW]` End card: site URL, subscribe button, "links in description."

---

## The One-Page Cheat Sheet

*(Use this as the video description, a pinned comment, or a community post.)*

**Where the numbers come from:** real F1 data → ML predicts quali & race → **10,000 race simulations** → official 2026 scoring. Every card is the *average* of 10,000 simulated races, plus the range.

**Reading a driver card:**
- Big number = predicted points (already includes everything).
- The range (90% CI) = where they land in 90% of simulations. **Wide = gamble, narrow = safe. Wide is honest, not broken.**
- Confidence: ~65% = history only (early), ~90% = practice data in, ~95% = post-qualifying.

**The habits that win:**
1. **Sort by PPM** to find underpriced value — build around it.
2. **Don't ignore constructors** — pit stops + the both-in-Q3 bonus are free, low-variance points.
3. **Lock your keepers** before running the Transfer Advisor.
4. **Respect the efficiency line** — never take a −10 transfer that doesn't clearly beat it.
5. **Plan ahead** with the Multi-Week Planner when you have 3+ transfers banked; it'll tell you when to *bank*.
6. **Build budget early** (Budget Builder strategy) — value compounds over the first 6–8 rounds.
7. **Time chips** to the weekend that suits them (see the chip table).
8. **Check FP pace** (Analysis tab) on Saturday before you lock.
9. **The Accuracy tab** is your reality check — read it before betting big.

**Clicks people miss:**
- **Left-click** a card = lock. **Right-click** = exclude. Carries into the optimizer.
- The **±** button = dial your own pace bump when you know better than the model.

**"Is this broken?" — no, it's intended:**
- Calendar skips R4 (Bahrain) & R5 (Saudi) — both cancelled, numbers preserved.
- Predictions shift Fri→Sun as data arrives.
- Monaco-type tracks score low for everyone (no overtakes).
- New teams (Cadillac) & rookies play conservative until 2026 data builds.

**The deadline:** F1 Fantasy locks at the **start of qualifying** (or sprint qualifying on sprint weekends). The countdown is in the site header.

**Chips quick guide:** Limitless = load up over budget · 3x Boost = one nailed-on big scorer · Wild Card = full rebuild · No Negative = chaos/wet insurance · Autopilot = auto-boost insurance · Final Fix = react to the grid post-quali.

---

*Companion docs: [USER_GUIDE.md](USER_GUIDE.md) (feature reference) · [TECHNICAL_DEEP_DIVE.md](TECHNICAL_DEEP_DIVE.md) (how the model works) · [OPERATIONS_GUIDE.md](OPERATIONS_GUIDE.md) (running the pipeline) · [SYSTEM_DIAGRAM.md](SYSTEM_DIAGRAM.md) (visual diagrams).*
