# Code Review Findings — 2026-07-02

Full-codebase review (pipeline, config, frontend, seed data) performed 2026-07-02, before Silverstone R11.
Method: file-by-file read of the scoring/MC/prediction path + **cross-validation of our computed
actual fantasy points against the manually-entered official F1 Fantasy points for all 10 completed
rounds** (R1-R3, R6-R10). That reconciliation produced exact, arithmetically-proven evidence for most
findings below.

Status legend: `[ ]` open, `[x]` fixed, `[~]` investigation item.
Companion execution plan: `docs/FIX_PLAN_2026-07-02_PROMPT.md`.

---

## Headline evidence (ours vs official, per driver)

Mean error ≈ −1.4 pts/driver; tails to ±27. Every mismatch decomposes into the findings below.
Proven decompositions (exact):

- **R9 LEC**: classified P15 after lap-62 retirement (posText=15). Official = quali 7 − 11 lost + 4 overtakes = **0**. Ours = −20 flat → −19 error class A1.
- **R9 ANT**: classified P16. Official = 8 − 13 + 1 = **−4**. Ours −12. (A1)
- **R10 STR/SAI/PER/BOT**: true DNFs (posText=R), each with exactly 3 official overtakes. Official = −20 + 3 = **−17** each. Ours −20 flat. (A3)
- **R6 VER**: −22 = −10 missing DOTD (A5) − 12 from his 20 official overtakes capped at 8 (A4).
- **R10 HAM**: −3 = 11 official overtakes capped at 8 (A4).
- **R9 ALB**: posText=R + status='Lapped' → our 'Lapped' override un-DNF'd him. Ours +4, official −16 = quali 4 − 20. (A2)
- **R3 PIA / R9 HAM / R10 VER**: exactly −10 each → missing DOTD winners (A5).

---

## A. Actual-results scoring (11_actual_fantasy_points.py) — highest impact

These distort the Accuracy tab MAE, CI-coverage stats, `driver_history.json` (multi-week planner
form input), H2H, and the PPM fallback path.

- [ ] **A1. Classified late-retirees scored as DNF.** F1 classifies cars completing ~90% distance;
  Jolpica marks them with *numeric* `positionText` (vs `"R"`). `parse_race_results` decides DNF from
  the `status` string ("Retired"), so LEC/ANT/BEA at R9 (retired laps 60-62 of 66, classified P15-17)
  got −20 instead of finisher scoring. **Fix: `is_dnf = (positionText == "R")`.** Same rule in
  `parse_sprint_results`.
- [ ] **A2. 'Lapped' status override runs after the posText check and un-DNFs genuine retirements**
  (ALB R9: posText=R, status='Lapped', retired lap 55/66). Subsumed by the A1 rule.
- [ ] **A3. DNF drivers get 0 overtakes; official credits overtakes made before retiring.**
  Proven by R10 retirees (−17 = −20 + 3 each, csv shows exactly 3 each) and R7/R9 retiree diffs
  matching csv counts (RUS 5, NOR 9, HUL 3, ALO 3, BOT 2). Fix in the DNF branch AND the component
  breakdown block AND `overtake_source`. Apply the same to sprint DNFs.
- [ ] **A4. Overtake caps clip OFFICIAL csv values.** `MAX_RACE_OVERTAKES = 8` and
  `MAX_SPRINT_OVERTAKES = 5` apply to the merged detected+seed dict, so official F1 Fantasy counts
  the user manually entered (VER R6: 20 → 8, HAM R10: 11 → 8) are silently clipped. Caps should
  apply ONLY to telemetry-detected values (which over-count), never to `overtakes.csv` values.
  Also: 11's estimation-fallback bases (`{≤3:2, ≤6:4, ≤12:6, ≥13:7}` race, `{1,2,3,4}+gains−1`
  sprint) are STALE — 07/08 were retuned 2026-06-28 to `{6,4,4,2}` race / `{2,2,3,2}` sprint.
