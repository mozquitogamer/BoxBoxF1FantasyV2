# PROMPT — BoxBoxF1Fantasy scoring-correctness fix bundle (2026-07-02)

Copy everything below this line into Claude Code (Opus 4.8) as the task prompt.

---

You are working in the BoxBoxF1Fantasy repo (`D:\OneDrive\BoxBoxF1FantasyV2`). Read `CLAUDE.md`
first, then read `docs/CODE_REVIEW_2026-07-02_FINDINGS.md` — it is the findings record this plan
executes. A full code review on 2026-07-02 cross-validated our computed actual fantasy points
against the manually-entered official F1 Fantasy points for all 10 completed rounds and found a
set of exactly-diagnosed scoring bugs. Your job is to fix them in the phased order below, with the
validation gates specified per phase. Do not skip gates. Do not reorder phases (later phases
depend on earlier ones).

## Ground rules (read carefully, these override convenience)

1. **Never modify or regenerate archived FORECASTS.** `web/public/data/predictions_round{N}*.json`,
   `data/predictions/round{N}/predictions.parquet`, `monte_carlo_fantasy.*`, and
   `fantasy_points*.parquet` for COMPLETED rounds (1,2,3,6,7,8,9,10) are frozen pre-race
   predictions. Never run `06/07/08_monte_carlo/08_export` with `--force` on a completed round.
   ACTUALS (`11_actual_fantasy_points.py` outputs) are NOT forecasts — re-running 11 for completed
   rounds is exactly what this plan requires.
2. **Round numbering:** internal rounds 1-22 with R4/R5 cancelled. `overtakes.csv` uses COMPRESSED
   numbering (internal R10 = csv round 8, R9 = csv 7, R8 = csv 6, R7 = csv 5, R6 = csv 4).
   `official_fantasy_points.json`, `pitstop_points.json`, `dotd_winners.json` use INTERNAL rounds.
   R11 (Silverstone, 2026-07-05) is a SPRINT weekend and is the current live round.
3. Line numbers cited below are as of 2026-07-02 — treat them as hints, re-locate with Grep.
4. **Do not stage or commit `PFP2.png`** (untracked personal file).
5. Commit at the end of each phase with a descriptive message ending in the trailer:
   `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`. Do NOT push until the user says so.
6. When `web/public/app.js` changes, bump the cache version in `web/public/index.html`
   (`app.js?v=N` → `v=N+1`) in the same commit.
7. Out of scope for this bundle (do NOT do these even if tempting): MC vectorization, the
   modelling roadmap in the findings doc (backtest harness, grid-conditioned sampling, ensembling),
   `fastf1_round` generalization, app.js fetch parallelization. Stretch items (Phase 8) only after
   every earlier gate passes.
8. Python is run as `python` from the repo root. FastF1/network calls can be slow — be patient,
   don't kill long downloads prematurely.

---

## Phase 0 — Reconciliation tool + baseline snapshot

**Goal:** a permanent script that diffs our computed actuals against official points, used as the
acceptance gate for every later phase, plus a saved "before" snapshot proving improvement.

Create `pipeline/reconcile_official_points.py`:

- For every completed round (every key in `data/seed/official_fantasy_points.json::rounds` that has
  a matching `data/predictions/round{N}/actual_fantasy_points.json`):
  - Load official driver + constructor points, and our computed actuals.
  - Print a per-round table: `driver | ours | official | diff | is_dnf | status | overtakes(ours)`,
    only rows with |diff| > 0.01, sorted by |diff| desc. Same for constructors.
  - Print per-round summary: `n_drivers, n_exact (|diff|<=0.01), mean_diff, mean_abs_diff, max_abs_diff`.
