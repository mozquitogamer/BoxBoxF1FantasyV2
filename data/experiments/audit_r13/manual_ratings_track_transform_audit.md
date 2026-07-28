# Manual ratings, circuit features, and FP/grid transform audit

Audit date: 2026-07-27
Data snapshot: corrected `models/training_data/all_training_data.parquet`, 2,855 rows, 142 race events, 11 completed 2026 events (239 valid driver rows).
Scope: manual driver/constructor ratings, manual circuit classifications, similarity-weighted priors, FP qualifying blend, hard-track grid anchoring, and track-driven Monte Carlo modifiers.

## Executive findings

1. **The present rating tables cannot support a clean historical validation claim.** The current 2026 ratings were edited after China R2 (commits on 2026-03-22 and 2026-03-27) and are applied unchanged to every 2020-2026 row. The driver-ID alias fix was only committed on 2026-07-17. A current walk-forward replay therefore gives early folds information/configuration they did not have live.
2. **The current ratings are material model inputs, not minor tie-breakers.** In the deployed, pre-correction artifacts, the nine manual/rating-interaction fields account for 9.79% of qualifying XGBoost gain, 8.01% of CatBoost post-quali prediction-value-change importance, and 8.35% of CatBoost post-FP importance.
3. **The circuit-similarity metric has almost no contrast.** Across 465 circuit pairs, cosine similarity has min 0.692, median 0.975, P90 0.994, and 71.4% of pairs are at least 0.95. Squaring the weights still gives a median weight of 0.951. The six similarity-weighted rolling features correlate 0.9988-0.9996 with their ordinary rolling equivalents.
4. **One hand-set track number is reused in several downstream mechanisms.** `overtaking_difficulty` affects the trained rankers, `quali_skill_x_ot_diff`, FP blend strength, grid anchoring, overtake damping, MC position damping, and MC chaos widening. This creates coupled assumptions and double/triple counting.
5. **The hard-track rules are not yet estimable from 11 events.** Only Monaco and Hungary provide non-sprint completed evidence for the hard FP/anchor ramp. They should be reported as a sensitivity analysis, not tuned and declared validated.
6. **The MC modifiers partly cancel or reverse one another.** Monaco's position-noise damping is 0.70, but its chaos multiplier is 2.32, for net race-position noise of 1.624 times neutral. Hungary is net 1.263 times neutral. The code comment that these tracks are simply "tighter/stickier" is not the combined behavior.
7. **`pit_stop_speed` is dead configuration.** It is manually rated for every constructor but has no caller outside `team_driver_ratings.py`; it affects neither rankers nor fantasy scoring.
8. **Manual weather skill can be counted twice.** `wet_skill` and `cold_skill` are unconditional model features, while the MC adds a second conditional wet/cold score perturbation. The model may already learn weather interactions, so the MC shift needs an ablation against a ranker with those skills removed.

## Exact feature groups for controlled ablation

These fields are in both current qualifying and race feature lists unless stated otherwise.

### Driver rating block

```text
tire_mgmt
wet_skill
overtaking
quali_skill
quali_skill_x_ot_diff
```

### Constructor rating block

```text
strategy_rating
adaptability
cold_skill
strategy_sc_advantage
```

### All manual rating-derived ranker fields

```text
strategy_rating,adaptability,cold_skill,tire_mgmt,wet_skill,overtaking,
quali_skill,strategy_sc_advantage,quali_skill_x_ot_diff
```

### Raw manual track block

```text
is_street
overtaking_difficulty
avg_corner_speed
straight_line_importance
downforce_level
turn1_incident_risk
safety_car_probability
track_evolution
grip_level
```

The raw track fields are constant within each ranking group. They have no standalone within-event rank correlation, but trees can use them to select different driver/prior splits by circuit type.

### Manual-track-similarity block

```text
sim_weighted_points_3
sim_weighted_finishpos_3
sim_weighted_quali_3
sim_weighted_points_5
sim_weighted_finishpos_5
sim_weighted_quali_5
```

### Circuit-history block (not manually rated, but track-keyed)

```text
driver_circuit_exp
driver_circuit_roll_3
constructor_circuit_exp
```

