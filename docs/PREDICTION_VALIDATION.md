# Forecast validation and replay

Accuracy defaults to the latest complete forecast saved before Fantasy lock. `pipeline.forecast_archive` selects named/session archives and immutable audit snapshots, rejects retrospective/reconstructed outputs and requires one-to-one historical asset coverage. The exporter writes `web/public/data/accuracy_prelock.json`; the browser checks the deadline again and matches explicit legacy driver IDs only within the same constructor.

`pipeline.qualifying_transform` is the shared live FP blend. `evaluate_prequential_2026.py` defaults to that transform and strict event-prior auxiliary qualifying inputs. Race tests predict the entire available field before selecting finishers for error measurement. `--race-fp-training-inputs legacy_season_raw` is an explicit deployed-recipe diagnostic control; its earliest-season actual-quali fallback is deliberately retained only to reproduce that control.

The 9 October paired experiment (R7–R18, including Malaysia) improved mean race-position MAE only from 3.018 to 2.977 places; event-level uncertainty includes no gain. Model weights and the default training recipe remain unchanged. `05_train_models.py --quali-input-mode aligned_event` opts into the experimental aligned recipe and writes that choice into training metadata. Validate it before choosing it for a production retrain.

Future predictions freeze exact ordered qualifying/race/sprint input frames under `data/audit/inputs`, with deduplicated model/source/prior objects under `data/audit/objects`. Prediction metadata points to the inference manifest and its hash. The simulation adds scoring frames and resolved calibration/weather/prices/overtake/retirement/pit-stop priors and records the simulation manifest hash. Objects and manifests are append-only; these are public prediction dependencies, not authentication/environment files. Existing audit publication already includes these paths.

Monte Carlo team iteration is sorted and its order is recorded in simulation parameters. This removes differences caused solely by Python process hash randomization. Individual draws can differ from earlier unordered runs while the model's probabilities and settings are unchanged.

Checks: the focused Python regression files, `tests/accuracy_prelock_test.js`, existing frontend behavior tests, and `tests/test_mc_reproducibility.py`. Do not choose settings from the last one or two races or claim Fantasy-point gains from a position-only diagnostic. Historical point-layer replay remains limited until prospective input bundles accumulate.
