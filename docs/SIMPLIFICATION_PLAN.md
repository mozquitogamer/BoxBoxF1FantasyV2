# BoxBoxF1Fantasy simplification plan

Work one area at a time. Keep each change small enough to compare the generated
outputs with the current pipeline before moving on. The 2026 model, scoring,
round numbering, and archived predictions are existing contracts.

## Current picture

- `pipeline/` began with 67 top-level Python scripts. Three historical sweep
  launchers now live in `pipeline/research/`. The active weekend entry point is
  `pipeline/run_weekend.py`; `publish_weekend.py` is a compatibility wrapper.
- `web/public/app.js` is about 574 KB. The static site has no build step, so
  script order and cache versions matter when moving code out of it.
- `pipeline/14_build_seo_pages.py` is about 361 KB and mixes page generation
  with many output formats.
- The former 31 KB `tests/smoke_app_js.js` now checks load-time behavior only;
  the optimizer and Final Fix behavior checks have their own test file.
- The four GitHub workflows run publishing or scheduled jobs. None runs the
  Python or JavaScript tests; `tests/README.md` now lists the current suite.
- The initial 2026-09-21 audit found 10 Python failures caused by a mix of
  stale test expectations and two replay defects. After the test cleanup pass,
  the full Python suite now passes (286 tests). All three JavaScript checks pass.

## Sequence

### 1. Weekend orchestration — completed

Keep one phase definition and one failure policy. The active runner now shares
the prediction steps between pre-FP, post-FP, and post-quali phases. A required
step failure stops execution and returns a failing process status; an optional
failure is shown as a warning and later steps continue. `publish_weekend.py`
now forwards to the active runner, with post-FP as its default phase.

Gate: phase command lists remain in the same order; required and optional
failure behavior is covered by focused tests and dry runs.

### 2. Test cleanup — completed in the second pass

The 10 failures were triaged. Tests tied to earlier CSP, archive, roster,
price, and manager states now check the intended contract against the right
round. The simulator reads each archive's active driver assets and maps
replacement IDs to official points; the V13 replay uses lock-time prices and
the risk report stops at its frozen experiment round. A test that wrote the
public V13 JSON now writes to a temporary path.

`tests/smoke_app_js.js` is now a short load-time check. The optimizer, Final
Fix, and team-comparison checks live in `tests/app_behavior_test.js`, sharing
`tests/app_js_harness.js`. `tests/README.md` lists the actual commands. A few
static shell checks remain because they still protect script order and form
uniqueness; move them to browser-level coverage before removing them.

Gate: 277 Python tests passed together, including the round-specific roster
test, and all three JavaScript checks passed. A test workflow can be added after
checking the suite from a clean checkout on the target CI runner.

### 3. Fantasy scoring boundary — completed

Review `config/fantasy_scoring.py` alongside `07_calculate_fantasy.py`,
`08_monte_carlo_fantasy.py`, and `11_actual_fantasy_points.py`. Move only pure,
identical point rules into shared functions. Keep expected-value, simulation,
and actual-result policies separate, including the official qualifying
classification versus penalised starting grid and constructor exclusions.

The first extraction puts the team pit stop time priors and generic fallback
in `config/pitstop_priors.py`. The Monte Carlo time-prior path uses the same
single-stop scoring function as actual constructor points. An unused second
pit stop sampler was removed. The analytical expected-value formula and the
simulation's official-history sampling remain separate because they answer
different questions. The 11 team priors, five bracket boundary scores, and
Red Bull/Cadillac expected values matched the baseline. Existing R14 sprint
and R15 regular archives each reconcile exactly with official totals (22/22
drivers and 11/11 constructors); archived outputs were not regenerated.

The second extraction puts the 2026 position-to-qualifying-segment conversion
and constructor teamwork bonus in `config/fantasy_scoring.py`. Projected,
simulated, and actual constructor scores call the same function. The 484 valid
position pairs produced the same five bonus counts before and after the change;
focused tests include the P16/P17 Q2 boundary and a Q3 classification without
a recorded Q3 lap time.

The remaining race and sprint calculations combine the shared point values
with different policies: expected values in `07`, sampled outcomes and DNF
severity in `08`, and recorded results in `11`. Keeping those paths separate
avoids changing the model's meaning while the common rules are now central.

Gate: compare scoring components and totals for representative completed
regular and sprint rounds before and after each extraction; run reconciliation
against official points.