`driver_circuit_reliability` and `driver_circuit_roll_3_reliability` are retained in data for diagnostics but explicitly excluded from the rankers.

### Inference-only/manual position controls

- `data/seed/pace_overrides.json`: currently forces R11 race ranks `NOR -> P6`, `PIA -> P7`; the reordered raw scores flow into MC and fantasy outputs. Pure-model evaluation must remove or separately label this layer.
- `data/seed/grid_penalties.json`: factual known penalties for R12 and R13. These change `predicted_grid_position`, positions-gained scoring, and hard-track anchoring, while official qualifying points remain unchanged.
- `data/seed/dotd_overrides.json`: R8 Leclerc DOTD probability 0.65. It changes fantasy ranking, not predicted qualifying/race position.
- A future `quali` pace override would not currently rebuild `predicted_grid_position`, because overrides are applied after the grid is constructed. The present seed only overrides `race`, so the bug is latent.

`grid_importance_factor`, `pole_advantage`, `front_row_advantage`, and the three `top10_*_interaction` fields are recomputed in `06_run_predictions.py`, but are absent from the corrected training data and saved feature lists. They currently do not influence ranker predictions.

## Coverage, cardinality, and target association

All nine material rating-derived columns are non-null on 100% of training rows because lookup misses receive defaults. Explicit table coverage is lower:

| lookup | explicit row coverage, all years | explicit row coverage, 2026 | missing historical IDs |
|---|---:|---:|---|
| tire management | 93.59% | 100% | aitken, de_vries, giovinazzi, grosjean, kubica, kvyat, pietro_fittipaldi, raikkonen, vettel |
| wet skill | 93.59% | 100% | same as tire management |
| overtaking | 92.82% | 100% | above plus mazepin |
| qualifying skill | 92.82% | 100% | above plus mazepin |
| team strategy/adaptability | 97.62% | 100% | racing_point, renault |
| constructor cold skill | 97.62% | 100% | racing_point, renault |

Mean per-event Spearman correlations are shown below. Position targets are lower-is-better, so a negative value means a higher manual rating is associated with a better result. Race correlations use classified finishers.

| feature | cardinality all / 2026 | qualifying corr all / 2026 | race corr all / 2026 |
|---|---:|---:|---:|
| strategy_rating | 6 / 6 | -0.504 / -0.802 | -0.481 / -0.702 |
| adaptability | 7 / 7 | -0.462 / -0.792 | -0.422 / -0.680 |
| cold_skill | 4 / 4 | -0.402 / -0.599 | -0.433 / -0.534 |
| tire_mgmt | 6 / 5 | -0.577 / -0.335 | -0.586 / -0.333 |
| wet_skill | 7 / 5 | -0.575 / -0.380 | -0.594 / -0.436 |
| overtaking | 6 / 5 | -0.532 / -0.397 | -0.521 / -0.435 |
| quali_skill | 7 / 7 | -0.561 / -0.752 | -0.549 / -0.700 |
| strategy_sc_advantage | 20 / 19 | -0.504 / -0.802 | -0.481 / -0.702 |
| quali_skill_x_ot_diff | 31 / 23 | -0.561 / -0.752 | -0.549 / -0.700 |

The interaction fields have exactly the same within-event rank correlation as their underlying rating because the track multiplier is constant within an event. Their benefit can only come from cross-track conditional tree behavior.

The unusually strong 2026 team-rating association is not independent evidence that the priors are valid: the source explicitly says the values were updated to reflect the 2026 constructor order after R2. In contrast, the 2026 tire/wet/overtaking ratings are much less predictive than they were over 2020-2025.

### Deployed-model reliance (diagnostic only)

These artifacts predate the current feature corrections and should not be used as a candidate score. They show that the fields are material:

| deployed artifact | manual ratings | raw track | similarity rolling | combined |
|---|---:|---:|---:|---:|
| qualifying XGBoost gain | 9.79% | 7.72% | 9.87% | 27.37% |
| race CatBoost prediction-value-change | 8.01% | 3.48% | 6.12% | 17.60% |
| race-FP CatBoost prediction-value-change | 8.35% | 3.93% | 7.20% | 19.48% |

