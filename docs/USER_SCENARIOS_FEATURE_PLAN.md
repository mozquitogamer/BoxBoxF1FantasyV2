# User-Facing "What-If Scenarios" Feature — Implementation Plan

**Status:** **Phase 1 shipped 2026-05-25** (commit `aa15acf`). Phases 2-5 deferred until traction is proven.

**What shipped:**
- Per-card ± slider opening a mini popup (driver and constructor cards)
- Floating purple header pill showing active bump count with Manage / Reset
- Full manager modal with per-team master sliders, share-via-URL, reset all
- Round-scoped LocalStorage; auto-clears on round change
- `scenarios.js` overlay re-ranks XGBRanker raw scores and applies position-points/positions-gained deltas (mirrors `pipeline/apply_upgrades.py`)
- `predictions.json` now ships `raw_scores` per driver + per-round `score_unit` adjacent-gap median so the JS can convert positions → raw bumps
- Reuses existing `.upgrade-delta` badge UI so the visual layer was free

**What didn't ship (deferred):**
- Phase 2: optimizer + transfer advisor + multi-week planner consulting scenario state (still use baseline). The infrastructure is in place; integration is a follow-up.
- Phase 3: compare-two-scenarios side-by-side, MC band overlay, suggest-a-bump hints
- Phase 4: Premium tier with backend (would need auth + payments — defer until usage proven)
- Phase 5: Smarter math (heuristic FL adjustments, track-record-conditional bumps, accuracy calibration)

**Approval history:** Approved 2026-05-22 to build during the next post-race break (after R7 Canada).

**TL;DR:** Visitors to the public site can tweak per-driver and per-team pace bumps in their own browser to see how predicted points and lineups change. The base ML prediction stays untouched as the canonical view; the user's scenario is a transparent overlay alongside it. All client-side, no backend required. Persists per-user via LocalStorage; shareable via URL.