### 4. Data loading and model boundaries — completed

Consolidate repeated seed and round asset lookups after listing their callers
and return shapes. Add a narrow contract for internal round versus FastF1 and
Jolpica round numbers at API boundaries. Then separate feature construction,
model loading, and output writing in the larger prediction scripts without
changing model inputs or archived outputs.

The first data-loading pass shares only the canonical ID-keyed driver and
constructor maps through `config/seed_roster.py`. The Monte Carlo, actual-score,
and website-export loaders retain their existing function names and return
shapes. The Monte Carlo and export loaders still switch to round-scoped active
assets when given a round; the actual-score loader still reads the canonical
season roster and applies round assets separately. The raw list loader in
`config/driver_assets.py` remains a list to preserve duplicate-row detection.
Nine representative lookups (including R13 and R14) produced identical
content fingerprints before and after consolidation: 22 drivers and 11
constructors in their respective keyed maps.

The round-boundary pass found a 2026 bulk-download defect: historical-mode
loops used compressed API round numbers as internal path and FastF1 inputs.
`config/settings.py` now defines the inverse map and the internal rounds in
an API schedule. Bulk Jolpica saves API round 4 to internal `round6` (Miami),
and all bulk FastF1 paths iterate internal round IDs. The existing FP-gap
downloader shares the same iterator. A cancelled internal round now raises
before a per-round API request or directory write. OpenF1 retains its direct
original-calendar lookup; a mocked six-round schedule tests that distinction.
All direct FastF1 session calls in `pipeline/` were reviewed and already apply
`fastf1_round` at the API boundary. Nine focused boundary tests and the full
277-test Python suite pass. Cached Jolpica payloads confirm internal R6 is
API R4 (Miami), R14 is API R12 (Dutch), and R16 is API R14 (Madrid); no
downloaded or archived data was rewritten.

The first prediction-script extraction makes the output boundary in
`06_run_predictions.py` explicit: one function selects the downstream frame,
one names the paired parquet/metadata paths, and one writes them. R14 sprint
and R16 regular cached predictions round-tripped through the new frame builder
with identical 22-row content, column order, and ranks (35 and 30 columns).
The horizon suffix is tested to keep both artifacts separate from the
canonical files. Neither archive was rewritten.

The FP feature join is now a dedicated `assemble_prediction_rows` boundary in
`06_run_predictions.py`. It attaches the round's Fantasy seats, converts each
FP abbreviation independently, and joins current-weekend telemetry without
letting FP metadata replace constructor or internal round identity. A repeated
FP driver now fails instead of duplicating a prediction row. When an FP field
already exists in priors, current FP replaces it, including NaN for missing
evidence, so old pace cannot masquerade as current-weekend pace. Cached R14
and R16 joins matched their pre-change 22-row, 137-column content fingerprints
exactly; mixed-ID, duplicate-row, priors-only, and stale-field cases have
focused tests. The extra driver-ID-map read was removed from output assembly.
The full Python suite passed with 280 tests after this extraction.

Race and sprint model selection now live in explicit functions alongside a
shared ranker loader. Each choice carries its model file, training feature
order, algorithm, and phase label; the chosen race file also feeds the audit
metadata. The existing pre-FP, post-FP, post-quali, sprint-grid, missing-FP-
model, and CatBoost fallback rules are covered by focused tests. On cached R14
and R16 FP feature rows, both race-model variants kept the same 22 rows, 113
feature columns, score fingerprints, and ranks as before the extraction. The
available R14 sprint model and both CatBoost race models also loaded and
predicted on the cached rows. No prediction archive was rewritten.
The full Python suite passed with 283 tests after this extraction.

The race-grid update now has one `build_race_grid_features` boundary. It keeps
the official qualifying classification, the race model's qualifying input, and
the penalised race start separate. Four qualifying-derived features now use
one formula in historical row construction, model training, and inference.
Cached R14 and R16 cases kept the exact pre-change fingerprints for all 22
rows and 18 grid/interaction fields, including a partial post-quali result and
a grid penalty. Focused tests cover those distinctions and missing track data.
The full Python suite passes with 286 tests; no archive was rewritten.