Notable individual fields in the stale deployed artifacts:

- qualifying: `sim_weighted_points_5` 3.63%, `quali_skill` 1.91%, `wet_skill` 1.54%;
- race: `wet_skill` 1.44%, `strategy_sc_advantage` 1.39%, `quali_skill_x_ot_diff` 1.37%;
- race-FP: `strategy_sc_advantage` 1.69%, `quali_skill_x_ot_diff` 1.34%, `wet_skill` 1.29%.

## Rating drift and version leakage

- `TEAM_STRATEGY_RATINGS` says "updated post China GP Round 2 race results" and explicitly cites R2 results/DNFs. Those values are now materialized onto R1 and R2 rows and onto all prior seasons.
- Driver tables say they were updated after Australia/China. Current validation of R1 or R2 therefore leaks future/current target knowledge.
- The same current value is used for a driver in every season. For example, a 2026 assessment of Hamilton, Russell, Antonelli, and others becomes a 2020-2025 input. Constructor ratings similarly assign the current Mercedes=9, Ferrari=7, Aston Martin=4 ordering to all historical rows.
- Git history shows rating edits on 2026-03-22 and 2026-03-27, a weather/cold addition on 2026-05-25, and the driver-ID alias fix on 2026-07-17. A replay using the current file does not reproduce the feature values available to the live system before those dates.
- Before the alias fix, most Jolpica driver IDs silently received the default value 6 while `max_verstappen` happened to match a full-name key. A present-day reforecast with the fixed mapping is not an honest replay of those live predictions.

Safest options:

1. exclude all rating-derived fields from historical model selection until snapshots exist; or
2. store ratings with `effective_from` and reconstruct each fold using only the snapshot available before that event.

If the ratings are retained as genuine expert priors, call their evaluation "current-prior reforecast," not historical walk-forward validation.

## Full current manual rating inventory

### Constructor ratings

`pit_stop_speed` is included for completeness but is currently unused.

| constructor key | strategy | pit stop speed | adaptability | cold skill |
|---|---:|---:|---:|---:|
| mercedes | 9 | 8 | 9 | 8 |
| ferrari | 7 | 8 | 7 | 6 |
| red_bull | 8 | 9 | 7 | 6 |
| mclaren | 8 | 8 | 8 | 6 |
| haas | 7 | 7 | 7 | 5 |
| rb | 7 | 7 | 7 | 5 |
| racing_bulls | 7 | 7 | 7 | 5 |
| alpine | 5 | 6 | 5 | 5 |
| williams | 6 | 7 | 6 | 7 |
| aston_martin | 4 | 3 | 3 | 5 |
| audi | 5 | 6 | 5 | 5 |
| cadillac | 4 | 5 | 4 | 5 |
| kick_sauber | 5 | 6 | 5 | 5 |
| alfa | 5 | 6 | 5 | 5 |
| alphatauri | 6 | 7 | 6 | 5 |

### Driver ratings

| rating key | tire | wet | overtaking | qualifying |
|---|---:|---:|---:|---:|
| alexander_albon | 7 | 7 | 7 | 7 |
| arvid_lindblad | 7 | 6 | 6 | 6 |
| carlos_sainz | 8 | 7 | 8 | 8 |
| charles_leclerc | 8 | 8 | 9 | 9 |
| daniel_ricciardo | 7 | 7 | 9 | 7 |
| esteban_ocon | 7 | 7 | 7 | 7 |
| fernando_alonso | 10 | 9 | 10 | 8 |
| franco_colapinto | 6 | 7 | 7 | 7 |
| gabriel_bortoleto | 6 | 6 | 7 | 7 |
| george_russell | 8 | 8 | 8 | 10 |
| isack_hadjar | 6 | 7 | 7 | 8 |
| jack_doohan | 6 | 6 | 6 | 6 |
| kevin_magnussen | 7 | 6 | 8 | 6 |
| kimi_antonelli | 8 | 8 | 8 | 9 |
| lance_stroll | 6 | 7 | 6 | 4 |
| lando_norris | 8 | 8 | 8 | 9 |
| lewis_hamilton | 9 | 10 | 9 | 9 |
| liam_lawson | 7 | 6 | 7 | 7 |
| logan_sargeant | 6 | 5 | 5 | 5 |
| max_verstappen | 9 | 10 | 10 | 9 |
| mick_schumacher | 6 | 6 | 6 | 6 |
| nicholas_latifi | 6 | 5 | 5 | 5 |
| nico_hulkenberg | 8 | 6 | 7 | 7 |
| nikita_mazepin | 5 | 4 | 6 (default; missing table entry) | 6 (default; missing table entry) |
| oliver_bearman | 7 | 6 | 8 | 7 |
| ollie_bearman | 6 | 6 | 7 | 7 |
| oscar_piastri | 8 | 7 | 7 | 8 |
| pierre_gasly | 7 | 7 | 7 | 7 |
| sergio_perez | 8 | 7 | 7 | 6 |
| valtteri_bottas | 7 | 7 | 7 | 5 |
| yuki_tsunoda | 6 | 6 | 7 | 7 |
| zhou_guanyu | 6 | 6 | 6 | 6 |