- Print a season-level summary table (per round: n_exact/n, mean_abs_diff) and overall totals.
- `--json PATH` flag: dump the full diff structure to a JSON file.
- Exit code 0 always (it's a report, not a test runner).

Run it and save the baseline:

```
python pipeline/reconcile_official_points.py --json data/experiments/reconcile_baseline_2026-07-02.json
```

**Gate 0:** the baseline must reproduce the review's headline numbers (sanity check that the tool
is correct): R7 mean_diff ≈ −1.41 with max_abs 9 (NOR); R9 must show LEC −19, BEA −27, ALB +20;
R10 must show STR/SAI/PER/BOT at −3 each and VER at −10. If your baseline disagrees with these,
your reconciliation script has a bug (most likely ID mapping: our actuals key drivers by
abbreviation e.g. "VER"; official file also keys by abbreviation) — fix the script before
proceeding.

Commit: `Reconciliation tool + pre-fix baseline snapshot`.

---

## Phase 1 — Actuals scoring engine fixes (findings A1-A4)

All in `pipeline/11_actual_fantasy_points.py` unless noted.

### 1a. DNF = positionText, not status (A1 + A2)

In `parse_race_results` (~line 277-295): replace the status-list DNF detection with:

```python
# Jolpica: numeric positionText = CLASSIFIED (scored as a finisher, even if the
# car retired late — F1 classifies cars completing ~90% distance). "R" = retired
# unclassified (true DNF). "D" = disqualified. "W" = withdrawn/DNS.
is_dsq = position_text == "D" or status == "Disqualified"
is_dns = position_text == "W" or status == "Did not start" or laps == 0
is_dnf = (position_text == "R") and not is_dns
```

Delete the old status-tuple check AND the `if status == "Lapped": is_dnf = False` override
entirely (both are subsumed; the Lapped override is what mis-scored ALB R9). Classified
late-retirees now flow down the normal-finisher branch automatically because `is_dnf` is False and
their `position` is numeric — verify the finisher branch reads `r["position"]` (it does).

Apply the same rule in `parse_sprint_results` (~line 391-410).

Keep the DNS ordering: a `W` must never be counted as DNF.

### 1b. DNF drivers keep their overtake points (A3)

Official rule (proven exactly by R10: each retiree −17 = −20 + 3 csv overtakes): a retired driver
scores quali points + the −20 DNF penalty + overtake points for passes made before retiring.

In the driver loop's `elif r["is_dnf"]:` branch (~line 595): resolve overtakes for DNF drivers the
same way finishers do — from `detected_race_ot` (which is detected merged with the seed csv, seed
winning) — but with NO estimation fallback (a retiree with no recorded count gets 0; do NOT apply
the grid-bucket estimate to DNFs) and the telemetry cap rules from 1c. Then:

```python
race_pts = RACE_DNF_DSQ_PENALTY + overtakes * RACE_OVERTAKE_POINTS
```

(Or extend `calc_race_points_driver` in `config/fantasy_scoring.py` to accept overtakes in its DNF
branch — your choice, but keep 11 and the function consistent, and check no other caller breaks.
Callers: grep `calc_race_points_driver`.)

Also update the component-breakdown block (~line 701-706): DNF drivers must now show their
`overtake_pts` (not 0) so the sum of components equals the total. And the `overtake_source` field
(~line 739) must not exclude DNF drivers from "detected" anymore.

DSQ drivers: keep 0 overtakes (excluded from results officially). DNS: keep 0.

Apply the same credit in the sprint DNF branch (~line 660): `sprint_pts = SPRINT_DNF_DSQ_PENALTY +
sprint_overtakes` with sprint overtakes resolved from detected/seed (no estimation fallback, no cap
for seed values).

### 1c. Caps must not clip official csv values (A4)

Currently `MAX_RACE_OVERTAKES = 8` / `MAX_SPRINT_OVERTAKES = 5` clip the merged dict, destroying
user-entered official counts (VER R6: 20→8; HAM R10: 11→8). Fix: track WHICH source each driver's
count came from. `load_seed_overtakes` returns the csv dicts — keep them separate (e.g. return
both, or build a `seed_covered: set[str]`). Rule:

- count from `overtakes.csv` → use verbatim, no cap;
- count from telemetry detection only → cap as before (8 race / 5 sprint);
- estimation fallback (finishers only) → cap as before.

### 1d. Stale estimation-fallback bases (A4, second half)

