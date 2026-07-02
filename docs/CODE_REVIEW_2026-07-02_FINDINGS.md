# Code Review Findings — 2026-07-02

Full-codebase review (pipeline, config, frontend, seed data) performed 2026-07-02, before Silverstone R11.
Method: file-by-file read of the scoring/MC/prediction path + **cross-validation of our computed
actual fantasy points against the manually-entered official F1 Fantasy points for all 10 completed
rounds** (R1-R3, R6-R10). That reconciliation produced exact, arithmetically-proven evidence for most
findings below.

Status legend: `[ ]` open, `[x]` fixed, `[~]` investigation item.
Companion execution plan: `docs/FIX_PLAN_2026-07-02_PROMPT.md`.

---

## RESOLUTION (executed 2026-07-02, commits c955fb5..HEAD)

The fix bundle was executed in full. Reconciliation vs official points:
**drivers 60.8% → 94.9% exact (mean_abs 2.278 → 0.199); constructors 38.6% →
89.8% (4.125 → 0.648).** R1/R2/R3/R9 are now 22/22 drivers + 11/11 constructors
exact.

- **A1/A2 FIXED** — DNF now decided by `positionText=="R"`; classified late-
  retirees (LEC/ANT/BEA R9) score their real position; the `Lapped` override is
  gone (ALB R9 correct).
- **A3 FIXED** — retirees keep overtake points (R10 retirees −17 = −20+3).
- **A4 FIXED** — official `overtakes.csv` counts used verbatim (uncapped); caps
  apply only to telemetry. Estimation bases realigned to 07.
- **A5 FIXED** — DOTD R3/R6/R9/R10 added; `11` warns on a missing completed round.
- **A6 RESOLVED** — R1 STR was the same classified-retiree bug (posText=R,
  status=Lapped), not stale data. R1 now 22/22 exact; no re-download needed.
- **NEW (found during execution) FIXED** — the constructor quali teamwork bonus
  used set-Q-time presence; F1 Fantasy counts the SEGMENT REACHED (final quali
  position). Now position-based (Q3=top10, Q2≤16). Fixed Ferrari R9 (LEC P10, no
  Q3 time → both-Q3 +10).
- **B1 FIXED** — Q2 cutoff 15 → 16 (07 + MC sim + fallback). Unit-checked.
- **B2 FIXED** — phantom sprint-quali points removed (07 total + driver cards +
  CLAUDE.md). Verified live on R11 (0 drivers show SQ points).
- **B3 FIXED** — 07 sprint DNF prob ×0.5 (matches MC).
- **B4 FIXED** — MC fixes the sprint grid across sims when post-SQ
  (`sprint_grid_is_actual` from 06); pre-SQ falls back to the proxy.
- **B5 FIXED** — FL/DOTD field-normalized to sum to 1.0 (overrides fixed).
- **B6 FIXED** — PPM from official→actuals→predicted with a per-round cache.
- **C4/C5/C6 FIXED** — dnf_causes unknown-abbrev warning; `DNF_EXPECTED_PENALTY_
  FACTOR` replaces hardcoded 0.6; MC constructor `quali_bonus` tracked directly.
- **DNF model re-fit** — corrected actuals show DNF race points = −20 + overtakes
  exactly (severity constant 1.0). MC severity tightened to ~fixed and the spread
  now comes from sampled retiree overtakes (`RETIREE_OT_MEAN` 3.6, std 3.0, fitted
  from 32 true-DNF driver-rounds). `calibrate_confidence` re-run: overall 90%
  coverage **82.4%** (below the 90% target — driven by chaotic R2/R6/R8; NOT hand-
  tuned per plan), DNF-driver coverage 96.9%, bias +2.0, noise mult 1.30 → 1.45.

**User-confirmed and FIXED (2026-07-02, second pass — final: drivers 95.5%,
constructors 90.9% exact):**
- **R6 HAD +5 → FIXED.** User confirmed HAD did not classify in qualifying (his
  Q1 time was deleted; Ergast shows an empty Q1 with later times — the only such
  case in R1-R10). Now scored −5 (no-time-set) via a new `no_time_set` flag in
  `parse_qualifying` (missing Q1 time). HAD R6 exact; R6 drivers 21/22.
- **R10 racing_bulls −10 → FIXED.** User confirmed the official pit was 15 =
  5 (bracket) + 10 (overall-fastest). This revealed the **overall-fastest-stop
  bonus is +10, not +5** — `FASTEST_PITSTOP_BONUS` corrected 5→10 and
  `pitstop_points.json` R10 racing_bulls 5→15. R10 constructors 11/11 exact.

**R6 audi/red_bull → FIXED (constructor DSQ/NC penalty rule).** User identified
the real cause: F1 Fantasy applies a per-driver, per-session CONSTRUCTOR penalty
(on top of summing the drivers' points) for a disqualification / non-
classification — quali NC/DSQ −5, sprint DSQ −10, race DSQ −20. The
`CONSTRUCTOR_*_DSQ_PENALTY` constants existed but 11 never applied them. Now
applied via new `quali_no_time` / `sprint_is_dsq` driver flags. Verified: BOR
sprint DSQ → audi −10 (−17→−27 exact); HAD quali NC → red_bull −5 (36→31 exact).
These are the ONLY DSQ/NC events in R1-R10, so no other round is affected.
Final: **drivers 95.5%, constructors 93.2% exact.**

**Remaining documented residuals (small, sprint/grid data nuances):**
- **R8 Monaco cluster** (GAS −13, PIA/LAW/HAD +3/+4) — post-penalty grid basis /
  fastest-lap attribution; pre-existing open investigation (A7).
- **R6 ANT −2 / mercedes −2** — ANT's `overtakes.csv` sprint count is 0 but
  official implies ~2 (he lost 4 places grid P2→P6 yet scored +1 sprint).
- **R10 OCO −1, R7 HAD −3** — grid/positions-gained + sprint-overtake sourcing.

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