There are separate `oliver_bearman` and legacy `ollie_bearman` keys with different ratings.

## Circuit classification and similarity audit

### Similarity distribution

There are 31 circuits and 465 non-self pairs.

| statistic | cosine similarity | squared weight used by rolling features |
|---|---:|---:|
| minimum | 0.6917 | 0.4784 |
| P10 | 0.9030 | 0.8154 |
| median | 0.9750 | 0.9505 |
| P90 | 0.9939 | 0.9878 |
| maximum | 1.0000 | 1.0000 |
| mean | 0.9589 | — |

Pair counts: 421/465 (90.5%) are at least 0.90; 332/465 (71.4%) are at least 0.95; 88/465 (18.9%) are at least 0.99. Madrid and Nürburgring have identical vectors. Other near-duplicates include Losail/Suzuka (0.9986), Interlagos/Mugello (0.9979), and Americas/Silverstone (0.9978).

The positive, uncentered 1-10 vectors are the cause: almost every coordinate points in the same direction. `is_street` is a 0/1 field beside eight mostly 4-9 fields and therefore contributes little to cosine distance.

### Similarity priors versus ordinary recency

| pair | Pearson corr | Spearman corr | mean absolute difference | P95 absolute difference |
|---|---:|---:|---:|---:|
| points, 3-race | 0.99944 | 0.99945 | 0.093 points | 0.442 |
| finish, 3-race | 0.99908 | 0.99882 | 0.104 positions | 0.421 |
| qualifying, 3-race | 0.99947 | 0.99934 | 0.087 positions | 0.353 |
| points, 5-race | 0.99958 | 0.99955 | 0.089 points | 0.400 |
| finish, 5-race | 0.99931 | 0.99920 | 0.099 positions | 0.346 |
| qualifying, 5-race | 0.99965 | 0.99960 | 0.080 positions | 0.272 |

This block mostly duplicates the ordinary rolling features while consuming 6.1-9.9% of deployed importance. First hypothesis to test: drop all six similarity fields. If a circuit relation is retained, replace the raw cosine with standardized/centered features, learned embeddings, or a small pre-registered archetype set and validate out of circuit.

### Raw feature dependence

Largest pairwise Spearman relationships among the 31 manual circuit rows:

- overtaking difficulty vs straight-line importance: -0.825;
- is-street vs track evolution: +0.739;
- straight-line importance vs downforce: -0.735;
- safety-car probability vs track evolution: +0.705;
- overtaking difficulty vs downforce: +0.685.

This means the nine fields do not provide nine independent degrees of information.

### Full classification inventory