This builds directly on the server-side admin feature shipped in commit `6523904` (the dashboard's Team Upgrades page + `pipeline/apply_upgrades.py`). The math is the same — just runs in JS on the user's device instead of Python on the admin's machine.

---

## Core architectural decision

**Client-side overlay** rather than server re-inference.

| Path | Verdict |
|---|---|
| Server-side re-inference (Vercel function / Lambda) | ❌ XGBoost in serverless is painful, every slider drag is a network round-trip, adds infra cost |
| Client-side overlay in JS | ✅ Instant feedback, scales infinitely, no infra, matches the static-site architecture |

The site already does fantasy points math in JS (optimizer, transfer advisor, multi-week planner). The scenario overlay is a natural extension.

---

## What a pace bump should affect (and what it shouldn't)

| Component | Adjusted? | How |
|---|---|---|
| Predicted quali position | ✅ Yes | Add bump to `predicted_quali_raw`, re-rank in JS |
| Predicted race position | ✅ Yes | Same, on `predicted_race_raw` |
| Predicted sprint position | ✅ Yes | Same |
| Position points (quali/race/sprint) | ✅ Yes | Look up in `RACE_POSITION_POINTS` table after re-rank |
| Positions gained/lost & overtakes | ✅ Yes | Driver gains/loses positions vs grid — directly observable from the re-rank |
| Constructor expected points | ✅ Yes | Sum the new driver points (skip rare quali-tier bonus flip — document approximation) |
| Fastest lap probability | ⚠️ Heuristic | Scale by pace bump: `fl_prob *= 1 + 0.5 * pace_bump`. Mark as approximate. |
| DOTD probability | ❌ Don't adjust | DOTD is about story, not pace |
| DNF probability | ❌ Don't adjust | Reliability is independent of pace |
| MC confidence intervals (P5/P95) | ⚠️ Mean-shift only | Shift the band by the points delta, keep width. Show baseline MC alongside adjusted point estimate so users see both. |

User-facing copy must make this clear: **"This is your what-if. MC bands reflect the model's view; adjusted points are your overlay."**

---

## Data model

Per user (LocalStorage; optionally URL-encoded for sharing):

```js
{
  scenarioName: "Canada upgrade fight",
  round: 7,                                       // tied to a round so it doesn't bleed
  driverModifiers: { "VER": 0.3, "HAM": -0.1 },   // raw-score units
  teamModifiers:   { "mercedes": 0.5, "mclaren": 0.3 },
  inputUnit: "positions"                          // UI surface unit; see below
}
```

Effective bump per driver = `teamModifiers[driver.team] + driverModifiers[driver.id]`. Both default to 0. Composable.

---

## UI surface unit

Pick **positions gained** (-5 to +5 in steps of 0.5).

Most intuitive ("Verstappen will gain 2 spots at Red Bull Ring"). Internally converted to raw-score units using the round's actual adjacent-gap distribution (median ~0.14 for Canada R7, varies per round). Tooltip shows the raw-score equivalent for transparency.

Per-round adjacent-gap median should be exported into the public JSON so the conversion is data-driven.

---

## UI placement — hybrid approach

1. **Per-card "±" icon** on each driver/constructor card opens a mini-popup with a positions-gained slider for that pick. Low-friction, contextual.
2. **Floating header pill** showing `Scenario: N modifiers · Reset` when any modifiers are active. Click expands a modal with:
   - Full list of active modifiers
   - Save/Load named presets
   - Share URL button
   - Master slider in "Per-team" mode for bulk team-level bumps
   - Reset all

The existing delta-badge UI (the dashed `+X.X` next to the points-badge) handles the visual layer for free — just point it at scenario state instead of the server's `adjustments.json`.

---

## Phased implementation plan

### Phase 1 — Foundation (~10–15 hours, one weekend)

- Ensure `predicted_*_raw` fields are in the public JSON (already present — verified in commit `6523904`)
- Export per-round adjacent-gap median into the JSON for unit conversion
- New `web/public/scenarios.js` module:
  - `currentScenario` state in LocalStorage
  - `applyScenarioToDriver(d)` returns overlaid driver object
  - `applyScenarioToConstructor(c)` returns overlaid constructor object
  - Hooks driver/constructor card renderers to consult these before display
- Reuse existing delta-badge UI for the visual overlay
- Per-card "±" icon → popup with positions-gained slider
- Header pill + scenario manager modal

**Acceptance criteria:** User can open the site, click "±" on Verstappen, drag a slider, see VER's predicted finish and expected points change in real time. Refresh the page → scenario persists. Click Reset → returns to baseline.

### Phase 2 — Optimizer & planner integration (~10 hours, one weekend)

- Lineup Optimizer, Transfer Advisor, Multi-Week Planner all consult scenario state when scoring
- Visual badge on optimizer results: "based on your scenario"
- Save/Load named scenarios in LocalStorage (up to N saved scenarios)
- Share-via-URL: base64-encode state into `?scenario=...`

**Acceptance criteria:** User bumps Mercedes +1 position → optimizer's "Max Points" lineup shifts to include Antonelli/Russell. Click "Share" → copies a URL. Open URL in incognito → same scenario loaded.

### Phase 3 — Polish + nice-to-haves (~10 hours, one weekend)

- Compare two scenarios side-by-side ("Mercedes upgrade lands" vs "Mercedes upgrade flops")
- MC band overlay: model's CI in faded color, adjusted point as a new marker on top
- "Reset to my last saved scenario" / "Reset to neutral" buttons
- Suggest-a-bump hint based on FP signal: "Mercedes were 0.2s/lap faster than expected in FP2 — apply +0.5?"

### Phase 4 — Premium (defer until traction proven)

This needs a backend. Significant operational complexity (auth, billing, support).

- Supabase / Clerk for auth, Stripe for payments
- Free tier: 1 active modifier, no presets, no sharing
- Premium ($X/month): unlimited modifiers, cloud-saved presets synced across devices, shareable URLs with rich preview cards, "this user's scenarios accuracy" leaderboard
- **Don't start until Phases 1–3 prove user demand.**

### Phase 5 — Smarter math (optional)

- Heuristic adjustments to fastest-lap probability
- Track-record-conditional bumps ("for VER at Red Bull Ring, historical performance suggests +0.X")
- Accuracy calibration: track whether users who tweaked X were right after the race (anonymous, opt-in)

---

## Risks and mitigations

| Risk | Mitigation |
|---|---|
| Users confuse "my scenario" with "the model's prediction" | Big colored banner when scenario is active. Adjusted numbers shown alongside (not replacing) baseline. Existing delta badges. |
| JS overlay drifts from `apply_upgrades.py` logic | Extract position-points constants + bump-application math into a shared spec file. Both implementations consume it. Add a regression test that exercises a known input through both paths. |
| Constructor scoring's quali bonus tiers not recomputed | Documented approximation: "Constructor Q3 / Q2 bonuses are NOT recomputed. Bumps affect only position points." Bonus-flip is rare. |
| Free tier feels too restrictive → users bounce | Phases 1–3 ship with NO gating. Only add premium gating once feature has traction. |
| Optimizer × scenario = slow | Overlay is O(1) per driver lookup. Negligible. |
| Mobile slider UX | Larger touch targets, snap to half-position values, "+/-1 spot" buttons alongside the slider. |

---

## One-evening proof-of-concept (smallest viable thing)

If we want to validate the idea before committing to Phase 1:

- Single per-driver slider on the existing driver cards
- No scenario manager, no team-level modifiers, no sharing
- LocalStorage persistence
- The existing delta-badge renders the tweak

Ship it, see if anyone uses it, then build the rest.

---

## Open question to revisit when starting work

**Round-specific or persistent across rounds?**

- **Round-specific** *(recommended)*: when a new race weekend starts, scenarios reset. More honest — pace bumps don't transfer between Monaco and Spa.
- **Persistent**: "VER is +0.5 stronger" survives round changes. Risk: user forgets, gets confused weeks later.

Pick: round-specific by default, with an explicit "carry to next round" button if user opts in. Stale scenarios auto-cleared when page detects a round change.

---

## Where this builds from

- Server-side dashboard feature: `dashboard/app.py::page_team_upgrades` + `pipeline/apply_upgrades.py` (commit `6523904`)
- Existing client-side fantasy math: `web/public/app.js` — optimizer, transfer advisor, multi-week planner
- Existing delta-badge UI: `.upgrade-delta` in `styles.css`, rendered in `driverCard()` / `constructorCard()` when `expected_points_adjusted` is present
- Pipeline JSON output: `08_export_website_json.py` already emits `predicted_quali_raw` / `predicted_race_raw` / `predicted_sprint_raw` — needed for client-side re-ranking

Most plumbing exists. The scenario overlay layer is the new piece.