11's race fallback bases `{≤3:2, ≤6:4, ≤12:6, ≥13:7}` and sprint bases `{1,2,3,4}` predate the
2026-06-28 retune. Align them with 07: race `{≤3:6, ≤6:4, ≤12:4, ≥13:2}` + `positions_gained`
(not `gains−1`), sprint `{2,2,3,2}` + gains. (These only fire for rounds/drivers absent from the
csv, but they should not silently contradict 07.)

**Gate 1 (unit-level, before regenerating anything):** run 11 for round 9 only
(`python pipeline/11_actual_fantasy_points.py --round 9`) then
`python pipeline/reconcile_official_points.py` and check round 9:

| driver | expected ours after fix | mechanism |
|---|---|---|
| LEC | 0 (== official) | classified P15: 7 − 11 + 4 OT |
| ANT | −4 | classified P16: 8 − 13 + 1 OT |
| BEA | 7 | classified P17 (grid 15): 0 − 2 + 9 OT |
| ALB | −16 | posText=R despite 'Lapped': 4 − 20 + 0 OT (csv ALB R9=4 → −12; if you get −12 and official is −16, ALB's 4 csv overtakes belong to a round-numbering error — STOP and re-check the compressed-round join before continuing) |
| HUL | −15 | −20 + 3 OT, quali +2 |
| ALO | −17 | −20 + 3 OT |
| BOT | −18 | −20 + 2 OT |

Every R9 driver must now match official exactly EXCEPT HAM (−10, fixed in Phase 2). If ALB lands
on −12 instead of −16: official credited him 0 overtakes (Jolpica/official may not credit passes
for unclassified cars in all cases) — in that case flag it, set the rule to "csv overtakes apply
to DNFs verbatim" anyway, and record ALB as a ±4 documented residual. Do not fabricate a special
case without evidence from a second driver.

Commit: `Actuals scoring: classification-aware DNF, retiree overtake credit, uncapped official counts`.

---

## Phase 2 — Seed data + raw refresh (A5, A6)

### 2a. DOTD winners

Edit `data/seed/dotd_winners.json`, add: `"3": "PIA"`, `"6": "VER"`, `"9": "HAM"`, `"10": "VER"`.
(Each proven by an exact −10 diff; R6 VER additionally decomposes as −10 DOTD − 12 capped
overtakes = −22 observed.) Leave `"8": "ANT"` alone — ANT's R8 total already matches official
including the +10, so the seed is right.

### 2b. Loud DOTD warning

In 11's main flow: if the round is completed and `load_dotd_winner(round_num)` returns None, print
a `!!!!!`-style banner (match the stale-price banner tone in `08_export_website_json.py`) telling
the user to update `dotd_winners.json`. This gap was silent for 4 rounds.

### 2c. R1 stale results (STR +25 anomaly)

Re-download R1's raw Jolpica data (check `pipeline/01_download_data.py --round 1` semantics first —
you want to refresh `data/raw/jolpica/year2026/round1/*.json` only; it must not touch prediction
outputs; if it resists overwriting, delete the round1 raw jolpica JSONs first and re-run). Then
inspect STR's entry in the new `results.json`. Expected: posText `D` (disqualified) or a changed
classification explaining official −23 (= quali −3? + −20). Whatever you find, the Phase 1 rules
should absorb it. If STR is unchanged (still a normal classified finisher), record the anomaly in
the findings doc as unresolved (possible official-app scoring anomaly) and move on — do NOT invent
a compensation.

Since raw results changed, rebuild the normalized layer + features so downstream stays coherent:
`python pipeline/03a_normalize_jolpica.py` then `python pipeline/03b_build_jolpica_features.py`
then `python pipeline/04_build_model_inputs.py`. Do NOT retrain models (out of scope; the next
scheduled retrain picks it up).

Commit: `Seed: DOTD winners R3/R6/R9/R10 + missing-DOTD warning + R1 raw refresh`.

---

## Phase 3 — Regenerate all actuals + web sync + season gate

For each completed round: `python pipeline/11_actual_fantasy_points.py --round N` for
N in 1, 2, 3, 6, 7, 8, 9, 10. (R2/R6/R7 are sprint rounds — the script handles that itself.)