| circuit | street | overtake difficulty | corner speed | straight importance | downforce | T1 incident | safety car | evolution | grip |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| monaco | 1 | 10 | 2 | 1 | 9 | 8 | 8 | 9 | 7 |
| marina_bay | 1 | 8 | 3 | 2 | 9 | 7 | 7 | 8 | 6 |
| baku | 1 | 4 | 4 | 8 | 6 | 9 | 9 | 8 | 5 |
| jeddah | 1 | 5 | 7 | 6 | 7 | 8 | 7 | 7 | 6 |
| miami | 1 | 6 | 5 | 5 | 6 | 7 | 6 | 7 | 6 |
| vegas | 1 | 4 | 6 | 8 | 4 | 6 | 6 | 7 | 5 |
| monza | 0 | 3 | 8 | 10 | 2 | 9 | 5 | 4 | 8 |
| spa | 0 | 4 | 8 | 8 | 5 | 7 | 6 | 5 | 7 |
| silverstone | 0 | 5 | 8 | 6 | 7 | 8 | 5 | 5 | 8 |
| suzuka | 0 | 6 | 8 | 5 | 8 | 7 | 5 | 5 | 8 |
| red_bull_ring | 0 | 4 | 7 | 7 | 6 | 8 | 5 | 4 | 7 |
| catalunya | 0 | 6 | 6 | 4 | 7 | 6 | 4 | 5 | 8 |
| hungaroring | 0 | 9 | 4 | 2 | 9 | 8 | 5 | 6 | 6 |
| imola | 0 | 7 | 6 | 4 | 7 | 7 | 6 | 5 | 7 |
| zandvoort | 0 | 8 | 5 | 3 | 8 | 7 | 5 | 6 | 7 |
| bahrain | 0 | 4 | 6 | 6 | 6 | 7 | 5 | 5 | 6 |
| albert_park | 0 | 5 | 6 | 5 | 6 | 7 | 6 | 6 | 7 |
| villeneuve | 0 | 4 | 6 | 7 | 5 | 6 | 7 | 6 | 6 |
| americas | 0 | 5 | 7 | 6 | 7 | 7 | 5 | 5 | 7 |
| rodriguez | 0 | 4 | 5 | 7 | 8 | 8 | 5 | 5 | 5 |
| interlagos | 0 | 5 | 6 | 5 | 6 | 7 | 6 | 5 | 6 |
| losail | 0 | 5 | 7 | 5 | 7 | 6 | 4 | 4 | 7 |
| shanghai | 0 | 5 | 6 | 7 | 6 | 7 | 5 | 5 | 6 |
| yas_marina | 0 | 6 | 5 | 6 | 6 | 6 | 5 | 5 | 7 |
| madrid | 0 | 5 | 6 | 6 | 6 | 7 | 5 | 5 | 7 |
| mugello | 0 | 6 | 7 | 6 | 7 | 8 | 6 | 5 | 7 |
| sochi | 1 | 6 | 5 | 7 | 6 | 6 | 6 | 6 | 6 |
| nurburgring | 0 | 5 | 6 | 6 | 6 | 7 | 5 | 5 | 7 |
| portimao | 0 | 5 | 6 | 6 | 6 | 7 | 5 | 6 | 6 |
| istanbul | 0 | 5 | 7 | 5 | 7 | 7 | 5 | 6 | 6 |
| ricard | 0 | 4 | 7 | 7 | 6 | 6 | 4 | 4 | 8 |

## 2026 transform weights

Definitions:

- `FP w`: z-space blend of the qualifying model with the FP composite. It is 0.60 on ordinary non-sprint tracks, ramps to 0.80 at difficulty 10, and is overridden to 0.15 on all sprint weekends.
- `anchor`: z-space blend of predicted race score with the penalized grid; active post-FP only when at least 10 drivers have FP pace, or post-quali.
- `FP×anchor`: a rough mechanical double-count indicator, not an exact causal coefficient because the grid is rank-transformed.
- `OT mult`: multiplier on expected overtakes.
- `pos mult`: MC position-noise damping.
- `chaos`: MC race-noise widening.
- `net race`: `pos mult * chaos`, before calibration and weather.