- [ ] **A5. `dotd_winners.json` missing R3, R6, R9, R10.** Diff evidence identifies: R3 = PIA,
  R6 = VER, R9 = HAM, R10 = VER (each exactly −10 after other effects removed). R8 = ANT is
  CORRECT (his total matches official incl. the +10). Add a loud warning in 11 when a completed
  round has no DOTD entry — this gap was silent for 4 rounds.
- [~] **A6. R1 STR: ours +2, official −23.** Looks like a post-race DSQ/reclassification our cached
  `results.json` predates. Re-download R1 raw results and re-check; if posText='D' appears, the A1
  rules handle it.
- [~] **A7. Open residuals** (document, don't force):
  - R8 Monaco cluster: GAS −13 (only 2 csv overtakes — NOT the cap; hypothesis: fastest-lap
    attribution or post-penalty grid basis), HAD/PIA/LAW +3/+4 (we over-credit; same hypotheses).
  - R2 sprint-weekend broad small diffs (OCO −10, HUL −9, LIN −6...) — sprint overtake sourcing
    (cap + estimation) should shrink these after A4; verify what remains.
  - R2 ALB DNS: ours −9 vs official −7 — DNS scoring rule slightly off (−20 race penalty may be
    wrong for DNS; official may score DNS as no-race-points instead).
  - R7 HAD −3 ('Lapped', sprint P21) — sprint overtake sourcing.

## B. Prediction-side scoring (07 / 08 / 06)

- [ ] **B1. Q2 cutoff wrong for 22 cars.** 2026 eliminates 6 per segment → Q2 = top 16 (verified:
  R3 and R9 raw qualifying show exactly 16 drivers with Q2 times). `07_calculate_fantasy.py`
  (`<=15` in the d1/d2 session mapping) and `08_monte_carlo_fantasy.py` per-sim constructor bonus
  (`both_q2/one_q2 = (q <= 15)`) + the no-sim-arrays fallback `q_tier_probs`. Midfield constructors
  get a systematically pessimistic quali teamwork bonus.
- [ ] **B2. Phantom sprint-quali points.** Official F1 Fantasy does NOT score sprint-quali position
  (our own actuals scorer never awards it; 15/22 exact matches at R7 confirm). But 07 adds
  `calc_qualifying_points_driver(pred_sprint_quali)` (up to +10) into the deterministic total, the
  export ships `expected_points_sprint_quali`, and driver cards render an "SQ" breakdown segment.
  The MC headline (`mc_total_mean`) is right; the card breakdown over-promises on sprint weekends.
- [ ] **B3. Sprint DNF inconsistency.** 07 applies the FULL race DNF probability and full −10 to the
  sprint expectation; the MC samples sprint DNFs at `dnf_probs * 0.5`. Align 07 to ×0.5.
- [ ] **B4. MC sprint grid uses the wrong session.** Per-sim sprint positions-gained/overtakes use
  the sampled SUNDAY quali as the sprint grid, ignoring the actual/predicted sprint-quali grid that
  06 loads (`predicted_sprint_quali_position`). Once real SQ results exist (post-SQ phase) the
  sprint grid is KNOWN and should be fixed per-sim, not resampled. Fix: 06 writes a
  `sprint_grid_is_actual` flag column; 08 uses the actual grid when flagged.
- [ ] **B5. 07 FL/DOTD probabilities don't normalize field-wide** (FL sums to ~134%, DOTD ~110%).
  MC samples one winner per sim correctly; normalize 07's so the deterministic breakdown matches
  (keep manual DOTD overrides fixed; normalize the remainder to 1 − Σoverrides).
- [ ] **B6. PPM circularity in 07.** `load_recent_fantasy_points` averages our own past PREDICTED
  totals. Should prefer official points → computed actuals → predicted (fallback). Also re-reads
  the same parquets 22×; cache per-round.

## C. Robustness quirks

- [ ] **C1. Race-day guard gap.** `is_race_completed` uses `race_date < today` (local), so all
  archive-protection guards are OFF on race Sunday itself — running 06/07/08 that evening would
  overwrite the genuine pre-race forecast. (Careful: race-morning refreshes are legitimate, so a
  blanket `<=` is wrong. Prefer race start time if available, else warn.) *Stretch.*
- [ ] **C2. Rookie dropout.** `build_live_priors` builds stub rows from each driver's last model
  row — a driver with zero career history (2027 rookies / mid-season swaps) silently vanishes
  from predictions. Should synthesize NaN-prior stubs for missing roster drivers + warn. *Stretch.*
- [ ] **C3. `fastf1_round` hardcodes 2026** cancellations; generalize (read races.json) before 2027.
- [ ] **C4. `load_dnf_causes` silently passes through unmapped abbreviations** → cause never joins.
  Warn on unknown abbrev.
- [ ] **C5. 07 hardcodes `0.6`** in the constructor DNF-impact display instead of the imported
  `DNF_EXPECTED_PENALTY_FACTOR`.
- [ ] **C6. MC `avg_quali_bonus`** reporting metric is contaminated by the DOTD subtraction
  (cosmetic). Track the bonus in its own accumulator.
- [ ] **C7. Constructor `expected_dnf_impact`** display understates true impact (ignores foregone
  points-if-finished). Cosmetic.

## D. Performance

- [ ] **D1. MC is pure-Python per-sim loops** (10k × 22 drivers + 11 × 10k constructor loop).
  Vectorizing would cut minutes → seconds. **Deliberately out of scope for the fix bundle**
  (same-seed outputs would change; do it standalone with a before/after distribution comparison).
- [ ] **D2. `load_recent_fantasy_points` parquet re-reads** — fold caching into B6.
- [ ] **D3. app.js `loadPitstopData` fetches rounds serially**; `Promise.all` would speed pit-panel
  first paint. Cosmetic.

## Post-fix recalibrations (required once A-fixes land)

- **MC_DNF_SEVERITY**: was fitted to reproduce DNF outcome spread measured against our BIASED
  actuals. Corrected data (R10 retirees at exactly −20+overtakes) implies severity ≈ 1.0 with small
  spread + a separate pre-retirement overtake credit. Re-fit from corrected actuals.
- **`calibrate_confidence.py`** rerun (MC noise multiplier + coverage stats are measured vs actuals).
- 07's deterministic DNF term should add the expected retiree overtake credit (~3 pts, from data).

## Verified clean (no action)

- Leakage discipline in 03b (`shift(1)` used consistently across all rolling features).
- Training sample weights (2026 ×2.5, wet ×6) applied where intended in 05.
- `pitstop_points.json` has explicit zeros for all 11 teams every round → official-history pit
  bootstrap in the MC is unbiased.
- Frontend PPM correctly prefers official points (getOfficialScore).
- Guards: race-completed + live-file downgrade + stale-price warnings all function as designed
  (modulo C1's race-day window).

---

## Backlog — modelling/simulation improvement roadmap (separate project, NOT in fix bundle)

Priority order, each gated on a measurable win:

1. **Points-level backtest harness**: replay each round's pre-lock forecast (phase archives exist
   for 10 rounds) against OFFICIAL points; metrics = points MAE + rank-correlation of driver
   ordering. Becomes the gate for everything below (positions are already walk-forward gated;
   the event layer is not).
2. **Grid-conditioned race sampling in the MC**: sample race as
   `α·(sim'd quali z) + (1−α)·(race model z) + noise` with α fit per track type from the accuracy
   archive. Fixes the positions-gained covariance the independent sampling gets wrong — the single
   biggest structural improvement available.
3. **Heteroscedastic position noise**: per-tier residual σ (front/mid/back) fit from 10 rounds of
   pred-vs-actual instead of one global noise base × confidence.
4. **Ensemble XGB + CatBoost race scores** (both already trained every run) — blend weight swept on
   the 97-fold harness; keep only if CI excludes zero.
5. **Event-layer calibration from history**: FL/DOTD position-conditional weights fit from
   2022-2026 actual winners (on disk); Negative-Binomial overtake sampling.
6. **DNF hazard model**: integrate `train_dnf_classifier.py` scaffold (reliability + circuit +
   weather features), gate on Brier vs current 0.164.
7. **Pit stops-per-race by circuit** for the bootstrap once ~15+ rounds of official history exist.