Then sync the corrected actuals to the website data dir. Read how
`08_export_website_json.py::copy_analysis_files` publishes `actual_round{N}.json` and reuse that
exact code path (small driver script or function call per round is fine) — do NOT hand-roll a
different JSON shape. Then run the full export for the CURRENT round only:
`python pipeline/08_export_website_json.py --round 11` — this rebuilds `season_summary.json` and
`driver_history.json` from the corrected actuals and re-syncs seed files. It must NOT rewrite any
`predictions_round{N}` archive for completed rounds (the guards handle this; just don't pass
`--force`).

**Gate 3 (season-level acceptance):** `python pipeline/reconcile_official_points.py --json
data/experiments/reconcile_postfix_2026-07-02.json` and require:

- R9: all 22 drivers exact (HAM now matches via DOTD).
- R10: all 22 exact (VER via DOTD, HAM via uncapped 11 OT, retirees via −20+OT).
- R6: VER exact at 52. R3: PIA exact at 43, STR −17 exact, BEA −14 exact (classified/OT per rules).
- Season overall: **≥ 90% of driver-rounds exact; mean_abs_diff ≤ 0.5**; every remaining mismatch
  belongs to the documented-residual list (R8 Monaco cluster, R2 sprint residuals + ALB DNS,
  R1 STR if unresolved, R7 HAD). List each survivor explicitly in your report — no unexplained
  mismatches allowed.
- Constructors: recompute and report the same stats. Constructor totals inherit the driver fixes +
  already-official pit points, so expect a large improvement; any constructor mismatch must trace
  to a surviving driver residual or the quali-bonus (fixed in Phase 4 — note B1 affects
  PREDICTIONS only; actual constructor bonuses come from real Q1/Q2/Q3 times and are already
  correct).

Also confirm `web/public/data/driver_history.json` changed (spot-check: LEC's R9 entry should now
be 0, not −19).

Commit: `Regenerate actuals R1-R10 against corrected scoring + web sync`.

---

## Phase 4 — Prediction-side fixes (B1-B4)

### 4a. Q2 cutoff 15 → 16 (B1)

2026 has 22 cars; Q1 eliminates 6 (P17-22), Q2 eliminates 6 (P11-16), Q3 = top 10. Verified: R3
and R9 raw qualifying each contain exactly 16 drivers with Q2 times.

- `pipeline/07_calculate_fantasy.py` (~line 557): session mapping becomes
  `Q3 if pos <= 10 else Q2 if pos <= 16 else Q1`.
- `pipeline/08_monte_carlo_fantasy.py` per-sim constructor bonus (~line 1464):
  `both_q2/one_q2` thresholds `<= 15` → `<= 16`.
- Same file, fallback `q_tier_probs` (~line 1538): shift the Q2 ramp by one position
  (`(17 - mean_pos) / 5` → `(18 - mean_pos) / 5`).
- Grep the whole repo for other `<= 15` / `15` quali-session boundaries (including `app.js`) —
  fix any you find, report any you deliberately leave.

Validation: quick REPL check — driver positions (11, 16) must now yield the both-Q2 bonus (+3, was
+1); (16, 17) yields one-Q2 (+1, was −1).

### 4b. Remove phantom sprint-quali points (B2)

Official F1 Fantasy does not score sprint-quali position (proven: our actuals scorer never awards
it and matches official). Changes:

- `07_calculate_fantasy.py`: stop adding `sprint_quali_pts` into `total_pts`. Set
  `expected_sprint_quali_pts` to 0.0 (keep the column for schema compatibility) and keep
  `predicted_sprint_quali_position` (it's the sprint GRID — still needed).
- `08_export_website_json.py` (~lines 300, 398): the exported `expected_points_sprint_quali` will
  now be 0 — leave the field for backward compatibility.
- `web/public/app.js` driver card breakdown (~lines 1469, 1481, 1530): remove the "SQ" segment and
  legend entry entirely (don't render a 0-width segment). Check `hasSprintPts` logic still shows
  the sprint-RACE segment. Bump the cache version in `index.html`.
- `CLAUDE.md`: fix the Fantasy Scoring section ("Sprint weekends add sprint qualifying + sprint
  race..." → sprint race only) so future sessions don't reintroduce it.

### 4c. Sprint DNF consistency (B3)

In 07's sprint block: use `sprint_dnf_prob = dnf_prob * 0.5` (matching the MC's
`dnf_probs * 0.5`), i.e. `(1 - sprint_dnf_prob) * (...) + sprint_dnf_prob * SPRINT_DNF_DSQ_PENALTY`.
Add a one-line comment cross-referencing the MC constant so they stay in sync.

### 4d. MC sprint grid (B4)

- `06_run_predictions.py` sprint block: it already computes `sprint_grid_loaded` (bool). Persist it:
  `pred_df["sprint_grid_is_actual"] = sprint_grid_loaded`, and make sure `sprint_grid` +
  `sprint_grid_is_actual` + `predicted_sprint_quali_position` are in `output_cols` for sprint
  weekends.
- `08_monte_carlo_fantasy.py`: in the sprint sim (~line 1202-1222) and the per-driver points call
  (~line 1241): when `sprint_grid_is_actual` is true for the round, use the FIXED actual
  `predicted_sprint_quali_position` values as the sprint grid every sim (both for
  `sample_overtakes(grid=...)` and `sprint_grid=` in the points calc) instead of the sampled
  Sunday-quali positions. When the flag is false/absent (pre-SQ or old parquets), keep current
  behavior (sampled quali as proxy) — that's the correct uncertainty model pre-SQ.

Validation for 4b-4d comes in Phase 6's R11 regeneration (deterministic-vs-MC agreement gate).

Commit: `Prediction scoring: Q2=16 cutoff, drop phantom SQ points, sprint DNF + grid consistency`.

---

## Phase 5 — 07 consistency extras (B5, B6, C4, C5, C6)

### 5a. FL/DOTD field normalization (B5)

In `07_calculate_fantasy.py`: after assigning per-driver raw `fl_prob` / `dotd_prob`, normalize
each so the field sums to 1.0. For DOTD with manual overrides: overrides keep their exact value;
scale only the non-overridden drivers to sum to `1 − Σ(overrides)` (floor at 0 if overrides ≥ 1).
This requires a small restructure (two passes over the predictions frame — compute raw probs
first, normalize, then build rows). Keep displayed `fastest_lap_probability` / `dotd_probability`
as the NORMALIZED values so cards stay honest.

Validation: assert in the run log `sum(fl_prob) == 1.0 ± 1e-6` and same for DOTD; a P1-predicted
driver should land around fl_prob ≈ 0.15 (0.20/1.34).

### 5b. PPM from real points (B6 + D2)

Rewrite `load_recent_fantasy_points` to a single pre-computed lookup (build once per run, not per
driver): for each of the last 3 completed rounds before `current_round`, resolve each driver's
points as: official (`data/seed/official_fantasy_points.json`) → else computed actuals
(`data/predictions/round{N}/actual_fantasy_points.json`) → else our archived predicted total
(current behavior, last resort). Cache the per-round loads in a dict.

### 5c-5e. Small ones

- `load_dnf_causes` (config/settings.py): print a warning when an abbrev has no mapping in
  `driver_ids.json` instead of silently passing it through (C4).
- 07 constructor block: replace the hardcoded `0.6` with `DNF_EXPECTED_PENALTY_FACTOR` (C5).
- 08 MC: accumulate the constructor quali bonus in its own array during the sim and report its
  true mean as `quali_bonus` instead of deriving it by subtraction (which is currently
  contaminated by the DOTD adjustment) (C6).
- 07 driver DNF term: add the expected retiree overtake credit so the deterministic expectation
  matches the corrected official rule: `dnf_prob * (soft_dnf_penalty + RETIREE_OT_MEAN)` where
  `RETIREE_OT_MEAN` is computed in Phase 6a (~3.0; define it as a named constant with a comment
  citing the source data).

Commit: `07/08 consistency: normalized FL/DOTD, real-points PPM, DNF overtake credit, misc`.

---

## Phase 6 — Recalibration + R11 regeneration + frontend

### 6a. Re-fit MC_DNF_SEVERITY (and define RETIREE_OT_MEAN)

The current severity distribution (mean 1.0, std 0.30, clip [0.3, 1.7]) was fitted against BIASED
actuals (retiree overtakes zeroed, classified retirees counted as DNFs). Recompute from corrected
data:

1. From the corrected actuals + official points, collect all TRUE DNF driver-rounds
   (posText == "R") across R1-R10.
2. For each: `race_component = official_total − quali_pts(ours, corrected) − sprint_pts(ours,
   corrected)`; `overtake_credit = overtakes(csv)`;
   `severity_i = −(race_component − overtake_credit) / 20`.
3. Report the distribution (mean/std/min/max, n≈25-30). Expectation from spot checks: mean very
   close to 1.0 (R10 retirees are exactly 1.0), std well under 0.30.
4. Set `MC_DNF_SEVERITY` mean/std to the fitted values (round to 2dp), narrow the clip range
   accordingly, and set `RETIREE_OT_MEAN` (Phase 5e) to the observed retiree mean overtake count.
5. In the MC's DNF branch (`calc_driver_fantasy_points_sim`), add the pre-retirement overtake
   credit: a DNF'd driver's race points become `RACE_DNF_DSQ_PENALTY * severity +
   round(max(0, rng-sampled overtakes ~ N(RETIREE_OT_MEAN, RETIREE_OT_STD)))` — use the fitted
   std; wire the sampled value through so `mc_overtakes_mean` stays honest (retirees no longer
   forced to 0). Keep the structure minimal — no new tunables beyond mean/std.
6. Document old→new values in the commit message.

### 6b. Recalibrate MC noise

`python pipeline/calibrate_confidence.py` (it measures MC intervals vs actuals, which just
changed). Report the noise multiplier + coverage before/after. If coverage_90 lands outside
[85%, 95%], say so loudly in your final report — do not hand-tune anything else to force it.

### 6c. Regenerate the live round (R11)

R11 has NOT happened (race 2026-07-05) — regenerating its forecast is legitimate and required so
the live site reflects every fix. Run the phase that matches the data state at execution time:

- Before FP1 (Fri 2026-07-03): `python pipeline/run_weekend.py --phase pre_fp_predict --round 11`
- After FP1 / SQ exist on disk: use `--phase post_fp` instead (check
  `data/processed/features/round11/` and what `run_weekend.py` detects).

Then verify `web/public/data/predictions.json`:
- `round == 11`; driver cards' breakdown fields contain NO sprint-quali component;
- deterministic `total_expected_fantasy_points` (07) vs `mc_total_mean` per driver: report the
  mean absolute gap. It should SHRINK vs the pre-fix R11 export (the SQ phantom alone was worth
  up to ~10 pts for front-runners). No hard threshold, but explain any driver with a gap > 8.
- constructor expected points for Haas/Audi/Cadillac should tick UP slightly vs the previous
  export (Q2=16 fix).

### 6d. Frontend + changelog + docs

- app.js SQ-segment removal was Phase 4b; confirm cache bump landed.
- Add a `web/public/data/changelog.json` entry (follow the existing entry schema/tags exactly —
  read a recent entry first; tag `fix`) explaining in plain English: official-rules reconciliation,
  classified-retiree scoring, retiree overtake credit, uncapped official overtake counts, DOTD
  backfill, Q2=16, SQ-points removal, and that historical actuals were regenerated (Accuracy tab
  history will shift slightly).
- Update `CLAUDE.md`: (a) sprint scoring description (no SQ points), (b) add a line to the
  post-race workflow checklist: "update dotd_winners.json (11 warns if missing)", (c) note the
  reconcile script as the post-race verification step.
- Update `docs/CODE_REVIEW_2026-07-02_FINDINGS.md`: tick `[x]` on everything fixed, fill in the
  resolution notes for investigations (A6/A7), keep unresolved residuals documented.

Commit: `MC DNF recalibration from corrected actuals + R11 regeneration + changelog`.

---

## Phase 7 — Final verification sweep

1. `python pipeline/reconcile_official_points.py` — paste the season summary table into your final
   report. Gates from Phase 3 must still hold.
2. Smoke the site data layer: run the local server (`python web/serve.py`) or a Node/JSON sanity
   script — whichever this repo already uses for smoke tests (check git log / scripts for the
   established pattern) — and confirm: predictions.json parses, driver cards data has no
   `expected_points_sprint_quali` > 0, actual_round9.json shows LEC 0.
3. `python -m py_compile` over every touched Python file.
4. `git status` — verify no forecast archives for completed rounds are modified
   (`git diff --stat` should show NO `predictions_round{1,2,3,6,7,8,9,10}` files, no
   `data/predictions/round{1..10}/predictions.parquet`, no `monte_carlo_fantasy` for those rounds).
   Changed actuals files ARE expected. If a forecast archive shows as modified, `git checkout` it
   and figure out which step touched it before proceeding.
5. Final report to the user: per-phase summary, the before/after reconciliation table
   (baseline vs postfix mean_abs_diff per round), the fitted severity numbers, surviving
   documented residuals, and anything you deliberately did not do. Ask the user before pushing.

## Phase 8 — Stretch (ONLY if all gates green and the user agrees)

- **C1 race-day guard:** check whether `data/seed/races.json` rows carry a start time; if yes,
  `is_race_completed` should treat a round as completed once `race_start_utc + 4h` has passed
  (keeps race-morning refreshes legal, closes the Sunday-evening window). If no time data, add a
  loud warning to 06/07/08 when running a prediction phase on race day itself. Validate: guard
  still False the morning before a 14:00 UTC race, True at 19:00 UTC same day.
- **C2 rookie stub rows:** in `06::build_live_priors`, after filtering to the current roster,
  synthesize an all-NaN-priors stub row (correct driver_id/constructor_id/season/round) for any
  roster driver missing entirely, with a warning. Validate by temporarily excluding a driver's
  history and confirming 22 prediction rows.

---

## Appendix — evidence tables (from the 2026-07-02 review; for reference, do not re-derive)

R7 diffs (ours − official): HAD −3, RUS −5, NOR −9, ALB −6, PER −4, ALO −4 (all retirees except
HAD; each gap = zeroed overtakes / sprint sourcing).
R9: HAM −10 (DOTD), HAD −1, ALB +20 (Lapped-override un-DNF), ANT −8 / LEC −19 / BEA −27
(classified retirees), HUL −3, ALO −3, BOT −2 (retiree overtakes).
R10: VER −10 (DOTD), HAM −3 (11 OT capped at 8), COL −1, OCO −1, STR/SAI/PER/BOT −3 each
(3 OT each, zeroed).
R6: VER −22 (= DOTD −10 + 20 OT capped at 8 → −12), RUS −5, LEC −4, GAS −5 / LAW −4 / HAD −1
(retirees), others −1..−3.
R3: PIA −10 (DOTD), STR −3, BEA −6 (retiree OT).
R2 (sprint): broad −1..−10 diffs + VER −27 (classified retiree + sprint), ALB DNS −2.
R1: VER −5, HAD −4 / ALO −6 / BOT −4 (retirees), STR +25 (stale results / suspected post-race DSQ).
R8 (Monaco, open): GAS −13 (NOT the cap — csv shows 2 OT; hypothesis: FL attribution or
post-penalty grid), HAD +4 / PIA +3 / LAW +3 (we over-credit; same hypotheses), SAI −17
(classified late retiree — WILL be fixed by A1), LIN −1, BEA −1.

Q2 cutoff proof: R3 and R9 `qualifying.json` each contain exactly 16 drivers with non-empty Q2
times and 10 with Q3 times.

csv cap proof: VER csv-r4 (=R6) overtakes_made=20; HAM csv-r8 (=R10) overtakes_made=11; both were
clipped to 8 by MAX_RACE_OVERTAKES.