| R | circuit | sprint | difficulty | FP w | anchor | FP×anchor | OT mult | pos mult | chaos | net race |
|---:|---|:---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | Albert Park | no | 5 | .600 | 0 | 0 | 1 | 1 | 1.360 | 1.360 |
| 2 | Shanghai | yes | 5 | .150 | 0 | 0 | 1 | 1 | 2.180 | 2.180 |
| 3 | Suzuka | no | 6 | .600 | 0 | 0 | 1 | 1 | 1.180 | 1.180 |
| 4 | Bahrain (cancelled) | no | 4 | .600 | 0 | 0 | 1 | 1 | 1.180 | 1.180 |
| 5 | Jeddah (cancelled) | no | 5 | .600 | 0 | 0 | 1 | 1 | 1.540 | 1.540 |
| 6 | Miami | yes | 6 | .150 | 0 | 0 | 1 | 1 | 2.360 | 2.360 |
| 7 | Montréal | yes | 4 | .150 | 0 | 0 | 1 | 1 | 2.540 | 2.540 |
| 8 | Monaco | no | 10 | .800 | .8500 | .6800 | .1300 | .7000 | 2.320 | 1.624 |
| 9 | Catalunya | no | 6 | .600 | 0 | 0 | 1 | 1 | 1.000 | 1.000 |
| 10 | Red Bull Ring | no | 4 | .600 | 0 | 0 | 1 | 1 | 1.180 | 1.180 |
| 11 | Silverstone | yes | 5 | .150 | 0 | 0 | 1 | 1 | 2.180 | 2.180 |
| 12 | Spa | no | 4 | .600 | 0 | 0 | 1 | 1 | 1.360 | 1.360 |
| 13 | Hungaroring | no | 9 | .750 | .6375 | .4781 | .3475 | .7750 | 1.630 | 1.263 |
| 14 | Zandvoort | yes | 8 | .150 | .4250 | .0638 | .5650 | .8500 | 2.480 | 2.108 |
| 15 | Monza | no | 3 | .600 | 0 | 0 | 1 | 1 | 1.180 | 1.180 |
| 16 | Madrid | no | 5 | .600 | 0 | 0 | 1 | 1 | 1.180 | 1.180 |
| 17 | Baku | no | 4 | .600 | 0 | 0 | 1 | 1 | 1.900 | 1.900 |
| 18 | Marina Bay | yes | 8 | .150 | .4250 | .0638 | .5650 | .8500 | 2.840 | 2.414 |
| 19 | Americas | no | 5 | .600 | 0 | 0 | 1 | 1 | 1.180 | 1.180 |
| 20 | Rodríguez | no | 4 | .600 | 0 | 0 | 1 | 1 | 1.180 | 1.180 |
| 21 | Interlagos | no | 5 | .600 | 0 | 0 | 1 | 1 | 1.360 | 1.360 |
| 22 | Vegas | no | 4 | .600 | 0 | 0 | 1 | 1 | 1.360 | 1.360 |
| 23 | Losail | no | 5 | .600 | 0 | 0 | 1 | 1 | 1.000 | 1.000 |
| 24 | Yas Marina | no | 6 | .600 | 0 | 0 | 1 | 1 | 1.180 | 1.180 |

The ordinary-track FP weight of 0.60 applies to 16 of 18 non-sprint active rounds. That makes it a core algorithm component, not a narrow adjustment. The hard ramp has only Monaco/Hungary completed evidence. The current use of the same difficulty field makes the model trust FP qualifying more and then anchor the race more strongly to the resulting grid.

## Compact experiment grid

The effective sample size is 11 events, not 239 driver rows. Do not tune individual rating numbers or nine circuit coordinates on this sample. Test blocks.

### Stage A: feature-block ablation (six pre-registered candidates)

Keep algorithm and hyperparameters fixed. Run paired event-level walk-forward predictions for qualifying and the actionable post-FP race path.

| ID | driver ratings | team ratings | raw track | similarity rolling | purpose |
|---|:---:|:---:|:---:|:---:|---|
| A0 | on | on | on | on | corrected current feature set |
| A1 | off | off | on | on | clean no-manual-rating baseline |
| A2 | on | off | on | on | isolate driver prior |
| A3 | off | on | on | on | isolate team prior |
| A4 | off | off | on | off | test similarity redundancy |
| A5 | off | off | off | off | dynamic priors + FP only; test all manual track vectors |

Do not add A2/A3 together as a new seventh candidate: that is A0. If A2 or A3 wins, the fields must still be versioned before calling the result walk-forward clean.

Suggested `--drop-features` strings:

```text
DRIVER=tire_mgmt,wet_skill,overtaking,quali_skill,quali_skill_x_ot_diff
TEAM=strategy_rating,adaptability,cold_skill,strategy_sc_advantage
TRACK=is_street,overtaking_difficulty,avg_corner_speed,straight_line_importance,downforce_level,turn1_incident_risk,safety_car_probability,track_evolution,grip_level
SIM=sim_weighted_points_3,sim_weighted_finishpos_3,sim_weighted_quali_3,sim_weighted_points_5,sim_weighted_finishpos_5,sim_weighted_quali_5
```

### Stage B: post-FP transforms (only after Stage A is locked)

Use the winning feature block. Do not jointly tune weights and model hyperparameters.

| ID | normal FP | sprint FP | hard ramp | grid anchor |
|---|---:|---:|---:|---:|
| B0 | 0 | 0 | off | off |
| B1 | .60 | .15 | off (hard=.60) | off |
| B2 | .60 | .15 | current (.80 at diff 10) | off |
| B3 | .60 | .15 | off | current |
| B4 | .60 | .15 | current | current |

B2-B4 have only two completed non-sprint hard-track observations and must be sensitivity results. Prefer B1 unless the hard-track effect improves both Monaco and Hungary without a large miss in either. Do not search a dense weight grid.

### Stage C: uncertainty/fantasy modifiers

Rank MAE cannot select `OT mult`, `pos mult`, or `chaos`; they affect overtakes and interval width. Compare:

- current combined modifiers;
- no position damping;
- no chaos widening;
- neither.

Use event-level driver/constructor P5-P95 and P25-P75 coverage, interval width, CRPS or pinball loss, and fantasy-point MAE. Treat Monaco/Hungary as named case studies, not a tunable subgroup.

## Selection safeguards

- Primary metric: equal-weight mean and median per-event MAE on 2026 actionable post-FP predictions. Never pool 239 drivers as independent observations.
- Secondary: per-event Spearman and top-5 overlap; for race, report DNFs separately and use classified finishers for rank MAE.
- Guardrail: 2022-2025 walk-forward event MAE must not materially regress. Current-year improvement is primary, but a candidate that only wins on one 2026 event should fail.
- Paired uncertainty: bootstrap whole events or use a paired sign/Wilcoxon test. Report all 11 fold deltas.
- Practical gate for this small sample: improvement on at least 7/11 events, mean 2026 MAE improvement at least 0.15 position, no single-event regression over 1.0 position without an explained data issue, and 2022-2025 regression no worse than 0.05 MAE.
- Multiple testing: compare only the six pre-registered Stage A candidates, then lock the winner before Stage B. Apply Holm correction or report unadjusted intervals as exploratory.
- Preserve R13 as a pseudo-holdout if the experiment list can be frozen before inspecting its candidate results. Regardless, R14 should be the first true prospective confirmation round.
- Store experiment data hash, git SHA, rating snapshot/effective date, feature list, phase, and whether pace/DOTD/grid overrides were active. Existing filename-only caches are not sufficient.

## Strongest hypotheses, in order

1. **Drop the six similarity-weighted rolling fields.** They duplicate ordinary recency almost exactly and are the cleanest low-risk simplification.
2. **Use no manual rating fields as the trustworthy baseline.** Re-add only a versioned block that wins prospectively. The current tables are outcome-informed and static across seasons.
3. **If a manual prior is retained, condition it explicitly.** `wet_skill` should matter only with a wet forecast/session; `cold_skill` only below the chosen temperature; strategy only in a measurable strategy/SC context. Do not expose them as unconditional identity proxies.
4. **Decouple overtaking difficulty from all downstream controls.** A single subjective 1-10 value should not simultaneously set FP trust, grid anchoring, overtakes, interval damping, and chaos. Estimate each behavior from its own observable target.
5. **Keep ordinary FP blend separate from hard-track policy.** The 0.60 ordinary weight has broader evidence. The .75/.80 plus .6375/.85 anchor stack is based on two completed events and should remain a transparent sensitivity layer.
6. **Validate MC net behavior, not each multiplier in isolation.** Current damping and chaos widening can reverse one another.