The fixed-snapshot handoff check is complete. Rebuilding website payloads from
the saved R14 sprint and R16 regular prediction, scoring, and Monte Carlo
artifacts preserved every driver's qualifying/grid/finish positions, raw
scores, deterministic and simulated points, plus every constructor's totals
(22 drivers and 11 constructors per round, no mismatches). Both payloads also
serialized as strict JSON. A separate R17 priors-only run completed prediction
→ deterministic scoring → 1,000 Monte Carlo simulations → website JSON in a
temporary directory: all 22 driver positions, raw scores, and point totals
matched their source artifacts, and the temporary files were removed. Frozen
phase archives have since diverged from the mutable round artifacts through
later price and scoring updates, so byte-for-byte comparison to those old
public snapshots would conflate data changes with this refactor.

Gate: cached model feature columns, row counts, score fingerprints, and ranks
matched; saved-artifact and isolated full-chain JSON handoffs passed. Rolling
training feature selection was unchanged.

### 5. Frontend modules and generated pages — completed

Extract one coherent feature at a time from `web/public/app.js`, starting with
pure optimizer or Final Fix calculations. Pass data into those functions
explicitly, then move the corresponding browser rendering. Keep the existing
static script order and bump cache versions when changing loaded assets.
Review `14_build_seo_pages.py` separately: group shared page data assembly and
templates before splitting outputs into files.

The first frontend extraction moves Final Fix qualifying/race scoring, the
deterministic projected-race fallback, and hold/switch comparison totals into
`web/public/final-fix.js`. The module takes drivers, bank, boost, and scenario
points as inputs. The script loads before `app.js`, and both cache versions were
set in `index.html`. Two representative comparison renderings (normal finish
and DNF) matched their pre-change HTML fingerprints exactly. All three
JavaScript checks passed, including banked-qualifying and boost-scope cases.
The operations guide now describes cache versions without a stale hardcoded
number.

The second pass moved the Final Fix form setup, event handlers, and HTML
rendering into the same module. `app.js` now mounts it with an explicit
document, current-data accessor, and grid-penalty label helper. The original
initial view and a recalculated DNF scenario matched their pre-change HTML
fingerprints exactly; the JavaScript behavior checks now exercise the mounted
form and its bank-change handler. A local R17 browser check loaded the Final
Fix view and confirmed that changing cash and selecting DNF recalculated the
comparison.

The third pass extracted the points-basis, chip, confidence-interval, and
team-total calculations into `web/public/optimizer-scoring.js`. The app passes
its selected points basis explicitly at the boundary; the same scorer serves
fresh lineups and Team Compare. All 12 basis/chip combinations for a fixed R17
lineup matched the pre-change totals and boost targets exactly. A separate
case checks that an explicit basis remains stable after another optimizer mode
changes its selection. The local R17 page searched 642,874 valid lineups and
rendered its ranked result.

The generated-page pass moved race page selection and publishing metadata into
`assemble_race_page` in `pipeline/14_build_seo_pages.py`. The main loop now
writes whichever current, result, archive, horizon, or calendar page the
assembler returns. Representative R16/R17/R18/R23 pages kept identical HTML
hashes, URLs, statuses, and update dates. An isolated full build wrote 22 race
pages and a 96-URL sitemap. `page_head` and `FOOTER` already provide the shared
HTML shell, so the page templates remain together for now. Next, audit one-off
scripts and align the operations docs with the active workflow.

Gate: compare representative pages and optimizer scenarios in a browser, and
verify generated URLs and metadata from a fixed input snapshot.

### 6. Retire one-off code and refresh operations docs — completed

Classify scripts such as sweeps, backfills, validators, and recovery tools as
active, occasional, or historical. Move or remove only those with no live
callers after recording their purpose and inputs. Bring `docs/OPERATIONS_GUIDE.md`
and `tests/README.md` into line with the active commands and checks.

Gate: every documented live command resolves, and every removed script has no
caller in weekend operations or scheduled jobs.

The inventory in `docs/PIPELINE_TOOLS.md` now labels weekend, scheduled,
operator, recovery, evaluation, and historical research tools by their inputs
and purpose. The three historical sweep launchers moved to
`pipeline/research/`; none had a caller in the weekend runner, workflows, or
tests. Their candidate lists and saved `data/experiments/` results remain
available, and their project-root/validator paths were checked after the move.

The operations guide no longer duplicates `run_weekend.py::PHASES` as a static
step list. It points to `--dry-run` for the exact current order and now places
actual-points scoring after overtake and pit-stop collection. The test README
notes that the publishing workflows do not run the test suite. All five phase
dry runs completed; the moved sweep entry points resolved, and no reference
to their former paths remained outside Git history.
